"""Transport boundaries on the existing PCM clock, without a second timer."""
from __future__ import annotations


def next_batch_boundary(cursor: int, origin: int, period_ms: int, target_ms: int) -> int:
    elapsed = max(0, cursor - origin)
    batch = elapsed * period_ms // target_ms + 1
    return origin + (batch * target_ms + period_ms - 1) // period_ms
