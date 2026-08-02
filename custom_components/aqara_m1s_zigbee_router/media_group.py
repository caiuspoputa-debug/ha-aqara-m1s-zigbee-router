from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
import shutil
from typing import Any

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components.media_player.browse_media import async_process_play_media_url
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DATA_COORDINATORS, DATA_RADIO_PLAYERS, DOMAIN, MEDIA_GROUP_ID, media_group_signal

_LOGGER = logging.getLogger(__name__)

RADIO_PORT = 12346
REMOTE_FIFO = "/tmp/aqara_m1s_radio_fifo"
REMOTE_NC_PID = "/tmp/aqara_m1s_radio_nc.pid"
REMOTE_APLAY_PID = "/tmp/aqara_m1s_radio_aplay.pid"

REMOTE_STOP_COMMAND = (
    f"for f in {REMOTE_NC_PID} {REMOTE_APLAY_PID}; do "
    "[ -f \"$f\" ] && kill -9 \"$(cat \"$f\")\" 2>/dev/null; done; "
    f"for p in $(ps w | grep \"[n]c -l -p {RADIO_PORT}\" | awk '{{print $1}}'); do "
    "kill -9 \"$p\" 2>/dev/null; done; "
    f"for p in $(ps w | grep \"[a]play .*{REMOTE_FIFO}\" | awk '{{print $1}}'); do "
    "kill -9 \"$p\" 2>/dev/null; done; "
    f"rm -f {REMOTE_NC_PID} {REMOTE_APLAY_PID} {REMOTE_FIFO}"
)

REMOTE_START_COMMAND = (
    REMOTE_STOP_COMMAND
    + f'; mkfifo {REMOTE_FIFO}; '
    + f'nc -l -p {RADIO_PORT} </dev/null > {REMOTE_FIFO} '
      '2>/tmp/aqara_m1s_radio_nc.log & '
    + f'echo $! > {REMOTE_NC_PID}; '
    + f'aplay -t raw -f S32_LE -c 1 -r 32000 {REMOTE_FIFO} </dev/null '
      '>/tmp/aqara_m1s_radio_aplay.log 2>&1 & '
    + f'echo $! > {REMOTE_APLAY_PID}'
)


class AqaraM1SMediaGroupManager:
    """Dynamic membership plus one shared FFmpeg PCM broadcaster."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.selected: set[str] = set()
        self.entity: AqaraM1SMediaGroup | None = None
        self.writers: dict[str, asyncio.StreamWriter] = {}
        self.ffmpeg: asyncio.subprocess.Process | None = None
        self.broadcast_task: asyncio.Task | None = None
        self.stderr_task: asyncio.Task | None = None
        self.generation = 0
        self.lock = asyncio.Lock()
        self.media_url: str | None = None
        self.volume = 0.05
        self.muted = False

    def set_selected(self, entry_id: str, selected: bool) -> None:
        if selected:
            self.selected.add(entry_id)
        else:
            self.selected.discard(entry_id)
        async_dispatcher_send(self.hass, media_group_signal())

    def players(self) -> list[Any]:
        players = self.hass.data.get(DOMAIN, {}).get(DATA_RADIO_PLAYERS, {})
        return [players[eid] for eid in tuple(self.selected) if eid in players]

    async def _run_remote(self, player: Any, command: str) -> None:
        await self.hass.async_add_executor_job(player.client.run_command, command)

    async def _prepare_member(self, entry_id: str, player: Any) -> tuple[str, asyncio.StreamWriter] | None:
        try:
            # Stop a possible individual stream first so port 12346 and aplay are free.
            await player.async_media_stop()
            await self._run_remote(player, REMOTE_START_COMMAND)
            last_error: Exception | None = None
            for _ in range(8):
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(player.client.host, RADIO_PORT), timeout=1.5
                    )
                    sock = writer.get_extra_info("socket")
                    if sock is not None:
                        with suppress(OSError):
                            sock.setsockopt(6, 1, 1)  # TCP_NODELAY
                    return entry_id, writer
                except (OSError, asyncio.TimeoutError) as err:
                    last_error = err
                    await asyncio.sleep(0.15)
            raise ConnectionError(f"receiver did not accept TCP: {last_error}")
        except Exception as err:
            _LOGGER.warning("Shared media skipped hub %s: %s", player.client.host, err)
            return None

    async def _close_writer(self, entry_id: str, *, stop_remote: bool = True) -> None:
        writer = self.writers.pop(entry_id, None)
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
        if stop_remote:
            player = self.hass.data.get(DOMAIN, {}).get(DATA_RADIO_PLAYERS, {}).get(entry_id)
            if player is not None:
                with suppress(Exception):
                    await self._run_remote(player, REMOTE_STOP_COMMAND)

    async def stop(self, *, update_entity: bool = True) -> None:
        async with self.lock:
            self.generation += 1
            current = asyncio.current_task()
            for task_name in ("broadcast_task", "stderr_task"):
                task = getattr(self, task_name)
                setattr(self, task_name, None)
                if task and task is not current and not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            proc = self.ffmpeg
            self.ffmpeg = None
            if proc is not None and proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            entries = list(self.writers)
            await asyncio.gather(
                *(self._close_writer(eid, stop_remote=True) for eid in entries),
                return_exceptions=True,
            )
            if update_entity and self.entity is not None:
                self.entity._attr_state = MediaPlayerState.IDLE
                self.entity.async_write_ha_state()

    async def start(self, media_url: str, volume: float, muted: bool) -> int:
        await self.stop(update_entity=False)
        async with self.lock:
            self.media_url = media_url
            self.volume = volume
            self.muted = muted
            players = {p.entry.entry_id: p for p in self.players()}
            if not players:
                return 0

            prepared = await asyncio.gather(
                *(self._prepare_member(eid, player) for eid, player in players.items())
            )
            self.writers = {item[0]: item[1] for item in prepared if item is not None}
            if not self.writers:
                return 0

            ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
            effective_volume = 0.0 if muted else volume
            args = [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning",
                "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                "-i", media_url, "-vn", "-ac", "1", "-ar", "32000",
                "-filter:a", f"volume={effective_volume:.4f}",
                "-c:a", "pcm_s32le", "-f", "s32le", "pipe:1",
            ]
            try:
                self.ffmpeg = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except Exception:
                entries = list(self.writers)
                await asyncio.gather(*(self._close_writer(eid) for eid in entries), return_exceptions=True)
                raise

            self.generation += 1
            generation = self.generation
            self.broadcast_task = self.hass.async_create_background_task(
                self._broadcast(generation), "aqara_m1s_shared_pcm_broadcast"
            )
            self.stderr_task = self.hass.async_create_background_task(
                self._drain_stderr(generation), "aqara_m1s_shared_ffmpeg_stderr"
            )
            return len(self.writers)

    async def _broadcast(self, generation: int) -> None:
        proc = self.ffmpeg
        if proc is None or proc.stdout is None:
            return
        try:
            while generation == self.generation:
                chunk = await proc.stdout.read(32768)
                if not chunk:
                    break
                failed: list[str] = []
                for entry_id, writer in tuple(self.writers.items()):
                    try:
                        writer.write(chunk)
                    except (OSError, ConnectionError):
                        failed.append(entry_id)
                drain_results = await asyncio.gather(
                    *(asyncio.wait_for(self.writers[eid].drain(), timeout=1.0)
                      for eid in tuple(self.writers) if eid not in failed),
                    return_exceptions=True,
                )
                for eid, result in zip(
                    [eid for eid in tuple(self.writers) if eid not in failed], drain_results
                ):
                    if isinstance(result, Exception):
                        failed.append(eid)
                for eid in set(failed):
                    player = self.hass.data.get(DOMAIN, {}).get(DATA_RADIO_PLAYERS, {}).get(eid)
                    _LOGGER.warning(
                        "Shared PCM removed slow/offline hub %s",
                        player.client.host if player else eid,
                    )
                    await self._close_writer(eid)
                if not self.writers:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.warning("Shared PCM broadcaster failed: %s", err)
        finally:
            if generation == self.generation and self.entity is not None:
                self.entity._attr_state = MediaPlayerState.IDLE
                self.entity.async_write_ha_state()

    async def _drain_stderr(self, generation: int) -> None:
        proc = self.ffmpeg
        if proc is None or proc.stderr is None:
            return
        try:
            while generation == self.generation:
                line = await proc.stderr.readline()
                if not line:
                    return
                _LOGGER.debug("Shared FFmpeg: %s", line.decode(errors="replace").strip())
        except asyncio.CancelledError:
            raise

    async def add_live_member(self, entry_id: str) -> None:
        """Add a member and resynchronise the whole playing group.

        Joining an already-running raw PCM stream creates a new FIFO/aplay buffer
        at an arbitrary point in time.  That member can therefore be hundreds of
        milliseconds or even seconds behind.  The only deterministic recovery is
        to restart the shared source once all selected receivers are prepared.
        """
        self.set_selected(entry_id, True)
        if self.entity is None or self.entity.state != MediaPlayerState.PLAYING:
            return
        if not self.media_url:
            return

        media_url = self.media_url
        volume = self.volume
        muted = self.muted

        active = await self.start(media_url, volume, muted)
        if self.entity is not None:
            self.entity._attr_state = (
                MediaPlayerState.PLAYING if active else MediaPlayerState.IDLE
            )
            self.entity.async_write_ha_state()
        async_dispatcher_send(self.hass, media_group_signal())

    async def remove_member(self, entry_id: str) -> None:
        self.set_selected(entry_id, False)
        await self._close_writer(entry_id)
        async_dispatcher_send(self.hass, media_group_signal())

    async def async_member_enabled(self, entry_id: str) -> None:
        await self.add_live_member(entry_id)

    async def async_member_disabled(self, entry_id: str) -> None:
        await self.remove_member(entry_id)


class AqaraM1SMediaGroup(MediaPlayerEntity, RestoreEntity):
    """One player using one FFmpeg source and identical PCM for every hub."""

    _attr_name = "M1S Media Group"
    _attr_unique_id = MEDIA_GROUP_ID
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_should_poll = False
    _attr_volume_step = 0.001
    _attr_supported_features = (
        MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(self, hass: HomeAssistant, manager: AqaraM1SMediaGroupManager) -> None:
        self.hass = hass
        self.manager = manager
        manager.entity = self
        self._attr_state = MediaPlayerState.IDLE
        self._attr_volume_level = 0.05
        self._attr_is_volume_muted = False
        self._attr_media_content_type = MediaType.MUSIC
        self._attr_media_title = None
        self.last_media_id: str | None = None
        self.last_media_type: str = MediaType.MUSIC
        self._resolved_media_url: str | None = None
        self._volume_restart_task: asyncio.Task | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last:
            attrs = last.attributes
            with suppress(TypeError, ValueError):
                self._attr_volume_level = max(0.0, min(1.0, float(attrs.get("volume_level", 0.05))))
            self._attr_is_volume_muted = bool(attrs.get("is_volume_muted", False))
            self.last_media_id = attrs.get("last_media_id") or attrs.get("media_content_id")
            self.last_media_type = attrs.get("last_media_type") or attrs.get("media_content_type") or MediaType.MUSIC
            self._attr_media_content_id = self.last_media_id
            self._attr_media_content_type = self.last_media_type
            self._attr_media_title = attrs.get("last_media_title") or attrs.get("media_title")
        self.async_on_remove(async_dispatcher_connect(self.hass, media_group_signal(), self._refresh))

    async def async_will_remove_from_hass(self) -> None:
        if self._volume_restart_task:
            self._volume_restart_task.cancel()
        await self.manager.stop(update_entity=False)
        await super().async_will_remove_from_hass()

    def _refresh(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return bool(self.manager.players())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        players = self.hass.data.get(DOMAIN, {}).get(DATA_RADIO_PLAYERS, {})
        coordinators = self.hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {})
        selected = [players[eid].client.host for eid in sorted(self.manager.selected) if eid in players]
        active = [players[eid].client.host for eid in self.manager.writers if eid in players]
        offline = [
            players[eid].client.host for eid in sorted(self.manager.selected)
            if eid in players and (eid not in coordinators or not coordinators[eid].last_update_success)
        ]
        return {
            "transport": "single_ffmpeg_shared_pcm",
            "selected_hubs": selected,
            "active_hubs": active,
            "offline_hubs": offline,
            "last_media_id": self.last_media_id,
            "last_media_type": self.last_media_type,
            "last_media_title": self._attr_media_title,
        }

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        return await media_source.async_browse_media(
            self.hass, media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def _resolve(self, media_id: str) -> str:
        resolved_id = media_id
        if media_source.is_media_source_id(media_id):
            resolved = await media_source.async_resolve_media(self.hass, media_id, self.entity_id)
            resolved_id = resolved.url
        return async_process_play_media_url(self.hass, resolved_id, allow_relative_url=False)

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        self.last_media_id = media_id
        self.last_media_type = media_type or MediaType.MUSIC
        self._attr_media_content_id = media_id
        self._attr_media_content_type = self.last_media_type
        extra = kwargs.get("extra") or {}
        if isinstance(extra, dict) and extra.get("title"):
            self._attr_media_title = extra["title"]
        self._resolved_media_url = await self._resolve(media_id)
        count = await self.manager.start(
            self._resolved_media_url, self._attr_volume_level or 0.0, self._attr_is_volume_muted
        )
        self._attr_state = MediaPlayerState.PLAYING if count else MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def async_media_play(self) -> None:
        if not self.last_media_id:
            return
        await self.async_play_media(
            self.last_media_type, self.last_media_id, extra={"title": self._attr_media_title}
        )

    async def async_media_stop(self) -> None:
        await self.manager.stop()

    async def async_turn_off(self) -> None:
        await self.async_media_stop()

    @staticmethod
    def _normalize_volume(volume: float) -> float:
        volume = max(0.0, min(1.0, float(volume)))
        return round(volume * (1000.0 if volume <= 0.04 else 100.0)) / (1000.0 if volume <= 0.04 else 100.0)

    async def async_set_volume_level(self, volume: float) -> None:
        self._attr_volume_level = self._normalize_volume(volume)
        self._attr_is_volume_muted = self._attr_volume_level == 0.0
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, media_group_signal())
        if self._attr_state == MediaPlayerState.PLAYING and self.last_media_id:
            if self._volume_restart_task:
                self._volume_restart_task.cancel()
            self._volume_restart_task = self.hass.async_create_task(self._restart_after_volume())

    async def _restart_after_volume(self) -> None:
        try:
            await asyncio.sleep(0.7)
            await self.async_media_play()
        except asyncio.CancelledError:
            raise

    async def async_volume_up(self) -> None:
        current = self._attr_volume_level or 0.0
        await self.async_set_volume_level(current + (0.001 if current < 0.04 else 0.01))

    async def async_volume_down(self) -> None:
        current = self._attr_volume_level or 0.0
        await self.async_set_volume_level(current - (0.001 if current <= 0.04 else 0.01))

    async def async_mute_volume(self, mute: bool) -> None:
        self._attr_is_volume_muted = bool(mute)
        self.async_write_ha_state()
        if self._attr_state == MediaPlayerState.PLAYING and self.last_media_id:
            await self.async_media_play()
