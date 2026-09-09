"""Read ICY on a separate HTTP connection; never touch playback or PCM."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)
_TITLE = re.compile(r"(?:^|;)\s*StreamTitle='(.*?)';", re.IGNORECASE | re.DOTALL)


def parse_stream_title(block: bytes) -> tuple[bool, str | None, str | None]:
    """Distinguish absent metadata (unchanged) from an explicitly empty title."""
    raw = block.rstrip(b"\x00")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    match = _TITLE.search(text)
    if match is None:
        return False, None, None
    title = match.group(1).strip()
    artist, separator, track = title.partition(" - ")
    if separator and artist.strip() and track.strip():
        return True, track.strip(), artist.strip()
    return True, title or None, None


def is_icy_candidate(url: str) -> bool:
    """Exclude known single-client Cast transports before any HTTP request.

    Probing their headers is already destructive: accepting a second client
    closes FFmpeg's response. This must happen before session.get(), regardless
    of the configured host/port or whether the player was restored from state.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        return False
    path = parts.path
    # Current continuous WAV bridge and earlier token-based Cast sessions.
    if re.fullmatch(r"/stream/[^/]+/[0-9]+\.wav/?", path, re.IGNORECASE):
        return False
    if re.fullmatch(r"/audio/[^/]+/[^/]+/[0-9]+/?", path):
        return False
    return True


async def watch_icy_metadata(
    session: ClientSession,
    url: str,
    update: Callable[[str | None, str | None, str | None], None],
) -> None:
    """Discard this connection's audio; retry metadata failures independently."""
    if not is_icy_candidate(url):
        return
    retry_delay = 15
    while True:
        try:
            async with session.get(
                url,
                headers={"Icy-MetaData": "1", "Accept-Encoding": "identity"},
                timeout=ClientTimeout(total=None, connect=10, sock_read=30),
                auto_decompress=False,
            ) as response:
                response.raise_for_status()
                station = response.headers.get("icy-name", "").strip() or None
                update(None, None, station)
                try:
                    interval = int(response.headers.get("icy-metaint", "0"))
                except ValueError:
                    return
                # Unsupported streams/playlists/HLS: close immediately, do not poll.
                if not 0 < interval <= 1024 * 1024:
                    return
                while True:
                    remaining = interval
                    while remaining:
                        count = min(remaining, 16384)
                        await response.content.readexactly(count)
                        remaining -= count
                    length = (await response.content.readexactly(1))[0] * 16
                    if not length:
                        continue  # Zero-length blocks mean unchanged metadata.
                    block = await response.content.readexactly(length)
                    present, title, artist = parse_stream_title(block)
                    if present:
                        update(title, artist, station)
                        retry_delay = 15
        except asyncio.CancelledError:
            raise
        except Exception as err:
            # Do not expose signed URLs or feed errors into the audio watchdog.
            _LOGGER.debug("M1S ICY reader disconnected (%s)", type(err).__name__)
        update(None, None, None)
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 120)
