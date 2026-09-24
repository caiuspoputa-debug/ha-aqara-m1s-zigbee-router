from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile, is_zipfile

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.core import HomeAssistant

from .const import UPLOAD_SOUND_ROOT

MAX_UPLOAD_SIZE = 20 * 1024 * 1024
MAX_BATCH_FILES = 64
MAX_BATCH_TOTAL_SIZE = 100 * 1024 * 1024
MAX_BATCH_ARCHIVE_SIZE = 100 * 1024 * 1024


def _infer_uploaded_filename(content: bytes) -> str:
    """Identify an upload when an older selector omits the original filename."""
    if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        return "sound.wav"
    if is_zipfile(BytesIO(content)):
        return "sounds.zip"
    raise ValueError("The uploaded data is not a readable WAV or ZIP file")


def _read_selected_file(
    hass: HomeAssistant,
    source: Any,
) -> tuple[str, bytes]:
    """Resolve a HA file-selector upload without deciding WAV versus ZIP."""
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
    """Resolve one WAV or a ZIP batch selected from the Configure dialog."""
    filename, content = _read_selected_file(hass, source)
    if not filename.lower().endswith(".zip"):
        return [_validate_upload(filename, content)]

    if len(content) > MAX_BATCH_ARCHIVE_SIZE:
        raise ValueError("ZIP archive is larger than the 100 MiB safety limit")

    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = [
                info
                for info in archive.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".wav")
            ]

            if not entries:
                raise ValueError("ZIP archive does not contain any WAV files")
            if len(entries) > MAX_BATCH_FILES:
                raise ValueError(
                    f"ZIP archive contains more than {MAX_BATCH_FILES} WAV files"
                )

            total_size = 0
            seen_names: set[str] = set()
            result: list[tuple[str, bytes]] = []

            for info in entries:
                if info.flag_bits & 0x1:
                    raise ValueError("Encrypted ZIP entries are not supported")
                if info.file_size > MAX_UPLOAD_SIZE:
                    raise ValueError(
                        f"{Path(info.filename).name} is larger than the 20 MiB safety limit"
                    )

                total_size += info.file_size
                if total_size > MAX_BATCH_TOTAL_SIZE:
                    raise ValueError("ZIP WAV contents exceed the 100 MiB batch limit")

                safe_name = Path(info.filename).name
                name_key = safe_name.casefold()
                if name_key in seen_names:
                    raise ValueError(f"Duplicate WAV filename in ZIP: {safe_name}")
                seen_names.add(name_key)

                with archive.open(info, "r") as source_file:
                    wav_content = source_file.read(MAX_UPLOAD_SIZE + 1)
                result.append(_validate_upload(safe_name, wav_content))

            return result
    except BadZipFile as err:
        raise ValueError("Selected ZIP archive is invalid") from err


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
