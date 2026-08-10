from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
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
            if resume_radio:
                await self.radio_player.async_resume_after_priority_sound(True)
        finally:
            await self.group_manager.async_release_sound(self.entry_id)

    async def async_play(self, path: str, volume: int) -> None:
        """Play exactly one WAV using the known-good v0.6.0 transport."""
        safe_volume = max(0, min(100, int(volume))) / 100.0
        async with self._lock:
            await self._stop_locked(restore_previous=False)
            await self._begin_priority_locked()
            try:
                # Keep this sequence identical to v0.6.0 after focus arbitration.
                await self.hass.async_add_executor_job(
                    self.client.run_command,
                    remote_start_command(path),
                )
                await asyncio.sleep(0.35)

                ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
                input_url = f"tcp://{self.client.host}:{SOURCE_PORT}?tcp_nodelay=1"
                output_url = f"tcp://{self.client.host}:{SINK_PORT}?tcp_nodelay=1"
                args = [
                    ffmpeg,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "warning",
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
                    process = await asyncio.create_subprocess_exec(
                        *args,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE,
                    )
                except FileNotFoundError as err:
                    await self._remote_stop()
                    await self._finish_priority()
                    raise RuntimeError("FFmpeg was not found on Home Assistant") from err

                self._ffmpeg = process
                self._try_set_ffmpeg_priority(process.pid)
                self._watch_task = self.hass.async_create_task(self._watch(process))
            except Exception:
                if self._ffmpeg is None:
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

    async def _watch(self, process: asyncio.subprocess.Process) -> None:
        stderr = b""
        try:
            _, stderr = await process.communicate()
        except asyncio.CancelledError:
            return

        if self._ffmpeg is not process:
            return

        self._ffmpeg = None
        self._watch_task = None
        if process.returncode not in (0, -15):
            _LOGGER.warning(
                "Aqara M1S priority sound FFmpeg exited with code %s: %s",
                process.returncode,
                stderr.decode(errors="ignore")[-1000:],
            )
        elif process.returncode == 0:
            await asyncio.sleep(0.2)
        await self._remote_stop()
        async with self._lock:
            await self._finish_priority()

    async def async_stop(self) -> None:
        async with self._lock:
            await self._stop_locked(restore_previous=True)

    async def _stop_locked(self, *, restore_previous: bool) -> None:
        process = self._ffmpeg
        self._ffmpeg = None
        watch_task = self._watch_task
        self._watch_task = None
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
