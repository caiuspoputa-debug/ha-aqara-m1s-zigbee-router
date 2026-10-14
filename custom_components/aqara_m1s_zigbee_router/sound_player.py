from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant

from .client import AqaraM1SClient
from .local_audio import safe_sound_path, safe_sound_url

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

    async def _begin_priority_locked(self) -> None:
        if self._interruption_active:
            return
        await self.group_manager.async_claim_sound(self.entry_id)
        self._interruption_active = True
        self._resume_radio = await self.radio_player.async_suspend_for_priority_sound()
        await asyncio.sleep(0.25)

    async def _finish_priority(self) -> None:
        if not self._interruption_active:
            return
        resume_radio = self._resume_radio
        self._resume_radio = False
        self._interruption_active = False
        try:
            await self.radio_player.async_resume_after_priority_sound(resume_radio)
        finally:
            await self.group_manager.async_release_sound(self.entry_id)

    async def async_play(self, path: str, volume: float | None = None) -> None:
        # The legacy argument is retained for callers; the shared media volume,
        # mute and existing fine trim are authoritative for local WAVs too.
        source = safe_sound_path(path)
        await self._play_local(source)

    async def _play_local(self, source: str, *, url: bool = False) -> None:
        if self.client.zigbee_role == "coordinator":
            raise RuntimeError("Dedicated coordinator does not expose audio")
        if self.local_audio is None:
            raise RuntimeError("Local hub audio is not configured")
        started = time.perf_counter()
        async with self._lock:
            try:
                await self._stop_locked(restore_previous=False)
                await self._begin_priority_locked()
                await self.local_audio.async_prepare(self.radio_player._effective_gain())
                start_method = self.local_audio.async_start_url if url else self.local_audio.async_start_sound
                start_task = self.hass.async_create_task(start_method(source))
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
                _LOGGER.info(
                    "M1S local WAV accepted host=%s request_to_accept_ms=%s mode=hub_alsa_no_audio_transfer",
                    self.client.host, round((time.perf_counter() - started) * 1000))
            except BaseException:
                await self._finish_priority()
                raise

    async def async_play_url(self, url: str) -> None:
        """Download an explicit WAV URL to hub RAM with the same priority policy."""
        await self._play_local(safe_sound_url(url), url=True)

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
