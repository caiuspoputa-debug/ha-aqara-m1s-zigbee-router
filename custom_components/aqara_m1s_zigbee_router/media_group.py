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
# Stable-master multi-room transport. Every Play still creates one fixed cohort
# (preserving the good phase alignment from 0.7.x), but source timing is now
# decoupled through one bounded jitter buffer and one monotonic playout clock.
# A transient backlog trims stale PCM instead of ejecting the hub.
SYNC_LEAD_SECONDS = 0.0  # compatibility attribute; late join is intentionally disabled
SYNC_LEAD_CHUNKS = 0
JOIN_BOUNDARY_SECONDS = 0.0
JOIN_BOUNDARY_CHUNKS = 1
INITIAL_PREROLL_SECONDS = 0.50
INITIAL_PREROLL_CHUNKS = max(1, round(INITIAL_PREROLL_SECONDS / CHUNK_SECONDS))
START_COHORT_GRACE_SECONDS = 3.0
START_FIRST_MEMBER_TIMEOUT = START_COHORT_GRACE_SECONDS
PLAYOUT_START_MARGIN_SECONDS = 0.0
PLAYOUT_REBASE_THRESHOLD_SECONDS = 0.0
PLAYOUT_REBASE_MARGIN_SECONDS = 0.0
# v0.8 transport: one bounded master jitter buffer feeds one 20 ms playout
# clock. Source bursts/reconnect catch-up can no longer flood per-hub queues.
MASTER_BUFFER_SECONDS = 8.0
MASTER_BUFFER_CHUNKS = int(MASTER_BUFFER_SECONDS / CHUNK_SECONDS)
MASTER_PREBUFFER_SECONDS = 4.0
MASTER_PREBUFFER_CHUNKS = int(MASTER_PREBUFFER_SECONDS / CHUNK_SECONDS)
MASTER_MIN_START_SECONDS = 1.0
MASTER_MIN_START_CHUNKS = int(MASTER_MIN_START_SECONDS / CHUNK_SECONDS)
MASTER_PREBUFFER_MAX_WAIT = 8.0
PLAYOUT_LATE_REBASE_SECONDS = 0.12
QUEUE_SECONDS = 1.0
QUEUE_CHUNKS = int(QUEUE_SECONDS / CHUNK_SECONDS)
MEMBER_CATCHUP_THRESHOLD_CHUNKS = int(0.30 / CHUNK_SECONDS)
MEMBER_CATCHUP_TARGET_CHUNKS = int(0.06 / CHUNK_SECONDS)
WARMUP_MAX_BACKLOG_CHUNKS = 3  # <=60 ms queued after 500 ms warm-up
RECONCILE_SECONDS = 2.0
RETURN_STABILIZE_SECONDS = 0.0
MEMBER_RETRY_BASE_SECONDS = 0.0
MEMBER_RETRY_MAX_SECONDS = 0.0
PCM_HEALTH_CHECK_SECONDS = 2.0
PCM_STALL_TIMEOUT = 12.0
PCM_START_GRACE_SECONDS = 8.0
WRITER_DRAIN_TIMEOUT = 5.0
WRITER_HIGH_WATER_BYTES = CHUNK_BYTES * 16
WRITER_LOW_WATER_BYTES = CHUNK_BYTES * 4
SOCKET_SNDBUF_BYTES = CHUNK_BYTES * 16
SOURCE_RESTART_DELAY = 1.0
WATCHDOG_RESTART_DELAY = 4.0
WATCHDOG_MAX_RESTARTS = 1
WATCHDOG_SLOW_RETRY_DELAY = 60.0
WATCHDOG_STABLE_SECONDS = 30.0
FULL_RESYNC_RETRY_SECONDS = 0.0
FULL_RESYNC_HARD_TIMEOUT = 20.0
MANUAL_RESET_NORMAL_STOP_TIMEOUT = 6.0
MANUAL_RESET_REMOTE_TIMEOUT = 3.0
MEMBER_REMOTE_START_TIMEOUT = 8.0  # informational; run_command owns its socket timeout
MEMBER_REMOTE_STOP_TIMEOUT = 8.0
MEMBER_CONNECT_ATTEMPTS = 10
MEMBER_CONNECT_TIMEOUT = 0.50
MEMBER_CONNECT_RETRY_DELAY = 0.10
WRITER_CLOSE_TIMEOUT = 0.75
TASK_CANCEL_TIMEOUT = 1.0
# Diagnostic-only thresholds. These DO NOT change buffering, timing, cohort
# membership, writer limits, or any synchronisation behavior.
PCM_DIAG_SOURCE_GAP_WARN_MS = 80.0
PCM_DIAG_MEMBER_FEED_GAP_WARN_MS = 80.0
PCM_DIAG_DRAIN_WARN_MS = 80.0
PCM_DIAG_EVENT_LOOP_INTERVAL_SECONDS = 0.10
PCM_DIAG_EVENT_LOOP_WARN_MS = 100.0
PCM_DIAG_EVENT_HISTORY = 16
# Transport liveness guards. These do not change cohort timing/synchronisation.
NO_ACTIVE_MEMBERS_TIMEOUT = 8.0
USER_PLAY_HARD_TIMEOUT = 14.0
WATCHDOG_RESTART_HARD_TIMEOUT = 14.0
PERIODIC_RECEIVER_RESYNC_ENABLED = False
PERIODIC_RECEIVER_RESYNC_SECONDS = 10 * 60.0
PERIODIC_RECEIVER_RESYNC_MIN_MEMBERS = 2
PERIODIC_RECEIVER_RESYNC_PAUSE_TIMEOUT = 2.0
GAIN_RAMP_SECONDS = 0.04
GAIN_RAMP_SAMPLES = max(1, int(PCM_RATE * GAIN_RAMP_SECONDS))
FFMPEG_NICE_TARGET = -5
APLAY_NICE_TARGET = -3

SILENCE_CHUNK = b"\x00" * CHUNK_BYTES

GROUP_STOP_COMMAND = (
    f"for f in {GROUP_NC_PID} {GROUP_APLAY_PID}; do "
    '[ -f "$f" ] && kill -9 "$(cat "$f")" 2>/dev/null; '
    "done; "
    # Fallback cleanup only for an nc whose stdout is our group FIFO.  The
    # integration sound source also listens on 12347 but writes to /dev/null;
    # this test deliberately leaves that process alone.
    f"for p in $(ps w | grep '[n]c -l -p {GROUP_PORT}' | awk '{{print $1}}'); do "
    f'[ "$(readlink /proc/$p/fd/1 2>/dev/null)" = "{GROUP_FIFO}" ] && '
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
    + f'aplay -t raw -f S32_LE -c 1 -r {PCM_RATE} {GROUP_FIFO} </dev/null '
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
    diag_last_feed_monotonic: float | None = None
    diag_feed_gap_max_ms: float = 0.0
    diag_feed_gap_count: int = 0
    diag_drain_max_ms: float = 0.0
    diag_slow_drain_count: int = 0
    diag_queue_peak_chunks: int = 0
    diag_stale_drop_chunks: int = 0
    diag_last_log_monotonic: float = 0.0


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
        self.source_task: asyncio.Task | None = None
        self.source_restart_task: asyncio.Task | None = None
        self.broadcast_task: asyncio.Task | None = None
        self.stderr_task: asyncio.Task | None = None
        self.source_queue: asyncio.Queue[bytes] | None = None
        self.reconcile_task: asyncio.Task | None = None
        self.watchdog_task: asyncio.Task | None = None
        self.stable_task: asyncio.Task | None = None
        self.health_task: asyncio.Task | None = None
        self.diag_task: asyncio.Task | None = None
        self.resync_task: asyncio.Task | None = None
        self.periodic_receiver_resync_task: asyncio.Task | None = None
        self.slow_retry_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._generation = 0
        self._source_serial = 0
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
        self._accept_initial_prepares = False
        self._sound_group_resume: set[str] = set()
        self._sound_return_restart_task: asyncio.Task | None = None
        self._no_active_since_monotonic: float | None = None
        self._transport_self_heal_count = 0
        self._source_restart_count = 0
        self._master_silence_frames = 0
        self._master_prebuffer_started_monotonic: float | None = None
        self._master_audio_started = False
        self._diag_source_gap_max_ms = 0.0
        self._diag_source_gap_count = 0
        self._diag_event_loop_lag_max_ms = 0.0
        self._diag_event_loop_lag_count = 0
        self._diag_events: list[str] = []
        self._browse_title_cache: dict[str, str] = {}
        self._source_lock = asyncio.Lock()

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
        self._sound_group_resume.discard(entry_id)
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
        had_group_session = bool(member and member.writer is not None)
        if had_group_session:
            self._sound_group_resume.add(entry_id)
        self.sound_intent.add(entry_id)
        await self._detach_member(
            entry_id,
            stop_remote=had_group_session,
            new_state="playing_sound",
        )
        self._signal_update()

    async def async_release_sound(self, entry_id: str) -> None:
        """Release sound focus; resynchronise the fixed cohort if needed."""
        resume_group = entry_id in self._sound_group_resume
        self._sound_group_resume.discard(entry_id)
        self.sound_intent.discard(entry_id)
        member = self.members.get(entry_id)
        if member is not None:
            if entry_id in self.individual_intent:
                member.state = "playing_individual"
            elif member.selected:
                member.state = "waiting_for_next_cohort" if self.desired_playing else "idle"
        self._signal_update()
        if resume_group and self.desired_playing and self.media_url:
            self._schedule_restart_after_priority_sound()

    def _schedule_restart_after_priority_sound(self) -> None:
        """One controlled restart restores the interrupted hub in sync."""
        task = self._sound_return_restart_task
        if task is not None and not task.done():
            return

        async def _runner() -> None:
            try:
                await asyncio.sleep(0.25)
                async with self._lock:
                    if self.desired_playing and self.media_url:
                        await self._restart_stream_locked(
                            reason="priority_sound_return"
                        )
                self._signal_update()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self._last_failure = f"priority_sound_return:{err}"
                _LOGGER.warning(
                    "M1S group could not rebuild cohort after priority sound: %s", err
                )
            finally:
                if self._sound_return_restart_task is asyncio.current_task():
                    self._sound_return_restart_task = None

        self._sound_return_restart_task = self.hass.async_create_background_task(
            _runner(), "aqara_m1s_group_priority_sound_return"
        )

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
        if self.active_members and self.broadcast_task is not None and not self.broadcast_task.done():
            return MediaPlayerState.PLAYING if self._master_audio_started else MediaPlayerState.BUFFERING
        return MediaPlayerState.BUFFERING

    def attributes(self) -> dict[str, Any]:
        by_state: dict[str, list[str]] = {}
        for member in self.members.values():
            by_state.setdefault(member.state, []).append(member.name)
        timestamp = None
        if self._stream_started_monotonic is not None:
            timestamp = round(self._sequence * CHUNK_SECONDS, 3)
        return {
            "transport": "stable_master_buffer_pcm",
            "architecture": "shared_source_jitter_buffer_paced_fixed_cohort",
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
            "rejoin_sync_mode": "hard_disconnect_waits_for_next_play; priority_sound_rebuild_preserved",
            "full_resync_count": self._full_resync_count,
            "last_full_resync_reason": self._last_full_resync_reason,
            "full_resync_retry_seconds": FULL_RESYNC_RETRY_SECONDS,
            "receiver_drift_guard_mode": "fixed_cohort_no_periodic_resync",
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
            "no_active_members_timeout_seconds": NO_ACTIVE_MEMBERS_TIMEOUT,
            "no_active_members_age_seconds": (
                None
                if self._no_active_since_monotonic is None
                else round(time.monotonic() - self._no_active_since_monotonic, 1)
            ),
            "transport_self_heal_count": self._transport_self_heal_count,
            "source_restart_count": self._source_restart_count,
            "master_buffer_target_seconds": MASTER_PREBUFFER_SECONDS,
            "master_buffer_max_seconds": MASTER_BUFFER_SECONDS,
            "master_buffer_depth_ms": (
                int(self.source_queue.qsize() * CHUNK_SECONDS * 1000)
                if self.source_queue is not None else 0
            ),
            "master_audio_started": self._master_audio_started,
            "master_silence_inserted_ms": int(self._master_silence_frames * CHUNK_SECONDS * 1000),
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
            "pcm_diag_source_gap_max_ms": round(self._diag_source_gap_max_ms, 1),
            "pcm_diag_source_gap_count": self._diag_source_gap_count,
            "pcm_diag_event_loop_lag_max_ms": round(self._diag_event_loop_lag_max_ms, 1),
            "pcm_diag_event_loop_lag_count": self._diag_event_loop_lag_count,
            "pcm_diag_member_feed_gap_max_ms": {
                member.name: round(member.diag_feed_gap_max_ms, 1)
                for member in self.members.values()
                if member.diag_feed_gap_max_ms > 0
            },
            "pcm_diag_member_feed_gap_count": {
                member.name: member.diag_feed_gap_count
                for member in self.members.values()
                if member.diag_feed_gap_count > 0
            },
            "pcm_diag_member_drain_max_ms": {
                member.name: round(member.diag_drain_max_ms, 1)
                for member in self.members.values()
                if member.diag_drain_max_ms > 0
            },
            "pcm_diag_member_slow_drain_count": {
                member.name: member.diag_slow_drain_count
                for member in self.members.values()
                if member.diag_slow_drain_count > 0
            },
            "pcm_diag_member_queue_peak_ms": {
                member.name: int(member.diag_queue_peak_chunks * CHUNK_SECONDS * 1000)
                for member in self.members.values()
                if member.diag_queue_peak_chunks > 0
            },
            "pcm_diag_member_stale_drop_ms": {
                member.name: int(member.diag_stale_drop_chunks * CHUNK_SECONDS * 1000)
                for member in self.members.values()
                if member.diag_stale_drop_chunks > 0
            },
            "pcm_diag_last_events": list(self._diag_events),
            "sync_policy": "fixed_cohort_paced_playout_drop_stale_not_member",
            "queue_overflow_policy": "drop_stale_frames_keep_member",
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
        }

    def _diag_record(self, kind: str, detail: str, *, warning: bool = True) -> None:
        """Keep a short in-entity history and emit one HA log line per anomaly."""
        event = f"{time.strftime('%H:%M:%S')} {kind} {detail}"
        self._diag_events.append(event)
        if len(self._diag_events) > PCM_DIAG_EVENT_HISTORY:
            del self._diag_events[:-PCM_DIAG_EVENT_HISTORY]
        if warning:
            _LOGGER.warning("M1S PCM DIAG %s %s", kind, detail)
        else:
            _LOGGER.info("M1S PCM DIAG %s %s", kind, detail)
        self._signal_update()

    async def _diagnostic_event_loop_watch(self, generation: int) -> None:
        """Measure HA event-loop scheduling stalls without touching audio timing."""
        last = time.monotonic()
        try:
            while generation == self._generation and self.desired_playing:
                await asyncio.sleep(PCM_DIAG_EVENT_LOOP_INTERVAL_SECONDS)
                now = time.monotonic()
                lag_ms = max(
                    0.0,
                    (now - last - PCM_DIAG_EVENT_LOOP_INTERVAL_SECONDS) * 1000.0,
                )
                last = now
                self._diag_event_loop_lag_max_ms = max(
                    self._diag_event_loop_lag_max_ms, lag_ms
                )
                if lag_ms >= PCM_DIAG_EVENT_LOOP_WARN_MS:
                    self._diag_event_loop_lag_count += 1
                    self._diag_record(
                        "event_loop_lag",
                        f"lag={lag_ms:.1f}ms sequence={self._sequence}",
                    )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.debug("M1S PCM diagnostic heartbeat failed: %s", err)
        finally:
            if self.diag_task is asyncio.current_task():
                self.diag_task = None

    async def _bounded_restart(self, *, reason: str, allow_hard_reset_retry: bool) -> bool:
        """Restart the transport with a hard deadline so HA controls never wedge."""

        async def _run() -> None:
            async with self._lock:
                await self._restart_stream_locked(reason=reason)

        try:
            await asyncio.wait_for(_run(), timeout=USER_PLAY_HARD_TIMEOUT)
            return True
        except asyncio.TimeoutError:
            self._last_failure = f"{reason}_timeout"
            _LOGGER.error(
                "M1S group %s exceeded %.1fs; hard-resetting transport",
                reason,
                USER_PLAY_HARD_TIMEOUT,
            )

        await self.async_force_reset(reason=f"{reason}_timeout")
        if not allow_hard_reset_retry or not self.media_url:
            return False

        # The hard reset deliberately clears desired_playing. Restore the user's
        # intent and attempt one clean bounded start. A second timeout returns the
        # entity to IDLE instead of leaving it buffering indefinitely.
        self.desired_playing = True
        try:
            await asyncio.wait_for(_run(), timeout=USER_PLAY_HARD_TIMEOUT)
            self._transport_self_heal_count += 1
            return True
        except asyncio.TimeoutError:
            self._last_failure = f"{reason}_retry_timeout"
            _LOGGER.error(
                "M1S group %s retry also exceeded %.1fs; returning to idle",
                reason,
                USER_PLAY_HARD_TIMEOUT,
            )
            await self.async_force_reset(reason=f"{reason}_retry_timeout")
            return False

    async def async_start(
        self,
        media_url: str,
        media_id: str,
        media_type: str,
        title: str | None,
    ) -> None:
        self.media_url = media_url
        self.media_id = media_id
        self.media_type = media_type or MediaType.MUSIC
        self.media_title = title
        self.desired_playing = True
        self._watchdog_attempts = 0
        self._no_active_since_monotonic = None
        await self._bounded_restart(reason="user_play", allow_hard_reset_retry=True)
        if self.desired_playing:
            self._ensure_reconcile_task()
        self._signal_update()

    async def async_resume(self) -> None:
        if not self.media_url:
            return
        self.desired_playing = True
        self._no_active_since_monotonic = None
        if not self.ffmpeg_running:
            await self._bounded_restart(reason="resume", allow_hard_reset_retry=True)
        if self.desired_playing:
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
        self._no_active_since_monotonic = None
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
                "source_task",
                "source_restart_task",
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
            self.source_queue = None
            self._master_audio_started = False
            self._master_prebuffer_started_monotonic = None
            self.ffmpeg = None
            self._ffmpeg_nice_applied = False
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                with suppress(Exception):
                    await asyncio.wait_for(process.wait(), timeout=1.0)

            for member in list(self.members.values()):
                member.generation += 1
                # Do not cancel a prepare task blocked in a Telnet executor; its
                # generation is invalidated above and it will self-clean on return.
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
        """Build one fixed receiver cohort and then start one shared source.

        There is intentionally no late join.  A hub that cannot become ready in
        this startup window stays out until the next Play (or a controlled
        priority-sound rebuild).  This trades clever recovery for deterministic
        phase alignment and prevents one bad hub from churning the whole group.
        """
        await self._stop_stream_locked(stop_members=True, reason=reason)
        if not self.desired_playing or not self.media_url:
            return

        eligible = [m for m in self.members.values() if self._eligible(m)]
        self._accept_initial_prepares = True
        prepare_tasks: list[asyncio.Task] = []
        for member in eligible:
            task = self._schedule_member_prepare(member, initial=True)
            if task is not None:
                prepare_tasks.append(task)

        if prepare_tasks:
            # asyncio.wait does NOT cancel slow Telnet executor jobs.  They are
            # allowed to finish, notice that the cohort window closed, and clean
            # up their own receiver instead of racing a newer session.
            await asyncio.wait(
                prepare_tasks, timeout=START_COHORT_GRACE_SECONDS
            )
        self._accept_initial_prepares = False

        if not self.active_members:
            self._last_failure = "no_group_member_ready"
            self.desired_playing = False
            _LOGGER.warning(
                "M1S group Play aborted: no receiver joined the %.1fs startup cohort",
                START_COHORT_GRACE_SECONDS,
            )
            return

        await self._warmup_cohort_locked()
        if not self.active_members:
            self._last_failure = "cohort_failed_warmup"
            self.desired_playing = False
            return

        await self._start_ffmpeg_locked()

    async def _warmup_cohort_locked(self) -> None:
        """Prime identical hub-side ALSA pipelines with paced silence."""
        for member in self.active_members:
            member.state = "warming_up"
            member.join_at_sequence = None

        for _ in range(INITIAL_PREROLL_CHUNKS):
            for member in list(self.active_members):
                queue = member.queue
                if queue is None:
                    continue
                try:
                    queue.put_nowait(SILENCE_CHUNK)
                except asyncio.QueueFull:
                    self._schedule_isolate_member(
                        member, reason="warmup_queue_full"
                    )
            await asyncio.sleep(CHUNK_SECONDS)

        # A receiver that still has more than ~60 ms waiting after a full 500 ms
        # warm-up is already behind before music starts.  Exclude it now rather
        # than creating an audible echo for the whole session.
        for member in list(self.active_members):
            queue = member.queue
            if queue is not None and queue.qsize() > WARMUP_MAX_BACKLOG_CHUNKS:
                _LOGGER.warning(
                    "M1S group excluding member before source start; warm-up backlog=%sms name=%s",
                    int(queue.qsize() * CHUNK_SECONDS * 1000),
                    member.name,
                )
                self._schedule_isolate_member(
                    member, reason="warmup_backlog"
                )
        await asyncio.sleep(0.08)

    async def _start_ffmpeg_locked(self) -> None:
        """Start the resilient master transport and its first source process.

        Receivers are already synchronised by the common warm-up.  From here on
        one HA playout clock sends exactly one 20 ms frame per tick.  FFmpeg may
        burst or pause; those variations are absorbed by source_queue instead of
        being copied into every member queue.
        """
        if not self.media_url or not self.desired_playing or not self.active_members:
            return

        self._generation += 1
        generation = self._generation
        self._sequence = 0
        self._stream_started_monotonic = time.monotonic()
        self._playout_epoch_monotonic = None
        self._last_pcm_monotonic = None
        self._no_active_since_monotonic = None
        self._diag_source_gap_max_ms = 0.0
        self._diag_source_gap_count = 0
        self._diag_event_loop_lag_max_ms = 0.0
        self._diag_event_loop_lag_count = 0
        self._diag_events.clear()
        self._master_silence_frames = 0
        self._master_audio_started = False
        self._master_prebuffer_started_monotonic = time.monotonic()
        self.source_queue = asyncio.Queue(maxsize=MASTER_BUFFER_CHUNKS)
        self._applied_volume = self.volume
        self._applied_muted = self.muted
        self._reset_live_gain()

        for member in self.active_members:
            member.join_at_sequence = None
            member.state = "playing_group"
            member.diag_last_feed_monotonic = None
            member.diag_feed_gap_max_ms = 0.0
            member.diag_feed_gap_count = 0
            member.diag_drain_max_ms = 0.0
            member.diag_slow_drain_count = 0
            member.diag_queue_peak_chunks = 0
            member.diag_stale_drop_chunks = 0
            member.diag_last_log_monotonic = 0.0

        self.broadcast_task = self.hass.async_create_background_task(
            self._broadcast_loop(generation),
            "aqara_m1s_group_master_playout",
        )
        self.health_task = self.hass.async_create_background_task(
            self._pcm_health_watch(generation),
            "aqara_m1s_group_pcm_health_watch",
        )
        self.diag_task = self.hass.async_create_background_task(
            self._diagnostic_event_loop_watch(generation),
            "aqara_m1s_group_pcm_diag_heartbeat",
        )
        await self._start_source_only(generation, reason="initial")
        _LOGGER.info(
            "M1S master-buffer transport started source=%s members=%s prebuffer=%.1fs",
            self._safe_media_for_log(self.media_url),
            [m.name for m in self.active_members],
            MASTER_PREBUFFER_SECONDS,
        )

    async def _start_source_only(self, generation: int, *, reason: str) -> bool:
        """(Re)start FFmpeg without touching receivers or the playout clock."""
        if generation != self._generation or not self.desired_playing or not self.media_url:
            return False
        async with self._source_lock:
            if generation != self._generation or not self.desired_playing or not self.media_url:
                return False

            old_task = self.source_task
            self.source_task = None
            if old_task and old_task is not asyncio.current_task():
                await self._cancel_task(old_task)
            old_stderr = self.stderr_task
            self.stderr_task = None
            if old_stderr and old_stderr is not asyncio.current_task():
                await self._cancel_task(old_stderr)
            old_stable = self.stable_task
            self.stable_task = None
            if old_stable and old_stable is not asyncio.current_task():
                await self._cancel_task(old_stable)
            process = self.ffmpeg
            self.ffmpeg = None
            self._ffmpeg_nice_applied = False
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.terminate()
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=1.5)
                if process.returncode is None:
                    with suppress(ProcessLookupError):
                        process.kill()

            ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
            args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning"]
            if urlsplit(self.media_url).scheme.lower() in ("http", "https"):
                args.extend([
                    "-reconnect", "1",
                    "-reconnect_streamed", "1",
                    "-reconnect_delay_max", "5",
                ])
            # Intentionally no -re. The bounded source queue can read ahead and
            # our own monotonic playout clock is the only timing authority.
            args.extend([
                "-i", self.media_url, "-vn", "-ac", "1", "-ar", str(PCM_RATE),
                "-c:a", "pcm_s32le", "-f", "s32le", "pipe:1",
            ])
            try:
                process = await asyncio.create_subprocess_exec(
                    *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
            except FileNotFoundError as err:
                self._last_failure = "ffmpeg_not_found"
                raise RuntimeError("FFmpeg was not found") from err

            self.ffmpeg = process
            self._ffmpeg_nice_applied = self._try_set_ffmpeg_priority(process.pid)
            self._source_serial += 1
            serial = self._source_serial
            self.source_task = self.hass.async_create_background_task(
                self._source_reader_loop(process, generation, serial),
                "aqara_m1s_group_source_reader",
            )
            self.stderr_task = self.hass.async_create_background_task(
                self._stderr_loop(process, generation, serial),
                "aqara_m1s_group_ffmpeg_stderr",
            )
            self.stable_task = self.hass.async_create_background_task(
                self._stable_watch(process, generation),
                "aqara_m1s_group_stable_watch",
            )
            _LOGGER.info(
                "M1S group source started pid=%s reason=%s source=%s",
                process.pid, reason, self._safe_media_for_log(self.media_url),
            )
            return True

    async def _source_reader_loop(
        self, process: asyncio.subprocess.Process, generation: int, serial: int
    ) -> None:
        queue = self.source_queue
        if process.stdout is None or queue is None:
            return
        last_read: float | None = None
        try:
            while (
                generation == self._generation
                and serial == self._source_serial
                and self.desired_playing
                and self.source_queue is queue
            ):
                try:
                    raw_chunk = await process.stdout.readexactly(CHUNK_BYTES)
                except asyncio.IncompleteReadError as err:
                    if err.partial:
                        _LOGGER.debug(
                            "M1S group source ended with partial PCM frame bytes=%s",
                            len(err.partial),
                        )
                    break
                now = time.monotonic()
                self._last_pcm_monotonic = now
                if last_read is not None:
                    gap_ms = (now - last_read) * 1000.0
                    # When our own master queue is nearly full, a large interval
                    # can simply be intentional backpressure and is not a source fault.
                    if gap_ms >= PCM_DIAG_SOURCE_GAP_WARN_MS and queue.qsize() < MASTER_PREBUFFER_CHUNKS:
                        self._diag_source_gap_max_ms = max(self._diag_source_gap_max_ms, gap_ms)
                        self._diag_source_gap_count += 1
                        self._diag_record(
                            "source_gap",
                            f"gap={gap_ms:.1f}ms master={queue.qsize() * CHUNK_SECONDS * 1000:.0f}ms",
                        )
                last_read = now
                await queue.put(raw_chunk)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._last_failure = f"source_reader:{err}"
            _LOGGER.warning("M1S group source reader failed: %s", err)
        finally:
            if (
                generation == self._generation
                and serial == self._source_serial
                and self.desired_playing
            ):
                self._last_failure = self._last_failure or "ffmpeg_stream_ended"
                self._schedule_source_restart(generation)
                self._signal_update()

    def _schedule_source_restart(self, generation: int) -> None:
        if self._shutting_down or not self.desired_playing or not self.media_url:
            return
        task = self.source_restart_task
        if task is not None and not task.done():
            return

        async def _runner() -> None:
            try:
                await asyncio.sleep(SOURCE_RESTART_DELAY)
                if generation != self._generation or not self.desired_playing:
                    return
                self._source_restart_count += 1
                await self._start_source_only(generation, reason="source_recovery")
                self._signal_update()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self._last_failure = f"source_restart:{err}"
                _LOGGER.warning("M1S group source-only restart failed: %s", err)
                if generation == self._generation and self.desired_playing:
                    self.source_restart_task = None
                    self._schedule_source_restart(generation)
            finally:
                if self.source_restart_task is asyncio.current_task():
                    self.source_restart_task = None

        self.source_restart_task = self.hass.async_create_background_task(
            _runner(), "aqara_m1s_group_source_restart"
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
        self._accept_initial_prepares = False
        self._broadcast_pause_requested.clear()
        self._broadcast_paused.clear()
        self._playout_epoch_monotonic = None
        self._no_active_since_monotonic = None
        self._generation += 1
        current = asyncio.current_task()
        for attr in (
            "source_task", "source_restart_task", "broadcast_task", "stderr_task",
            "stable_task", "health_task", "diag_task"
        ):
            task = getattr(self, attr)
            setattr(self, attr, None)
            if task and task is not current:
                await self._cancel_task(task)

        self.source_queue = None
        self._master_audio_started = False
        self._master_prebuffer_started_monotonic = None
        process = self.ffmpeg
        self.ffmpeg = None
        self._ffmpeg_nice_applied = False
        if process is not None and process.returncode is None:
            process.terminate()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=2.0)
            if process.returncode is None:
                process.kill()
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=1.0)
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
        member.state = "dropped_until_next_play"

        async def _runner() -> None:
            try:
                await self._detach_member(
                    member.entry_id,
                    stop_remote=True,
                    new_state=(
                        "offline" if not self._member_online(member)
                        else "dropped_until_next_play"
                    ),
                )
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
            await self.hass.async_add_executor_job(
                member.client.run_command, GROUP_START_COMMAND
            )

            # A slow Telnet command may finish after the startup cohort closed or
            # after Stop/another owner changed this member.  Never let that stale
            # completion become a late audible join.
            if (
                member.generation != generation
                or not self.desired_playing
                or not self._eligible(member)
                or (initial and not self._accept_initial_prepares)
            ):
                await self.hass.async_add_executor_job(
                    member.client.run_command, GROUP_STOP_COMMAND
                )
                member.state = self._idle_member_state(member)
                self._signal_update()
                return False

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

            if (
                member.generation != generation
                or not self.desired_playing
                or not self._eligible(member)
                or (initial and not self._accept_initial_prepares)
            ):
                writer.close()
                with suppress(Exception):
                    await asyncio.wait_for(writer.wait_closed(), timeout=WRITER_CLOSE_TIMEOUT)
                await self.hass.async_add_executor_job(
                    member.client.run_command, GROUP_STOP_COMMAND
                )
                return False

            sock = writer.get_extra_info("socket")
            if sock is not None:
                with suppress(OSError):
                    import socket
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_SNDBUF_BYTES)
            transport = getattr(writer, "transport", None)
            if transport is not None:
                with suppress(Exception):
                    transport.set_write_buffer_limits(
                        high=WRITER_HIGH_WATER_BYTES, low=WRITER_LOW_WATER_BYTES
                    )

            member.writer = writer
            member.queue = asyncio.Queue(maxsize=QUEUE_CHUNKS)
            member.detaching = False
            member.lag_since_monotonic = None
            member.lag_peak_chunks = 0
            member.join_at_sequence = None
            member.state = "prepared"
            member.last_error = None
            member.writer_task = self.hass.async_create_background_task(
                self._member_writer_loop(member, generation),
                f"aqara_m1s_group_writer_{member.entry_id}",
            )
            _LOGGER.info("M1S group cohort member ready: %s", member.name)
            self._signal_update()
            return True
        except asyncio.CancelledError:
            raise
        except Exception as err:
            member.last_error = str(err)
            member.state = "offline" if not self._member_online(member) else "waiting_for_next_play"
            _LOGGER.warning("M1S group skipped %s: %s", member.name, err)
            # Precise cleanup cannot kill the priority-sound source on 12347.
            with suppress(Exception):
                await self.hass.async_add_executor_job(
                    member.client.run_command, GROUP_STOP_COMMAND
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
                now = time.monotonic()
                if member.diag_last_feed_monotonic is not None:
                    feed_gap_ms = (now - member.diag_last_feed_monotonic) * 1000.0
                    member.diag_feed_gap_max_ms = max(member.diag_feed_gap_max_ms, feed_gap_ms)
                    if feed_gap_ms >= PCM_DIAG_MEMBER_FEED_GAP_WARN_MS:
                        member.diag_feed_gap_count += 1
                        if now - member.diag_last_log_monotonic >= 0.25:
                            member.diag_last_log_monotonic = now
                            self._diag_record(
                                "member_feed_gap",
                                f"hub={member.name} gap={feed_gap_ms:.1f}ms "
                                f"queue={queue.qsize() * CHUNK_SECONDS * 1000:.0f}ms",
                            )
                member.diag_last_feed_monotonic = now
                member.diag_queue_peak_chunks = max(member.diag_queue_peak_chunks, queue.qsize())
                writer.write(chunk)
                drain_started = time.monotonic()
                await asyncio.wait_for(writer.drain(), timeout=WRITER_DRAIN_TIMEOUT)
                drain_ms = (time.monotonic() - drain_started) * 1000.0
                member.diag_drain_max_ms = max(member.diag_drain_max_ms, drain_ms)
                if drain_ms >= PCM_DIAG_DRAIN_WARN_MS:
                    member.diag_slow_drain_count += 1
                    now2 = time.monotonic()
                    if now2 - member.diag_last_log_monotonic >= 0.25:
                        member.diag_last_log_monotonic = now2
                        transport = getattr(writer, "transport", None)
                        write_buffer = transport.get_write_buffer_size() if transport is not None else -1
                        self._diag_record(
                            "slow_drain",
                            f"hub={member.name} drain={drain_ms:.1f}ms "
                            f"write_buffer={write_buffer}B queue={queue.qsize() * CHUNK_SECONDS * 1000:.0f}ms",
                        )

                # Never replay a seconds-old backlog after a scheduling/network
                # pause: that is what creates the audible echo. Keep this member
                # on the current shared timeline by dropping stale queued frames.
                if queue.qsize() > MEMBER_CATCHUP_THRESHOLD_CHUNKS:
                    dropped = 0
                    while queue.qsize() > MEMBER_CATCHUP_TARGET_CHUNKS:
                        try:
                            stale = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        if stale is None:
                            return
                        dropped += 1
                    if dropped:
                        member.diag_stale_drop_chunks += dropped
                        self._diag_record(
                            "member_catchup_drop",
                            f"hub={member.name} dropped={dropped * CHUNK_SECONDS * 1000:.0f}ms "
                            f"remain={queue.qsize() * CHUNK_SECONDS * 1000:.0f}ms",
                        )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            member.last_error = str(err)
            _LOGGER.warning("M1S group member writer failed %s: %s", member.name, err)
        finally:
            if member.generation == generation and not member.detaching:
                # Only a real writer/socket failure removes the member. Queue
                # pressure alone is handled above without killing its receiver.
                self._schedule_isolate_member(member, reason=member.last_error or "writer_ended")

    async def _detach_member(
        self, entry_id: str, *, stop_remote: bool, new_state: str
    ) -> None:
        member = self.members.get(entry_id)
        if member is None:
            return
        member.generation += 1
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
        if task and task is not asyncio.current_task():
            await self._cancel_task(task)
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=WRITER_CLOSE_TIMEOUT)
        if stop_remote and self._member_online(member):
            # Run cleanup as an independent task. Closing TCP already makes nc/FIFO
            # hit EOF quickly; this avoids Home Assistant Stop waiting on Telnet.
            self.hass.async_create_background_task(
                self._remote_group_stop(member),
                f"aqara_m1s_group_remote_stop_{member.entry_id}",
            )
        member.state = new_state
        member.detaching = False
        self._signal_update()

    async def _remote_group_stop(self, member: GroupMember) -> None:
        try:
            await self.hass.async_add_executor_job(
                member.client.run_command, GROUP_STOP_COMMAND
            )
        except Exception as err:
            _LOGGER.debug("M1S group remote cleanup failed %s: %s", member.name, err)

    async def _fanout_frame(self, chunk: bytes, sequence: int) -> None:
        """Queue one paced frame for each member without letting backlog create echo."""
        for member in list(self.active_members):
            queue = member.queue
            if queue is None:
                continue
            depth = queue.qsize()
            member.lag_peak_chunks = max(member.lag_peak_chunks, depth)
            member.diag_queue_peak_chunks = max(member.diag_queue_peak_chunks, depth)
            try:
                queue.put_nowait(chunk)
                continue
            except asyncio.QueueFull:
                pass

            # A full member queue no longer ejects the hub. Drop stale PCM from
            # only that member and keep the newest shared-timeline frame.
            dropped = 0
            while queue.qsize() > MEMBER_CATCHUP_TARGET_CHUNKS:
                try:
                    stale = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if stale is None:
                    break
                dropped += 1
            try:
                queue.put_nowait(chunk)
            except asyncio.QueueFull:
                # Should be extremely rare; the writer will retry next tick.
                dropped += 1
            member.diag_stale_drop_chunks += dropped
            now = time.monotonic()
            if now - member.diag_last_log_monotonic >= 0.5:
                member.diag_last_log_monotonic = now
                self._diag_record(
                    "member_queue_trim",
                    f"hub={member.name} dropped={dropped * CHUNK_SECONDS * 1000:.0f}ms "
                    f"queue={queue.qsize() * CHUNK_SECONDS * 1000:.0f}ms",
                )

    async def _broadcast_loop(self, generation: int) -> None:
        queue = self.source_queue
        if queue is None:
            return
        next_deadline = time.monotonic()
        last_silence_log = 0.0
        try:
            while generation == self._generation and self.desired_playing:
                now = time.monotonic()
                delay = next_deadline - now
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    late = -delay
                    if late >= PLAYOUT_LATE_REBASE_SECONDS:
                        # Never catch up by blasting many frames into TCP. Rebase
                        # the common clock and keep every hub on the same cadence.
                        next_deadline = time.monotonic()
                        self._clock_rebase_count += 1
                now = time.monotonic()

                if not self._master_audio_started:
                    age = (
                        0.0 if self._master_prebuffer_started_monotonic is None
                        else now - self._master_prebuffer_started_monotonic
                    )
                    if queue.qsize() >= MASTER_PREBUFFER_CHUNKS or (
                        age >= MASTER_PREBUFFER_MAX_WAIT and queue.qsize() >= MASTER_MIN_START_CHUNKS
                    ):
                        self._master_audio_started = True
                        _LOGGER.info(
                            "M1S group master buffer ready depth=%sms wait=%.2fs",
                            int(queue.qsize() * CHUNK_SECONDS * 1000), age,
                        )
                        self._signal_update()

                raw_chunk: bytes | None = None
                if self._master_audio_started:
                    with suppress(asyncio.QueueEmpty):
                        raw_chunk = queue.get_nowait()

                if raw_chunk is None:
                    chunk = SILENCE_CHUNK
                    self._master_silence_frames += 1
                    if self._master_audio_started and now - last_silence_log >= 1.0:
                        last_silence_log = now
                        self._diag_record(
                            "master_buffer_empty",
                            f"inserted_silence sequence={self._sequence} source_running={self.ffmpeg_running}",
                        )
                else:
                    chunk = self._apply_live_pcm_gain(raw_chunk)

                sequence = self._sequence
                self._sequence += 1
                await self._fanout_frame(chunk, sequence)
                next_deadline += CHUNK_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._last_failure = f"master_playout:{err}"
            _LOGGER.exception("M1S group master playout failed")
        finally:
            if generation == self._generation and self.desired_playing:
                self._last_failure = self._last_failure or "master_playout_ended"
                self._schedule_watchdog_restart()
                self._signal_update()

    async def _stderr_loop(
        self, process: asyncio.subprocess.Process, generation: int, serial: int
    ) -> None:
        if process.stderr is None:
            return
        lines: list[str] = []
        try:
            while generation == self._generation and serial == self._source_serial:
                line = await process.stderr.readline()
                if not line:
                    break
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
        """Maintain eligibility only; never alter the running cohort membership."""
        try:
            while self.desired_playing and not self._shutting_down:
                await asyncio.sleep(RECONCILE_SECONDS)
                if not self.desired_playing:
                    return
                for member in list(self.members.values()):
                    if member.writer is not None and not self._eligible(member):
                        self._schedule_isolate_member(
                            member, reason="member_no_longer_eligible"
                        )
                    elif member.writer is None and self._eligible(member):
                        # Deliberately no late join. Preserve the fixed-cohort
                        # synchronisation policy during healthy playback.
                        if member.state not in (
                            "dropped_until_next_play",
                            "waiting_for_next_play",
                            "playing_sound",
                        ):
                            member.state = "waiting_for_next_play"

                # If every receiver disappears while FFmpeg is still healthy,
                # the old code could remain BUFFERING forever because PCM itself
                # continued to advance. This is the one case where the whole
                # transport is already lost, so a fresh cohort cannot disturb any
                # audible member. Trigger one bounded watchdog recovery.
                if self.desired_playing and not self.active_members and not self.sound_intent:
                    now = time.monotonic()
                    if self._no_active_since_monotonic is None:
                        self._no_active_since_monotonic = now
                    elif now - self._no_active_since_monotonic >= NO_ACTIVE_MEMBERS_TIMEOUT:
                        self._last_failure = "no_active_group_members"
                        _LOGGER.warning(
                            "M1S group has no active receivers for %.1fs; restarting transport",
                            now - self._no_active_since_monotonic,
                        )
                        self._no_active_since_monotonic = None
                        self._transport_self_heal_count += 1
                        self._signal_update()
                        self._schedule_watchdog_restart()
                        return
                else:
                    self._no_active_since_monotonic = None

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

    async def _pcm_health_watch(self, generation: int) -> None:
        """Recover only the source when PCM stalls; receivers keep playing buffered/silence PCM."""
        try:
            while generation == self._generation and self.desired_playing:
                await asyncio.sleep(PCM_HEALTH_CHECK_SECONDS)
                if generation != self._generation or not self.desired_playing:
                    return
                now = time.monotonic()
                if (
                    self._stream_started_monotonic is not None
                    and now - self._stream_started_monotonic < PCM_START_GRACE_SECONDS
                ):
                    continue
                pcm_age = None if self._last_pcm_monotonic is None else now - self._last_pcm_monotonic
                # A full/healthy master buffer intentionally backpressures the
                # FFmpeg stdout reader, so an old read timestamp is not a stall.
                buffered_chunks = self.source_queue.qsize() if self.source_queue is not None else 0
                if buffered_chunks >= MASTER_MIN_START_CHUNKS:
                    continue
                if pcm_age is None or pcm_age >= PCM_STALL_TIMEOUT:
                    age_text = "never" if pcm_age is None else f"{pcm_age:.1f}s"
                    self._last_failure = f"pcm_stall:{age_text}"
                    _LOGGER.warning(
                        "M1S group source PCM stalled (last=%s); restarting source only", age_text
                    )
                    process = self.ffmpeg
                    if process is not None and process.returncode is None:
                        with suppress(ProcessLookupError):
                            process.terminate()
                    self._schedule_source_restart(generation)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._last_failure = f"pcm_health:{err}"
            _LOGGER.warning("M1S group PCM health watchdog failed: %s", err)

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
            if not self.desired_playing or not self.media_url:
                return
            transport_alive = self.broadcast_task is not None and not self.broadcast_task.done()
            if transport_alive and self.active_members:
                # Source faults are recovered independently; never tear down a healthy cohort.
                if not self.ffmpeg_running:
                    self._schedule_source_restart(self._generation)
                return
            self._watchdog_attempts += 1
            _LOGGER.warning(
                "M1S group watchdog restart %s/%s last_failure=%s",
                self._watchdog_attempts,
                WATCHDOG_MAX_RESTARTS,
                self._last_failure or "unknown",
            )
            async def _run_restart() -> None:
                async with self._lock:
                    await self._restart_stream_locked(reason="watchdog")

            try:
                await asyncio.wait_for(
                    _run_restart(), timeout=WATCHDOG_RESTART_HARD_TIMEOUT
                )
            except asyncio.TimeoutError:
                _LOGGER.error(
                    "M1S group watchdog restart exceeded %.1fs; forcing idle reset",
                    WATCHDOG_RESTART_HARD_TIMEOUT,
                )
                await self.async_force_reset(reason="watchdog_restart_timeout")
                return
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
        self._last_failure = self._last_failure or "restart_limit_reached"
        _LOGGER.warning(
            "M1S group automatic restart limit reached; waiting for next user Play"
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
                (self._last_pcm_monotonic is not None
                 and now - self._last_pcm_monotonic < PCM_HEALTH_CHECK_SECONDS * 2)
                or (self.source_queue is not None and self.source_queue.qsize() >= MASTER_MIN_START_CHUNKS)
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
            "source_restart_task",
            "watchdog_task",
            "slow_retry_task",
            "resync_task",
            "periodic_receiver_resync_task",
            "_sound_return_restart_task",
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


    def remember_browse_titles(self, root: Any) -> None:
        """Cache Media Browser labels so Play can expose the selected station name."""
        stack = [root]
        seen = 0
        while stack and seen < 5000:
            item = stack.pop()
            seen += 1
            if isinstance(item, dict):
                media_id = item.get("media_content_id")
                title = item.get("title")
                children = item.get("children") or []
            else:
                media_id = getattr(item, "media_content_id", None)
                title = getattr(item, "title", None)
                children = getattr(item, "children", None) or []
            if media_id and title:
                self._browse_title_cache[str(media_id)] = str(title)
            with suppress(TypeError):
                stack.extend(children)
        if len(self._browse_title_cache) > 10000:
            # Keep recent browser navigation only; titles are convenience metadata.
            self._browse_title_cache = dict(list(self._browse_title_cache.items())[-5000:])

    def media_title_for(self, media_id: str, resolved_id: str, kwargs: dict[str, Any]) -> str:
        """Choose the best available user-facing label for the selected media."""
        extra = kwargs.get("extra") or {}
        candidates: list[Any] = []
        if isinstance(extra, dict):
            candidates.extend((extra.get("title"), extra.get("media_title"), extra.get("name")))
        metadata = kwargs.get("metadata") or {}
        if isinstance(metadata, dict):
            candidates.extend((metadata.get("title"), metadata.get("media_title"), metadata.get("name")))
        candidates.extend((
            kwargs.get("title"),
            kwargs.get("media_title"),
            self._browse_title_cache.get(media_id),
            self._browse_title_cache.get(resolved_id),
        ))
        for candidate in candidates:
            if candidate and str(candidate).strip():
                return str(candidate).strip()

        # Direct stream URLs do not carry Home Assistant browser labels. Produce
        # a harmless readable fallback rather than the generic "M1S group stream".
        try:
            parts = urlsplit(resolved_id)
            filename = parts.path.rsplit("/", 1)[-1]
            stem = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
            if stem and len(stem) <= 80:
                return stem
            if parts.hostname:
                return parts.hostname
        except Exception:
            pass
        return "M1S Media Group"


class AqaraM1SMediaGroup(MediaPlayerEntity, RestoreEntity):
    """Single group entity backed by one fixed, synchronised receiver cohort."""

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
        result = await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )
        self.manager.remember_browse_titles(result)
        return result

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
        title = self.manager.media_title_for(original, resolved_id, kwargs)
        await self.manager.async_start(
            url, original, media_type or MediaType.MUSIC, title
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
