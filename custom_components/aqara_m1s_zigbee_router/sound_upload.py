from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.core import HomeAssistant

from .const import MANAGED_SOUND_ROOT

MAX_UPLOAD_SIZE = 20 * 1024 * 1024


def read_uploaded_sound(
    hass: HomeAssistant,
    source: Any,
) -> tuple[str, bytes]:
    """Resolve a HA file-selector upload or an allowed automation path."""
    value = source
    if isinstance(value, dict):
        if value.get("content"):
            encoded = str(value["content"]).split(",", 1)[-1]
            filename = str(value.get("filename") or "sound.wav")
            return _validate_upload(
                filename,
                base64.b64decode(encoded, validate=True),
            )
        value = value.get("path") or value.get("file")

    if not isinstance(value, str):
        raise ValueError("The file selector did not return a readable file")

    if value.startswith("data:audio/") and "," in value:
        return _validate_upload(
            "sound.wav",
            base64.b64decode(value.split(",", 1)[1], validate=True),
        )

    try:
        with process_uploaded_file(hass, value) as uploaded_path:
            return _validate_upload(
                uploaded_path.name,
                uploaded_path.read_bytes(),
            )
    except ValueError:
        pass

    path = Path(value)
    if not hass.config.is_allowed_path(str(path)):
        raise ValueError("The selected WAV path is not allowed by Home Assistant")
    return _validate_upload(path.name, path.read_bytes())


def destination_for_filename(filename: str) -> str:
    """Return the only remote destination managed by this integration."""
    safe_filename = Path(filename).name
    if not safe_filename.lower().endswith(".wav"):
        raise ValueError("Only .wav files can be uploaded")
    return f"{MANAGED_SOUND_ROOT}/{safe_filename}"


def _validate_upload(filename: str, content: bytes) -> tuple[str, bytes]:
    if len(content) > MAX_UPLOAD_SIZE:
        raise ValueError("WAV file is larger than the 20 MiB safety limit")
    destination_for_filename(filename)
    return Path(filename).name, content
