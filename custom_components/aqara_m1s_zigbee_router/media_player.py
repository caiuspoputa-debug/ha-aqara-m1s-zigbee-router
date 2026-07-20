from __future__ import annotations

import asyncio
import logging
import shutil
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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import AqaraM1SClient
from .const import DATA_CLIENTS, DATA_COORDINATORS, DATA_RADIO_PLAYERS, DOMAIN

_LOGGER = logging.getLogger(__name__)

RADIO_PORT = 12346
REMOTE_FIFO = "/tmp/aqara_m1s_radio_fifo"
REMOTE_NC_PID = "/tmp/aqara_m1s_radio_nc.pid"
REMOTE_APLAY_PID = "/tmp/aqara_m1s_radio_aplay.pid"

REMOTE_STOP_COMMAND = (
    f'for f in {REMOTE_NC_PID} {REMOTE_APLAY_PID}; do '
    '[ -f "$f" ] && kill -9 "$(cat "$f")" 2>/dev/null; '
    'done; '
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


class AqaraM1SRadioPlayer(CoordinatorEntity, MediaPlayerEntity):
    """Stream Home Assistant media to the Aqara M1S speaker."""

    _attr_name = "Media Player"
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_should_poll = False
    # Home Assistant volume uses a 0.0-1.0 scale. A step of 0.001 is 0.1%.
    # This keeps the native media-player control while allowing fine adjustment
    # between 0% and 1%, without creating a second volume entity.
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
        self._ffmpeg: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._watch_task: asyncio.Task | None = None
        self._volume_restart_task: asyncio.Task | None = None
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.host)},
            "name": entry.data.get("name", f"Aqara M1S {client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._schedule_cleanup)

    def _schedule_cleanup(self) -> None:
        self.hass.async_create_task(self.async_shutdown())

    async def async_shutdown(self) -> None:
        if self._volume_restart_task:
            self._volume_restart_task.cancel()
            self._volume_restart_task = None
        async with self._lock:
            await self._stop_locked(update_state=False)

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
        """Resolve a HA media source and stream it to the hub."""
        if media_source.is_media_source_id(media_id):
            resolved = await media_source.async_resolve_media(
                self.hass,
                media_id,
                self.entity_id,
            )
            media_id = resolved.url

        media_url = async_process_play_media_url(
            self.hass,
            media_id,
            allow_relative_url=False,
        )

        title = None
        extra = kwargs.get("extra") or {}
        if isinstance(extra, dict):
            title = extra.get("title")

        async with self._lock:
            self._media_url = media_url
            self._attr_media_content_id = media_id
            self._attr_media_content_type = media_type or MediaType.MUSIC
            self._attr_media_title = title or "Radio stream"
            await self._start_locked()

    async def async_media_play(self) -> None:
        if self._media_url is None:
            return
        async with self._lock:
            await self._start_locked()

    async def async_media_stop(self) -> None:
        async with self._lock:
            await self._stop_locked(update_state=True)

    async def async_turn_off(self) -> None:
        await self.async_media_stop()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume and debounce the FFmpeg restart.

        The hub does not expose a proven safe live-volume command through the
        current Telnet transport. FFmpeg therefore still has to be restarted,
        but only once after the slider stops moving instead of once per step.
        """
        volume = max(0.0, min(1.0, float(volume)))
        self._attr_volume_level = volume
        self._attr_is_volume_muted = volume == 0.0
        self.async_write_ha_state()

        if self._volume_restart_task:
            self._volume_restart_task.cancel()
            self._volume_restart_task = None

        if self._attr_state == MediaPlayerState.PLAYING and self._media_url:
            self._volume_restart_task = self.hass.async_create_task(
                self._restart_after_volume_settle()
            )

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

    async def _start_locked(self) -> None:
        if not self._media_url:
            return

        await self._stop_local_ffmpeg()
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

        self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()
        self._watch_task = self.hass.async_create_task(
            self._watch_ffmpeg(self._ffmpeg)
        )

    async def _watch_ffmpeg(self, process: asyncio.subprocess.Process) -> None:
        stderr = b""
        try:
            _, stderr = await process.communicate()
        except asyncio.CancelledError:
            return

        if self._ffmpeg is not process:
            return

        self._ffmpeg = None
        if process.returncode not in (0, -15):
            _LOGGER.warning(
                "Aqara M1S radio FFmpeg exited with code %s: %s",
                process.returncode,
                stderr.decode(errors="ignore")[-1000:],
            )
        self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def _stop_local_ffmpeg(self) -> None:
        process = self._ffmpeg
        self._ffmpeg = None
        if self._watch_task:
            self._watch_task.cancel()
            self._watch_task = None
        if process is None or process.returncode is not None:
            return
        process.terminate()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=2)
        if process.returncode is None:
            process.kill()
            await process.wait()

    async def _stop_locked(self, update_state: bool) -> None:
        await self._stop_local_ffmpeg()
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
