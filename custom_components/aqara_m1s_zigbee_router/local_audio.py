"""One hub-side ALSA gain for local WAVs and unchanged PCM transports."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import base64
import hashlib
import logging
import math
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import threading
from typing import Any
from urllib.parse import urlsplit

_LOGGER = logging.getLogger(__name__)
REMOTE_ROOT = "/data/m1s_audio_03714"
REMOTE_CONFIG = REMOTE_ROOT + "/alsa.conf"
REMOTE_CONTROL = REMOTE_ROOT + "/volume_ctl"
REMOTE_SOUND = REMOTE_ROOT + "/sound.sh"
ASSET_ROOT = Path(__file__).with_name("hub_audio")
ASSETS = ("volume_ctl", "alsa.conf", "sound.sh")
STORAGE_RESERVE_BYTES = 8 * 1024 * 1024
GAIN_MIN_DB = -80.0
GAIN_MAX_LEVEL = 1023


def gain_to_level(gain: float) -> int:
    if not math.isfinite(gain):
        raise ValueError("Volume must be finite")
    if gain <= 0:
        return 0
    if gain >= 1:
        return GAIN_MAX_LEVEL
    db = max(GAIN_MIN_DB, 20 * math.log10(gain))
    # ALSA reserves level zero for silence; the smallest positive UI step stays audible.
    return max(1, min(GAIN_MAX_LEVEL, round((db - GAIN_MIN_DB) / -GAIN_MIN_DB * GAIN_MAX_LEVEL)))


def level_to_gain(level: int) -> float:
    if level <= 0:
        return 0.0
    db = GAIN_MIN_DB + min(GAIN_MAX_LEVEL, level) / GAIN_MAX_LEVEL * -GAIN_MIN_DB
    return 10 ** (db / 20)


def safe_sound_path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/data/musics/"):
        raise ValueError("Sound must be an existing hub WAV under /data/musics")
    parts = PurePosixPath(path).parts
    if ".." in parts or any(ord(c) < 32 for c in path) or PurePosixPath(path).suffix.lower() != ".wav":
        raise ValueError("Invalid local WAV path")
    return str(PurePosixPath(path))


def safe_sound_url(url: str) -> str:
    if not isinstance(url, str) or any(ord(c) < 32 for c in url):
        raise ValueError("Invalid WAV URL")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("WAV URL must use HTTP or HTTPS")
    return url


def _gain_reply(output: str) -> int | None:
    match = re.search(r"(?m)^M1S_GAIN=(\d+)\s*$", output)
    return int(match.group(1)) if match else None


class LocalAudioBusy(RuntimeError):
    """The hub rejected playback before starting any audio process."""


class AqaraM1SLocalAudio:
    def __init__(self, hass: Any, client: Any) -> None:
        self.hass = hass
        self.client = client
        self._lock = asyncio.Lock()
        self._ready = False
        self._closed = False
        self._gain_task: asyncio.Task | None = None
        self._control_lock = threading.RLock()
        self._control_client = None
        self.desired_gain = 0.05
        self._sound_gain: float | None = None
        self._sound_muted = False
        self.applied_level: int | None = None
        self.last_error: str | None = None

    @property
    def apply_pending(self) -> bool:
        return gain_to_level(self._target_gain()) != self.applied_level

    def _target_gain(self) -> float:
        if self._sound_gain is not None and self._sound_muted:
            return 0.0
        return self.desired_gain if self._sound_gain is None else self._sound_gain

    def _isolated(self):
        return type(self.client)(host=self.client.host, port=self.client.port,
                                 username=self.client.username, password=self.client.password,
                                 timeout=8)

    @staticmethod
    def _command(client, command: str, timeout: float = 10) -> str:
        with client._lock:
            client._connect_locked().settimeout(0.02)
            return client._run_command_locked(command, timeout=timeout)

    def _run(self, command: str) -> str:
        # A private persistent channel avoids a fresh Telnet login for each
        # gain/start/status command. Never replay an uncertain playback command.
        with self._control_lock:
            if self._closed:
                raise RuntimeError("Local audio controller is closed")
            if self._control_client is None:
                self._control_client = self._isolated()
            try:
                return self._command(self._control_client, command)
            except Exception:
                self._disconnect_control()
                raise

    def _disconnect_control(self) -> None:
        with self._control_lock:
            client, self._control_client = self._control_client, None
            if client is not None:
                client.disconnect()

    def _provision(self) -> None:
        if self.client.zigbee_role == "coordinator":
            raise RuntimeError("Local audio must never be installed on a dedicated coordinator")
        isolated = self._isolated()
        try:
            self._command(isolated, f"mkdir -p {REMOTE_ROOT}")
            for name in ASSETS:
                content = (ASSET_ROOT / name).read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                destination = REMOTE_ROOT + "/" + name
                output = self._command(isolated, f"sha256sum {destination} 2>/dev/null")
                if digest in output:
                    continue
                temp = destination + "." + secrets.token_hex(4)
                encoded = base64.b64encode(content).decode("ascii")
                capacity = self._command(isolated,
                    "printf 'M1S_FREE_KB='; df -k /data 2>/dev/null | awk 'END {print $4}'")
                match = re.search(r"(?m)^M1S_FREE_KB=(\d+)\s*$", capacity)
                if match is None:
                    raise RuntimeError("Cannot verify local audio storage capacity")
                if int(match.group(1)) * 1024 < STORAGE_RESERVE_BYTES + len(encoded) + len(content):
                    raise RuntimeError("Local audio install would leave less than 8 MiB free on /data")
                try:
                    for offset in range(0, len(encoded), 512):
                        redirection = ">" if offset == 0 else ">>"
                        self._command(isolated, f"printf '%s' '{encoded[offset:offset + 512]}' "
                                      f"{redirection} {temp}.b64")
                    self._command(isolated, f"base64 -d {temp}.b64 > {temp}")
                    actual = self._command(isolated, f"sha256sum {temp}")
                    if digest not in actual:
                        raise RuntimeError(f"Local audio asset transfer failed: {name}")
                    mode = "700" if name in ("volume_ctl", "sound.sh") else "600"
                    installed = self._command(isolated,
                        f"chmod {mode} {temp} && mv {temp} {destination} && printf 'M1S_ASSET_OK\\n'")
                    if "M1S_ASSET_OK" not in installed.splitlines():
                        raise RuntimeError(f"Local audio asset install failed: {name}")
                finally:
                    self._command(isolated, f"rm -f {temp} {temp}.b64")
        finally:
            isolated.disconnect()

    def _ensure_gain(self, level: int) -> int:
        command = (
            f"if ! {REMOTE_CONTROL} get >/dev/null 2>&1; then "
            f"ALSA_CONFIG_PATH={REMOTE_CONFIG} aplay -D m1s_volume_init "
            "-t raw -f S32_LE -c 1 -r 32000 -d 1 /dev/zero >/dev/null 2>&1; fi; "
            f"{REMOTE_CONTROL} set {level}"
        )
        output = self._run(command)
        applied = _gain_reply(output)
        if applied != level:
            raise RuntimeError("Hub did not acknowledge its local ALSA volume")
        return applied

    async def async_prepare(self, gain: float) -> None:
        gain_to_level(float(gain))
        self.desired_gain = max(0.0, min(1.0, float(gain)))
        await self._async_prepare_gain()

    async def async_prepare_sound(self, gain: float, *, muted: bool = False) -> None:
        """Hold a notification-only gain after the media receiver has stopped."""
        gain_to_level(float(gain))
        output = await self.hass.async_add_executor_job(
            self._run,
            "if grep -q '^closed$' /proc/asound/card0/pcm0p/sub0/status; then "
            "printf 'M1S_AUDIO_IDLE\\n'; else printf 'M1S_AUDIO_BUSY\\n'; fi")
        if "M1S_AUDIO_BUSY" in output.splitlines():
            raise LocalAudioBusy("Hub audio has not yielded; sound volume was not applied")
        if "M1S_AUDIO_IDLE" not in output.splitlines():
            raise RuntimeError("Cannot confirm media released hub audio")
        self._sound_gain = max(0.0, min(1.0, float(gain)))
        self._sound_muted = muted
        await self._async_prepare_gain()

    async def async_restore_media(self, gain: float) -> None:
        """Clear the temporary gain and acknowledge media gain before resuming."""
        gain_to_level(float(gain))
        self.desired_gain = max(0.0, min(1.0, float(gain)))
        self._sound_gain = None
        await self._async_prepare_gain()

    async def _async_prepare_gain(self) -> None:
        async with self._lock:
            if self._closed:
                raise RuntimeError("Local audio controller is closed")
            try:
                if not self._ready:
                    await self.hass.async_add_executor_job(self._provision)
                    self._ready = True
                self.applied_level = await self.hass.async_add_executor_job(
                    self._ensure_gain, gain_to_level(self._target_gain()))
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                self._ready = False
                raise

    def request_gain(self, gain: float, *, sound_muted: bool | None = None) -> None:
        if not math.isfinite(gain):
            raise ValueError("Volume must be finite")
        self.desired_gain = max(0.0, min(1.0, float(gain)))
        if sound_muted is not None:
            self._sound_muted = sound_muted
        if self._closed or not self._ready:
            return
        if self._gain_task is None or self._gain_task.done():
            self._gain_task = self.hass.async_create_task(self._apply_requested_gain())

    async def _apply_requested_gain(self) -> None:
        try:
            await asyncio.sleep(0.03)
            async with self._lock:
                while not self._closed:
                    level = gain_to_level(self._target_gain())
                    if level == self.applied_level:
                        break
                    self.applied_level = await self.hass.async_add_executor_job(self._ensure_gain, level)
                    self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
            self._ready = False
            _LOGGER.warning("M1S local volume update failed host=%s: %s", self.client.host, exc)
        finally:
            self._gain_task = None

    async def async_start_sound(self, path: str) -> str:
        source = safe_sound_path(path)
        return await self._async_start_job("start", source)

    async def async_start_url(self, url: str) -> str:
        return await self._async_start_job("start-url", safe_sound_url(url))

    async def _async_start_job(self, action: str, source: str) -> str:
        token = secrets.token_hex(16)
        try:
            output = await self.hass.async_add_executor_job(
                self._run, f"{REMOTE_SOUND} {action} {token} {shlex.quote(source)}")
            if "M1S_AUDIO_BUSY" in output.splitlines():
                raise LocalAudioBusy("Hub audio is occupied; WAV was not started")
            if f"M1S_SOUND_STARTED:{token}" not in output.splitlines():
                raise RuntimeError("Hub rejected local WAV playback")
        except LocalAudioBusy:
            raise
        except Exception:
            with suppress(Exception):
                await self.async_stop_sound(token)
                await self.async_cleanup_sound(token)
            raise
        return token

    async def async_sound_status(self, token: str) -> tuple[str, int | None]:
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("Invalid playback token")
        output = await self.hass.async_add_executor_job(self._run, f"{REMOTE_SOUND} status {token}")
        for line in output.splitlines():
            match = re.fullmatch(r"DONE:(\d+)", line.strip())
            if match:
                return "done", int(match.group(1))
            if re.fullmatch(r"RUNNING:\d+:\d+", line.strip()) or line.strip() == "PENDING":
                return "running", None
            if re.fullmatch(r"DOWNLOADING:\d+:\d+", line.strip()):
                return "downloading", None
            if line.strip() == "MISSING":
                return "missing", None
        raise RuntimeError("Invalid local WAV status response")

    async def async_stop_sound(self, token: str) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("Invalid playback token")
        output = await self.hass.async_add_executor_job(self._run, f"{REMOTE_SOUND} stop {token}")
        if f"M1S_SOUND_STOPPED:{token}" not in output.splitlines():
            raise RuntimeError("Hub did not acknowledge local WAV stop")

    async def async_cleanup_sound(self, token: str) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("Invalid playback token")
        await self.hass.async_add_executor_job(self._run, f"{REMOTE_SOUND} cleanup {token}")

    async def async_shutdown(self) -> None:
        self._closed = True
        if self._gain_task is not None:
            with suppress(asyncio.CancelledError):
                await self._gain_task
        await self.hass.async_add_executor_job(self._disconnect_control)
