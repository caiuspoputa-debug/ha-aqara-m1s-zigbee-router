from __future__ import annotations

import asyncio
import logging
import shutil
import time
from urllib.parse import urlsplit, urlunsplit
from contextlib import suppress
from typing import Any

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components.media_player.browse_media import (
    async_process_play_media_url,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import AqaraM1SClient
from .const import (
    DATA_CLIENTS,
    DATA_COORDINATORS,
    DATA_RADIO_PLAYERS,
    DOMAIN,
    radio_volume_signal,
)

_LOGGER = logging.getLogger(__name__)

RADIO_PORT = 12346
REMOTE_FIFO = "/tmp/aqara_m1s_radio_fifo"
REMOTE_NC_PID = "/tmp/aqara_m1s_radio_nc.pid"
REMOTE_APLAY_PID = "/tmp/aqara_m1s_radio_aplay.pid"

WATCHDOG_RESTART_DELAY = 5.0
WATCHDOG_MAX_RESTARTS = 3
WATCHDOG_STABLE_SECONDS = 30.0

REMOTE_STOP_COMMAND = (
    # First stop the exact PIDs recorded when this integration started the
    # receiver. PID files can be stale after a hub reboot, so this is followed
    # by command-line scoped fallbacks. Never use killall: the hub may run
    # unrelated nc/aplay processes.
    f'for f in {REMOTE_NC_PID} {REMOTE_APLAY_PID}; do '
    '[ -f "$f" ] && kill -9 "$(cat "$f")" 2>/dev/null; '
    'done; '
    f'for p in $(ps w | grep "[n]c -l -p {RADIO_PORT}" | awk '"'"'{print $1}'"'"'); do '
    'kill -9 "$p" 2>/dev/null; done; '
    f'for p in $(ps w | grep "[a]play .*{REMOTE_FIFO}" | awk '"'"'{print $1}'"'"'); do '
    'kill -9 "$p" 2>/dev/null; done; '
    f'rm -f {REMOTE_NC_PID} {REMOTE_APLAY_PID} {REMOTE_FIFO}'
)

REMOTE_START_COMMAND = (
    REMOTE_STOP_COMMAND
    + f'; mkfifo {REMOTE_FIFO}; '
    + f'nc -l -p {RADIO_PORT} </dev/null > {REMOTE_FIFO} '
      '2>/tmp/aqara_m1s_radio_nc.log & '
    + f'echo $! > {REMOTE_NC_PID}; '
    + f'aplay -t raw -f S32_LE -c 1 -r 32000 '
      f'{REMOTE_FIFO} </dev/null '
      '>/tmp/aqara_m1s_radio_aplay.log 2>&1 & '
    + f'echo $! > {REMOTE_APLAY_PID}'
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: AqaraM1SClient = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    player = AqaraM1SRadioPlayer(
        hass, entry, client, hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    )
    hass.data[DOMAIN].setdefault(DATA_RADIO_PLAYERS, {})[entry.entry_id] = player
    async_add_entities([player])


class AqaraM1SRadioPlayer(CoordinatorEntity, MediaPlayerEntity, RestoreEntity):
    """Stream Home Assistant media to the Aqara M1S speaker."""

    _attr_name = "Media Player"
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_should_poll = False
    # Home Assistant exposes one fixed slider step. Use 0.1% so low-volume
    # values are selectable everywhere the media player is shown; values above
    # 4% are normalized to whole percentages by async_set_volume_level().
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

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AqaraM1SClient,
        coordinator,
    ) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.client = client
        self._attr_unique_id = f"{entry.entry_id}_radio"
        self._attr_state = MediaPlayerState.IDLE
        self._attr_volume_level = 0.05
        self._attr_is_volume_muted = False
        self._attr_media_content_type = MediaType.MUSIC
        self._attr_media_title = None
        self._media_url: str | None = None
        self._resume_media_id: str | None = None
        self._resume_media_type: str = MediaType.MUSIC
        self._resume_after_reconnect = False
        self._last_online_generation = 0
        self._resume_task: asyncio.Task | None = None
        self._ffmpeg: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._watch_task: asyncio.Task | None = None
        self._volume_restart_task: asyncio.Task | None = None
        self._watchdog_restart_task: asyncio.Task | None = None
        self._watchdog_stable_task: asyncio.Task | None = None
        self._watchdog_restart_attempts = 0
        self._ffmpeg_started_monotonic: float | None = None
        self._ffmpeg_session = 0
        self._shutting_down = False
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.host)},
            "name": entry.data.get("name", f"Aqara M1S {client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is not None:
            attrs = last_state.attributes

            restored_volume = attrs.get("volume_level")
            if restored_volume is not None:
                try:
                    self._attr_volume_level = max(
                        0.0, min(1.0, float(restored_volume))
                    )
                except (TypeError, ValueError):
                    pass

            self._attr_is_volume_muted = bool(
                attrs.get("is_volume_muted", False)
            )
            self._resume_media_id = (
                attrs.get("last_media_id") or attrs.get("media_content_id")
            )
            self._resume_media_type = (
                attrs.get("last_media_type")
                or attrs.get("media_content_type")
                or MediaType.MUSIC
            )
            self._attr_media_content_id = self._resume_media_id
            self._attr_media_content_type = self._resume_media_type
            self._attr_media_title = (
                attrs.get("last_media_title") or attrs.get("media_title")
            )
            self._resume_after_reconnect = bool(
                attrs.get("resume_after_reconnect", last_state.state == MediaPlayerState.PLAYING)
            )

            # Direct URLs can be prepared immediately. Media-source IDs are
            # resolved freshly only when PLAY is pressed, because their resolved
            # URLs may contain temporary authentication data.
            if self._resume_media_id and not media_source.is_media_source_id(
                self._resume_media_id
            ):
                self._media_url = async_process_play_media_url(
                    self.hass,
                    self._resume_media_id,
                    allow_relative_url=False,
                )

            self._attr_state = MediaPlayerState.IDLE

        data = self.coordinator.data or {}
        self._last_online_generation = int(data.get("online_generation", 0) or 0)
        if self._resume_after_reconnect and self._resume_media_id:
            self._schedule_resume(delay=2.0)

        async_dispatcher_send(
            self.hass, radio_volume_signal(self.entry.entry_id)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Persist the last playable media and the radio volume."""
        return {
            "last_media_id": self._resume_media_id,
            "last_media_type": self._resume_media_type,
            "last_media_title": self._attr_media_title,
            "volume_level": self._attr_volume_level,
            "is_volume_muted": self._attr_is_volume_muted,
            "resume_after_reconnect": self._resume_after_reconnect,
            "watchdog_restart_attempts": self._watchdog_restart_attempts,
        }

    async def async_will_remove_from_hass(self) -> None:
        """Stop background work cleanly before the entity is removed."""
        await self.async_shutdown()
        await super().async_will_remove_from_hass()

    async def _cancel_task(self, task: asyncio.Task | None) -> None:
        """Cancel and await a task so it cannot leak into HA shutdown/startup."""
        if task is None or task is asyncio.current_task():
            return
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def async_shutdown(self) -> None:
        """Stop FFmpeg and every watchdog task without clearing resume intent."""
        if self._shutting_down:
            return
        self._shutting_down = True

        tasks = [
            self._resume_task,
            self._volume_restart_task,
            self._watchdog_restart_task,
            self._watchdog_stable_task,
        ]
        self._resume_task = None
        self._volume_restart_task = None
        self._watchdog_restart_task = None
        self._watchdog_stable_task = None
        for task in tasks:
            await self._cancel_task(task)

        async with self._lock:
            await self._stop_locked(
                update_state=False, reason="integration_shutdown"
            )

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ):
        """Expose Home Assistant audio sources in the native media browser."""
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def async_play_media(
        self,
        media_type: str,
        media_id: str,
        **kwargs: Any,
    ) -> None:
        """Resolve a HA media source, remember it, and stream it to the hub."""
        original_media_id = media_id
        resolved_media_id = media_id

        if media_source.is_media_source_id(media_id):
            resolved = await media_source.async_resolve_media(
                self.hass,
                media_id,
                self.entity_id,
            )
            resolved_media_id = resolved.url

        media_url = async_process_play_media_url(
            self.hass,
            resolved_media_id,
            allow_relative_url=False,
        )

        title = None
        extra = kwargs.get("extra") or {}
        if isinstance(extra, dict):
            title = extra.get("title")

        async with self._lock:
            self._resume_media_id = original_media_id
            self._resume_media_type = media_type or MediaType.MUSIC
            self._media_url = media_url
            self._attr_media_content_id = original_media_id
            self._attr_media_content_type = self._resume_media_type
            self._attr_media_title = title or self._attr_media_title or "Radio stream"
            self._resume_after_reconnect = True
            await self._start_locked()

    async def async_media_play(self) -> None:
        """Resume the last remembered media."""
        if self._shutting_down:
            return
        self._resume_after_reconnect = True
        if not self._resume_media_id and not self._media_url:
            return

        if self._resume_media_id and media_source.is_media_source_id(
            self._resume_media_id
        ):
            resolved = await media_source.async_resolve_media(
                self.hass,
                self._resume_media_id,
                self.entity_id,
            )
            media_url = async_process_play_media_url(
                self.hass,
                resolved.url,
                allow_relative_url=False,
            )
            async with self._lock:
                self._media_url = media_url
                await self._start_locked()
            return

        async with self._lock:
            await self._start_locked()

    async def async_media_stop(self) -> None:
        self._resume_after_reconnect = False
        self._watchdog_restart_attempts = 0
        if self._watchdog_restart_task:
            self._watchdog_restart_task.cancel()
            self._watchdog_restart_task = None
        if self._watchdog_stable_task:
            self._watchdog_stable_task.cancel()
            self._watchdog_stable_task = None
        if self._resume_task:
            self._resume_task.cancel()
            self._resume_task = None
        async with self._lock:
            await self._stop_locked(update_state=True, reason="user_stop")

    async def async_turn_off(self) -> None:
        await self.async_media_stop()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume and debounce the FFmpeg restart.

        The hub does not expose a proven safe live-volume command through the
        current Telnet transport. FFmpeg therefore still has to be restarted,
        but only once after the slider stops moving instead of once per step.
        """
        volume = self._normalize_volume(float(volume))
        self._attr_volume_level = volume
        self._attr_is_volume_muted = volume == 0.0
        self.async_write_ha_state()
        async_dispatcher_send(
            self.hass, radio_volume_signal(self.entry.entry_id)
        )

        if self._volume_restart_task:
            self._volume_restart_task.cancel()
            self._volume_restart_task = None

        if self._attr_state == MediaPlayerState.PLAYING and self._media_url:
            self._volume_restart_task = self.hass.async_create_task(
                self._restart_after_volume_settle()
            )


    @staticmethod
    def _normalize_volume(volume: float) -> float:
        """Use 0.1% steps through 4%, then whole 1% steps."""
        volume = max(0.0, min(1.0, volume))
        if volume <= 0.04:
            return round(volume * 1000.0) / 1000.0
        return round(volume * 100.0) / 100.0

    async def async_volume_up(self) -> None:
        """Increase by 0.1% at low volume and by 1% above 4%."""
        current = self._attr_volume_level or 0.0
        step = 0.001 if current < 0.04 else 0.01
        await self.async_set_volume_level(current + step)

    async def async_volume_down(self) -> None:
        """Decrease by 0.1% through 4% and by 1% above it."""
        current = self._attr_volume_level or 0.0
        step = 0.001 if current <= 0.04 else 0.01
        await self.async_set_volume_level(current - step)

    def _handle_coordinator_update(self) -> None:
        """Resume the remembered media after a real hub reconnect."""
        data = self.coordinator.data or {}
        generation = int(data.get("online_generation", 0) or 0)
        if generation > self._last_online_generation:
            self._last_online_generation = generation
            # A genuine offline/online cycle starts a fresh recovery window.
            # Fast watchdog retries may have been exhausted while the hub was
            # unreachable; reconnect must still resume the remembered stream.
            self._watchdog_restart_attempts = 0
            if self._resume_after_reconnect and self._resume_media_id:
                self._schedule_resume(delay=2.0)
        super()._handle_coordinator_update()

    def _schedule_resume(self, delay: float) -> None:
        if self._resume_task and not self._resume_task.done():
            return
        self._resume_task = self.hass.async_create_task(
            self._async_resume_after_delay(delay)
        )

    async def _async_resume_after_delay(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            if (
                self._resume_after_reconnect
                and self._resume_media_id
                and self.coordinator.last_update_success
                and self._attr_state != MediaPlayerState.PLAYING
            ):
                await self.async_media_play()
        except asyncio.CancelledError:
            return
        except Exception as err:
            _LOGGER.warning("Could not automatically resume Aqara media: %s", err)
        finally:
            if self._resume_task is asyncio.current_task():
                self._resume_task = None

    async def _restart_after_volume_settle(self) -> None:
        """Apply the final slider value after a short quiet period."""
        try:
            await asyncio.sleep(0.7)
            async with self._lock:
                if self._attr_state == MediaPlayerState.PLAYING and self._media_url:
                    await self._start_locked()
        except asyncio.CancelledError:
            return
        finally:
            if self._volume_restart_task is asyncio.current_task():
                self._volume_restart_task = None

    async def async_mute_volume(self, mute: bool) -> None:
        self._attr_is_volume_muted = bool(mute)
        self.async_write_ha_state()

        if self._volume_restart_task:
            self._volume_restart_task.cancel()
            self._volume_restart_task = None

        if self._attr_state == MediaPlayerState.PLAYING and self._media_url:
            async with self._lock:
                await self._start_locked()

    @staticmethod
    def _safe_media_for_log(media_url: str | None) -> str:
        """Return a useful media identifier without query tokens or credentials."""
        if not media_url:
            return "<none>"
        try:
            parts = urlsplit(media_url)
            host = parts.hostname or ""
            if parts.port:
                host = f"{host}:{parts.port}"
            return urlunsplit((parts.scheme, host, parts.path, "", ""))
        except Exception:
            return "<unparseable>"

    async def _log_remote_audio_snapshot(self, session: int) -> None:
        """Capture a small hub-side snapshot after an unexpected FFmpeg exit."""
        command = (
            'echo "--- aplay ---"; ps w | grep "[a]play"; '
            'echo "--- nc ---"; ps w | grep "[n]c"; '
            f'echo "--- TCP {RADIO_PORT} ---"; netstat -an 2>/dev/null | grep {RADIO_PORT}; '
            'echo "--- memory ---"; free 2>/dev/null; '
            'echo "--- receiver logs ---"; '
            'tail -n 20 /tmp/aqara_m1s_radio_nc.log 2>/dev/null; '
            'tail -n 20 /tmp/aqara_m1s_radio_aplay.log 2>/dev/null'
        )
        try:
            snapshot = await self.hass.async_add_executor_job(
                self.client.run_command, command
            )
            _LOGGER.warning(
                "Aqara media diagnostic hub snapshot entity=%s session=%s host=%s\n%s",
                self.entity_id,
                session,
                self.client.host,
                snapshot[-6000:],
            )
        except Exception as err:
            _LOGGER.warning(
                "Aqara media diagnostic could not read hub snapshot "
                "entity=%s session=%s host=%s error=%s",
                self.entity_id,
                session,
                self.client.host,
                err,
            )

    async def _start_locked(self) -> None:
        if self._shutting_down or not self._media_url:
            return

        current_task = asyncio.current_task()
        if (
            self._watchdog_restart_task
            and self._watchdog_restart_task is not current_task
        ):
            self._watchdog_restart_task.cancel()
            self._watchdog_restart_task = None
        if self._watchdog_stable_task:
            self._watchdog_stable_task.cancel()
            self._watchdog_stable_task = None

        await self._stop_local_ffmpeg("replace_before_start")
        await self.hass.async_add_executor_job(
            self.client.run_command,
            REMOTE_START_COMMAND,
        )
        await asyncio.sleep(0.25)

        ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
        effective_volume = 0.0 if self._attr_is_volume_muted else self._attr_volume_level
        output_url = f"tcp://{self.client.host}:{RADIO_PORT}?tcp_nodelay=1"
        args = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-i",
            self._media_url,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "32000",
            "-filter:a",
            f"volume={effective_volume:.4f}",
            "-c:a",
            "pcm_s32le",
            "-f",
            "s32le",
            output_url,
        ]

        try:
            self._ffmpeg = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as err:
            self._attr_state = MediaPlayerState.IDLE
            self.async_write_ha_state()
            raise RuntimeError(
                "FFmpeg was not found. On Home Assistant OS/Container it is "
                "normally pre-installed; otherwise install/configure FFmpeg."
            ) from err

        self._ffmpeg_session += 1
        session = self._ffmpeg_session
        self._ffmpeg_started_monotonic = time.monotonic()
        _LOGGER.info(
            "Aqara media FFmpeg started entity=%s session=%s pid=%s host=%s "
            "source=%s volume=%.3f muted=%s",
            self.entity_id,
            session,
            self._ffmpeg.pid,
            self.client.host,
            self._safe_media_for_log(self._media_url),
            self._attr_volume_level or 0.0,
            self._attr_is_volume_muted,
        )
        self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()
        self._watch_task = self.hass.async_create_background_task(
            self._watch_ffmpeg(self._ffmpeg),
            f"aqara_m1s_ffmpeg_watch_{self.entry.entry_id}",
        )
        self._watchdog_stable_task = self.hass.async_create_background_task(
            self._reset_watchdog_after_stable_playback(self._ffmpeg),
            f"aqara_m1s_stable_watch_{self.entry.entry_id}",
        )

    async def _watch_ffmpeg(self, process: asyncio.subprocess.Process) -> None:
        stderr = b""
        session = self._ffmpeg_session
        started = self._ffmpeg_started_monotonic
        try:
            _, stderr = await process.communicate()

            if self._ffmpeg is not process or self._shutting_down:
                return

            runtime = max(0.0, time.monotonic() - started) if started else 0.0
            stderr_text = stderr.decode(errors="replace")[-4000:].strip()
            self._ffmpeg = None
            self._ffmpeg_started_monotonic = None
            stable_task = self._watchdog_stable_task
            self._watchdog_stable_task = None
            await self._cancel_task(stable_task)

            _LOGGER.warning(
                "Aqara media FFmpeg ended unexpectedly entity=%s session=%s pid=%s "
                "host=%s returncode=%s runtime=%.1fs playback_requested=%s "
                "source=%s stderr=%r",
                self.entity_id,
                session,
                process.pid,
                self.client.host,
                process.returncode,
                runtime,
                self._resume_after_reconnect,
                self._safe_media_for_log(self._media_url),
                stderr_text,
            )
            self._attr_state = MediaPlayerState.IDLE
            self.async_write_ha_state()

            await self._log_remote_audio_snapshot(session)

            if (
                not self._shutting_down
                and self._resume_after_reconnect
                and self._resume_media_id
                and self.coordinator.last_update_success
            ):
                self._schedule_watchdog_restart()
        except asyncio.CancelledError:
            _LOGGER.debug(
                "Aqara media FFmpeg watcher cancelled intentionally "
                "entity=%s session=%s pid=%s",
                self.entity_id,
                session,
                process.pid,
            )
            raise
        finally:
            if self._watch_task is asyncio.current_task():
                self._watch_task = None

    def _schedule_watchdog_restart(self) -> None:
        if self._shutting_down:
            return
        if self._watchdog_restart_attempts >= WATCHDOG_MAX_RESTARTS:
            _LOGGER.warning(
                "Aqara media watchdog exhausted %s fast retries for %s; "
                "waiting for the hub coordinator to report an online reconnect",
                WATCHDOG_MAX_RESTARTS,
                self.entity_id,
            )
            return
        if self._watchdog_restart_task and not self._watchdog_restart_task.done():
            return
        self._watchdog_restart_task = self.hass.async_create_background_task(
            self._async_watchdog_restart(),
            f"aqara_m1s_restart_watch_{self.entry.entry_id}",
        )

    async def _async_watchdog_restart(self) -> None:
        try:
            await asyncio.sleep(WATCHDOG_RESTART_DELAY)
            if (
                not self._resume_after_reconnect
                or not self._resume_media_id
                or not self.coordinator.last_update_success
                or self._attr_state == MediaPlayerState.PLAYING
            ):
                return
            self._watchdog_restart_attempts += 1
            _LOGGER.warning(
                "Aqara media watchdog restarting %s (%s/%s)",
                self.entity_id,
                self._watchdog_restart_attempts,
                WATCHDOG_MAX_RESTARTS,
            )
            await self.async_media_play()
        except asyncio.CancelledError:
            return
        except Exception as err:
            _LOGGER.warning(
                "Aqara media watchdog restart failed for %s: %s",
                self.entity_id,
                err,
            )
            if self._resume_after_reconnect:
                self._watchdog_restart_task = None
                self._schedule_watchdog_restart()
                return
        finally:
            if self._watchdog_restart_task is asyncio.current_task():
                self._watchdog_restart_task = None

    async def _reset_watchdog_after_stable_playback(
        self, process: asyncio.subprocess.Process
    ) -> None:
        try:
            await asyncio.sleep(WATCHDOG_STABLE_SECONDS)
            if self._ffmpeg is process and process.returncode is None:
                self._watchdog_restart_attempts = 0
                self.async_write_ha_state()
        except asyncio.CancelledError:
            return
        finally:
            if self._watchdog_stable_task is asyncio.current_task():
                self._watchdog_stable_task = None

    async def _stop_local_ffmpeg(self, reason: str) -> None:
        process = self._ffmpeg
        session = self._ffmpeg_session
        started = self._ffmpeg_started_monotonic
        self._ffmpeg = None
        self._ffmpeg_started_monotonic = None
        watch_task = self._watch_task
        self._watch_task = None
        await self._cancel_task(watch_task)
        if process is None:
            return
        runtime = max(0.0, time.monotonic() - started) if started else 0.0
        if process.returncode is None:
            process.terminate()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=2)
            if process.returncode is None:
                process.kill()
                await process.wait()
        _LOGGER.info(
            "Aqara media FFmpeg stopped intentionally entity=%s session=%s "
            "pid=%s host=%s reason=%s returncode=%s runtime=%.1fs",
            self.entity_id,
            session,
            process.pid,
            self.client.host,
            reason,
            process.returncode,
            runtime,
        )

    async def _stop_locked(self, update_state: bool, reason: str) -> None:
        await self._stop_local_ffmpeg(reason)
        try:
            await self.hass.async_add_executor_job(
                self.client.run_command,
                REMOTE_STOP_COMMAND,
            )
        except Exception as err:  # Hub may already be offline during unload.
            _LOGGER.debug("Could not stop Aqara radio receiver: %s", err)
        if update_state:
            self._attr_state = MediaPlayerState.IDLE
            self.async_write_ha_state()
