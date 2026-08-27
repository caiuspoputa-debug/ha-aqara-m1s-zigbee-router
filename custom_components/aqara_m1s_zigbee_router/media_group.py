from __future__ import annotations

import asyncio
from array import array
from contextlib import suppress
from dataclasses import dataclass
import logging
import os
import shutil
import sys
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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

from .const import media_group_signal, media_group_volume_signal

_LOGGER = logging.getLogger(__name__)

GROUP_PORT = 12347
GROUP_FIFO = "/tmp/aqara_m1s_group_fifo"
GROUP_NC_PID = "/tmp/aqara_m1s_group_nc.pid"
GROUP_APLAY_PID = "/tmp/aqara_m1s_group_aplay.pid"
GROUP_OWNER = "/tmp/aqara_m1s_group_owner"

PCM_RATE = 32000
PCM_CHANNELS = 1
PCM_SAMPLE_BYTES = 4
CHUNK_SECONDS = 0.02
CHUNK_BYTES = int(PCM_RATE * PCM_CHANNELS * PCM_SAMPLE_BYTES * CHUNK_SECONDS)
# Clocked multi-room transport.  Home Assistant owns one playout clock; every
# hub is an independent receiver.  A slow/offline member is isolated and may
# rejoin later without restarting healthy members.
SYNC_LEAD_SECONDS = 0.60
SYNC_LEAD_CHUNKS = max(1, round(SYNC_LEAD_SECONDS / CHUNK_SECONDS))
JOIN_BOUNDARY_SECONDS = 0.20
JOIN_BOUNDARY_CHUNKS = max(1, round(JOIN_BOUNDARY_SECONDS / CHUNK_SECONDS))
INITIAL_PREROLL_SECONDS = 0.36
INITIAL_PREROLL_CHUNKS = max(1, round(INITIAL_PREROLL_SECONDS / CHUNK_SECONDS))
START_COHORT_GRACE_SECONDS = 0.30
START_FIRST_MEMBER_TIMEOUT = 3.0
PLAYOUT_START_MARGIN_SECONDS = 0.05
PLAYOUT_REBASE_THRESHOLD_SECONDS = 0.12
PLAYOUT_REBASE_MARGIN_SECONDS = 0.02
QUEUE_SECONDS = 1.5
QUEUE_CHUNKS = int(QUEUE_SECONDS / CHUNK_SECONDS)
RECONCILE_SECONDS = 1.0
RETURN_STABILIZE_SECONDS = 1.0
MEMBER_RETRY_BASE_SECONDS = 1.5
MEMBER_RETRY_MAX_SECONDS = 15.0
PCM_HEALTH_CHECK_SECONDS = 2.0
PCM_STALL_TIMEOUT = 12.0
PCM_START_GRACE_SECONDS = 8.0
WRITER_DRAIN_TIMEOUT = 1.0
WRITER_HIGH_WATER_BYTES = CHUNK_BYTES * 8   # ~160 ms at 32 kHz mono S32
WRITER_LOW_WATER_BYTES = CHUNK_BYTES * 2    # ~40 ms
SOCKET_SNDBUF_BYTES = CHUNK_BYTES * 8
WATCHDOG_RESTART_DELAY = 3.0
WATCHDOG_MAX_RESTARTS = 3
WATCHDOG_SLOW_RETRY_DELAY = 30.0
WATCHDOG_STABLE_SECONDS = 30.0
FULL_RESYNC_RETRY_SECONDS = MEMBER_RETRY_BASE_SECONDS  # compatibility attribute only
FULL_RESYNC_HARD_TIMEOUT = 20.0  # compatibility safety net; member faults never call it
MANUAL_RESET_NORMAL_STOP_TIMEOUT = 6.0
MANUAL_RESET_REMOTE_TIMEOUT = 3.0
GROUP_FFMPEG_TERMINATE_TIMEOUT = 2.0
GROUP_FFMPEG_KILL_TIMEOUT = 3.0
MEMBER_REMOTE_START_TIMEOUT = 2.5
MEMBER_REMOTE_STOP_TIMEOUT = 1.5
MEMBER_CONNECT_ATTEMPTS = 6
MEMBER_CONNECT_TIMEOUT = 0.40
MEMBER_CONNECT_RETRY_DELAY = 0.08
WRITER_CLOSE_TIMEOUT = 0.75
TASK_CANCEL_TIMEOUT = 1.0
PERIODIC_RECEIVER_RESYNC_ENABLED = False
PERIODIC_RECEIVER_RESYNC_SECONDS = 10 * 60.0
PERIODIC_RECEIVER_RESYNC_MIN_MEMBERS = 2
PERIODIC_RECEIVER_RESYNC_PAUSE_TIMEOUT = 2.0
GAIN_RAMP_SECONDS = 0.04
GAIN_RAMP_SAMPLES = max(1, int(PCM_RATE * GAIN_RAMP_SECONDS))
FFMPEG_NICE_TARGET = -5
APLAY_NICE_TARGET = -3
APLAY_BUFFER_TIME_US = 2000000
APLAY_PERIOD_TIME_US = 50000

SILENCE_CHUNK = b"\x00" * CHUNK_BYTES

GROUP_STOP_COMMAND = (
    f"for f in {GROUP_NC_PID} {GROUP_APLAY_PID}; do "
    '[ -f "$f" ] && kill -9 "$(cat "$f")" 2>/dev/null; '
    "done; "
    f"for p in $(ps w | grep '[n]c -l -p {GROUP_PORT}' | awk '{{print $1}}'); do "
    'kill -9 "$p" 2>/dev/null; done; '
    f"for p in $(ps w | grep '[a]play .*{GROUP_FIFO}' | awk '{{print $1}}'); do "
    'kill -9 "$p" 2>/dev/null; done; '
    f"rm -f {GROUP_NC_PID} {GROUP_APLAY_PID} {GROUP_FIFO} {GROUP_OWNER}"
)

GROUP_START_COMMAND = (
    GROUP_STOP_COMMAND
    + f'; rm -f {GROUP_FIFO}; mkfifo {GROUP_FIFO}; '
    + f'nc -l -p {GROUP_PORT} </dev/null > {GROUP_FIFO} '
      '2>/tmp/aqara_m1s_group_nc.log & '
    + f'echo $! > {GROUP_NC_PID}; '
    + f'aplay -t raw -f S32_LE -c 1 -r {PCM_RATE} '
      f'--buffer-time={APLAY_BUFFER_TIME_US} '
      f'--period-time={APLAY_PERIOD_TIME_US} '
      f'{GROUP_FIFO} </dev/null '
      '>/tmp/aqara_m1s_group_aplay.log 2>&1 & '
    + f'echo $! > {GROUP_APLAY_PID}; '
    + f'APID=$(cat {GROUP_APLAY_PID}); '
      f'renice {APLAY_NICE_TARGET} -p "$APID" '
      '>/tmp/aqara_m1s_group_aplay_renice.log 2>&1 || true; '
    + f'echo group > {GROUP_OWNER}'
)


@dataclass
class GroupMember:
    entry_id: str
    name: str
    client: Any
    coordinator: Any
    selected: bool = True
    state: str = "waiting"
    writer: asyncio.StreamWriter | None = None
    queue: asyncio.Queue[bytes | None] | None = None
    writer_task: asyncio.Task | None = None
    prepare_task: asyncio.Task | None = None
    join_at_sequence: int | None = None
    last_error: str | None = None
    generation: int = 0
    last_prepare_attempt_monotonic: float = 0.0
    prepare_failures: int = 0
    next_prepare_monotonic: float = 0.0
    was_online: bool | None = None
    online_since_monotonic: float | None = None
    lag_since_monotonic: float | None = None
    lag_peak_chunks: int = 0
    detaching: bool = False


class AqaraM1SMediaGroupManager:
    """Own one HA-clocked PCM timeline and independent multi-room receivers."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.members: dict[str, GroupMember] = {}
        self.individual_intent: set[str] = set()
        self.sound_intent: set[str] = set()
        self.entity: AqaraM1SMediaGroup | None = None
        self.media_entity_added = False

        self.media_url: str | None = None
        self.media_id: str | None = None
        self.media_type: str = MediaType.MUSIC
        self.media_title: str | None = None
        self.volume = 0.05
        self.muted = False
        self.desired_playing = False

        self.ffmpeg: asyncio.subprocess.Process | None = None
        self.broadcast_task: asyncio.Task | None = None
        self.stderr_task: asyncio.Task | None = None
        self.reconcile_task: asyncio.Task | None = None
        self.watchdog_task: asyncio.Task | None = None
        self.stable_task: asyncio.Task | None = None
        self.health_task: asyncio.Task | None = None
        self.resync_task: asyncio.Task | None = None
        self.periodic_receiver_resync_task: asyncio.Task | None = None
        self.slow_retry_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._generation = 0
        self._sequence = 0
        self._stream_started_monotonic: float | None = None
        self._playout_epoch_monotonic: float | None = None
        self._clock_rebase_count = 0
        self._last_pcm_monotonic: float | None = None
        self._watchdog_attempts = 0
        self._last_failure: str | None = None
        self._full_resync_count = 0
        self._last_full_resync_reason: str | None = None
        self._receiver_resync_count = 0
        self._last_receiver_resync_monotonic: float | None = None
        self._last_receiver_resync_reason: str | None = None
        self._broadcast_pause_requested = asyncio.Event()
        self._broadcast_paused = asyncio.Event()
        self._applied_volume = self.volume
        self._applied_muted = self.muted
        self._gain_current = self._effective_gain()
        self._gain_target = self._gain_current
        self._gain_ramp_start = self._gain_current
        self._gain_ramp_remaining = 0
        self._ffmpeg_nice_applied = False
        self._shutting_down = False

    def register_member(self, entry_id: str, name: str, client: Any, coordinator: Any) -> None:
        existing = self.members.get(entry_id)
        selected = existing.selected if existing else True
        online = bool(coordinator.last_update_success)
        self.members[entry_id] = GroupMember(
            entry_id=entry_id,
            name=name,
            client=client,
            coordinator=coordinator,
            selected=selected,
            state="waiting" if selected else "excluded",
            was_online=online,
            online_since_monotonic=time.monotonic() if online else None,
        )
        self._signal_update()

    async def unregister_member(self, entry_id: str) -> None:
        member = self.members.get(entry_id)
        await self._detach_member(
            entry_id,
            stop_remote=bool(member and member.writer is not None),
            new_state="unloaded",
        )
        self.members.pop(entry_id, None)
        self.individual_intent.discard(entry_id)
        self.sound_intent.discard(entry_id)
        self._signal_update()

    def set_selected(self, entry_id: str, selected: bool) -> None:
        member = self.members.get(entry_id)
        if member is None:
            return
        member.selected = selected
        if not selected:
            member.state = "excluded"
        elif entry_id in self.sound_intent:
            member.state = "playing_sound"
        elif entry_id in self.individual_intent:
            member.state = "playing_individual"
        else:
            member.state = "waiting_for_sync"
            member.last_prepare_attempt_monotonic = 0.0
            member.prepare_failures = 0
            member.next_prepare_monotonic = 0.0
        self._signal_update()
        if self.desired_playing:
            self._ensure_reconcile_task()

    async def async_member_disabled(self, entry_id: str) -> None:
        member = self.members.get(entry_id)
        had_group_session = bool(member and member.writer is not None)
        self.set_selected(entry_id, False)
        await self._detach_member(
            entry_id, stop_remote=had_group_session, new_state="excluded"
        )

    async def async_member_enabled(self, entry_id: str) -> None:
        self.set_selected(entry_id, True)
        if self.desired_playing:
            self._ensure_reconcile_task()

    async def async_claim_individual(self, entry_id: str) -> None:
        """Give the individual player priority and remove only the group receiver."""
        member = self.members.get(entry_id)
        had_group_session = bool(
            member
            and (
                member.writer is not None
                or (self.desired_playing and member.state in ("playing_group", "waiting_for_sync"))
            )
        )
        self.individual_intent.add(entry_id)
        await self._detach_member(
            entry_id,
            stop_remote=had_group_session,
            new_state=("playing_sound" if entry_id in self.sound_intent else "playing_individual"),
        )
        self._signal_update()

    async def async_claim_sound(self, entry_id: str) -> None:
        """Give an integration sound absolute priority on exactly one hub."""
        member = self.members.get(entry_id)
        had_group_session = bool(
            member
            and (
                member.writer is not None
                or (self.desired_playing and member.state in ("playing_group", "waiting_for_sync"))
            )
        )
        self.sound_intent.add(entry_id)
        await self._detach_member(
            entry_id,
            stop_remote=had_group_session,
            new_state="playing_sound",
        )
        self._signal_update()

    async def async_release_sound(self, entry_id: str) -> None:
        """Release a priority sound and let the previous owner resume/rejoin."""
        self.sound_intent.discard(entry_id)
        member = self.members.get(entry_id)
        if member is not None:
            if entry_id in self.individual_intent:
                member.state = "playing_individual"
            elif member.selected:
                member.state = "waiting_for_sync" if self.desired_playing else "idle"
                member.last_prepare_attempt_monotonic = 0.0
                member.prepare_failures = 0
                member.next_prepare_monotonic = 0.0
        self._signal_update()
        if self.desired_playing:
            self._ensure_reconcile_task()

    def member_is_sound(self, entry_id: str) -> bool:
        return entry_id in self.sound_intent

    def mark_individual_intent(self, entry_id: str, active: bool) -> None:
        if active:
            self.individual_intent.add(entry_id)
            member = self.members.get(entry_id)
            if member and member.writer is None and entry_id not in self.sound_intent:
                member.state = "playing_individual"
        else:
            self.individual_intent.discard(entry_id)
            member = self.members.get(entry_id)
            if member and member.selected:
                member.state = "playing_sound" if entry_id in self.sound_intent else "waiting_for_sync"
                member.last_prepare_attempt_monotonic = 0.0
                member.prepare_failures = 0
                member.next_prepare_monotonic = 0.0
        self._signal_update()
        if self.desired_playing:
            self._ensure_reconcile_task()

    async def async_release_individual(self, entry_id: str) -> None:
        self.mark_individual_intent(entry_id, False)

    def member_is_individual(self, entry_id: str) -> bool:
        return entry_id in self.individual_intent

    def _member_online(self, member: GroupMember) -> bool:
        return bool(member.coordinator.last_update_success)

    def _eligible(self, member: GroupMember) -> bool:
        return (
            member.selected
            and member.entry_id not in self.individual_intent
            and member.entry_id not in self.sound_intent
            and self._member_online(member)
        )

    def _signal_update(self) -> None:
        async_dispatcher_send(self.hass, media_group_signal())

    @property
    def active_members(self) -> list[GroupMember]:
        return [
            m for m in self.members.values()
            if m.writer is not None and not m.detaching
        ]

    @property
    def ffmpeg_running(self) -> bool:
        return self.ffmpeg is not None and self.ffmpeg.returncode is None

    def group_state(self) -> MediaPlayerState:
        if not self.desired_playing:
            return MediaPlayerState.IDLE
        if self.ffmpeg_running and self.active_members:
            return MediaPlayerState.PLAYING
        return MediaPlayerState.BUFFERING

    def attributes(self) -> dict[str, Any]:
        by_state: dict[str, list[str]] = {}
        for member in self.members.values():
            by_state.setdefault(member.state, []).append(member.name)
        timestamp = None
        if self._stream_started_monotonic is not None:
            timestamp = round(self._sequence * CHUNK_SECONDS, 3)
        return {
            "transport": "clocked_shared_pcm_timeline",
            "architecture": "google_home_style_coordinator_independent_receivers",
            "stream_sequence": self._sequence,
            "stream_timestamp_seconds": timestamp,
            "sync_lead_seconds": SYNC_LEAD_SECONDS,
            "initial_preroll_seconds": INITIAL_PREROLL_SECONDS,
            "join_boundary_seconds": JOIN_BOUNDARY_SECONDS,
            "playout_clock_rebases": self._clock_rebase_count,
            "selected_hubs": sorted(m.name for m in self.members.values() if m.selected),
            "active_hubs": sorted(m.name for m in self.active_members),
            "waiting_for_sync": sorted(by_state.get("waiting_for_sync", [])),
            "join_at_timestamp_seconds": {
                member.name: round(member.join_at_sequence * CHUNK_SECONDS, 3)
                for member in self.members.values()
                if member.join_at_sequence is not None
            },
            "offline_hubs": sorted(by_state.get("offline", [])),
            "individual_hubs": sorted(by_state.get("playing_individual", [])),
            "priority_sound_hubs": sorted(by_state.get("playing_sound", [])),
            "excluded_hubs": sorted(by_state.get("excluded", [])),
            "last_failure": self._last_failure,
            "watchdog_restart_attempts": self._watchdog_attempts,
            "rejoin_sync_mode": "late_join_future_clock_boundary",
            "full_resync_count": self._full_resync_count,
            "last_full_resync_reason": self._last_full_resync_reason,
            "full_resync_retry_seconds": FULL_RESYNC_RETRY_SECONDS,
            "receiver_drift_guard_mode": "clock_paced_stream_no_periodic_global_resync",
            "receiver_resync_interval_seconds": PERIODIC_RECEIVER_RESYNC_SECONDS,
            "receiver_resync_count": self._receiver_resync_count,
            "last_receiver_resync_reason": self._last_receiver_resync_reason,
            "last_receiver_resync_age_seconds": (
                None
                if self._last_receiver_resync_monotonic is None
                else round(time.monotonic() - self._last_receiver_resync_monotonic, 1)
            ),
            "return_stabilize_seconds": RETURN_STABILIZE_SECONDS,
            "pcm_health_check_seconds": PCM_HEALTH_CHECK_SECONDS,
            "pcm_stall_timeout_seconds": PCM_STALL_TIMEOUT,
            "pcm_age_seconds": (
                round(time.monotonic() - self._last_pcm_monotonic, 3)
                if self._last_pcm_monotonic is not None
                else None
            ),
            "member_retry_backoff_seconds": {
                member.name: (
                    0.0
                    if member.next_prepare_monotonic <= time.monotonic()
                    else round(member.next_prepare_monotonic - time.monotonic(), 1)
                )
                for member in self.members.values()
                if member.writer is None and member.selected
            },
            "member_queue_depth_ms": {
                member.name: int(member.queue.qsize() * CHUNK_SECONDS * 1000)
                for member in self.active_members
                if member.queue is not None
            },
            "member_lag_age_seconds": {
                member.name: round(time.monotonic() - member.lag_since_monotonic, 3)
                for member in self.active_members
                if member.lag_since_monotonic is not None
            },
            "sync_policy": "clocked_timeline_isolate_member_late_rejoin_source_failure_only_global_restart",
            "queue_overflow_policy": "detach_only_slow_member",
            "writer_high_water_ms": int(WRITER_HIGH_WATER_BYTES / (PCM_RATE * PCM_CHANNELS * PCM_SAMPLE_BYTES) * 1000),
            "periodic_receiver_resync_enabled": PERIODIC_RECEIVER_RESYNC_ENABLED,
            "volume_apply_mode": "live_pcm_software_gain",
            "volume_stream_restart": False,
            "volume_apply_pending": False,
            "applied_volume_level": self._applied_volume,
            "applied_is_volume_muted": self._applied_muted,
            "volume_step_percent": 0.1,
            "gain_ramp_ms": int(GAIN_RAMP_SECONDS * 1000),
            "ffmpeg_nice_target": FFMPEG_NICE_TARGET,
            "ffmpeg_nice_applied": self._ffmpeg_nice_applied,
            "aplay_nice_target": APLAY_NICE_TARGET,
            "aplay_buffer_ms": int(APLAY_BUFFER_TIME_US / 1000),
            "aplay_period_ms": int(APLAY_PERIOD_TIME_US / 1000),
        }

    async def async_start(
        self,
        media_url: str,
        media_id: str,
        media_type: str,
        title: str | None,
    ) -> None:
        async with self._lock:
            self.media_url = media_url
            self.media_id = media_id
            self.media_type = media_type or MediaType.MUSIC
            self.media_title = title
            self.desired_playing = True
            self._watchdog_attempts = 0
            await self._restart_stream_locked(reason="user_play")
        self._ensure_reconcile_task()
        self._signal_update()

    async def async_resume(self) -> None:
        if not self.media_url:
            return
        self.desired_playing = True
        async with self._lock:
            if not self.ffmpeg_running:
                await self._restart_stream_locked(reason="resume")
        self._ensure_reconcile_task()
        self._signal_update()

    async def async_stop(self, *, clear_intent: bool = True) -> None:
        if clear_intent:
            self.desired_playing = False
        try:
            await asyncio.wait_for(self._cancel_background_recovery(), timeout=3.0)
        except Exception as err:
            _LOGGER.warning(
                "M1S group STOP recovery-task cleanup incomplete: %s", err
            )

        async def _normal_stop() -> None:
            async with self._lock:
                await self._stop_stream_locked(stop_members=True, reason="user_stop")

        try:
            await asyncio.wait_for(
                _normal_stop(), timeout=MANUAL_RESET_NORMAL_STOP_TIMEOUT
            )
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "M1S group normal STOP timed out; forcing transport reset"
            )
            await self.async_force_reset(reason="user_stop_timeout")
        self._signal_update()

    async def async_force_reset(self, *, reason: str = "manual_reset") -> None:
        """Hard-reset only the shared group audio transport.

        This is stronger than STOP and is safe to call when a queue-full /
        resynchronisation path leaves the group stuck.  It never touches the
        individual receiver on 12346 or the Zigbee UART bridge on 1886.
        """
        _LOGGER.warning("M1S group hard transport reset requested reason=%s", reason)

        # Disable every automatic restart path first.  The next user Play starts
        # a completely new timeline instead of inheriting a stuck recovery task.
        self.desired_playing = False
        self._watchdog_attempts = 0
        self._last_failure = reason
        self._last_full_resync_reason = reason
        self._broadcast_pause_requested.clear()
        self._broadcast_paused.clear()
        self._playout_epoch_monotonic = None
        self._generation += 1

        try:
            await asyncio.wait_for(self._cancel_background_recovery(), timeout=3.0)
        except Exception as err:
            _LOGGER.warning(
                "M1S group reset: recovery-task cleanup incomplete: %s", err
            )

        async def _normal_reset_stop() -> None:
            async with self._lock:
                await self._stop_stream_locked(
                    stop_members=True, reason=reason
                )

        normal_stopped = False
        try:
            await asyncio.wait_for(
                _normal_reset_stop(), timeout=MANUAL_RESET_NORMAL_STOP_TIMEOUT
            )
            normal_stopped = True
        except Exception as err:
            _LOGGER.warning(
                "M1S group reset: normal stop timed out/failed: %s", err
            )

        if not normal_stopped:
            # Emergency HA-side cleanup.  Do not await objects that may be the
            # reason the group is wedged.  Invalidate generations, cancel known
            # tasks, kill FFmpeg, and forget every queue/socket reference.
            current = asyncio.current_task()
            for attr in (
                "broadcast_task",
                "stderr_task",
                "stable_task",
                "health_task",
                "reconcile_task",
                "watchdog_task",
                "slow_retry_task",
                "resync_task",
                "periodic_receiver_resync_task",
            ):
                task = getattr(self, attr, None)
                setattr(self, attr, None)
                if task and task is not current and not task.done():
                    task.cancel()

            process = self.ffmpeg
            self.ffmpeg = None
            self._ffmpeg_nice_applied = False
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                with suppress(Exception):
                    await asyncio.wait_for(process.wait(), timeout=1.0)

            for member in list(self.members.values()):
                member.generation += 1
                prepare_task = member.prepare_task
                member.prepare_task = None
                if prepare_task and prepare_task is not current and not prepare_task.done():
                    prepare_task.cancel()
                task = member.writer_task
                member.writer_task = None
                if task and task is not current and not task.done():
                    task.cancel()
                queue = member.queue
                member.queue = None
                if queue is not None:
                    with suppress(asyncio.QueueFull):
                        queue.put_nowait(None)
                writer = member.writer
                member.writer = None
                member.join_at_sequence = None
                member.lag_since_monotonic = None
                member.lag_peak_chunks = 0
                if writer is not None:
                    with suppress(Exception):
                        writer.close()
                member.state = self._idle_member_state(member)

        # Always clean the remote GROUP receiver on every reachable member.
        # GROUP_STOP_COMMAND is scoped to port 12347 + group FIFO/PIDs only.
        async def _remote_cleanup(member: GroupMember) -> None:
            if not self._member_online(member):
                return
            try:
                await asyncio.wait_for(
                    self.hass.async_add_executor_job(
                        member.client.run_command, GROUP_STOP_COMMAND
                    ),
                    timeout=MANUAL_RESET_REMOTE_TIMEOUT,
                )
            except Exception as err:
                member.last_error = f"group reset cleanup: {err}"
                _LOGGER.warning(
                    "M1S group reset remote cleanup failed %s: %s",
                    member.name,
                    err,
                )

        await asyncio.gather(
            *(_remote_cleanup(member) for member in list(self.members.values())),
            return_exceptions=True,
        )

        self._sequence = 0
        self._stream_started_monotonic = None
        self._last_pcm_monotonic = None
        self._gain_ramp_remaining = 0
        for member in self.members.values():
            if member.writer is None:
                member.state = self._idle_member_state(member)
        self._signal_update()

    async def async_shutdown(self) -> None:
        self._shutting_down = True
        await self._cancel_background_recovery()
        async with self._lock:
            await self._stop_stream_locked(stop_members=True, reason="shutdown")

    async def async_set_volume(self, volume: float) -> None:
        """Apply group volume inside the running PCM broadcaster.

        The shared FFmpeg process and every hub receiver remain untouched.
        Only the software gain used for the next 20 ms PCM chunk changes, so
        slider movement cannot interrupt or resynchronise the stream.
        """
        normalized = self.normalize_volume(volume)
        self.volume = normalized
        self._applied_volume = normalized
        async_dispatcher_send(self.hass, media_group_volume_signal())
        self._signal_update()

    async def async_set_muted(self, muted: bool) -> None:
        """Mute or unmute through live PCM gain without restarting audio."""
        normalized = bool(muted)
        self.muted = normalized
        self._applied_muted = normalized
        self._signal_update()

    @staticmethod
    def normalize_volume(volume: float) -> float:
        """Quantize the complete 0-100% range in uniform 0.1% steps."""
        volume = max(0.0, min(1.0, float(volume)))
        quantized = round(volume / 0.001) * 0.001
        return max(0.0, min(1.0, round(quantized, 3)))

    def _effective_gain(self) -> float:
        if self._applied_muted:
            return 0.0
        return max(0.0, min(1.0, float(self._applied_volume)))

    def _reset_live_gain(self) -> None:
        target = self._effective_gain()
        self._gain_current = target
        self._gain_target = target
        self._gain_ramp_start = target
        self._gain_ramp_remaining = 0

    def _apply_live_pcm_gain(self, chunk: bytes) -> bytes:
        """Scale one common S32_LE chunk with a 40 ms anti-click ramp."""
        target = self._effective_gain()
        if target != self._gain_target:
            self._gain_ramp_start = self._gain_current
            self._gain_target = target
            self._gain_ramp_remaining = GAIN_RAMP_SAMPLES

        if self._gain_ramp_remaining <= 0:
            self._gain_current = target
            if target <= 0.0:
                return SILENCE_CHUNK
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

    async def _restart_stream_locked(self, reason: str) -> None:
        """Restart the shared SOURCE timeline, never because one member is slow.

        Member failures are handled by isolation + late rejoin.  A global restart
        is reserved for user Play/source/FFmpeg health failures.
        """
        await self._stop_stream_locked(stop_members=True, reason=reason)
        if not self.desired_playing or not self.media_url:
            return

        eligible = [m for m in self.members.values() if self._eligible(m)]
        prepare_tasks: list[asyncio.Task] = []
        for member in eligible:
            task = self._schedule_member_prepare(member, initial=True)
            if task is not None:
                prepare_tasks.append(task)

        # Google-Home-like startup policy: establish a small initial cohort, not
        # a hard all-members barrier.  Start as soon as one hub is ready, allow a
        # short grace window for other healthy hubs, and let the rest join later.
        pending = set(prepare_tasks)
        deadline = time.monotonic() + START_FIRST_MEMBER_TIMEOUT
        while pending and not self.active_members:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            done, pending = await asyncio.wait(
                pending,
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                break

        if self.active_members and pending:
            # Preparation continues independently during this tiny cohort window.
            await asyncio.sleep(START_COHORT_GRACE_SECONDS)

        if not self.active_members:
            self._last_failure = "no_group_member_ready"
            _LOGGER.warning(
                "M1S group Play has no ready receiver yet; keeping intent and "
                "retrying members in background"
            )
            return

        await self._start_ffmpeg_locked()

    async def _start_ffmpeg_locked(self) -> None:
        if not self.media_url or not self.desired_playing:
            return
        ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
        args = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "warning",
        ]
        if urlsplit(self.media_url).scheme.lower() in ("http", "https"):
            args.extend(
                [
                    "-reconnect",
                    "1",
                    "-reconnect_streamed",
                    "1",
                    "-reconnect_delay_max",
                    "5",
                ]
            )
        args.extend([
            "-i",
            self.media_url,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(PCM_RATE),
            "-c:a",
            "pcm_s32le",
            "-f",
            "s32le",
            "pipe:1",
        ])
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as err:
            self._last_failure = "ffmpeg_not_found"
            raise RuntimeError("FFmpeg was not found") from err

        self.ffmpeg = process
        self._ffmpeg_nice_applied = self._try_set_ffmpeg_priority(process.pid)
        self._applied_volume = self.volume
        self._applied_muted = self.muted
        self._reset_live_gain()
        self._generation += 1
        generation = self._generation
        self._sequence = 0
        self._stream_started_monotonic = time.monotonic()
        self._playout_epoch_monotonic = None
        self._last_pcm_monotonic = None
        for member in self.active_members:
            member.lag_since_monotonic = None
            member.lag_peak_chunks = 0
            # All initial receivers warm their local aplay pipeline with the same
            # scheduled silence before source audio begins.
            member.join_at_sequence = INITIAL_PREROLL_CHUNKS
            member.state = "waiting_for_sync"

        self.broadcast_task = self.hass.async_create_background_task(
            self._broadcast_loop(process, generation),
            "aqara_m1s_group_pcm_broadcast",
        )
        self.stderr_task = self.hass.async_create_background_task(
            self._stderr_loop(process, generation),
            "aqara_m1s_group_ffmpeg_stderr",
        )
        self.stable_task = self.hass.async_create_background_task(
            self._stable_watch(process, generation),
            "aqara_m1s_group_stable_watch",
        )
        self.health_task = self.hass.async_create_background_task(
            self._pcm_health_watch(process, generation),
            "aqara_m1s_group_pcm_health_watch",
        )
        _LOGGER.info(
            "M1S group FFmpeg started pid=%s source=%s members=%s",
            process.pid,
            self._safe_media_for_log(self.media_url),
            [m.name for m in self.active_members],
        )

    @staticmethod
    def _try_set_ffmpeg_priority(pid: int) -> bool:
        """Best-effort moderate CPU priority; never fail group playback."""
        try:
            os.setpriority(os.PRIO_PROCESS, pid, FFMPEG_NICE_TARGET)
            return os.getpriority(os.PRIO_PROCESS, pid) <= FFMPEG_NICE_TARGET
        except (AttributeError, OSError, PermissionError) as err:
            _LOGGER.debug(
                "Could not apply group FFmpeg nice=%s to pid=%s: %s",
                FFMPEG_NICE_TARGET,
                pid,
                err,
            )
            return False

    async def _stop_stream_locked(self, *, stop_members: bool, reason: str) -> None:
        self._broadcast_pause_requested.clear()
        self._broadcast_paused.clear()
        self._playout_epoch_monotonic = None
        self._generation += 1
        current = asyncio.current_task()
        broadcast_task = self.broadcast_task
        stderr_task = self.stderr_task
        self.broadcast_task = None
        self.stderr_task = None
        for attr in ("stable_task", "health_task"):
            task = getattr(self, attr)
            setattr(self, attr, None)
            if task and task is not current:
                await self._cancel_task(task)

        process = self.ffmpeg
        self.ffmpeg = None
        self._ffmpeg_nice_applied = False
        if process is not None and process.returncode is None:
            with suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(
                    process.wait(), timeout=GROUP_FFMPEG_TERMINATE_TIMEOUT
                )
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "M1S group FFmpeg terminate timeout while stdout drains "
                    "pid=%s reason=%s; killing process",
                    process.pid,
                    reason,
                )
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        process.wait(), timeout=GROUP_FFMPEG_KILL_TIMEOUT
                    )
                if process.returncode is None:
                    _LOGGER.warning(
                        "M1S group FFmpeg did not reap after kill pid=%s "
                        "reason=%s broadcaster_done=%s",
                        process.pid,
                        reason,
                        bool(broadcast_task and broadcast_task.done()),
                    )
        for task in (broadcast_task, stderr_task):
            if task and task is not current:
                if not task.done():
                    with suppress(asyncio.TimeoutError, asyncio.CancelledError):
                        await asyncio.wait_for(task, timeout=TASK_CANCEL_TIMEOUT)
                if not task.done():
                    await self._cancel_task(task)
        if stop_members:
            await asyncio.gather(
                *(
                    self._detach_member(
                        member.entry_id,
                        stop_remote=member.writer is not None,
                        new_state=self._idle_member_state(member),
                    )
                    for member in list(self.members.values())
                ),
                return_exceptions=True,
            )
        _LOGGER.info("M1S group stream stopped reason=%s", reason)

    def _idle_member_state(self, member: GroupMember) -> str:
        if not member.selected:
            return "excluded"
        if member.entry_id in self.sound_intent:
            return "playing_sound"
        if member.entry_id in self.individual_intent:
            return "playing_individual"
        if not self._member_online(member):
            return "offline"
        return "waiting_for_sync" if self.desired_playing else "idle"

    def _future_join_sequence(self) -> int:
        """Return a future global clock boundary for one late receiver."""
        target = self._sequence + SYNC_LEAD_CHUNKS
        boundary = JOIN_BOUNDARY_CHUNKS
        return ((target + boundary - 1) // boundary) * boundary

    def _set_member_retry(self, member: GroupMember, *, failed: bool) -> None:
        if not failed:
            member.prepare_failures = 0
            member.next_prepare_monotonic = 0.0
            return
        member.prepare_failures = min(member.prepare_failures + 1, 8)
        delay = min(
            MEMBER_RETRY_MAX_SECONDS,
            MEMBER_RETRY_BASE_SECONDS * (2 ** (member.prepare_failures - 1)),
        )
        member.next_prepare_monotonic = time.monotonic() + delay

    async def _pace_frame(self, sequence: int) -> None:
        """Pace every PCM frame from one HA monotonic playout clock.

        FFmpeg/network reads can arrive in bursts.  Without this clock, several
        20 ms frames may be dumped into TCP back-to-back and different hub socket
        buffers grow by different amounts.  Clock pacing keeps every receiver fed
        at the same cadence and rebases instead of doing a catch-up burst.
        """
        now = time.monotonic()
        if self._playout_epoch_monotonic is None:
            self._playout_epoch_monotonic = now + PLAYOUT_START_MARGIN_SECONDS

        deadline = self._playout_epoch_monotonic + (sequence * CHUNK_SECONDS)
        lag = now - deadline
        if lag > PLAYOUT_REBASE_THRESHOLD_SECONDS:
            self._playout_epoch_monotonic += lag + PLAYOUT_REBASE_MARGIN_SECONDS
            self._clock_rebase_count += 1
            deadline = self._playout_epoch_monotonic + (sequence * CHUNK_SECONDS)

        delay = deadline - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

    def _schedule_isolate_member(self, member: GroupMember, *, reason: str) -> None:
        if member.detaching:
            return
        member.detaching = True
        member.last_error = reason
        member.state = "waiting_for_sync"
        self._set_member_retry(member, failed=True)

        async def _runner() -> None:
            try:
                await self._detach_member(
                    member.entry_id,
                    stop_remote=False,
                    new_state=(
                        "offline" if not self._member_online(member)
                        else "waiting_for_sync"
                    ),
                )
                if self._member_online(member):
                    await self._remote_group_stop(member)
            finally:
                member.detaching = False
                self._signal_update()

        self.hass.async_create_background_task(
            _runner(), f"aqara_m1s_group_isolate_{member.entry_id}"
        )

    def _schedule_member_prepare(
        self, member: GroupMember, *, initial: bool
    ) -> asyncio.Task | None:
        """Prepare one receiver without allowing it to block healthy members."""
        existing = member.prepare_task
        if existing is not None and not existing.done():
            return existing

        async def _runner() -> bool:
            try:
                return await self._prepare_member(member, initial=initial)
            finally:
                if member.prepare_task is asyncio.current_task():
                    member.prepare_task = None

        task = self.hass.async_create_background_task(
            _runner(), f"aqara_m1s_group_prepare_{member.entry_id}"
        )
        member.prepare_task = task
        return task

    async def _prepare_member(self, member: GroupMember, *, initial: bool) -> bool:
        if not self._eligible(member) or member.writer is not None:
            return False
        member.last_prepare_attempt_monotonic = time.monotonic()
        member.generation += 1
        generation = member.generation
        try:
            await asyncio.wait_for(
                self.hass.async_add_executor_job(
                    member.client.run_command, GROUP_START_COMMAND
                ),
                timeout=MEMBER_REMOTE_START_TIMEOUT,
            )
            writer: asyncio.StreamWriter | None = None
            last_error: Exception | None = None
            for _ in range(MEMBER_CONNECT_ATTEMPTS):
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(member.client.host, GROUP_PORT),
                        timeout=MEMBER_CONNECT_TIMEOUT,
                    )
                    break
                except (OSError, asyncio.TimeoutError) as err:
                    last_error = err
                    await asyncio.sleep(MEMBER_CONNECT_RETRY_DELAY)
            if writer is None:
                raise ConnectionError(f"group receiver unavailable: {last_error}")

            sock = writer.get_extra_info("socket")
            if sock is not None:
                with suppress(OSError):
                    import socket
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    # Keep kernel buffering bounded so a stalled hub is noticed
                    # quickly instead of silently accumulating seconds of audio.
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_SNDBUF_BYTES)
            transport = getattr(writer, "transport", None)
            if transport is not None:
                with suppress(Exception):
                    transport.set_write_buffer_limits(
                        high=WRITER_HIGH_WATER_BYTES,
                        low=WRITER_LOW_WATER_BYTES,
                    )

            member.writer = writer
            member.queue = asyncio.Queue(maxsize=QUEUE_CHUNKS)
            member.detaching = False
            member.lag_since_monotonic = None
            member.lag_peak_chunks = 0
            member.join_at_sequence = (
                INITIAL_PREROLL_CHUNKS
                if not self.ffmpeg_running or self._sequence == 0
                else self._future_join_sequence()
            )
            member.state = "waiting_for_sync"
            member.last_error = None
            self._set_member_retry(member, failed=False)
            member.writer_task = self.hass.async_create_background_task(
                self._member_writer_loop(member, generation),
                f"aqara_m1s_group_writer_{member.entry_id}",
            )
            _LOGGER.info(
                "M1S group member prepared name=%s join_at_sequence=%s current=%s",
                member.name,
                member.join_at_sequence,
                self._sequence,
            )
            self._signal_update()
            return True
        except Exception as err:
            member.last_error = str(err)
            self._set_member_retry(member, failed=True)
            member.state = "offline" if not self._member_online(member) else "waiting_for_sync"
            _LOGGER.warning("M1S group skipped %s: %s", member.name, err)
            with suppress(Exception):
                await asyncio.wait_for(
                    self.hass.async_add_executor_job(
                        member.client.run_command, GROUP_STOP_COMMAND
                    ),
                    timeout=MEMBER_REMOTE_STOP_TIMEOUT,
                )
            self._signal_update()
            return False

    async def _member_writer_loop(self, member: GroupMember, generation: int) -> None:
        queue = member.queue
        writer = member.writer
        if queue is None or writer is None:
            return
        try:
            while member.generation == generation:
                chunk = await queue.get()
                if chunk is None:
                    return
                writer.write(chunk)
                await asyncio.wait_for(writer.drain(), timeout=WRITER_DRAIN_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            member.last_error = str(err)
            self._set_member_retry(member, failed=True)
            member.detaching = True
            _LOGGER.warning("M1S group member writer failed %s: %s", member.name, err)
        finally:
            if member.generation == generation:
                self.hass.async_create_task(
                    self._detach_member(
                        member.entry_id,
                        stop_remote=True,
                        new_state="offline" if not self._member_online(member) else "waiting_for_sync",
                    )
                )

    async def _detach_member(
        self, entry_id: str, *, stop_remote: bool, new_state: str
    ) -> None:
        member = self.members.get(entry_id)
        if member is None:
            return
        member.generation += 1
        prepare_task = member.prepare_task
        member.prepare_task = None
        task = member.writer_task
        member.writer_task = None
        queue = member.queue
        member.queue = None
        writer = member.writer
        member.writer = None
        member.join_at_sequence = None
        member.lag_since_monotonic = None
        member.lag_peak_chunks = 0
        if queue is not None:
            with suppress(asyncio.QueueFull):
                queue.put_nowait(None)
        if prepare_task and prepare_task is not asyncio.current_task():
            await self._cancel_task(prepare_task)
        if task and task is not asyncio.current_task():
            await self._cancel_task(task)
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await asyncio.wait_for(
                    writer.wait_closed(), timeout=WRITER_CLOSE_TIMEOUT
                )
        if stop_remote and self._member_online(member):
            with suppress(Exception):
                await asyncio.wait_for(
                    self.hass.async_add_executor_job(
                        member.client.run_command, GROUP_STOP_COMMAND
                    ),
                    timeout=MEMBER_REMOTE_STOP_TIMEOUT,
                )
        member.state = new_state
        member.detaching = False
        if new_state == "offline":
            # A real offline -> online transition gets a fresh short backoff when
            # the coordinator sees it return.
            member.last_prepare_attempt_monotonic = 0.0
        self._signal_update()

    async def _remote_group_stop(self, member: GroupMember) -> None:
        with suppress(Exception):
            await asyncio.wait_for(
                self.hass.async_add_executor_job(
                    member.client.run_command, GROUP_STOP_COMMAND
                ),
                timeout=MEMBER_REMOTE_STOP_TIMEOUT,
            )

    async def _fanout_frame(self, chunk: bytes, sequence: int) -> None:
        """Fan one clocked frame to every healthy receiver without blocking peers."""
        for member in list(self.active_members):
            queue = member.queue
            if queue is None:
                continue
            queue_depth = queue.qsize()
            member.lag_peak_chunks = max(member.lag_peak_chunks, queue_depth)

            outgoing = (
                SILENCE_CHUNK
                if member.join_at_sequence is not None
                and sequence < member.join_at_sequence
                else chunk
            )
            if (
                member.join_at_sequence is not None
                and sequence >= member.join_at_sequence
            ):
                member.join_at_sequence = None
                member.state = "playing_group"
                self._signal_update()

            try:
                queue.put_nowait(outgoing)
            except asyncio.QueueFull:
                _LOGGER.warning(
                    "M1S group isolating slow member after %.0f ms queue overflow: %s",
                    QUEUE_SECONDS * 1000,
                    member.name,
                )
                self._schedule_isolate_member(
                    member,
                    reason=(
                        f"PCM queue reached {int(QUEUE_SECONDS * 1000)} ms; "
                        "member isolated"
                    ),
                )

    async def _broadcast_loop(
        self, process: asyncio.subprocess.Process, generation: int
    ) -> None:
        if process.stdout is None:
            return
        buffer = bytearray()
        try:
            # Common receiver warm-up: same silence, same HA clock, no source
            # samples discarded.  This replaces the old 'throw away the first
            # N source chunks as silence' startup behaviour.
            for _ in range(INITIAL_PREROLL_CHUNKS):
                if generation != self._generation or not self.desired_playing:
                    break
                sequence = self._sequence
                await self._pace_frame(sequence)
                await self._fanout_frame(SILENCE_CHUNK, sequence)
                self._sequence += 1
                self._last_pcm_monotonic = time.monotonic()

            while not self._shutting_down:
                active_generation = generation == self._generation and self.desired_playing
                if active_generation and self._broadcast_pause_requested.is_set():
                    self._broadcast_paused.set()
                    try:
                        while (
                            self._broadcast_pause_requested.is_set()
                            and generation == self._generation
                            and self.desired_playing
                        ):
                            await asyncio.sleep(0.01)
                    finally:
                        self._broadcast_paused.clear()
                    if generation != self._generation or not self.desired_playing:
                        active_generation = False

                data = await process.stdout.read(32768)
                if not data:
                    break
                if not active_generation:
                    buffer.clear()
                    continue
                buffer.extend(data)
                while (
                    len(buffer) >= CHUNK_BYTES
                    and generation == self._generation
                    and self.desired_playing
                ):
                    raw_chunk = bytes(buffer[:CHUNK_BYTES])
                    del buffer[:CHUNK_BYTES]
                    chunk = self._apply_live_pcm_gain(raw_chunk)
                    sequence = self._sequence

                    # The HA clock, not FFmpeg pipe burst timing, decides when a
                    # frame is released to all receiver queues.
                    await self._pace_frame(sequence)
                    await self._fanout_frame(chunk, sequence)
                    self._sequence += 1
                    self._last_pcm_monotonic = time.monotonic()
                if generation != self._generation or not self.desired_playing:
                    buffer.clear()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._last_failure = str(err)
            _LOGGER.warning("M1S group broadcaster failed: %s", err)
        finally:
            if generation == self._generation and self.desired_playing:
                self._last_failure = self._last_failure or "ffmpeg_stream_ended"
                self._schedule_watchdog_restart()
                self._signal_update()

    async def _stderr_loop(
        self, process: asyncio.subprocess.Process, generation: int
    ) -> None:
        if process.stderr is None:
            return
        lines: list[str] = []
        try:
            while not self._shutting_down:
                line = await process.stderr.readline()
                if not line:
                    break
                if generation != self._generation:
                    continue
                text = line.decode(errors="replace").strip()
                if text:
                    lines.append(text)
                    lines = lines[-20:]
        except asyncio.CancelledError:
            raise
        finally:
            if process.returncode not in (None, 0) and lines:
                _LOGGER.warning("M1S group FFmpeg stderr: %s", " | ".join(lines))

    def _ensure_periodic_receiver_resync_task(self) -> None:
        """Keep long-running group playback from accumulating inter-hub drift."""
        if self._shutting_down or not self.desired_playing:
            return
        if (
            self.periodic_receiver_resync_task is None
            or self.periodic_receiver_resync_task.done()
        ):
            self.periodic_receiver_resync_task = self.hass.async_create_background_task(
                self._periodic_receiver_resync_loop(),
                "aqara_m1s_group_periodic_receiver_resync",
            )

    async def _periodic_receiver_resync_loop(self) -> None:
        """Periodically restart only hub receivers while preserving FFmpeg position."""
        try:
            while self.desired_playing and not self._shutting_down:
                await asyncio.sleep(5.0)
                if not self.desired_playing or not self.ffmpeg_running:
                    continue
                if len(self.active_members) < PERIODIC_RECEIVER_RESYNC_MIN_MEMBERS:
                    continue
                started = self._stream_started_monotonic
                if started is None:
                    continue
                if time.monotonic() - started < PERIODIC_RECEIVER_RESYNC_SECONDS:
                    continue
                async with self._lock:
                    if (
                        self.desired_playing
                        and self.ffmpeg_running
                        and len(self.active_members)
                        >= PERIODIC_RECEIVER_RESYNC_MIN_MEMBERS
                        and self._stream_started_monotonic is not None
                        and time.monotonic() - self._stream_started_monotonic
                        >= PERIODIC_RECEIVER_RESYNC_SECONDS
                    ):
                        await self._resync_receivers_preserve_source_locked(
                            reason="periodic_drift_guard"
                        )
                self._signal_update()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._last_failure = str(err)
            _LOGGER.warning("M1S periodic receiver resync failed: %s", err)
        finally:
            if self.periodic_receiver_resync_task is asyncio.current_task():
                self.periodic_receiver_resync_task = None

    async def _resync_receivers_preserve_source_locked(self, reason: str) -> None:
        """Pause PCM at a frame boundary, rebuild all receivers, then resume.

        FFmpeg is deliberately kept alive.  Its stdout back-pressure pauses the
        source while the hub-side nc/aplay pipelines are recreated, so finite
        media does not restart from the beginning and every receiver resumes
        from the same PCM position after the common silent lead-in.
        """
        if not self.ffmpeg_running or not self.desired_playing:
            return
        eligible = [m for m in self.members.values() if self._eligible(m)]
        if len(eligible) < PERIODIC_RECEIVER_RESYNC_MIN_MEMBERS:
            return

        self._broadcast_pause_requested.set()
        try:
            await asyncio.wait_for(
                self._broadcast_paused.wait(),
                timeout=PERIODIC_RECEIVER_RESYNC_PAUSE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            self._broadcast_pause_requested.clear()
            _LOGGER.warning(
                "M1S receiver resync could not pause broadcaster; using full restart"
            )
            await self._restart_stream_locked(reason=f"receiver_pause_timeout:{reason}")
            return

        try:
            active_ids = [m.entry_id for m in self.active_members]
            await asyncio.gather(
                *(
                    self._detach_member(
                        entry_id,
                        stop_remote=True,
                        new_state="waiting_for_sync",
                    )
                    for entry_id in active_ids
                ),
                return_exceptions=True,
            )
            active_members = [
                self.members[entry_id]
                for entry_id in active_ids
                if entry_id in self.members and self._eligible(self.members[entry_id])
            ]
            if active_members:
                await asyncio.gather(
                    *(
                        self._prepare_member(member, initial=False)
                        for member in active_members
                    ),
                    return_exceptions=True,
                )
            self._receiver_resync_count += 1
            self._last_receiver_resync_monotonic = time.monotonic()
            self._last_receiver_resync_reason = reason
            # Reset the interval without restarting FFmpeg or changing media position.
            self._stream_started_monotonic = time.monotonic()
            _LOGGER.info(
                "M1S group receivers resynchronised without restarting FFmpeg "
                "reason=%s active=%s",
                reason,
                [m.name for m in self.active_members],
            )
        finally:
            self._broadcast_pause_requested.clear()

    def _ensure_reconcile_task(self) -> None:
        if self._shutting_down:
            return
        if self.reconcile_task is None or self.reconcile_task.done():
            self.reconcile_task = self.hass.async_create_background_task(
                self._reconcile_loop(), "aqara_m1s_group_reconcile"
            )

    async def _reconcile_loop(self) -> None:
        """Continuously heal individual receivers without disturbing the group."""
        try:
            while self.desired_playing and not self._shutting_down:
                await asyncio.sleep(RECONCILE_SECONDS)
                if not self.desired_playing:
                    return

                now = time.monotonic()
                for member in self.members.values():
                    online = self._member_online(member)
                    if member.was_online is None:
                        member.was_online = online
                        member.online_since_monotonic = now if online else None
                    elif online and not member.was_online:
                        member.was_online = True
                        member.online_since_monotonic = now
                        member.last_prepare_attempt_monotonic = 0.0
                        member.prepare_failures = 0
                        member.next_prepare_monotonic = 0.0
                        member.state = "waiting_for_sync"
                        _LOGGER.info(
                            "M1S group member back online; short stabilization before "
                            "late clock join: %s",
                            member.name,
                        )
                    elif not online and member.was_online:
                        member.was_online = False
                        member.online_since_monotonic = None

                # Remove ineligible members independently.
                for member in list(self.members.values()):
                    if member.writer is not None and not self._eligible(member):
                        self._schedule_isolate_member(
                            member, reason="member no longer eligible"
                        )

                missing = [
                    member
                    for member in self.members.values()
                    if member.writer is None
                    and member.prepare_task is None
                    and self._eligible(member)
                    and not member.detaching
                ]
                due = [
                    member
                    for member in missing
                    if (
                        member.online_since_monotonic is None
                        or now - member.online_since_monotonic >= RETURN_STABILIZE_SECONDS
                    )
                    and now >= member.next_prepare_monotonic
                ]
                for member in due:
                    self._schedule_member_prepare(
                        member, initial=not self.ffmpeg_running
                    )

                # If Play was requested while every receiver was unavailable, start
                # the source automatically as soon as any background preparation
                # succeeds.  No global receiver teardown is performed.
                if not self.ffmpeg_running and self.active_members and self.media_url:
                    async with self._lock:
                        if (
                            self.desired_playing
                            and not self.ffmpeg_running
                            and self.active_members
                            and self.media_url
                        ):
                            await self._start_ffmpeg_locked()

                for member in self.members.values():
                    if member.writer is None and member.prepare_task is None:
                        member.state = self._idle_member_state(member)
                self._signal_update()
        except asyncio.CancelledError:
            raise
        finally:
            if self.reconcile_task is asyncio.current_task():
                self.reconcile_task = None

    def _schedule_full_resync(self, reason: str) -> None:
        """Legacy compatibility hook.  Member faults never restart the group."""
        _LOGGER.warning(
            "M1S group ignored legacy full-resync request reason=%s; "
            "receiver isolation policy is active",
            reason,
        )

    async def _pcm_health_watch(
        self, process: asyncio.subprocess.Process, generation: int
    ) -> None:
        """Treat PCM progress, not merely a live FFmpeg PID, as stream health."""
        try:
            while generation == self._generation and self.desired_playing:
                await asyncio.sleep(PCM_HEALTH_CHECK_SECONDS)
                if (
                    generation != self._generation
                    or self.ffmpeg is not process
                    or not self.desired_playing
                ):
                    return
                now = time.monotonic()
                if (
                    self._stream_started_monotonic is not None
                    and now - self._stream_started_monotonic < PCM_START_GRACE_SECONDS
                ):
                    continue
                pcm_age = (
                    None
                    if self._last_pcm_monotonic is None
                    else now - self._last_pcm_monotonic
                )
                if pcm_age is None or pcm_age >= PCM_STALL_TIMEOUT:
                    age_text = "never" if pcm_age is None else f"{pcm_age:.1f}s"
                    self._last_failure = f"pcm_stall:{age_text}"
                    _LOGGER.warning(
                        "M1S group PCM stalled while FFmpeg pid=%s is still alive; "
                        "forcing full restart (last PCM=%s)",
                        process.pid,
                        age_text,
                    )
                    async with self._lock:
                        if (
                            generation == self._generation
                            and self.ffmpeg is process
                            and self.desired_playing
                        ):
                            await self._restart_stream_locked(reason="pcm_stall")
                    self._ensure_reconcile_task()
                    self._signal_update()
                    return
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._last_failure = str(err)
            _LOGGER.warning("M1S group PCM health watchdog failed: %s", err)
            self._schedule_watchdog_restart()

    def _schedule_watchdog_restart(self) -> None:
        if self._shutting_down or not self.desired_playing or not self.media_url:
            return
        if self.watchdog_task and not self.watchdog_task.done():
            return
        if self._watchdog_attempts >= WATCHDOG_MAX_RESTARTS:
            self._schedule_slow_retry()
            return
        self.watchdog_task = self.hass.async_create_background_task(
            self._watchdog_restart(), "aqara_m1s_group_watchdog"
        )

    async def _watchdog_restart(self) -> None:
        try:
            await asyncio.sleep(WATCHDOG_RESTART_DELAY)
            if not self.desired_playing or self.ffmpeg_running or not self.media_url:
                return
            self._watchdog_attempts += 1
            _LOGGER.warning(
                "M1S group watchdog restart %s/%s last_failure=%s",
                self._watchdog_attempts,
                WATCHDOG_MAX_RESTARTS,
                self._last_failure or "unknown",
            )
            async with self._lock:
                await self._restart_stream_locked(reason="watchdog")
            self._ensure_reconcile_task()
            await asyncio.sleep(0.5)
            if self.desired_playing and not self.ffmpeg_running:
                self.watchdog_task = None
                self._schedule_watchdog_restart()
                return
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._last_failure = str(err)
            _LOGGER.warning("M1S group watchdog restart failed: %s", err)
            self.watchdog_task = None
            self._schedule_watchdog_restart()
        finally:
            if self.watchdog_task is asyncio.current_task():
                self.watchdog_task = None

    def _schedule_slow_retry(self) -> None:
        if self.slow_retry_task and not self.slow_retry_task.done():
            return
        self.slow_retry_task = self.hass.async_create_background_task(
            self._slow_retry(), "aqara_m1s_group_slow_retry"
        )

    async def _slow_retry(self) -> None:
        try:
            await asyncio.sleep(WATCHDOG_SLOW_RETRY_DELAY)
            if not self.desired_playing or self.ffmpeg_running or not self.media_url:
                return
            self._watchdog_attempts = 0
            async with self._lock:
                await self._restart_stream_locked(reason="slow_retry")
            self._ensure_reconcile_task()
            await asyncio.sleep(0.5)
            if self.desired_playing and not self.ffmpeg_running:
                self.slow_retry_task = None
                self._schedule_slow_retry()
                return
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._last_failure = str(err)
            self.slow_retry_task = None
            self._schedule_slow_retry()
        finally:
            if self.slow_retry_task is asyncio.current_task():
                self.slow_retry_task = None

    async def _stable_watch(
        self, process: asyncio.subprocess.Process, generation: int
    ) -> None:
        try:
            await asyncio.sleep(WATCHDOG_STABLE_SECONDS)
            now = time.monotonic()
            pcm_recent = (
                self._last_pcm_monotonic is not None
                and now - self._last_pcm_monotonic < PCM_HEALTH_CHECK_SECONDS * 2
            )
            if (
                generation == self._generation
                and self.ffmpeg is process
                and process.returncode is None
                and pcm_recent
                and bool(self.active_members)
            ):
                self._watchdog_attempts = 0
                self._last_failure = None
                if self.slow_retry_task:
                    await self._cancel_task(self.slow_retry_task)
                    self.slow_retry_task = None
                self._signal_update()
        except asyncio.CancelledError:
            raise

    async def _cancel_background_recovery(self) -> None:
        current = asyncio.current_task()
        for attr in (
            "reconcile_task",
            "watchdog_task",
            "slow_retry_task",
            "resync_task",
            "periodic_receiver_resync_task",
        ):
            task = getattr(self, attr)
            setattr(self, attr, None)
            if task and task is not current:
                await self._cancel_task(task)

    @staticmethod
    async def _cancel_task(task: asyncio.Task | None) -> None:
        if task is None or task is asyncio.current_task():
            return
        if not task.done():
            task.cancel()
        try:
            await asyncio.wait_for(task, timeout=TASK_CANCEL_TIMEOUT)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    @staticmethod
    def _safe_media_for_log(media_url: str | None) -> str:
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


class AqaraM1SMediaGroup(MediaPlayerEntity, RestoreEntity):
    """Single group entity backed by one HA-clocked multi-room PCM timeline."""

    _attr_name = "M1S Media Group"
    _attr_unique_id = "aqara_m1s_media_group"
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
        self.manager.entity = self
        self._attr_state = MediaPlayerState.IDLE
        self._attr_volume_level = manager.volume
        self._attr_is_volume_muted = manager.muted
        self._attr_media_content_type = MediaType.MUSIC
        self._resume_task: asyncio.Task | None = None

    @property
    def state(self) -> MediaPlayerState:
        return self.manager.group_state()

    @property
    def volume_level(self) -> float:
        return self.manager.volume

    @property
    def is_volume_muted(self) -> bool:
        return self.manager.muted

    @property
    def media_content_id(self) -> str | None:
        return self.manager.media_id

    @property
    def media_content_type(self) -> str:
        return self.manager.media_type

    @property
    def media_title(self) -> str | None:
        return self.manager.media_title

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            **self.manager.attributes(),
            "last_media_id": self.manager.media_id,
            "last_media_type": self.manager.media_type,
            "last_media_title": self.manager.media_title,
            "volume_level": self.manager.volume,
            "is_volume_muted": self.manager.muted,
            "resume_after_restart": self.manager.desired_playing,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            attrs = last.attributes
            self.manager.media_id = attrs.get("last_media_id") or attrs.get("media_content_id")
            self.manager.media_type = attrs.get("last_media_type") or MediaType.MUSIC
            self.manager.media_title = attrs.get("last_media_title") or attrs.get("media_title")
            with suppress(TypeError, ValueError):
                self.manager.volume = self.manager.normalize_volume(
                    float(attrs.get("volume_level", 0.05))
                )
            self.manager.muted = bool(attrs.get("is_volume_muted", False))
            self.manager.desired_playing = bool(
                attrs.get("resume_after_restart", last.state in (MediaPlayerState.PLAYING, MediaPlayerState.BUFFERING))
            )
            if self.manager.media_id and not media_source.is_media_source_id(self.manager.media_id):
                self.manager.media_url = async_process_play_media_url(
                    self.hass, self.manager.media_id, allow_relative_url=False
                )
            if self.manager.desired_playing and self.manager.media_id:
                self._resume_task = self.hass.async_create_background_task(
                    self._restore_after_startup(), "aqara_m1s_group_restore"
                )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, media_group_signal(), self._handle_group_update
            )
        )

    def _handle_group_update(self) -> None:
        self.schedule_update_ha_state()

    async def _restore_after_startup(self) -> None:
        try:
            await asyncio.sleep(15.0)
            if not self.manager.desired_playing or not self.manager.media_id:
                return
            if media_source.is_media_source_id(self.manager.media_id):
                resolved = await media_source.async_resolve_media(
                    self.hass, self.manager.media_id, self.entity_id
                )
                self.manager.media_url = async_process_play_media_url(
                    self.hass, resolved.url, allow_relative_url=False
                )
            if self.manager.media_url:
                await self.manager.async_resume()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.warning("Could not restore M1S media group: %s", err)
            self.manager._schedule_watchdog_restart()

    async def async_will_remove_from_hass(self) -> None:
        if self._resume_task:
            await self.manager._cancel_task(self._resume_task)
            self._resume_task = None
        self.manager.media_entity_added = False
        if self.manager.entity is self:
            self.manager.entity = None
        await super().async_will_remove_from_hass()

    async def async_browse_media(
        self, media_content_type: str | None = None, media_content_id: str | None = None
    ):
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        original = media_id
        resolved_id = media_id
        if media_source.is_media_source_id(media_id):
            resolved = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            resolved_id = resolved.url
        url = async_process_play_media_url(
            self.hass, resolved_id, allow_relative_url=False
        )
        extra = kwargs.get("extra") or {}
        title = extra.get("title") if isinstance(extra, dict) else None
        await self.manager.async_start(
            url, original, media_type or MediaType.MUSIC, title or "M1S group stream"
        )
        self.async_write_ha_state()

    async def async_media_play(self) -> None:
        if not self.manager.media_id:
            return
        if media_source.is_media_source_id(self.manager.media_id):
            resolved = await media_source.async_resolve_media(
                self.hass, self.manager.media_id, self.entity_id
            )
            self.manager.media_url = async_process_play_media_url(
                self.hass, resolved.url, allow_relative_url=False
            )
        await self.manager.async_resume()
        self.async_write_ha_state()

    async def async_media_stop(self) -> None:
        await self.manager.async_stop(clear_intent=True)
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        # Power/Off is the emergency-safe group-only reset path.
        await self.manager.async_force_reset(reason="user_turn_off")
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float) -> None:
        await self.manager.async_set_volume(volume)
        self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        current = self.manager.volume
        await self.async_set_volume_level(current + 0.001)

    async def async_volume_down(self) -> None:
        current = self.manager.volume
        await self.async_set_volume_level(current - 0.001)

    async def async_mute_volume(self, mute: bool) -> None:
        await self.manager.async_set_muted(mute)
        self.async_write_ha_state()
