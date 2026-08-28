from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import time
from contextlib import suppress
from typing import Any

from homeassistant.core import HomeAssistant

from .client import AqaraM1SClient

_LOGGER = logging.getLogger(__name__)

# IMPORTANT: This transport block intentionally matches the known-good v0.6.0
# sound pipeline. Audio priority is handled only by the HA-side arbiter around it.
SOURCE_PORT = 12347
SINK_PORT = 12348
REMOTE_FIFO = "/tmp/aqara_m1s_sound_fifo"
REMOTE_SOURCE_PID = "/tmp/aqara_m1s_sound_source_nc.pid"
REMOTE_SINK_PID = "/tmp/aqara_m1s_sound_sink_nc.pid"
REMOTE_APLAY_PID = "/tmp/aqara_m1s_sound_aplay.pid"
FFMPEG_NICE_TARGET = -5
APLAY_NICE_TARGET = -3
SOUND_SETTLE_DELAY = 0.35

REMOTE_STOP_COMMAND = (
    f"for f in {REMOTE_SOURCE_PID} {REMOTE_SINK_PID} {REMOTE_APLAY_PID}; do "
        '[ -f "$f" ] && kill -9 "$(cat "$f")" 2>/dev/null; '
    "done; "
    f"rm -f {REMOTE_SOURCE_PID} {REMOTE_SINK_PID} {REMOTE_APLAY_PID} {REMOTE_FIFO}"
)


def remote_start_command(path: str) -> str:
    """Build the original known-good hub-side one-shot source/sink pipeline."""
    source = shlex.quote(path)
    return (
        REMOTE_STOP_COMMAND
        + f"; mkfifo {REMOTE_FIFO}; "
        + f"nc -l -p {SINK_PORT} < /dev/null > {REMOTE_FIFO} "
          "2>/tmp/aqara_m1s_sound_sink_nc.log & "
        + f"echo $! > {REMOTE_SINK_PID}; "
        + f"aplay -t raw -f S32_LE -c 1 -r 32000 {REMOTE_FIFO} </dev/null "
          ">/tmp/aqara_m1s_sound_aplay.log 2>&1 & "
        + f"echo $! > {REMOTE_APLAY_PID}; "
        + f"APID=$(cat {REMOTE_APLAY_PID}); "
          f"renice {APLAY_NICE_TARGET} -p \"$APID\" "
          ">/tmp/aqara_m1s_sound_aplay_renice.log 2>&1 || true; "
        + f"cat {source} | nc -l -p {SOURCE_PORT} "
          ">/dev/null 2>/tmp/aqara_m1s_sound_source_nc.log & "
        + f"echo $! > {REMOTE_SOURCE_PID}"
    )


class AqaraM1SSoundPlayer:
    """Play one hub WAV, with HA-side priority but the original sound transport."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AqaraM1SClient,
        entry_id: str,
        radio_player: Any,
        group_manager: Any,
    ) -> None:
        self.hass = hass
        self.client = client
        self.entry_id = entry_id
        self.radio_player = radio_player
        self.group_manager = group_manager
        self._lock = asyncio.Lock()
        self._ffmpeg: asyncio.subprocess.Process | None = None
        self._watch_task: asyncio.Task | None = None
        self._interruption_active = False
        self._resume_radio = False
        self._active_timing_start: float | None = None
        self._active_timing: dict[str, int] | None = None

    async def _begin_priority_locked(self) -> None:
        """Release group/individual ownership before starting the proven sound path."""
        if self._interruption_active:
            return
        await self.group_manager.async_claim_sound(self.entry_id)
        self._resume_radio = await self.radio_player.async_suspend_for_priority_sound()
        self._interruption_active = True
        # Only a short ALSA settle delay. Do not manipulate hub sound transport here.
        await asyncio.sleep(0.25)

    async def _finish_priority(self) -> None:
        if not self._interruption_active:
            return
        resume_radio = self._resume_radio
        self._resume_radio = False
        self._interruption_active = False
        try:
            # Always release the radio-player priority gate. The boolean controls
            # whether remembered single media should resume; the sound transport
            # itself remains exactly the known-good v0.6.0/v0.6.3 pipeline.
            await self.radio_player.async_resume_after_priority_sound(resume_radio)
        finally:
            await self.group_manager.async_release_sound(self.entry_id)

    async def async_play(self, path: str, volume: int) -> None:
        """Play exactly one WAV using the known-good v0.6.0 transport."""
        request_started = time.perf_counter()
        timing: dict[str, int] = {}
        safe_volume = max(0, min(100, int(volume))) / 100.0
        _LOGGER.info(
            "Aqara M1S sound timing request entity=%s host=%s path=%s volume=%s",
            self.entry_id,
            self.client.host,
            path,
            volume,
        )
        async with self._lock:
            timing["button_to_lock_ms"] = self._elapsed_ms(request_started)

            stage_started = time.perf_counter()
            await self._stop_locked(restore_previous=False, remote_stop=False)
            timing["existing_sound_stop_ms"] = self._elapsed_ms(stage_started)

            stage_started = time.perf_counter()
            await self._begin_priority_locked()
            timing["arbitration_ms"] = self._elapsed_ms(stage_started)
            try:
                # Keep this sequence identical to v0.6.0 after focus arbitration.
                stage_started = time.perf_counter()
                await self.hass.async_add_executor_job(
                    self.client.run_command,
                    remote_start_command(path),
                )
                timing["remote_sound_start_ms"] = self._elapsed_ms(stage_started)

                stage_started = time.perf_counter()
                await asyncio.sleep(SOUND_SETTLE_DELAY)
                timing["settle_ms"] = self._elapsed_ms(stage_started)

                ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
                input_url = f"tcp://{self.client.host}:{SOURCE_PORT}?tcp_nodelay=1"
                output_url = f"tcp://{self.client.host}:{SINK_PORT}?tcp_nodelay=1"
                args = [
                    ffmpeg,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "warning",
                    "-progress",
                    "pipe:2",
                    "-re",
                    "-i",
                    input_url,
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "32000",
                    "-filter:a",
                    f"volume={safe_volume:.4f}",
                    "-c:a",
                    "pcm_s32le",
                    "-f",
                    "s32le",
                    output_url,
                ]

                try:
                    stage_started = time.perf_counter()
                    process = await asyncio.create_subprocess_exec(
                        *args,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    timing["ffmpeg_spawn_ms"] = self._elapsed_ms(stage_started)
                except FileNotFoundError as err:
                    await self._remote_stop()
                    await self._finish_priority()
                    raise RuntimeError("FFmpeg was not found on Home Assistant") from err

                self._ffmpeg = process
                self._active_timing_start = request_started
                self._active_timing = timing
                self._try_set_ffmpeg_priority(process.pid)
                timing["button_to_ffmpeg_spawn_ms"] = self._elapsed_ms(request_started)
                _LOGGER.info(
                    "Aqara M1S sound timing start entity=%s host=%s "
                    "button_to_lock_ms=%s existing_sound_stop_ms=%s arbitration_ms=%s "
                    "remote_sound_start_ms=%s settle_ms=%s ffmpeg_spawn_ms=%s "
                    "button_to_ffmpeg_spawn_ms=%s",
                    self.entry_id,
                    self.client.host,
                    timing.get("button_to_lock_ms"),
                    timing.get("existing_sound_stop_ms"),
                    timing.get("arbitration_ms"),
                    timing.get("remote_sound_start_ms"),
                    timing.get("settle_ms"),
                    timing.get("ffmpeg_spawn_ms"),
                    timing.get("button_to_ffmpeg_spawn_ms"),
                )
                self._watch_task = self.hass.async_create_task(self._watch(process))
            except Exception:
                if self._ffmpeg is None:
                    self._active_timing_start = None
                    self._active_timing = None
                    await self._remote_stop()
                    await self._finish_priority()
                raise

    async def async_play_url(self, url: str) -> None:
        """Play URL with the same focus policy; does not alter normal WAV transport."""
        async with self._lock:
            await self._stop_locked(restore_previous=False)
            await self._begin_priority_locked()
        quoted = shlex.quote(url)
        command = (
            f"wget -q {quoted} -O /tmp/ha_audio.wav "
            "&& (aplay -x 1 /tmp/ha_audio.wav & "
            "APID=$!; renice -3 -p \"$APID\" "
            ">/tmp/aqara_m1s_play_url_aplay_renice.log 2>&1 || true; "
            "wait \"$APID\")"
        )
        try:
            await self.hass.async_add_executor_job(self.client.run_command, command)
        finally:
            async with self._lock:
                await self._finish_priority()

    @staticmethod
    def _try_set_ffmpeg_priority(pid: int) -> bool:
        try:
            os.setpriority(os.PRIO_PROCESS, pid, FFMPEG_NICE_TARGET)
            return os.getpriority(os.PRIO_PROCESS, pid) <= FFMPEG_NICE_TARGET
        except (AttributeError, OSError, PermissionError) as err:
            _LOGGER.debug(
                "Could not apply sound FFmpeg nice=%s to pid=%s: %s",
                FFMPEG_NICE_TARGET,
                pid,
                err,
            )
            return False

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return round((time.perf_counter() - started) * 1000)

    async def _watch(self, process: asyncio.subprocess.Process) -> None:
        stderr_tail: list[str] = []
        first_pcm_logged = False
        try:
            if process.stderr is not None:
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    text = line.decode(errors="ignore").strip()
                    if text:
                        stderr_tail.append(text)
                        stderr_tail = stderr_tail[-40:]
                    if not first_pcm_logged and self._ffmpeg is process:
                        first_pcm_logged = self._maybe_log_first_pcm_write(text)
            await process.wait()
        except asyncio.CancelledError:
            return

        if self._ffmpeg is not process:
            return

        timing_start = self._active_timing_start
        timing = self._active_timing
        self._ffmpeg = None
        self._watch_task = None
        self._active_timing_start = None
        self._active_timing = None
        if process.returncode not in (0, -15):
            _LOGGER.warning(
                "Aqara M1S priority sound FFmpeg exited with code %s: %s",
                process.returncode,
                "\n".join(stderr_tail)[-1000:],
            )
        elif process.returncode == 0:
            await asyncio.sleep(0.2)
        if timing_start is not None and timing is not None:
            _LOGGER.info(
                "Aqara M1S sound timing complete entity=%s host=%s "
                "button_to_lock_ms=%s existing_sound_stop_ms=%s arbitration_ms=%s "
                "remote_sound_start_ms=%s settle_ms=%s ffmpeg_spawn_ms=%s "
                "first_pcm_write_ms=%s total_ms=%s returncode=%s",
                self.entry_id,
                self.client.host,
                timing.get("button_to_lock_ms"),
                timing.get("existing_sound_stop_ms"),
                timing.get("arbitration_ms"),
                timing.get("remote_sound_start_ms"),
                timing.get("settle_ms"),
                timing.get("ffmpeg_spawn_ms"),
                timing.get("first_pcm_write_ms"),
                self._elapsed_ms(timing_start),
                process.returncode,
            )
        await self._remote_stop()
        async with self._lock:
            await self._finish_priority()

    def _maybe_log_first_pcm_write(self, text: str) -> bool:
        if not text.startswith("out_time_ms="):
            return False
        try:
            out_time_ms = int(text.split("=", 1)[1])
        except ValueError:
            return False
        if out_time_ms <= 0 or self._active_timing_start is None:
            return False
        timing = self._active_timing
        first_pcm_write_ms = self._elapsed_ms(self._active_timing_start)
        if timing is not None:
            timing["first_pcm_write_ms"] = first_pcm_write_ms
        _LOGGER.info(
            "Aqara M1S sound timing first PCM write entity=%s host=%s "
            "first_pcm_write_ms=%s ffmpeg_out_time_ms=%s",
            self.entry_id,
            self.client.host,
            first_pcm_write_ms,
            out_time_ms,
        )
        return True

    async def async_stop(self) -> None:
        async with self._lock:
            await self._stop_locked(restore_previous=True)

    async def _stop_locked(
        self, *, restore_previous: bool, remote_stop: bool = True
    ) -> None:
        process = self._ffmpeg
        self._ffmpeg = None
        watch_task = self._watch_task
        self._watch_task = None
        self._active_timing_start = None
        self._active_timing = None
        if watch_task and watch_task is not asyncio.current_task():
            watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await watch_task
        if process is not None and process.returncode is None:
            process.terminate()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=2)
            if process.returncode is None:
                process.kill()
                await process.wait()
        if remote_stop:
            await self._remote_stop()
        if restore_previous:
            await self._finish_priority()

    async def _remote_stop(self) -> None:
        try:
            await self.hass.async_add_executor_job(
                self.client.run_command,
                REMOTE_STOP_COMMAND,
            )
        except Exception as err:
            _LOGGER.debug("Could not stop Aqara sound pipeline: %s", err)
