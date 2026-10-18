from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
import math
import time
from typing import Any

from homeassistant.core import HomeAssistant

from .client import AqaraM1SClient
from .local_audio import LocalAudioBusy, safe_sound_path, safe_sound_url

_LOGGER = logging.getLogger(__name__)
SOUND_STATUS_INTERVAL = 0.5
SOUND_STATUS_FAILURE_LIMIT = 3
SOUND_DOWNLOAD_TIMEOUT = 30


class AqaraM1SSoundPlayer:
    """Play stored WAVs locally while retaining the existing HA priority arbiter."""

    def __init__(self, hass: HomeAssistant, client: AqaraM1SClient, entry_id: str,
                 radio_player: Any, group_manager: Any, local_audio: Any = None) -> None:
        self.hass = hass
        self.client = client
        self.entry_id = entry_id
        self.radio_player = radio_player
        self.group_manager = group_manager
        self.local_audio = local_audio
        self._lock = asyncio.Lock()
        self._watch_task: asyncio.Task | None = None
        self._token: str | None = None
        self._interruption_active = False
        self._resume_radio = False
        self._temporary_volume_active = False

    async def _begin_priority_locked(self) -> None:
        if self._interruption_active:
            return
        self._interruption_active = True
        had_group = await self.group_manager.async_claim_sound(self.entry_id)
        self._resume_radio = await self.radio_player.async_suspend_for_priority_sound()
        if had_group or getattr(self.radio_player, "_priority_sound_had_transport", self._resume_radio):
            await asyncio.sleep(0.25)

    async def _finish_priority(self) -> None:
        if not self._interruption_active:
            return
        resume_radio = self._resume_radio
        self._resume_radio = False
        self._interruption_active = False
        try:
            if self._temporary_volume_active:
                self._temporary_volume_active = False
                try:
                    await self.local_audio.async_restore_media(self.radio_player._effective_gain())
                except Exception as exc:
                    # Receiver starts re-confirm normal gain before opening ALSA;
                    # their existing recovery handles an offline hub safely.
                    _LOGGER.warning("M1S media gain restore failed host=%s: %s", self.client.host, exc)
            await self.radio_player.async_resume_after_priority_sound(resume_radio)
        finally:
            await self.group_manager.async_release_sound(self.entry_id)

    @staticmethod
    def _validate_policy(volume_percent: float | None, respect_mute: bool) -> float | None:
        if not isinstance(respect_mute, bool):
            raise ValueError("respect_mute must be a boolean")
        if volume_percent is None:
            return None
        if isinstance(volume_percent, bool):
            raise ValueError("Notification volume must be between 0 and 100 percent")
        percent = float(volume_percent)
        if not math.isfinite(percent) or not 0 <= percent <= 100:
            raise ValueError("Notification volume must be between 0 and 100 percent")
        return percent

    def _notification_gain(self, volume_percent: float | None,
                           fallback_volume: float | None) -> float:
        if volume_percent is not None:
            return volume_percent / 100
        # A muted player's effective gain is zero; its saved slider is still
        # the notification volume. Never unmute or overwrite media intent.
        gain = getattr(self.radio_player, "_attr_volume_level", None)
        if gain is None:
            gain = (float(fallback_volume) / 100 if fallback_volume is not None
                    else self.radio_player._effective_gain())
        gain = float(gain)
        if not math.isfinite(gain):
            raise ValueError("Notification volume must be finite")
        return max(0.0, min(1.0, gain))

    async def async_play(self, path: str, volume: float | None = None, *,
                         volume_percent: float | None = None,
                         respect_mute: bool = False) -> None:
        # Only the priority WAV bypasses media mute. Button calls use the saved
        # slider; an explicit service volume belongs only to this notification.
        source = safe_sound_path(path)
        volume_percent = self._validate_policy(volume_percent, respect_mute)
        await self._play_local(source, volume_percent=volume_percent,
                               respect_mute=respect_mute, fallback_volume=volume)

    async def _play_local(self, source: str, *, url: bool = False,
                          volume_percent: float | None = None,
                          respect_mute: bool = False,
                          fallback_volume: float | None = None) -> None:
        if self.client.zigbee_role == "coordinator":
            raise RuntimeError("Dedicated coordinator does not expose audio")
        if self.local_audio is None:
            raise RuntimeError("Local hub audio is not configured")
        started = time.perf_counter()
        async with self._lock:
            try:
                phase = time.perf_counter()
                timings = {"lock_wait": round((phase - started) * 1000)}
                await self._stop_locked(restore_previous=False)
                now = time.perf_counter()
                timings["previous_wav_stop"] = round((now - phase) * 1000)
                phase = now
                await self._begin_priority_locked()
                now = time.perf_counter()
                timings["priority_handover"] = round((now - phase) * 1000)
                phase = now
                gain = self._notification_gain(volume_percent, fallback_volume)
                self._temporary_volume_active = True
                try:
                    await self.local_audio.async_prepare_sound(
                        gain, muted=bool(self.radio_player._attr_is_volume_muted),
                        respect_mute=respect_mute)
                except LocalAudioBusy:
                    await self.radio_player.async_cleanup_priority_receiver()
                    await asyncio.sleep(0.25)
                    await self.local_audio.async_prepare_sound(
                        gain, muted=bool(self.radio_player._attr_is_volume_muted),
                        respect_mute=respect_mute)
                now = time.perf_counter()
                timings["volume_prepare"] = round((now - phase) * 1000)
                phase = now
                start_method = self.local_audio.async_start_url if url else self.local_audio.async_start_sound

                async def start_owned_sound():
                    try:
                        return await start_method(source)
                    except LocalAudioBusy:
                        # Only an explicit pre-start rejection permits a retry.
                        # A missing acknowledgement never causes replay.
                        await self.radio_player.async_cleanup_priority_receiver()
                        await asyncio.sleep(0.25)
                        return await start_method(source)

                start_task = self.hass.async_create_task(start_owned_sound())
                try:
                    token = await asyncio.shield(start_task)
                except asyncio.CancelledError:
                    # A remote command may already have started playback. Settle
                    # it and stop only its token before releasing audio ownership.
                    with suppress(Exception):
                        cancelled_token = await start_task
                        await self.local_audio.async_stop_sound(cancelled_token)
                        await self.local_audio.async_cleanup_sound(cancelled_token)
                    raise
                self._token = token
                self._watch_task = self.hass.async_create_task(self._watch(token))
                timings["hub_start"] = round((time.perf_counter() - phase) * 1000)
                _LOGGER.info(
                    "M1S local WAV accepted host=%s request_to_accept_ms=%s phases_ms=%s mode=hub_alsa_no_audio_transfer",
                    self.client.host, round((time.perf_counter() - started) * 1000), timings)
            except BaseException:
                await self._finish_priority()
                raise

    async def async_play_url(self, url: str, *, volume_percent: float | None = None,
                             respect_mute: bool = False) -> None:
        """Download an explicit WAV URL to hub RAM with the same priority policy."""
        source = safe_sound_url(url)
        volume_percent = self._validate_policy(volume_percent, respect_mute)
        await self._play_local(source, url=True, volume_percent=volume_percent,
                               respect_mute=respect_mute)

    async def _watch(self, token: str) -> None:
        failures = 0
        started = time.monotonic()
        try:
            while self._token == token:
                await asyncio.sleep(SOUND_STATUS_INTERVAL)
                try:
                    state, returncode = await self.local_audio.async_sound_status(token)
                    failures = 0
                except Exception as exc:
                    failures += 1
                    if failures < SOUND_STATUS_FAILURE_LIMIT:
                        continue
                    _LOGGER.warning("M1S local WAV status failed host=%s: %s", self.client.host, exc)
                    with suppress(Exception):
                        await self.local_audio.async_stop_sound(token)
                    break
                if state == "done":
                    if returncode != 0:
                        _LOGGER.warning("M1S local WAV failed host=%s exit=%s", self.client.host, returncode)
                    break
                if state == "missing":
                    _LOGGER.warning("M1S local WAV session disappeared host=%s", self.client.host)
                    break
                if state == "downloading" and time.monotonic() - started > SOUND_DOWNLOAD_TIMEOUT:
                    with suppress(Exception):
                        await self.local_audio.async_stop_sound(token)
                    _LOGGER.warning("M1S WAV URL download timed out host=%s", self.client.host)
                    break
        except asyncio.CancelledError:
            return
        except Exception as exc:
            _LOGGER.warning("M1S local WAV watcher failed host=%s: %s", self.client.host, exc)
            with suppress(Exception):
                await self.local_audio.async_stop_sound(token)
        async with self._lock:
            if self._token != token:
                return
            self._token = None
            self._watch_task = None
            with suppress(Exception):
                await self.local_audio.async_cleanup_sound(token)
            try:
                await self._finish_priority()
            except Exception as exc:
                _LOGGER.warning("M1S audio resume failed after local WAV host=%s: %s", self.client.host, exc)

    async def async_stop(self) -> None:
        async with self._lock:
            await self._stop_locked(restore_previous=True)

    async def _stop_locked(self, *, restore_previous: bool) -> None:
        token, self._token = self._token, None
        watch, self._watch_task = self._watch_task, None
        if watch is not None and watch is not asyncio.current_task():
            watch.cancel()
            with suppress(asyncio.CancelledError):
                await watch
        try:
            if token is not None:
                await self.local_audio.async_stop_sound(token)
                await self.local_audio.async_cleanup_sound(token)
        finally:
            if restore_previous:
                await self._finish_priority()
