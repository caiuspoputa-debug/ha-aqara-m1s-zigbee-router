from __future__ import annotations

import asyncio
from array import array
import logging
import os
import shutil
import socket
import sys
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
from .media_group import AqaraM1SMediaGroup
from .const import (
    DATA_CLIENTS,
    DATA_COORDINATORS,
    DATA_RADIO_PLAYERS,
    DATA_MEDIA_GROUP,
    DOMAIN,
    radio_volume_signal,
)

_LOGGER = logging.getLogger(__name__)

RADIO_PORT = 12346
REMOTE_FIFO = "/tmp/aqara_m1s_radio_fifo"
REMOTE_NC_PID = "/tmp/aqara_m1s_radio_nc.pid"
REMOTE_APLAY_PID = "/tmp/aqara_m1s_radio_aplay.pid"

WATCHDOG_RESTART_DELAY = 5.0
WATCHDOG_FAST_RESTART_DELAY = 0.25
WATCHDOG_MAX_RESTARTS = 3
WATCHDOG_STABLE_SECONDS = 30.0
WATCHDOG_SLOW_RETRY_DELAY = 60.0

PCM_RATE = 32000
PCM_CHANNELS = 1
PCM_SAMPLE_BYTES = 4
# The M1S ALSA driver reports period_size=1120 at 32 kHz, i.e. 35 ms.
# Pace single-player PCM in the same unit so aplay receives period-aligned data.
PCM_CHUNK_SECONDS = 0.035
PCM_CHUNK_BYTES = int(
    PCM_RATE * PCM_CHANNELS * PCM_SAMPLE_BYTES * PCM_CHUNK_SECONDS
)
PCM_SILENCE_CHUNK = b"\x00" * PCM_CHUNK_BYTES
# Single-player stable transport. Keep a bounded HA-side PCM jitter buffer so
# short scheduler/network stalls do not starve aplay, while volume/mute is still
# applied only when a chunk leaves the buffer. This keeps audible volume latency
# below a few seconds without returning to the old 5-6 s volume lag.
SINGLE_JITTER_BUFFER_SECONDS = 4.00
SINGLE_PREBUFFER_SECONDS = 2.50
SINGLE_REBUFFER_RESUME_SECONDS = 2.00
SINGLE_REMOTE_PREFILL_SECONDS = 0.56
SINGLE_JITTER_BUFFER_CHUNKS = max(1, int(SINGLE_JITTER_BUFFER_SECONDS / PCM_CHUNK_SECONDS))
SINGLE_PREBUFFER_CHUNKS = max(1, int(SINGLE_PREBUFFER_SECONDS / PCM_CHUNK_SECONDS))
SINGLE_REBUFFER_RESUME_CHUNKS = max(1, int(SINGLE_REBUFFER_RESUME_SECONDS / PCM_CHUNK_SECONDS))
SINGLE_REMOTE_PREFILL_CHUNKS = max(
    1, int(SINGLE_REMOTE_PREFILL_SECONDS / PCM_CHUNK_SECONDS)
)
SINGLE_LOW_QUEUE_CHUNKS = max(2, int(0.30 / PCM_CHUNK_SECONDS))
SINGLE_WRITE_HIGH_WATER_BYTES = PCM_CHUNK_BYTES * 16
SINGLE_WRITE_LOW_WATER_BYTES = PCM_CHUNK_BYTES * 8
SINGLE_SOCKET_SNDBUF_BYTES = PCM_CHUNK_BYTES * 16
SINGLE_PACE_REBASE_SECONDS = 0.50
SINGLE_LOW_QUEUE_LOG_INTERVAL = 30.0
SINGLE_SOURCE_STALL_TIMEOUT = 5.0
SINGLE_TCP_RECOVERY_WINDOW_SECONDS = 30.0
SINGLE_TCP_RECOVERY_BURST_LIMIT = 3
SINGLE_TCP_RECOVERY_SILENCE_SECONDS = 0.14
SINGLE_TCP_RECOVERY_SILENCE_CHUNKS = max(
    1, int(SINGLE_TCP_RECOVERY_SILENCE_SECONDS / PCM_CHUNK_SECONDS)
)
SINGLE_TCP_RECOVERY_DROP_SECONDS = 0.14
SINGLE_TCP_RECOVERY_DROP_CHUNKS = max(
    1, int(SINGLE_TCP_RECOVERY_DROP_SECONDS / PCM_CHUNK_SECONDS)
)
SINGLE_RECEIVER_HEALTH_INTERVAL_SECONDS = 5.0
SINGLE_RECEIVER_STALE_DELAY_FRAMES = int(PCM_RATE * 0.20)
SINGLE_RECEIVER_STALE_AVAIL_MULTIPLIER = 2
GAIN_RAMP_SECONDS = 0.04
GAIN_RAMP_SAMPLES = max(1, int(PCM_RATE * GAIN_RAMP_SECONDS))
WRITER_DRAIN_TIMEOUT = 5.0
# Teardown must never hold the single-player transport lock indefinitely.
# Stop/Play only detaches the active session. The producer keeps draining
# FFmpeg stdout and discards PCM after detach; the watcher remains the sole
# coroutine that awaits/reaps its FFmpeg process. A separate escalator may
# terminate/kill a stale process but never calls process.wait().
WRITER_CLOSE_TIMEOUT = 0.50
FFMPEG_TERMINATE_TIMEOUT = 1.50
FFMPEG_KILL_TIMEOUT = 3.00
FFMPEG_NICE_TARGET = -5
APLAY_NICE_TARGET = -3
APLAY_BUFFER_TIME_US = 2000000
APLAY_PERIOD_TIME_US = 35000

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
    + f'aplay -t raw -f S32_LE -c 1 -r {PCM_RATE} '
      f'--buffer-time={APLAY_BUFFER_TIME_US} '
      f'--period-time={APLAY_PERIOD_TIME_US} '
      f'{REMOTE_FIFO} </dev/null '
      '>/tmp/aqara_m1s_radio_aplay.log 2>&1 & '
    + f'echo $! > {REMOTE_APLAY_PID}; '
    + f'APID=$(cat {REMOTE_APLAY_PID}); '
      f'renice {APLAY_NICE_TARGET} -p "$APID" '
      '>/tmp/aqara_m1s_radio_aplay_renice.log 2>&1 || true'
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    player = hass.data[DOMAIN][DATA_RADIO_PLAYERS][entry.entry_id]
    entities: list[MediaPlayerEntity] = [player]
    manager = hass.data[DOMAIN][DATA_MEDIA_GROUP]
    if not manager.media_entity_added:
        manager.media_entity_added = True
        entities.append(AqaraM1SMediaGroup(hass, manager))
    async_add_entities(entities)


class AqaraM1SRadioPlayer(CoordinatorEntity, MediaPlayerEntity, RestoreEntity):
    """Stream Home Assistant media to the Aqara M1S speaker."""

    _attr_name = "Media Player"
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_should_poll = False
    # Main native Home Assistant slider: 0-100% in uniform 0.1% steps.
        # v0.5.9 adds a separate per-player Fine Volume Trim Number entity
        # (-2.00..+1.00 percentage points in 0.01 steps) without changing this
    # convenient coarse/main control.
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
        # Absolute percentage-point trim applied after the main volume.
        # Example: 6.0% main + 0.27% trim = 6.27% effective gain.
        self._fine_volume_trim_percent = 0.0
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
        self._stream_writer: asyncio.StreamWriter | None = None
        self._ffmpeg_nice_applied = False
        self._gain_current = self._effective_gain()
        self._gain_target = self._gain_current
        self._gain_ramp_start = self._gain_current
        self._gain_ramp_remaining = 0
        self._watchdog_restart_task: asyncio.Task | None = None
        self._watchdog_stable_task: asyncio.Task | None = None
        self._watchdog_slow_retry_task: asyncio.Task | None = None
        self._watchdog_restart_attempts = 0
        self._ffmpeg_started_monotonic: float | None = None
        self._ffmpeg_session = 0
        self._last_failure_kind: str | None = None
        self._last_failure_detail: str | None = None
        self._recovery_pending = False
        self._single_receiver_rebuilds = 0
        self._last_receiver_health: dict[str, Any] | None = None
        self._last_receiver_rebuild_reason: str | None = None
        self._shutting_down = False
        self._group_manager = None
        self._priority_sound_suspended = False
        # Monotonic user/audio intent generation. Every new Play/Stop/priority
        # request invalidates older queued starts so only the newest request
        # may touch the hub audio receiver (latest request wins).
        self._play_generation = 0
        self._last_superseded_generation: int | None = None
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.host)},
            "name": entry.data.get("name", f"Aqara M1S {client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    def set_group_manager(self, manager) -> None:
        """Attach the shared group arbiter without changing individual behavior."""
        self._group_manager = manager

    @property
    def playback_requested(self) -> bool:
        return bool(self._resume_after_reconnect)

    def _next_play_generation(self, reason: str) -> int:
        """Invalidate every older queued single-audio operation."""
        self._play_generation += 1
        generation = self._play_generation
        _LOGGER.info(
            "Aqara media intent entity=%s host=%s generation=%s reason=%s",
            self.entity_id,
            self.client.host,
            generation,
            reason,
        )
        return generation

    def _generation_is_current(self, generation: int) -> bool:
        return bool(
            generation == self._play_generation
            and not self._shutting_down
            and not self._priority_sound_suspended
        )

    def _cancel_recovery_tasks_now(self) -> None:
        """Cancel retries immediately, before waiting for the transport lock."""
        current = asyncio.current_task()
        for attr in (
            "_watchdog_restart_task",
            "_watchdog_stable_task",
            "_watchdog_slow_retry_task",
            "_resume_task",
        ):
            task = getattr(self, attr, None)
            if task is not None and task is not current and not task.done():
                task.cancel()
                setattr(self, attr, None)

    async def _cleanup_stale_receiver_locked(
        self, generation: int, phase: str
    ) -> None:
        """Clean only the single-player 12346 receiver after a superseded start."""
        self._last_superseded_generation = generation
        _LOGGER.warning(
            "Aqara media request superseded entity=%s host=%s "
            "generation=%s current_generation=%s phase=%s",
            self.entity_id,
            self.client.host,
            generation,
            self._play_generation,
            phase,
        )
        try:
            await self.hass.async_add_executor_job(
                self.client.run_command, REMOTE_STOP_COMMAND
            )
        except Exception as err:
            _LOGGER.debug(
                "Aqara media stale receiver cleanup failed entity=%s host=%s "
                "generation=%s phase=%s error=%s",
                self.entity_id,
                self.client.host,
                generation,
                phase,
                err,
            )

    async def _restart_current_generation(self, generation: int) -> None:
        """Restart remembered media without creating a newer user intent."""
        if (
            not self._generation_is_current(generation)
            or not self._resume_after_reconnect
            or (not self._resume_media_id and not self._media_url)
        ):
            return

        media_url = self._media_url
        if self._resume_media_id and media_source.is_media_source_id(
            self._resume_media_id
        ):
            resolved = await media_source.async_resolve_media(
                self.hass, self._resume_media_id, self.entity_id
            )
            if not self._generation_is_current(generation):
                return
            media_url = async_process_play_media_url(
                self.hass, resolved.url, allow_relative_url=False
            )

        async with self._lock:
            if not self._generation_is_current(generation):
                return
            if media_url is not None:
                self._media_url = media_url
            await self._start_locked(generation)

    async def _claim_individual_audio(self) -> None:
        if self._group_manager is not None:
            await self._group_manager.async_claim_individual(self.entry.entry_id)

    async def _release_individual_audio(self) -> None:
        if self._group_manager is not None:
            await self._group_manager.async_release_individual(self.entry.entry_id)

    async def async_suspend_for_priority_sound(self) -> bool:
        """Temporarily stop this player's transport without forgetting its source."""
        if self._shutting_down:
            return False
        generation = self._next_play_generation("priority_sound_preempt")
        self._priority_sound_suspended = True
        self._cancel_recovery_tasks_now()
        _LOGGER.info(
            "Aqara media priority preempt requested entity=%s host=%s generation=%s",
            self.entity_id, self.client.host, generation
        )
        # Resume any accepted single-media intent after the priority sound.
        # This also covers the narrow window where a rapid Play is already inside
        # REMOTE_START_COMMAND but has not assigned _stream_writer/_ffmpeg yet.
        should_resume = bool(self._resume_after_reconnect and self._media_url)
        # Always wait for the transport lock. A rapid Play request may still be
        # inside REMOTE_START_COMMAND before _ffmpeg/_stream_writer are assigned.
        # The generation bump above makes that start stale; taking this lock waits
        # for it to abort/clean up before the priority sound transport begins.
        async with self._lock:
            await self._stop_locked(update_state=True, reason="priority_sound")
        # Keep remembered media/intent intact only when something was actually
        # playing or starting. _finish_priority() clears the suspend flag either way.
        return should_resume

    async def async_resume_after_priority_sound(self, should_resume: bool) -> None:
        """Resume media that was temporarily displaced by an integration sound."""
        self._priority_sound_suspended = False
        if (
            not should_resume
            or self._shutting_down
            or not self._resume_after_reconnect
            or not self._media_url
        ):
            return
        try:
            generation = self._next_play_generation("priority_sound_resume")
            async with self._lock:
                if self._ffmpeg is None and self._generation_is_current(generation):
                    await self._start_locked(generation)
        except Exception as err:
            _LOGGER.warning(
                "Aqara media could not resume after priority sound entity=%s host=%s: %s",
                self.entity_id,
                self.client.host,
                err,
            )
            self._schedule_watchdog_restart()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is not None:
            attrs = last_state.attributes

            restored_volume = attrs.get("volume_level")
            if restored_volume is not None:
                try:
                    self._attr_volume_level = self._normalize_volume(
                        float(restored_volume)
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

        self._reset_live_gain()

        if self._group_manager is not None:
            self._group_manager.mark_individual_intent(
                self.entry.entry_id, self._resume_after_reconnect
            )

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
            "fine_volume_trim_percent": round(self._fine_volume_trim_percent, 2),
            "effective_volume_percent": round(self._effective_gain() * 100.0, 2),
            "is_volume_muted": self._attr_is_volume_muted,
            "resume_after_reconnect": self._resume_after_reconnect,
            "watchdog_restart_attempts": self._watchdog_restart_attempts,
            "watchdog_fast_restart_delay_seconds": WATCHDOG_FAST_RESTART_DELAY,
            "last_failure_kind": self._last_failure_kind,
            "last_failure_detail": self._last_failure_detail,
            "play_intent_generation": self._play_generation,
            "last_superseded_generation": self._last_superseded_generation,
            "single_request_policy": "latest_request_wins",
            "volume_apply_mode": "live_pcm_software_gain",
            "volume_stream_restart": False,
            "volume_step_percent": 0.1,
            "gain_ramp_ms": int(GAIN_RAMP_SECONDS * 1000),
            "pcm_writer_timeout_seconds": WRITER_DRAIN_TIMEOUT,
            "writer_close_timeout_seconds": WRITER_CLOSE_TIMEOUT,
            "ffmpeg_reap_mode": "watcher_owned_detach_drain",
            "ffmpeg_terminate_grace_seconds": FFMPEG_TERMINATE_TIMEOUT,
            "ffmpeg_kill_grace_seconds": FFMPEG_KILL_TIMEOUT,
            "user_stop_remote_cleanup": "deferred_until_next_play",
            "single_stable_jitter_buffer": True,
            "single_pcm_pace_ms": int(PCM_CHUNK_SECONDS * 1000),
            "single_jitter_buffer_ms": int(SINGLE_JITTER_BUFFER_SECONDS * 1000),
            "single_prebuffer_ms": int(SINGLE_PREBUFFER_SECONDS * 1000),
            "single_rebuffer_resume_ms": int(SINGLE_REBUFFER_RESUME_SECONDS * 1000),
            "single_remote_prefill_ms": int(SINGLE_REMOTE_PREFILL_SECONDS * 1000),
            "single_tcp_self_heal": True,
            "single_tcp_recovery_mode": "in_place_drop_stale_pcm",
            "single_tcp_recovery_window_seconds": SINGLE_TCP_RECOVERY_WINDOW_SECONDS,
            "single_tcp_recovery_burst_limit": SINGLE_TCP_RECOVERY_BURST_LIMIT,
            "single_tcp_recovery_silence_ms": int(
                SINGLE_TCP_RECOVERY_SILENCE_SECONDS * 1000
            ),
            "single_tcp_recovery_drop_ms": int(
                SINGLE_TCP_RECOVERY_DROP_SECONDS * 1000
            ),
            "single_receiver_health_interval_seconds": (
                SINGLE_RECEIVER_HEALTH_INTERVAL_SECONDS
            ),
            "single_receiver_stale_delay_ms": int(
                SINGLE_RECEIVER_STALE_DELAY_FRAMES / PCM_RATE * 1000
            ),
            "single_receiver_stale_policy": (
                "rebuild_on_alsa_pointer_underrun"
            ),
            "single_receiver_tcp_stale_diagnostic_only": True,
            "single_receiver_rebuilds": self._single_receiver_rebuilds,
            "last_receiver_health": self._last_receiver_health,
            "last_receiver_rebuild_reason": self._last_receiver_rebuild_reason,
            "single_source_stall_timeout_seconds": SINGLE_SOURCE_STALL_TIMEOUT,
            "single_write_high_water_ms": int(
                SINGLE_WRITE_HIGH_WATER_BYTES / (PCM_RATE * PCM_SAMPLE_BYTES) * 1000
            ),
            "single_socket_send_buffer_bytes": SINGLE_SOCKET_SNDBUF_BYTES,
            "ffmpeg_realtime_input": False,
            "ffmpeg_nice_target": FFMPEG_NICE_TARGET,
            "ffmpeg_nice_applied": self._ffmpeg_nice_applied,
            "aplay_nice_target": APLAY_NICE_TARGET,
            "aplay_buffer_ms": int(APLAY_BUFFER_TIME_US / 1000),
            "aplay_period_ms": int(APLAY_PERIOD_TIME_US / 1000),
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

    async def _close_writer_bounded(
        self, writer: asyncio.StreamWriter | None, *, reason: str
    ) -> None:
        """Close one TCP writer, aborting its transport if FIN teardown wedges."""
        if writer is None:
            return
        writer.close()
        close_task = self.hass.async_create_task(writer.wait_closed())
        done, _ = await asyncio.wait({close_task}, timeout=WRITER_CLOSE_TIMEOUT)
        if done:
            try:
                close_task.result()
                return
            except (OSError, ConnectionError) as err:
                log = (
                    _LOGGER.debug
                    if reason.startswith("tcp_recovery:")
                    else _LOGGER.warning
                )
                log(
                    "Aqara media writer close failed entity=%s host=%s reason=%s "
                    "error=%r; aborting transport",
                    self.entity_id,
                    self.client.host,
                    reason,
                    err,
                )
        else:
            log = (
                _LOGGER.debug
                if reason.startswith("tcp_recovery:")
                else _LOGGER.warning
            )
            log(
                "Aqara media writer close timeout entity=%s host=%s reason=%s "
                "timeout=%.2fs; aborting transport",
                self.entity_id,
                self.client.host,
                reason,
                WRITER_CLOSE_TIMEOUT,
            )
            close_task.cancel()
            # Do not await a wait_closed() coroutine that already exceeded the
            # hard bound. Consume any eventual non-cancellation exception.
            close_task.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
        transport = getattr(writer, "transport", None)
        if transport is not None:
            with suppress(Exception):
                transport.abort()
        # Yield once so callbacks caused by abort can run, but never wait again.
        await asyncio.sleep(0)

    def _configure_single_writer(self, writer: asyncio.StreamWriter) -> None:
        sock = writer.get_extra_info("socket")
        if sock is not None:
            with suppress(OSError):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with suppress(OSError):
                sock.setsockopt(
                    socket.SOL_SOCKET, socket.SO_SNDBUF, SINGLE_SOCKET_SNDBUF_BYTES
                )
        writer.transport.set_write_buffer_limits(
            high=SINGLE_WRITE_HIGH_WATER_BYTES,
            low=SINGLE_WRITE_LOW_WATER_BYTES,
        )

    async def _connect_single_writer(
        self, generation: int, *, reason: str
    ) -> asyncio.StreamWriter:
        writer: asyncio.StreamWriter | None = None
        last_error: Exception | None = None
        for attempt in range(12):
            if not self._generation_is_current(generation) or self._shutting_down:
                raise RuntimeError(f"single TCP connect became stale during {reason}")
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.client.host, RADIO_PORT), timeout=1.0
                )
                self._configure_single_writer(writer)
                return writer
            except (OSError, asyncio.TimeoutError) as err:
                last_error = err
                if attempt < 11:
                    await asyncio.sleep(0.15)
        raise ConnectionError(
            f"individual audio receiver unavailable during {reason}: {last_error}"
        )

    async def _recover_single_tcp_writer(
        self,
        process: asyncio.subprocess.Process,
        writer: asyncio.StreamWriter,
        generation: int,
        session: int,
        *,
        reason: str,
    ) -> asyncio.StreamWriter:
        if (
            self._ffmpeg is not process
            or not self._generation_is_current(generation)
            or self._shutting_down
        ):
            raise RuntimeError("single TCP recovery skipped for stale session")

        if self._stream_writer is writer:
            self._stream_writer = None
        await self._close_writer_bounded(writer, reason=f"tcp_recovery:{reason}")

        await self.hass.async_add_executor_job(
            self.client.run_command, REMOTE_START_COMMAND
        )
        new_writer = await self._connect_single_writer(
            generation, reason=f"tcp_recovery:{reason}"
        )

        if (
            self._ffmpeg is not process
            or not self._generation_is_current(generation)
            or self._shutting_down
        ):
            await self._close_writer_bounded(new_writer, reason="stale_tcp_recovery")
            raise RuntimeError("single TCP recovery finished on stale session")

        self._stream_writer = new_writer
        self._single_receiver_rebuilds += 1
        self._last_receiver_rebuild_reason = reason
        _LOGGER.warning(
            "Aqara media single TCP receiver recovered entity=%s session=%s "
            "generation=%s host=%s pid=%s reason=%s",
            self.entity_id,
            session,
            generation,
            self.client.host,
            process.pid,
            reason,
        )
        return new_writer

    @staticmethod
    def _parse_receiver_int(line: str) -> int | None:
        if ":" not in line:
            return None
        try:
            return int(line.split(":", 1)[1].strip().split()[0])
        except (IndexError, ValueError):
            return None

    def _parse_single_receiver_health(self, snapshot: str) -> dict[str, Any]:
        text = snapshot or ""
        upper = text.upper()
        tcp_stale_states = [
            state
            for state in ("FIN_WAIT", "CLOSE_WAIT", "LAST_ACK", "CLOSING")
            if state in upper
        ]
        has_established = "ESTABLISHED" in upper
        tcp_stale = bool(tcp_stale_states and not has_established)

        delay: int | None = None
        avail: int | None = None
        avail_max: int | None = None
        buffer_size: int | None = None
        state: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("state:"):
                state = line.split(":", 1)[1].strip()
            elif line.startswith("delay"):
                delay = self._parse_receiver_int(line)
            elif line.startswith("avail_max"):
                avail_max = self._parse_receiver_int(line)
            elif line.startswith("avail"):
                avail = self._parse_receiver_int(line)
            elif line.startswith("buffer_size"):
                buffer_size = self._parse_receiver_int(line)

        stale_reasons: list[str] = []
        if delay is not None and delay <= -SINGLE_RECEIVER_STALE_DELAY_FRAMES:
            stale_reasons.append(f"alsa_delay:{delay}")
        if (
            avail is not None
            and buffer_size is not None
            and avail >= buffer_size * SINGLE_RECEIVER_STALE_AVAIL_MULTIPLIER
        ):
            stale_reasons.append(f"alsa_avail:{avail}/{buffer_size}")

        return {
            "stale": bool(stale_reasons),
            "reason": ";".join(stale_reasons),
            "tcp_stale_states": tcp_stale_states,
            "tcp_established": has_established,
            "tcp_stale_diagnostic_only": tcp_stale,
            "alsa_state": state,
            "alsa_delay_frames": delay,
            "alsa_avail_frames": avail,
            "alsa_avail_max_frames": avail_max,
            "alsa_buffer_frames": buffer_size,
        }

    async def _read_single_receiver_health(self) -> dict[str, Any]:
        command = (
            f'echo "__tcp__"; netstat -an 2>/dev/null | grep {RADIO_PORT}; '
            'echo "__status__"; '
            'cat /proc/asound/card0/pcm0p/sub0/status 2>/dev/null; '
            'echo "__hw__"; '
            'cat /proc/asound/card0/pcm0p/sub0/hw_params 2>/dev/null'
        )
        snapshot = await self.hass.async_add_executor_job(
            self.client.run_command, command
        )
        return self._parse_single_receiver_health(str(snapshot))

    async def _terminate_process_bounded(
        self, process: asyncio.subprocess.Process | None, *, reason: str
    ) -> None:
        """Terminate and reap FFmpeg when called from its owning watcher."""
        if process is None or process.returncode is not None:
            return
        with suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=FFMPEG_TERMINATE_TIMEOUT)
            return
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Aqara media watcher terminate timeout entity=%s host=%s pid=%s "
                "reason=%s; escalating to kill",
                self.entity_id,
                self.client.host,
                process.pid,
                reason,
            )
        with suppress(ProcessLookupError):
            process.kill()
        try:
            await asyncio.wait_for(process.wait(), timeout=FFMPEG_KILL_TIMEOUT)
        except asyncio.TimeoutError:
            _LOGGER.error(
                "Aqara media watcher could not reap FFmpeg after kill entity=%s "
                "host=%s pid=%s reason=%s",
                self.entity_id,
                self.client.host,
                process.pid,
                reason,
            )

    async def _terminate_process_while_stdout_drains(
        self,
        process: asyncio.subprocess.Process,
        producer_task: asyncio.Task,
        *,
        reason: str,
    ) -> None:
        """Terminate FFmpeg while its stdout reader remains active."""
        if process.returncode is not None:
            return
        with suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=FFMPEG_TERMINATE_TIMEOUT)
            return
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Aqara media watcher terminate timeout while draining stdout "
                "entity=%s host=%s pid=%s reason=%s; escalating to kill",
                self.entity_id,
                self.client.host,
                process.pid,
                reason,
            )

        with suppress(ProcessLookupError):
            process.kill()
        try:
            await asyncio.wait_for(process.wait(), timeout=FFMPEG_KILL_TIMEOUT)
        except asyncio.TimeoutError:
            _LOGGER.error(
                "Aqara media watcher could not reap FFmpeg after kill with "
                "stdout reader active entity=%s host=%s pid=%s reason=%s "
                "producer_done=%s",
                self.entity_id,
                self.client.host,
                process.pid,
                reason,
                producer_task.done(),
            )

    def _schedule_detached_process_escalation(
        self,
        process: asyncio.subprocess.Process | None,
        *,
        reason: str,
        session: int,
    ) -> None:
        """Signal an old FFmpeg without waiting for it in Stop/Play."""
        if process is None or process.returncode is not None:
            return

        # Stop is deliberately non-blocking: ownership has already moved away
        # from this process.  Its existing watcher drains/reaps it.
        with suppress(ProcessLookupError):
            process.terminate()

        async def _escalate() -> None:
            try:
                await asyncio.sleep(FFMPEG_TERMINATE_TIMEOUT)
                if process.returncode is not None:
                    return
                _LOGGER.warning(
                    "Aqara media detached FFmpeg still running after terminate; "
                    "killing in background entity=%s session=%s host=%s pid=%s "
                    "reason=%s",
                    self.entity_id,
                    session,
                    self.client.host,
                    process.pid,
                    reason,
                )
                with suppress(ProcessLookupError):
                    process.kill()

                # Never call process.wait() here.  The original watcher is the
                # sole reaper and may still be draining subprocess pipes.
                await asyncio.sleep(FFMPEG_KILL_TIMEOUT)
                if process.returncode is None:
                    _LOGGER.warning(
                        "Aqara media detached FFmpeg has no returncode yet after "
                        "background kill entity=%s session=%s host=%s pid=%s "
                        "reason=%s; watcher remains responsible for reap",
                        self.entity_id,
                        session,
                        self.client.host,
                        process.pid,
                        reason,
                    )
            except asyncio.CancelledError:
                return
            except Exception as err:
                _LOGGER.debug(
                    "Aqara media detached FFmpeg escalation failed entity=%s "
                    "session=%s host=%s pid=%s reason=%s error=%r",
                    self.entity_id,
                    session,
                    self.client.host,
                    process.pid,
                    reason,
                    err,
                )

        self.hass.async_create_background_task(
            _escalate(),
            f"aqara_m1s_ffmpeg_escalate_{self.entry.entry_id}_{session}",
        )

    async def async_shutdown(self) -> None:
        """Stop FFmpeg and every watchdog task without clearing resume intent."""
        if self._shutting_down:
            return
        self._shutting_down = True

        tasks = [
            self._resume_task,
            self._watchdog_restart_task,
            self._watchdog_stable_task,
            self._watchdog_slow_retry_task,
        ]
        self._resume_task = None
        self._watchdog_restart_task = None
        self._watchdog_stable_task = None
        self._watchdog_slow_retry_task = None
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
        """Resolve and play media; rapid requests use latest-request-wins."""
        generation = self._next_play_generation("play_media")
        self._cancel_recovery_tasks_now()
        original_media_id = media_id
        resolved_media_id = media_id

        if media_source.is_media_source_id(media_id):
            resolved = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            if not self._generation_is_current(generation):
                _LOGGER.warning(
                    "Aqara media request superseded before resolve finished "
                    "entity=%s host=%s generation=%s current_generation=%s",
                    self.entity_id, self.client.host, generation, self._play_generation
                )
                return
            resolved_media_id = resolved.url

        media_url = async_process_play_media_url(
            self.hass, resolved_media_id, allow_relative_url=False
        )

        title = None
        extra = kwargs.get("extra") or {}
        if isinstance(extra, dict):
            title = extra.get("title")

        async with self._lock:
            if not self._generation_is_current(generation):
                _LOGGER.warning(
                    "Aqara media request superseded queued request discarded "
                    "entity=%s host=%s "
                    "generation=%s current_generation=%s",
                    self.entity_id, self.client.host, generation, self._play_generation
                )
                return
            self._resume_media_id = original_media_id
            self._resume_media_type = media_type or MediaType.MUSIC
            self._media_url = media_url
            self._attr_media_content_id = original_media_id
            self._attr_media_content_type = self._resume_media_type
            self._attr_media_title = title or self._attr_media_title or "Radio stream"
            self._resume_after_reconnect = True
            await self._start_locked(generation)

    async def async_media_play(self) -> None:
        """Resume the last remembered media as a new user intent."""
        if self._shutting_down:
            return
        generation = self._next_play_generation("media_play")
        self._cancel_recovery_tasks_now()
        self._resume_after_reconnect = True
        if not self._resume_media_id and not self._media_url:
            return

        if self._resume_media_id and media_source.is_media_source_id(
            self._resume_media_id
        ):
            resolved = await media_source.async_resolve_media(
                self.hass, self._resume_media_id, self.entity_id
            )
            if not self._generation_is_current(generation):
                return
            media_url = async_process_play_media_url(
                self.hass, resolved.url, allow_relative_url=False
            )
            async with self._lock:
                if not self._generation_is_current(generation):
                    return
                self._media_url = media_url
                await self._start_locked(generation)
            return

        async with self._lock:
            if self._generation_is_current(generation):
                await self._start_locked(generation)

    async def async_media_stop(self) -> None:
        generation = self._next_play_generation("user_stop")
        self._cancel_recovery_tasks_now()
        self._resume_after_reconnect = False
        self._watchdog_restart_attempts = 0
        _LOGGER.info(
            "Aqara media STOP requested entity=%s host=%s generation=%s",
            self.entity_id,
            self.client.host,
            generation,
        )
        async with self._lock:
            # Do not run a potentially slow Telnet cleanup while holding the
            # transport lock. Closing/aborting the TCP stream makes hub-side nc
            # reach EOF; the next REMOTE_START_COMMAND always begins with the
            # exact PID/port-scoped cleanup before creating a fresh receiver.
            await self._stop_locked(
                update_state=True, reason="user_stop", remote_cleanup=False
            )
        _LOGGER.info(
            "Aqara media STOP local teardown complete entity=%s host=%s "
            "generation=%s; remote receiver cleanup deferred to next Play",
            self.entity_id,
            self.client.host,
            generation,
        )
        await self._release_individual_audio()

    async def async_turn_off(self) -> None:
        await self.async_media_stop()

    async def async_set_volume_level(self, volume: float) -> None:
        """Apply individual-player volume live to the running PCM stream."""
        self._attr_volume_level = self._normalize_volume(float(volume))
        self.async_write_ha_state()
        async_dispatcher_send(
            self.hass, radio_volume_signal(self.entry.entry_id)
        )

    @staticmethod
    def _normalize_volume(volume: float) -> float:
        """Quantize the complete 0-100% range in uniform 0.1% steps."""
        volume = max(0.0, min(1.0, volume))
        quantized = round(volume / 0.001) * 0.001
        return max(0.0, min(1.0, round(quantized, 3)))

    async def async_volume_up(self) -> None:
        """Increase volume by 0.1%."""
        current = self._attr_volume_level or 0.0
        await self.async_set_volume_level(current + 0.001)

    async def async_volume_down(self) -> None:
        """Decrease volume by 0.1%."""
        current = self._attr_volume_level or 0.0
        await self.async_set_volume_level(current - 0.001)

    async def async_mute_volume(self, mute: bool) -> None:
        """Apply mute live through the same PCM gain path."""
        self._attr_is_volume_muted = bool(mute)
        self.async_write_ha_state()
        async_dispatcher_send(
            self.hass, radio_volume_signal(self.entry.entry_id)
        )

    @property
    def fine_volume_trim_percent(self) -> float:
        """Return the per-player absolute fine trim in percentage points."""
        return self._fine_volume_trim_percent

    @staticmethod
    def _normalize_fine_volume_trim_percent(value: float) -> float:
        """Clamp/quantize fine trim to -2.00..+1.00 in 0.01% steps."""
        value = max(-2.0, min(1.0, float(value)))
        return round(round(value / 0.01) * 0.01, 2)

    def set_fine_volume_trim_percent(self, value: float) -> None:
        """Apply a fine absolute percentage-point trim to live PCM gain."""
        self._fine_volume_trim_percent = self._normalize_fine_volume_trim_percent(value)
        # _apply_live_pcm_gain() samples _effective_gain() for every 20 ms PCM
        # chunk, so no FFmpeg/TCP/aplay restart is needed. If the media-player
        # entity is already registered, refresh its diagnostic attributes too.
        if self.entity_id is not None:
            self.async_write_ha_state()

    def _effective_gain(self) -> float:
        if self._attr_is_volume_muted:
            return 0.0
        main_gain = max(0.0, min(1.0, float(self._attr_volume_level or 0.0)))
        # Volume 0 is a hard silence. A positive trim must never make a player
        # audible when the main Home Assistant volume is explicitly zero.
        if main_gain <= 0.0:
            return 0.0
        trimmed_gain = main_gain + (self._fine_volume_trim_percent / 100.0)
        return max(0.0, min(1.0, trimmed_gain))

    def _reset_live_gain(self) -> None:
        target = self._effective_gain()
        self._gain_current = target
        self._gain_target = target
        self._gain_ramp_start = target
        self._gain_ramp_remaining = 0

    def _apply_live_pcm_gain(self, chunk: bytes) -> bytes:
        """Scale one S32_LE PCM chunk with a short anti-click transition."""
        target = self._effective_gain()
        if target != self._gain_target:
            self._gain_ramp_start = self._gain_current
            self._gain_target = target
            self._gain_ramp_remaining = GAIN_RAMP_SAMPLES

        if self._gain_ramp_remaining <= 0:
            self._gain_current = target
            if target <= 0.0:
                return PCM_SILENCE_CHUNK
            if target >= 1.0:
                return chunk

        samples = array("i")
        samples.frombytes(chunk)
        if samples.itemsize != PCM_SAMPLE_BYTES:
            raise RuntimeError(
                f"Unsupported native int size for S32_LE PCM: {samples.itemsize}"
            )
        if sys.byteorder != "little":
            samples.byteswap()

        if self._gain_ramp_remaining > 0:
            start_gain = self._gain_ramp_start
            change = self._gain_target - start_gain
            remaining = self._gain_ramp_remaining
            total = GAIN_RAMP_SAMPLES
            elapsed = total - remaining
            for index, sample in enumerate(samples):
                if remaining > 0:
                    progress = min(1.0, (elapsed + index + 1) / total)
                    gain = start_gain + (change * progress)
                    remaining -= 1
                else:
                    gain = self._gain_target
                samples[index] = int(sample * gain)
            self._gain_ramp_remaining = remaining
            if remaining <= 0:
                self._gain_current = self._gain_target
            else:
                progress = min(1.0, (total - remaining) / total)
                self._gain_current = start_gain + (change * progress)
        else:
            gain = self._gain_current
            for index, sample in enumerate(samples):
                samples[index] = int(sample * gain)

        if sys.byteorder != "little":
            samples.byteswap()
        return samples.tobytes()

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
            if self._watchdog_slow_retry_task:
                self._watchdog_slow_retry_task.cancel()
                self._watchdog_slow_retry_task = None
            if self._resume_after_reconnect and self._resume_media_id:
                _LOGGER.info(
                    "Aqara media hub reconnected; scheduling remembered media resume "
                    "entity=%s host=%s",
                    self.entity_id,
                    self.client.host,
                )
                self._schedule_resume(delay=2.0)
        super()._handle_coordinator_update()

    def _schedule_resume(self, delay: float) -> None:
        generation = self._play_generation
        if self._resume_task and not self._resume_task.done():
            self._resume_task.cancel()
        self._resume_task = self.hass.async_create_task(
            self._async_resume_after_delay(delay, generation)
        )

    async def _async_resume_after_delay(
        self, delay: float, generation: int
    ) -> None:
        try:
            await asyncio.sleep(delay)
            if (
                self._generation_is_current(generation)
                and self._resume_after_reconnect
                and self._resume_media_id
                and self.coordinator.last_update_success
                and self._attr_state != MediaPlayerState.PLAYING
            ):
                await self._restart_current_generation(generation)
            await asyncio.sleep(0.5)
            if (
                generation == self._play_generation
                and self._resume_after_reconnect
                and self._attr_state != MediaPlayerState.PLAYING
                and self.coordinator.last_update_success
            ):
                next_kind = self._last_failure_kind or "unknown"
                self._watchdog_restart_task = None
                self._schedule_watchdog_restart(next_kind, generation)
                return
        except asyncio.CancelledError:
            return
        except Exception as err:
            _LOGGER.warning(
                "Could not automatically resume Aqara media entity=%s "
                "generation=%s: %s", self.entity_id, generation, err
            )
        finally:
            if self._resume_task is asyncio.current_task():
                self._resume_task = None

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

    @staticmethod
    def _classify_ffmpeg_failure(stderr_text: str, runtime: float) -> tuple[str, str]:
        """Classify an FFmpeg exit so recovery targets the real failure domain."""
        text = stderr_text.lower()
        source_patterns = (
            "error opening input",
            "error opening input file",
            "connection refused",
            "server returned 4",
            "server returned 5",
            "http error",
            "failed to resolve hostname",
            "temporary failure in name resolution",
            "name or service not known",
            "input/output error",
            "invalid data found when processing input",
            "end of file",
            "connection timed out",
        )
        output_patterns = (
            "broken pipe",
            "error muxing a packet",
            "error writing trailer",
            "error closing file",
            "connection reset by peer",
        )
        if runtime <= 10.0 and any(pattern in text for pattern in source_patterns):
            return "source_unavailable", "FFmpeg could not open or keep the media source"
        if any(pattern in text for pattern in output_patterns):
            return "hub_audio", "The hub-side TCP/audio receiver closed the output"
        return "unknown", "FFmpeg exited for an unclassified reason"

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

    async def _start_locked(self, generation: int) -> None:
        """Start one single-player transport only if its intent is still current."""
        if not self._generation_is_current(generation) or not self._media_url:
            return

        await self._claim_individual_audio()
        if not self._generation_is_current(generation):
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
        if self._watchdog_slow_retry_task:
            self._watchdog_slow_retry_task.cancel()
            self._watchdog_slow_retry_task = None

        await self._stop_local_ffmpeg("replace_before_start")
        if not self._generation_is_current(generation):
            return

        _LOGGER.warning(
            "Aqara media receiver start entity=%s host=%s generation=%s port=%s",
            self.entity_id, self.client.host, generation, RADIO_PORT
        )
        await self.hass.async_add_executor_job(
            self.client.run_command, REMOTE_START_COMMAND
        )
        if not self._generation_is_current(generation):
            await self._cleanup_stale_receiver_locked(generation, "after_remote_start")
            return

        writer: asyncio.StreamWriter | None = None
        last_error: Exception | None = None
        for attempt in range(12):
            if not self._generation_is_current(generation):
                await self._cleanup_stale_receiver_locked(generation, "tcp_connect")
                return
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.client.host, RADIO_PORT), timeout=1.0
                )
                break
            except (OSError, asyncio.TimeoutError) as err:
                last_error = err
                if attempt < 11:
                    await asyncio.sleep(0.15)
        if writer is None:
            with suppress(Exception):
                await self.hass.async_add_executor_job(
                    self.client.run_command, REMOTE_STOP_COMMAND
                )
            raise ConnectionError(
                f"individual audio receiver unavailable: {last_error}"
            )

        if not self._generation_is_current(generation):
            await self._close_writer_bounded(
                writer, reason="stale_after_tcp_connect"
            )
            await self._cleanup_stale_receiver_locked(generation, "after_tcp_connect")
            return

        self._configure_single_writer(writer)
        self._stream_writer = writer

        ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
        args = [
            ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning",
            "-reconnect", "1", "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            # Decode freely into the bounded HA-side jitter buffer. The consumer
            # below is the only real-time clock, so FFmpeg can refill the buffer
            # after a short stall without ever filling the hub several seconds ahead.
            "-i", self._media_url,
            "-vn", "-ac", str(PCM_CHANNELS), "-ar", str(PCM_RATE),
            "-c:a", "pcm_s32le", "-f", "s32le", "pipe:1",
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except Exception as err:
            await self._close_writer_bounded(
                writer, reason="ffmpeg_spawn_failure"
            )
            if self._stream_writer is writer:
                self._stream_writer = None
            with suppress(Exception):
                await self.hass.async_add_executor_job(
                    self.client.run_command, REMOTE_STOP_COMMAND
                )
            self._attr_state = MediaPlayerState.IDLE
            self.async_write_ha_state()
            if isinstance(err, FileNotFoundError):
                raise RuntimeError(
                    "FFmpeg was not found. On Home Assistant OS/Container it is "
                    "normally pre-installed; otherwise install/configure FFmpeg."
                ) from err
            raise

        if not self._generation_is_current(generation):
            await self._terminate_process_bounded(
                process, reason="stale_after_ffmpeg_start"
            )
            await self._close_writer_bounded(
                writer, reason="stale_after_ffmpeg_start"
            )
            if self._stream_writer is writer:
                self._stream_writer = None
            await self._cleanup_stale_receiver_locked(generation, "after_ffmpeg_start")
            return

        self._ffmpeg = process
        self._ffmpeg_nice_applied = self._try_set_ffmpeg_priority(process.pid)
        self._reset_live_gain()
        self._ffmpeg_session += 1
        session = self._ffmpeg_session
        self._ffmpeg_started_monotonic = time.monotonic()
        _LOGGER.info(
            "Aqara media FFmpeg started entity=%s session=%s generation=%s pid=%s "
            "host=%s source=%s volume=%.3f muted=%s nice_target=%s nice_applied=%s",
            self.entity_id, session, generation, process.pid, self.client.host,
            self._safe_media_for_log(self._media_url),
            self._attr_volume_level or 0.0, self._attr_is_volume_muted,
            FFMPEG_NICE_TARGET, self._ffmpeg_nice_applied,
        )
        self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()
        self._watch_task = self.hass.async_create_background_task(
            self._watch_ffmpeg(process, writer, generation),
            f"aqara_m1s_ffmpeg_watch_{self.entry.entry_id}",
        )
        self._watchdog_stable_task = self.hass.async_create_background_task(
            self._reset_watchdog_after_stable_playback(process),
            f"aqara_m1s_stable_watch_{self.entry.entry_id}",
        )

    @staticmethod
    def _try_set_ffmpeg_priority(pid: int) -> bool:
        """Best-effort moderate CPU priority; never fail playback."""
        try:
            os.setpriority(os.PRIO_PROCESS, pid, FFMPEG_NICE_TARGET)
            return os.getpriority(os.PRIO_PROCESS, pid) <= FFMPEG_NICE_TARGET
        except (AttributeError, OSError, PermissionError) as err:
            _LOGGER.debug(
                "Could not apply FFmpeg nice=%s to pid=%s: %s",
                FFMPEG_NICE_TARGET,
                pid,
                err,
            )
            return False

    @staticmethod
    async def _read_ffmpeg_stderr(
        process: asyncio.subprocess.Process,
    ) -> str:
        if process.stderr is None:
            return ""
        lines: list[str] = []
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            decoded = line.decode(errors="replace").strip()
            if decoded:
                lines.append(decoded)
                lines = lines[-40:]
        return "\n".join(lines)[-4000:]

    async def _watch_ffmpeg(
        self,
        process: asyncio.subprocess.Process,
        writer: asyncio.StreamWriter,
        generation: int,
    ) -> None:
        """Buffer raw PCM briefly, then pace it steadily to the hub."""
        session = self._ffmpeg_session
        started = self._ffmpeg_started_monotonic
        stderr_task = self.hass.async_create_background_task(
            self._read_ffmpeg_stderr(process),
            f"aqara_m1s_ffmpeg_stderr_{self.entry.entry_id}",
        )
        stderr_text = ""
        pump_error: Exception | None = None
        queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=SINGLE_JITTER_BUFFER_CHUNKS
        )
        producer_done = asyncio.Event()
        producer_error: Exception | None = None
        producer_discard = False
        low_queue_events = 0
        silence_fill_events = 0
        rebuffer_events = 0
        rebuffering = False
        tcp_recovery_events = 0
        tcp_recovery_window_started = 0.0
        consecutive_drain_timeouts = 0
        last_low_queue_log = 0.0
        last_real_pcm_monotonic = time.monotonic()
        health_task: asyncio.Task | None = None
        last_health_probe = 0.0

        async def _produce_pcm() -> None:
            nonlocal producer_error
            buffer = bytearray()
            try:
                if process.stdout is None:
                    raise RuntimeError("FFmpeg PCM stdout pipe is unavailable")
                while not self._shutting_down:
                    data = await process.stdout.read(PCM_CHUNK_BYTES * 8)
                    if not data:
                        break
                    if self._ffmpeg is not process or producer_discard:
                        buffer.clear()
                        continue
                    buffer.extend(data)
                    while len(buffer) >= PCM_CHUNK_BYTES:
                        raw_chunk = bytes(buffer[:PCM_CHUNK_BYTES])
                        del buffer[:PCM_CHUNK_BYTES]
                        while (
                            self._ffmpeg is process
                            and not producer_discard
                            and not self._shutting_down
                        ):
                            try:
                                await asyncio.wait_for(queue.put(raw_chunk), timeout=0.05)
                                break
                            except asyncio.TimeoutError:
                                continue
                        if (
                            self._ffmpeg is not process
                            or producer_discard
                            or self._shutting_down
                        ):
                            buffer.clear()
                            break
            except asyncio.CancelledError:
                raise
            except Exception as err:
                producer_error = err
            finally:
                producer_done.set()

        producer_task = self.hass.async_create_background_task(
            _produce_pcm(),
            f"aqara_m1s_pcm_producer_{self.entry.entry_id}",
        )

        async def _prefill_remote_receiver() -> int:
            """Move a short PCM cushion from the HA queue to the hub pipeline."""
            nonlocal consecutive_drain_timeouts
            primed_chunks = 0
            while primed_chunks < SINGLE_REMOTE_PREFILL_CHUNKS:
                try:
                    raw_chunk = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                writer.write(self._apply_live_pcm_gain(raw_chunk))
                primed_chunks += 1

            if primed_chunks:
                await asyncio.wait_for(
                    writer.drain(), timeout=WRITER_DRAIN_TIMEOUT
                )
                consecutive_drain_timeouts = 0
            return primed_chunks

        async def _rebuild_receiver_and_resync(
            *, stage: str, cause: str, error: Exception | None = None
        ) -> None:
            nonlocal writer, tcp_recovery_events, tcp_recovery_window_started
            nonlocal consecutive_drain_timeouts
            now = time.monotonic()
            if now - tcp_recovery_window_started > SINGLE_TCP_RECOVERY_WINDOW_SECONDS:
                tcp_recovery_window_started = now
                tcp_recovery_events = 0
            tcp_recovery_events += 1
            if tcp_recovery_events > SINGLE_TCP_RECOVERY_BURST_LIMIT:
                raise RuntimeError(
                    "single TCP recovery burst limit exceeded"
                ) from error

            _LOGGER.warning(
                "Aqara media single receiver fault; rebuilding receiver "
                "and dropping stale PCM entity=%s session=%s generation=%s "
                "host=%s pid=%s stage=%s cause=%s recovery=%s/%s error=%r",
                self.entity_id,
                session,
                generation,
                self.client.host,
                process.pid,
                stage,
                cause,
                tcp_recovery_events,
                SINGLE_TCP_RECOVERY_BURST_LIMIT,
                error,
            )
            writer = await self._recover_single_tcp_writer(
                process,
                writer,
                generation,
                session,
                reason=f"{stage}:{cause}",
            )

            dropped_chunks = 0
            while dropped_chunks < SINGLE_TCP_RECOVERY_DROP_CHUNKS:
                try:
                    queue.get_nowait()
                    dropped_chunks += 1
                except asyncio.QueueEmpty:
                    break

            self._reset_live_gain()
            for _ in range(SINGLE_TCP_RECOVERY_SILENCE_CHUNKS):
                writer.write(PCM_SILENCE_CHUNK)
            await asyncio.wait_for(
                writer.drain(), timeout=WRITER_DRAIN_TIMEOUT
            )
            primed_chunks = await _prefill_remote_receiver()
            consecutive_drain_timeouts = 0
            _LOGGER.warning(
                "Aqara media single receiver resumed after stale PCM drop "
                "entity=%s session=%s generation=%s host=%s pid=%s "
                "dropped_ms=%s silence_ms=%s remote_prefill_ms=%s cause=%s",
                self.entity_id,
                session,
                generation,
                self.client.host,
                process.pid,
                int(dropped_chunks * PCM_CHUNK_SECONDS * 1000),
                int(SINGLE_TCP_RECOVERY_SILENCE_SECONDS * 1000),
                int(primed_chunks * PCM_CHUNK_SECONDS * 1000),
                cause,
            )

        async def _write_chunk_to_hub(raw_chunk: bytes, *, stage: str) -> None:
            nonlocal consecutive_drain_timeouts
            pcm = self._apply_live_pcm_gain(raw_chunk)
            try:
                writer.write(pcm)
                await asyncio.wait_for(
                    writer.drain(), timeout=WRITER_DRAIN_TIMEOUT
                )
                consecutive_drain_timeouts = 0
                return
            except asyncio.TimeoutError as err:
                consecutive_drain_timeouts += 1
                if stage != "playout" and consecutive_drain_timeouts < 2:
                    _LOGGER.warning(
                        "Aqara media single TCP drain timeout tolerated "
                        "entity=%s session=%s generation=%s host=%s pid=%s "
                        "stage=%s timeout=%ss consecutive_timeouts=%s "
                        "action=keep_receiver",
                        self.entity_id,
                        session,
                        generation,
                        self.client.host,
                        process.pid,
                        stage,
                        WRITER_DRAIN_TIMEOUT,
                        consecutive_drain_timeouts,
                    )
                    return
                _LOGGER.warning(
                    "Aqara media single TCP drain timeout; rebuilding "
                    "receiver entity=%s session=%s generation=%s host=%s pid=%s "
                    "stage=%s timeout=%ss consecutive_timeouts=%s "
                    "action=rebuild_receiver",
                    self.entity_id,
                    session,
                    generation,
                    self.client.host,
                    process.pid,
                    stage,
                    WRITER_DRAIN_TIMEOUT,
                    consecutive_drain_timeouts,
                )
                await _rebuild_receiver_and_resync(
                    stage=stage,
                    cause=err.__class__.__name__,
                    error=err,
                )
                return
            except (OSError, ConnectionError) as err:
                await _rebuild_receiver_and_resync(
                    stage=stage,
                    cause=err.__class__.__name__,
                    error=err,
                )
                return

        try:
            # Build a real jitter cushion before opening the playout clock. For
            # short files, start as soon as FFmpeg reaches EOF instead of waiting.
            prebuffer_started = time.monotonic()
            while (
                queue.qsize() < SINGLE_PREBUFFER_CHUNKS
                and not producer_done.is_set()
                and self._ffmpeg is process
                and not self._shutting_down
            ):
                await asyncio.sleep(0.01)

            _LOGGER.info(
                "Aqara media stable buffer primed entity=%s session=%s host=%s "
                "queued_ms=%s target_ms=%s prime_time_ms=%s",
                self.entity_id,
                session,
                self.client.host,
                int(queue.qsize() * PCM_CHUNK_SECONDS * 1000),
                int(SINGLE_PREBUFFER_SECONDS * 1000),
                int((time.monotonic() - prebuffer_started) * 1000),
            )

            primed_chunks = await _prefill_remote_receiver()
            _LOGGER.info(
                "Aqara media remote receiver prefilled entity=%s session=%s "
                "host=%s remote_prefill_ms=%s remaining_ha_buffer_ms=%s",
                self.entity_id,
                session,
                self.client.host,
                int(primed_chunks * PCM_CHUNK_SECONDS * 1000),
                int(queue.qsize() * PCM_CHUNK_SECONDS * 1000),
            )

            next_send_monotonic = time.monotonic()
            while self._ffmpeg is process and not self._shutting_down:
                if producer_error is not None:
                    raise producer_error

                # If FFmpeg is finished and every buffered frame was played,
                # normal end-of-media has been reached.
                if producer_done.is_set() and queue.empty():
                    break

                now = time.monotonic()
                delay = next_send_monotonic - now
                if delay > 0:
                    await asyncio.sleep(delay)
                    now = time.monotonic()
                elif now - next_send_monotonic > SINGLE_PACE_REBASE_SECONDS:
                    # A long HA event-loop stall must not trigger a multi-second
                    # catch-up burst. Rebase, while retaining the jitter buffer.
                    next_send_monotonic = now

                if health_task is not None and health_task.done():
                    try:
                        health = health_task.result()
                    except Exception as err:
                        _LOGGER.debug(
                            "Aqara media single receiver health check failed "
                            "entity=%s session=%s host=%s error=%s",
                            self.entity_id,
                            session,
                            self.client.host,
                            err,
                        )
                    else:
                        self._last_receiver_health = health
                        if health.get("stale"):
                            cause = str(health.get("reason") or "receiver_stale")
                            _LOGGER.warning(
                                "Aqara media ALSA playout underrun detected; "
                                "rebuilding receiver entity=%s session=%s "
                                "generation=%s host=%s pid=%s cause=%s "
                                "alsa_state=%s delay_frames=%s avail_frames=%s "
                                "buffer_frames=%s action=rebuild_receiver",
                                self.entity_id,
                                session,
                                generation,
                                self.client.host,
                                process.pid,
                                cause,
                                health.get("alsa_state"),
                                health.get("alsa_delay_frames"),
                                health.get("alsa_avail_frames"),
                                health.get("alsa_buffer_frames"),
                            )
                            await _rebuild_receiver_and_resync(
                                stage="health_check",
                                cause=cause,
                            )
                            next_send_monotonic = time.monotonic()
                    health_task = None

                if (
                    health_task is None
                    and now - last_health_probe >= SINGLE_RECEIVER_HEALTH_INTERVAL_SECONDS
                    and self._generation_is_current(generation)
                ):
                    last_health_probe = now
                    health_task = self.hass.async_create_background_task(
                        self._read_single_receiver_health(),
                        f"aqara_m1s_receiver_health_{self.entry.entry_id}",
                    )

                if queue.qsize() <= SINGLE_LOW_QUEUE_CHUNKS and not producer_done.is_set():
                    low_queue_events += 1
                    if now - last_low_queue_log >= SINGLE_LOW_QUEUE_LOG_INTERVAL:
                        last_low_queue_log = now
                        _LOGGER.warning(
                            "Aqara media single buffer low entity=%s session=%s host=%s "
                            "queued_ms=%s low_events=%s silence_fill_events=%s",
                            self.entity_id,
                            session,
                            self.client.host,
                            int(queue.qsize() * PCM_CHUNK_SECONDS * 1000),
                            low_queue_events,
                            silence_fill_events,
                        )

                if not rebuffering and queue.empty() and not producer_done.is_set():
                    rebuffering = True
                    rebuffer_events += 1
                    _LOGGER.warning(
                        "Aqara media single rebuffer started entity=%s session=%s "
                        "host=%s rebuffer_events=%s silence_fill_events=%s",
                        self.entity_id,
                        session,
                        self.client.host,
                        rebuffer_events,
                        silence_fill_events,
                    )

                if rebuffering:
                    if producer_done.is_set() or queue.qsize() >= SINGLE_REBUFFER_RESUME_CHUNKS:
                        rebuffering = False
                        _LOGGER.info(
                            "Aqara media single rebuffer ended entity=%s session=%s "
                            "host=%s queued_ms=%s",
                            self.entity_id,
                            session,
                            self.client.host,
                            int(queue.qsize() * PCM_CHUNK_SECONDS * 1000),
                        )
                    elif time.monotonic() - last_real_pcm_monotonic > SINGLE_SOURCE_STALL_TIMEOUT:
                        raise RuntimeError(
                            f"PCM source stalled for more than {SINGLE_SOURCE_STALL_TIMEOUT:.1f}s"
                        )
                    else:
                        raw_chunk = PCM_SILENCE_CHUNK
                        silence_fill_events += 1
                        await _write_chunk_to_hub(raw_chunk, stage="rebuffer_silence")
                        next_send_monotonic += PCM_CHUNK_SECONDS
                        continue

                if not rebuffering:
                    try:
                        raw_chunk = queue.get_nowait()
                        last_real_pcm_monotonic = time.monotonic()
                    except asyncio.QueueEmpty:
                        if producer_done.is_set():
                            break
                        if time.monotonic() - last_real_pcm_monotonic > SINGLE_SOURCE_STALL_TIMEOUT:
                            raise RuntimeError(
                                f"PCM source stalled for more than {SINGLE_SOURCE_STALL_TIMEOUT:.1f}s"
                            )
                        raw_chunk = PCM_SILENCE_CHUNK
                        silence_fill_events += 1

                # Volume/mute is deliberately applied here, not in the producer.
                # Therefore the 4.0 s jitter buffer does not add 4.0 s of volume lag.
                await _write_chunk_to_hub(raw_chunk, stage="playout")
                next_send_monotonic += PCM_CHUNK_SECONDS

            detached = self._ffmpeg is not process and not self._shutting_down
            if not producer_task.done() and not detached:
                producer_task.cancel()
            with suppress(asyncio.CancelledError):
                await producer_task

            await process.wait()
            stderr_text = await stderr_task

            if detached:
                _LOGGER.debug(
                    "Aqara media detached FFmpeg drained and reaped entity=%s "
                    "session=%s pid=%s host=%s returncode=%s",
                    self.entity_id,
                    session,
                    process.pid,
                    self.client.host,
                    process.returncode,
                )
                return

            if self._ffmpeg is not process or self._shutting_down:
                return
        except asyncio.CancelledError:
            if not producer_task.done():
                producer_task.cancel()
            with suppress(asyncio.CancelledError):
                await producer_task
            if not stderr_task.done():
                stderr_task.cancel()
            with suppress(asyncio.CancelledError):
                await stderr_task
            _LOGGER.debug(
                "Aqara media PCM watcher cancelled intentionally "
                "entity=%s session=%s pid=%s",
                self.entity_id,
                session,
                process.pid,
            )
            raise
        except Exception as err:
            if self._ffmpeg is not process and not self._shutting_down:
                with suppress(asyncio.CancelledError):
                    await producer_task
                await process.wait()
                stderr_text = await stderr_task
                _LOGGER.debug(
                    "Aqara media detached watcher ignored playout exception "
                    "entity=%s session=%s pid=%s host=%s returncode=%s error=%r "
                    "stderr=%r",
                    self.entity_id,
                    session,
                    process.pid,
                    self.client.host,
                    process.returncode,
                    err,
                    stderr_text,
                )
                return
            pump_error = err
            producer_discard = True
            while not queue.empty():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            if process.returncode is None:
                await self._terminate_process_while_stdout_drains(
                    process,
                    producer_task,
                    reason="watcher_exception",
                )
            if not producer_task.done():
                with suppress(asyncio.TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(producer_task, timeout=1.0)
            if not producer_task.done():
                producer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await producer_task
            if not stderr_task.done():
                with suppress(asyncio.TimeoutError):
                    stderr_text = await asyncio.wait_for(stderr_task, timeout=1.0)
            elif not stderr_task.cancelled():
                with suppress(Exception):
                    stderr_text = stderr_task.result()

            if self._ffmpeg is not process or self._shutting_down:
                return
        finally:
            if health_task is not None:
                if not health_task.done():
                    health_task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await health_task
            if not producer_task.done():
                producer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await producer_task
            if not stderr_task.done():
                stderr_task.cancel()
                with suppress(asyncio.CancelledError):
                    await stderr_task

        runtime = max(0.0, time.monotonic() - started) if started else 0.0
        self._ffmpeg = None
        self._ffmpeg_started_monotonic = None
        if self._stream_writer is writer:
            self._stream_writer = None
        await self._close_writer_bounded(writer, reason="watcher_exit")

        stable_task = self._watchdog_stable_task
        self._watchdog_stable_task = None
        await self._cancel_task(stable_task)

        if not self.coordinator.last_update_success:
            failure_kind = "hub_offline"
            failure_detail = "The coordinator reports the hub offline"
        elif isinstance(pump_error, asyncio.TimeoutError):
            failure_kind = "tcp_pcm_backpressure"
            failure_detail = (
                f"PCM/TCP writer did not drain within "
                f"{WRITER_DRAIN_TIMEOUT:.1f}s"
            )
        elif pump_error is not None:
            failure_kind = "hub_audio"
            failure_detail = f"PCM/TCP writer failed: {pump_error}"
        else:
            failure_kind, failure_detail = self._classify_ffmpeg_failure(
                stderr_text, runtime
            )
        self._last_failure_kind = failure_kind
        self._last_failure_detail = failure_detail
        self._recovery_pending = True

        _LOGGER.warning(
            "Aqara media FFmpeg/PCM ended unexpectedly entity=%s session=%s generation=%s "
            "pid=%s host=%s returncode=%s runtime=%.1fs playback_requested=%s "
            "failure_kind=%s source=%s pump_error=%r stderr=%r "
            "buffer_low_events=%s silence_fill_events=%s tcp_recovery_events=%s",
            self.entity_id,
            session,
            generation,
            process.pid,
            self.client.host,
            process.returncode,
            runtime,
            self._resume_after_reconnect,
            failure_kind,
            self._safe_media_for_log(self._media_url),
            pump_error,
            stderr_text,
            low_queue_events,
            silence_fill_events,
            tcp_recovery_events,
        )
        self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()

        if failure_kind in ("tcp_pcm_backpressure", "hub_audio", "unknown"):
            await self._log_remote_audio_snapshot(session)
        else:
            _LOGGER.info(
                "Aqara media skipped hub snapshot entity=%s session=%s "
                "failure_kind=%s detail=%s",
                self.entity_id,
                session,
                failure_kind,
                failure_detail,
            )

        if generation != self._play_generation:
            _LOGGER.info(
                "Aqara media stale watcher will not retry entity=%s host=%s "
                "generation=%s current_generation=%s",
                self.entity_id,
                self.client.host,
                generation,
                self._play_generation,
            )
        elif (
            not self._shutting_down
            and self._resume_after_reconnect
            and self._resume_media_id
        ):
            if failure_kind == "hub_offline":
                _LOGGER.warning(
                    "Aqara media recovery waiting for hub reconnect "
                    "entity=%s host=%s",
                    self.entity_id,
                    self.client.host,
                )
            else:
                self._schedule_watchdog_restart(failure_kind)

        if self._watch_task is asyncio.current_task():
            self._watch_task = None

    def _schedule_watchdog_restart(
        self, failure_kind: str | None = None, generation: int | None = None
    ) -> None:
        if self._shutting_down:
            return
        generation = self._play_generation if generation is None else generation
        if generation != self._play_generation:
            return
        failure_kind = failure_kind or self._last_failure_kind or "unknown"
        if self._watchdog_restart_attempts >= WATCHDOG_MAX_RESTARTS:
            if failure_kind == "hub_offline":
                _LOGGER.warning(
                    "Aqara media watchdog exhausted %s fast retries for %s; "
                    "waiting for a real hub reconnect generation=%s",
                    WATCHDOG_MAX_RESTARTS, self.entity_id, generation
                )
                return
            self._schedule_slow_retry(failure_kind, generation)
            return
        if self._watchdog_restart_task and not self._watchdog_restart_task.done():
            return
        self._watchdog_restart_task = self.hass.async_create_background_task(
            self._async_watchdog_restart(failure_kind, generation),
            f"aqara_m1s_restart_watch_{self.entry.entry_id}",
        )

    def _schedule_slow_retry(self, failure_kind: str, generation: int) -> None:
        if (
            self._shutting_down
            or not self._resume_after_reconnect
            or generation != self._play_generation
        ):
            return
        if self._watchdog_slow_retry_task and not self._watchdog_slow_retry_task.done():
            return
        _LOGGER.warning(
            "Aqara media watchdog exhausted %s fast retries for %s; "
            "scheduling slow retry in %.0fs failure_kind=%s generation=%s",
            WATCHDOG_MAX_RESTARTS, self.entity_id, WATCHDOG_SLOW_RETRY_DELAY,
            failure_kind, generation
        )
        self._watchdog_slow_retry_task = self.hass.async_create_background_task(
            self._async_watchdog_slow_retry(failure_kind, generation),
            f"aqara_m1s_slow_retry_{self.entry.entry_id}",
        )

    async def _async_watchdog_restart(
        self, failure_kind: str, generation: int
    ) -> None:
        try:
            restart_delay = (
                WATCHDOG_FAST_RESTART_DELAY
                if failure_kind in ("tcp_pcm_backpressure", "hub_audio")
                else WATCHDOG_RESTART_DELAY
            )
            await asyncio.sleep(restart_delay)
            if (
                generation != self._play_generation
                or not self._resume_after_reconnect
                or not self._resume_media_id
                or self._attr_state == MediaPlayerState.PLAYING
            ):
                return
            if not self.coordinator.last_update_success:
                self._last_failure_kind = "hub_offline"
                _LOGGER.warning(
                    "Aqara media watchdog paused because hub is offline "
                    "entity=%s host=%s generation=%s",
                    self.entity_id, self.client.host, generation
                )
                return
            self._watchdog_restart_attempts += 1
            _LOGGER.warning(
                "Aqara media watchdog restarting %s (%s/%s) "
                "failure_kind=%s generation=%s delay=%.2fs",
                self.entity_id, self._watchdog_restart_attempts,
                WATCHDOG_MAX_RESTARTS, failure_kind, generation, restart_delay
            )
            await self._restart_current_generation(generation)
            await asyncio.sleep(0.5)
            if (
                generation == self._play_generation
                and self._resume_after_reconnect
                and self._attr_state != MediaPlayerState.PLAYING
                and self.coordinator.last_update_success
            ):
                next_kind = self._last_failure_kind or failure_kind
                self._watchdog_restart_task = None
                self._schedule_watchdog_restart(next_kind, generation)
                return
        except asyncio.CancelledError:
            return
        except Exception as err:
            self._last_failure_kind = (
                "source_unavailable" if failure_kind == "source_unavailable" else "unknown"
            )
            self._last_failure_detail = str(err)
            _LOGGER.warning(
                "Aqara media watchdog restart failed for %s failure_kind=%s "
                "generation=%s: %s",
                self.entity_id, self._last_failure_kind, generation, err
            )
            if (
                self._resume_after_reconnect
                and generation == self._play_generation
            ):
                self._watchdog_restart_task = None
                self._schedule_watchdog_restart(self._last_failure_kind, generation)
                return
        finally:
            if self._watchdog_restart_task is asyncio.current_task():
                self._watchdog_restart_task = None

    async def _async_watchdog_slow_retry(
        self, failure_kind: str, generation: int
    ) -> None:
        try:
            await asyncio.sleep(WATCHDOG_SLOW_RETRY_DELAY)
            if (
                generation != self._play_generation
                or not self._resume_after_reconnect
                or not self._resume_media_id
                or self._attr_state == MediaPlayerState.PLAYING
            ):
                return
            if not self.coordinator.last_update_success:
                self._last_failure_kind = "hub_offline"
                _LOGGER.warning(
                    "Aqara media slow retry deferred because hub is offline "
                    "entity=%s host=%s generation=%s",
                    self.entity_id, self.client.host, generation
                )
                return
            _LOGGER.warning(
                "Aqara media watchdog slow retry entity=%s failure_kind=%s "
                "generation=%s source=%s",
                self.entity_id, failure_kind, generation,
                self._safe_media_for_log(self._media_url),
            )
            self._watchdog_restart_attempts = 0
            await self._restart_current_generation(generation)
        except asyncio.CancelledError:
            return
        except Exception as err:
            self._last_failure_detail = str(err)
            _LOGGER.warning(
                "Aqara media slow retry failed entity=%s failure_kind=%s "
                "generation=%s: %s",
                self.entity_id, failure_kind, generation, err
            )
            if (
                self._resume_after_reconnect
                and generation == self._play_generation
            ):
                self._watchdog_slow_retry_task = None
                self._schedule_slow_retry(failure_kind, generation)
                return
        finally:
            if self._watchdog_slow_retry_task is asyncio.current_task():
                self._watchdog_slow_retry_task = None

    async def _reset_watchdog_after_stable_playback(
        self, process: asyncio.subprocess.Process
    ) -> None:
        try:
            await asyncio.sleep(WATCHDOG_STABLE_SECONDS)
            if self._ffmpeg is process and process.returncode is None:
                previous_attempts = self._watchdog_restart_attempts
                previous_kind = self._last_failure_kind
                self._watchdog_restart_attempts = 0
                if self._watchdog_slow_retry_task:
                    self._watchdog_slow_retry_task.cancel()
                    self._watchdog_slow_retry_task = None
                if self._recovery_pending:
                    _LOGGER.info(
                        "Aqara media playback recovered and remained stable "
                        "entity=%s session=%s host=%s previous_failure_kind=%s "
                        "fast_attempts=%s source=%s",
                        self.entity_id,
                        self._ffmpeg_session,
                        self.client.host,
                        previous_kind or "unknown",
                        previous_attempts,
                        self._safe_media_for_log(self._media_url),
                    )
                self._recovery_pending = False
                self._last_failure_kind = None
                self._last_failure_detail = None
                self.async_write_ha_state()
        except asyncio.CancelledError:
            return
        finally:
            if self._watchdog_stable_task is asyncio.current_task():
                self._watchdog_stable_task = None

    async def _stop_local_ffmpeg(self, reason: str) -> None:
        """Detach current transport immediately; reap old FFmpeg asynchronously."""
        process = self._ffmpeg
        session = self._ffmpeg_session
        started = self._ffmpeg_started_monotonic

        # Invalidate ownership before doing any I/O.  A new Play generation can
        # now create its own process/writer and an old watcher cannot overwrite
        # the new session because all watcher state updates are identity-guarded.
        self._ffmpeg = None
        self._ffmpeg_started_monotonic = None
        watch_task = self._watch_task
        self._watch_task = None
        writer = self._stream_writer
        self._stream_writer = None
        self._ffmpeg_nice_applied = False

        # Do NOT cancel/await watch_task here.  Cancelling its stdout/stderr
        # readers and simultaneously awaiting process.wait() was the v0.9.3
        # Stop -> terminate timeout -> kill -> reap timeout failure.  The old
        # watcher notices self._ffmpeg is no longer its process, exits playout,
        # drains/reaps FFmpeg, and returns without touching the new session.
        await self._close_writer_bounded(writer, reason=reason)
        self._schedule_detached_process_escalation(
            process, reason=reason, session=session
        )

        if process is None:
            return
        runtime = max(0.0, time.monotonic() - started) if started else 0.0
        _LOGGER.info(
            "Aqara media FFmpeg detached entity=%s session=%s pid=%s host=%s "
            "reason=%s returncode=%s runtime=%.1fs watcher_active=%s",
            self.entity_id,
            session,
            process.pid,
            self.client.host,
            reason,
            process.returncode,
            runtime,
            bool(watch_task and not watch_task.done()),
        )

    async def _stop_locked(
        self, update_state: bool, reason: str, *, remote_cleanup: bool = True
    ) -> None:
        await self._stop_local_ffmpeg(reason)
        if remote_cleanup:
            try:
                await self.hass.async_add_executor_job(
                    self.client.run_command,
                    REMOTE_STOP_COMMAND,
                )
            except Exception as err:  # Hub may already be offline during unload.
                _LOGGER.debug("Could not stop Aqara radio receiver: %s", err)
        else:
            _LOGGER.debug(
                "Aqara media skipped synchronous remote stop entity=%s host=%s "
                "reason=%s; next start performs scoped cleanup",
                self.entity_id,
                self.client.host,
                reason,
            )
        if update_state:
            self._attr_state = MediaPlayerState.IDLE
            self.async_write_ha_state()
