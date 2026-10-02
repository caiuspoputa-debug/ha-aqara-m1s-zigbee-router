from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.core import HomeAssistant

from .const import UPLOAD_SOUND_ROOT

MAX_UPLOAD_SIZE = 20 * 1024 * 1024


def _infer_uploaded_filename(content: bytes) -> str:
    """Identify an upload when an older selector omits the original filename."""
    if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        return "sound.wav"
    raise ValueError("The uploaded data is not a readable WAV file")


def _read_selected_file(
    hass: HomeAssistant,
    source: Any,
) -> tuple[str, bytes]:
    """Resolve one HA file-selector WAV upload."""
    value = source
    if isinstance(value, dict):
        if value.get("content"):
            encoded = str(value["content"]).split(",", 1)[-1]
            content = base64.b64decode(encoded, validate=True)
            if filename := value.get("filename"):
                return Path(str(filename)).name, content
            return _infer_uploaded_filename(content), content
        value = value.get("path") or value.get("file")

    if not isinstance(value, str):
        raise ValueError("The file selector did not return a readable file")

    if value.startswith("data:") and "," in value:
        _, encoded = value.split(",", 1)
        content = base64.b64decode(encoded, validate=True)
        return _infer_uploaded_filename(content), content

    try:
        with process_uploaded_file(hass, value) as uploaded_path:
            return uploaded_path.name, uploaded_path.read_bytes()
    except ValueError:
        pass

    path = Path(value)
    if not hass.config.is_allowed_path(str(path)):
        raise ValueError("The selected upload path is not allowed by Home Assistant")
    return path.name, path.read_bytes()


def read_uploaded_sound(
    hass: HomeAssistant,
    source: Any,
) -> tuple[str, bytes]:
    """Resolve one WAV upload for the existing service action."""
    filename, content = _read_selected_file(hass, source)
    return _validate_upload(filename, content)


def read_uploaded_sounds(
    hass: HomeAssistant,
    source: Any,
) -> list[tuple[str, bytes]]:
    """Resolve the single WAV selected from the Configure dialog."""
    return [read_uploaded_sound(hass, source)]


def destination_for_filename(filename: str) -> str:
    """Return the only remote destination managed by this integration."""
    safe_filename = Path(filename).name
    if not safe_filename.lower().endswith(".wav"):
        raise ValueError("Only .wav files can be uploaded")
    return f"{UPLOAD_SOUND_ROOT}/{safe_filename}"


def _validate_upload(filename: str, content: bytes) -> tuple[str, bytes]:
    if len(content) > MAX_UPLOAD_SIZE:
        raise ValueError("WAV file is larger than the 20 MiB safety limit")
    destination_for_filename(filename)
    return Path(filename).name, content
