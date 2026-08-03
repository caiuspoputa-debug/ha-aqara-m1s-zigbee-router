from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import logging
import shutil
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
SYNC_LEAD_SECONDS = 1.5
SYNC_LEAD_CHUNKS = int(SYNC_LEAD_SECONDS / CHUNK_SECONDS)
QUEUE_SECONDS = 1.0
QUEUE_CHUNKS = int(QUEUE_SECONDS / CHUNK_SECONDS)
RECONCILE_SECONDS = 3.0
WRITER_DRAIN_TIMEOUT = 1.0
WATCHDOG_RESTART_DELAY = 5.0
WATCHDOG_MAX_RESTARTS = 3
WATCHDOG_SLOW_RETRY_DELAY = 60.0
WATCHDOG_STABLE_SECONDS = 30.0
FULL_RESYNC_RETRY_SECONDS = 30.0
GROUP_VOLUME_SETTLE_SECONDS = 0.8

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
    + f'aplay -t raw -f S32_LE -c 1 -r {PCM_RATE} {GROUP_FIFO} </dev/null '
      '>/tmp/aqara_m1s_group_aplay.log 2>&1 & '
    + f'echo $! > {GROUP_APLAY_PID}; '
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
    join_at_sequence: int | None = None
    last_error: str | None = None
    generation: int = 0
    last_prepare_attempt_monotonic: float = 0.0


class AqaraM1SMediaGroupManager:
    """Own one FFmpeg timeline and fan the same timestamped PCM to many hubs."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.members: dict[str, GroupMember] = {}
        self.individual_intent: set[str] = set()
        self.entity: AqaraM1SMediaGroup | None = None
        self.media_entity_added = False
        self.volume_entity_added = False

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
        self.slow_retry_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._generation = 0
        self._sequence = 0
        self._stream_started_monotonic: float | None = None
        self._watchdog_attempts = 0
        self._last_failure: str | None = None
        self._full_resync_count = 0
        self._last_full_resync_reason: str | None = None
        self._volume_restart_task: asyncio.Task | None = None
        self._applied_volume = self.volume
        self._applied_muted = self.muted
        self._shutting_down = False

    def register_member(self, entry_id: str, name: str, client: Any, coordinator: Any) -> None:
        existing = self.members.get(entry_id)
        selected = existing.selected if existing else True
        self.members[entry_id] = GroupMember(
            entry_id=entry_id,
            name=name,
            client=client,
            coordinator=coordinator,
            selected=selected,
            state="waiting" if selected else "excluded",
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
        self._signal_update()

    def set_selected(self, entry_id: str, selected: bool) -> None:
        member = self.members.get(entry_id)
        if member is None:
            return
        member.selected = selected
        if not selected:
            member.state = "excluded"
        elif entry_id in self.individual_intent:
            member.state = "playing_individual"
        else:
            member.state = "waiting_for_sync"
            member.last_prepare_attempt_monotonic = 0.0
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
            new_state="playing_individual",
        )
        self._signal_update()

    def mark_individual_intent(self, entry_id: str, active: bool) -> None:
        if active:
            self.individual_intent.add(entry_id)
            member = self.members.get(entry_id)
            if member and member.writer is None:
                member.state = "playing_individual"
        else:
            self.individual_intent.discard(entry_id)
            member = self.members.get(entry_id)
            if member and member.selected:
                member.state = "waiting_for_sync"
                member.last_prepare_attempt_monotonic = 0.0
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
            and self._member_online(member)
        )

    def _signal_update(self) -> None:
        async_dispatcher_send(self.hass, media_group_signal())

    @property
    def active_members(self) -> list[GroupMember]:
        return [m for m in self.members.values() if m.writer is not None]

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
            "transport": "single_ffmpeg_shared_pcm_timeline",
            "stream_sequence": self._sequence,
            "stream_timestamp_seconds": timestamp,
            "sync_lead_seconds": SYNC_LEAD_SECONDS,
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
            "excluded_hubs": sorted(by_state.get("excluded", [])),
            "last_failure": self._last_failure,
            "watchdog_restart_attempts": self._watchdog_attempts,
            "rejoin_sync_mode": "full_group_restart",
            "full_resync_count": self._full_resync_count,
            "last_full_resync_reason": self._last_full_resync_reason,
            "full_resync_retry_seconds": FULL_RESYNC_RETRY_SECONDS,
            "volume_apply_mode": "debounced_final_value",
            "volume_settle_seconds": GROUP_VOLUME_SETTLE_SECONDS,
            "volume_apply_pending": bool(
                self._volume_restart_task and not self._volume_restart_task.done()
            ),
            "applied_volume_level": self._applied_volume,
            "applied_is_volume_muted": self._applied_muted,
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
        await self._cancel_pending_volume_apply()
        await self._cancel_background_recovery()
        async with self._lock:
            await self._stop_stream_locked(stop_members=True, reason="user_stop")
        self._signal_update()

    async def async_shutdown(self) -> None:
        self._shutting_down = True
        await self._cancel_pending_volume_apply()
        await self._cancel_background_recovery()
        async with self._lock:
            await self._stop_stream_locked(stop_members=True, reason="shutdown")

    async def async_set_volume(self, volume: float) -> None:
        """Store every slider position but apply only the final settled value.

        Home Assistant may issue several volume service calls while a slider is
        being dragged. Restarting the shared FFmpeg timeline for every intermediate
        value causes repeated interruptions. Each new value therefore replaces the
        pending value and resets a short quiet-period timer. Only one full group
        restart is performed after the calls stop.
        """
        self.volume = self.normalize_volume(volume)
        async_dispatcher_send(self.hass, media_group_volume_signal())
        self._signal_update()

        previous = self._volume_restart_task
        self._volume_restart_task = None
        if previous and previous is not asyncio.current_task():
            previous.cancel()

        if (
            self.desired_playing
            and self.media_url
            and (
                self.volume != self._applied_volume
                or self.muted != self._applied_muted
            )
        ):
            self._volume_restart_task = self.hass.async_create_background_task(
                self._apply_volume_after_settle(),
                "aqara_m1s_group_final_volume_apply",
            )

    async def _apply_volume_after_settle(self) -> None:
        """Restart the shared timeline once, using the last requested volume."""
        try:
            await asyncio.sleep(GROUP_VOLUME_SETTLE_SECONDS)
            async with self._lock:
                if (
                    self.desired_playing
                    and self.media_url
                    and (
                        self.volume != self._applied_volume
                        or self.muted != self._applied_muted
                    )
                ):
                    await self._restart_stream_locked(
                        reason="volume_change_final"
                    )
        except asyncio.CancelledError:
            return
        finally:
            if self._volume_restart_task is asyncio.current_task():
                self._volume_restart_task = None
            self._signal_update()

    async def _cancel_pending_volume_apply(self) -> None:
        task = self._volume_restart_task
        self._volume_restart_task = None
        if task and task is not asyncio.current_task():
            await self._cancel_task(task)

    async def async_set_muted(self, muted: bool) -> None:
        muted = bool(muted)
        if muted == self.muted and muted == self._applied_muted:
            self._signal_update()
            return
        await self._cancel_pending_volume_apply()
        self.muted = muted
        if self.desired_playing and self.media_url:
            async with self._lock:
                await self._restart_stream_locked(reason="mute_change")
        self._signal_update()

    @staticmethod
    def normalize_volume(volume: float) -> float:
        """Quantize the complete 0-100% range in uniform 0.2% steps."""
        volume = max(0.0, min(1.0, float(volume)))
        quantized = round(volume / 0.002) * 0.002
        return max(0.0, min(1.0, round(quantized, 3)))

    async def _restart_stream_locked(self, reason: str) -> None:
        if reason.startswith("member_rejoin:"):
            self._full_resync_count += 1
            self._last_full_resync_reason = reason
        await self._stop_stream_locked(stop_members=True, reason=reason)
        if not self.desired_playing or not self.media_url:
            return

        eligible = [m for m in self.members.values() if self._eligible(m)]
        if eligible:
            await asyncio.gather(
                *(self._prepare_member(member, initial=True) for member in eligible),
                return_exceptions=True,
            )

        await self._start_ffmpeg_locked()

    async def _start_ffmpeg_locked(self) -> None:
        if not self.media_url or not self.desired_playing:
            return
        ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
        effective_volume = 0.0 if self.muted else self.volume
        args = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-re",
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
            "-filter:a",
            f"volume={effective_volume:.4f}",
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
        self._applied_volume = self.volume
        self._applied_muted = self.muted
        self._generation += 1
        generation = self._generation
        self._sequence = 0
        self._stream_started_monotonic = time.monotonic()
        for member in self.active_members:
            member.join_at_sequence = SYNC_LEAD_CHUNKS
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
        _LOGGER.info(
            "M1S group FFmpeg started pid=%s source=%s members=%s",
            process.pid,
            self._safe_media_for_log(self.media_url),
            [m.name for m in self.active_members],
        )

    async def _stop_stream_locked(self, *, stop_members: bool, reason: str) -> None:
        self._generation += 1
        current = asyncio.current_task()
        for attr in ("broadcast_task", "stderr_task", "stable_task"):
            task = getattr(self, attr)
            setattr(self, attr, None)
            if task and task is not current:
                await self._cancel_task(task)

        process = self.ffmpeg
        self.ffmpeg = None
        if process is not None and process.returncode is None:
            process.terminate()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=2.0)
            if process.returncode is None:
                process.kill()
                await process.wait()
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
        if member.entry_id in self.individual_intent:
            return "playing_individual"
        if not self._member_online(member):
            return "offline"
        return "waiting_for_sync" if self.desired_playing else "idle"

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
            writer: asyncio.StreamWriter | None = None
            last_error: Exception | None = None
            for _ in range(12):
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(member.client.host, GROUP_PORT),
                        timeout=1.0,
                    )
                    break
                except (OSError, asyncio.TimeoutError) as err:
                    last_error = err
                    await asyncio.sleep(0.15)
            if writer is None:
                raise ConnectionError(f"group receiver unavailable: {last_error}")

            sock = writer.get_extra_info("socket")
            if sock is not None:
                with suppress(OSError):
                    import socket
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            member.writer = writer
            member.queue = asyncio.Queue(maxsize=QUEUE_CHUNKS)
            member.join_at_sequence = (
                SYNC_LEAD_CHUNKS
                if initial or self._sequence == 0
                else self._sequence + SYNC_LEAD_CHUNKS
            )
            member.state = "waiting_for_sync"
            member.last_error = None
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
            member.state = "offline" if not self._member_online(member) else "waiting_for_sync"
            _LOGGER.warning("M1S group skipped %s: %s", member.name, err)
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
                writer.write(chunk)
                await asyncio.wait_for(writer.drain(), timeout=WRITER_DRAIN_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            member.last_error = str(err)
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
        task = member.writer_task
        member.writer_task = None
        queue = member.queue
        member.queue = None
        writer = member.writer
        member.writer = None
        member.join_at_sequence = None
        if queue is not None:
            with suppress(asyncio.QueueFull):
                queue.put_nowait(None)
        if task and task is not asyncio.current_task():
            await self._cancel_task(task)
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
        if stop_remote and self._member_online(member):
            with suppress(Exception):
                await self.hass.async_add_executor_job(
                    member.client.run_command, GROUP_STOP_COMMAND
                )
        member.state = new_state
        if new_state == "offline":
            # A real offline -> online transition must trigger an immediate full
            # resynchronisation, even when the previous preparation was recent.
            member.last_prepare_attempt_monotonic = 0.0
        self._signal_update()

    async def _remote_group_stop(self, member: GroupMember) -> None:
        with suppress(Exception):
            await self.hass.async_add_executor_job(
                member.client.run_command, GROUP_STOP_COMMAND
            )

    async def _broadcast_loop(
        self, process: asyncio.subprocess.Process, generation: int
    ) -> None:
        if process.stdout is None:
            return
        buffer = bytearray()
        try:
            while generation == self._generation and self.desired_playing:
                data = await process.stdout.read(32768)
                if not data:
                    break
                buffer.extend(data)
                while len(buffer) >= CHUNK_BYTES:
                    chunk = bytes(buffer[:CHUNK_BYTES])
                    del buffer[:CHUNK_BYTES]
                    sequence = self._sequence
                    self._sequence += 1
                    failed: list[str] = []
                    for member in list(self.active_members):
                        queue = member.queue
                        if queue is None:
                            continue
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
                            failed.append(member.entry_id)
                    for entry_id in failed:
                        member = self.members.get(entry_id)
                        if member:
                            member.last_error = "PCM queue exceeded one second"
                        await self._detach_member(
                            entry_id,
                            stop_remote=False,
                            new_state="waiting_for_sync",
                        )
                        if member is not None and self._member_online(member):
                            self.hass.async_create_background_task(
                                self._remote_group_stop(member),
                                f"aqara_m1s_group_cleanup_{entry_id}",
                            )
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
            while generation == self._generation:
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

    def _ensure_reconcile_task(self) -> None:
        if self._shutting_down:
            return
        if self.reconcile_task is None or self.reconcile_task.done():
            self.reconcile_task = self.hass.async_create_background_task(
                self._reconcile_loop(), "aqara_m1s_group_reconcile"
            )

    async def _reconcile_loop(self) -> None:
        try:
            while self.desired_playing and not self._shutting_down:
                await asyncio.sleep(RECONCILE_SECONDS)
                if not self.desired_playing:
                    return
                if not self.ffmpeg_running and self.media_url:
                    self._schedule_watchdog_restart()
                    continue

                # Remove members that are no longer eligible without disturbing
                # the hubs that are still playing.  When such a hub becomes
                # eligible again, the block below performs a deterministic full
                # restart of every selected receiver and the shared FFmpeg source.
                for member in list(self.members.values()):
                    if member.writer is not None and not self._eligible(member):
                        await self._detach_member(
                            member.entry_id,
                            stop_remote=True,
                            new_state=self._idle_member_state(member),
                        )

                if self.ffmpeg_running:
                    now = time.monotonic()
                    missing = [
                        member
                        for member in self.members.values()
                        if member.writer is None and self._eligible(member)
                    ]
                    due = [
                        member
                        for member in missing
                        if now - member.last_prepare_attempt_monotonic
                        >= FULL_RESYNC_RETRY_SECONDS
                    ]
                    if due:
                        names = ",".join(sorted(member.name for member in due))
                        _LOGGER.info(
                            "M1S group member rejoin detected; restarting all "
                            "receivers for deterministic synchronization: %s",
                            names,
                        )
                        async with self._lock:
                            if self.desired_playing and self.ffmpeg_running:
                                await self._restart_stream_locked(
                                    reason=f"member_rejoin:{names}"
                                )
                        self._signal_update()
                        continue

                for member in self.members.values():
                    if member.writer is None:
                        member.state = self._idle_member_state(member)
                self._signal_update()
        except asyncio.CancelledError:
            raise
        finally:
            if self.reconcile_task is asyncio.current_task():
                self.reconcile_task = None

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
                "M1S group watchdog restart %s/%s",
                self._watchdog_attempts,
                WATCHDOG_MAX_RESTARTS,
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
            if (
                generation == self._generation
                and self.ffmpeg is process
                and process.returncode is None
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
        for attr in ("reconcile_task", "watchdog_task", "slow_retry_task"):
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
        with suppress(asyncio.CancelledError):
            await task

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
    """Single group entity backed by one timestamped PCM timeline."""

    _attr_name = "M1S Media Group"
    _attr_unique_id = "aqara_m1s_media_group"
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_should_poll = False
    _attr_volume_step = 0.002
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
        await self.async_media_stop()

    async def async_set_volume_level(self, volume: float) -> None:
        await self.manager.async_set_volume(volume)
        self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        current = self.manager.volume
        await self.async_set_volume_level(current + 0.002)

    async def async_volume_down(self) -> None:
        current = self.manager.volume
        await self.async_set_volume_level(current - 0.002)

    async def async_mute_volume(self, mute: bool) -> None:
        await self.manager.async_set_muted(mute)
        self.async_write_ha_state()
