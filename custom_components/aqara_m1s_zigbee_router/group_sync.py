"""Pure group synchronization recovery policy.

This module deliberately has no Home Assistant dependencies so transport-loss
decisions can be exercised with deterministic simulations.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping


GROUP_HARD_SYNC_LOSS_MS = 1000
GROUP_DRAIN_TIMEOUT_CONFIRMATIONS = 2
GROUP_STALE_CONFIRMATIONS = 3
COHORT_ALIGNMENT_COOLDOWN_SECONDS = 60.0
COHORT_ALIGNMENT_SETTLE_SECONDS = 3.0
RECEIVER_TIMING_CONFIRMATIONS = 3
RECEIVER_TIMING_DRIFT_MS = 200.0


@dataclass(frozen=True)
class GroupSyncDecision:
    """Describe whether one receiver must leave the healthy live cohort."""

    requires_member_isolation: bool
    trigger: str | None = None


def decide_group_sync_recovery(
    *,
    shared_lag_ms: int = 0,
    consecutive_drain_timeouts: int = 0,
    stale_samples: int = 0,
) -> GroupSyncDecision:
    """Return a deterministic recovery action for one receiver snapshot."""
    if shared_lag_ms >= GROUP_HARD_SYNC_LOSS_MS:
        return GroupSyncDecision(True, "shared_cursor_lag")
    if consecutive_drain_timeouts >= GROUP_DRAIN_TIMEOUT_CONFIRMATIONS:
        return GroupSyncDecision(True, "tcp_drain_timeouts")
    if stale_samples >= GROUP_STALE_CONFIRMATIONS:
        return GroupSyncDecision(True, "alsa_stale")
    return GroupSyncDecision(False)


@dataclass
class CohortAlignmentGate:
    """Coalesce recovery requests; a flapping hub cannot restart peers rapidly."""

    pending_since: float | None = None
    reason: str | None = None
    last_attempt: float | None = None

    def request(self, now: float, reason: str) -> None:
        if self.pending_since is None:
            self.pending_since = now
            self.reason = reason

    def due(self, now: float, *, has_receivers: bool, has_healthy: bool) -> bool:
        if self.pending_since is None or not has_receivers:
            return False
        if not has_healthy:
            return True
        return (
            now - self.pending_since >= COHORT_ALIGNMENT_SETTLE_SECONDS
            and (
                self.last_attempt is None
                or now - self.last_attempt >= COHORT_ALIGNMENT_COOLDOWN_SECONDS
            )
        )

    def mark_attempt(self, now: float) -> None:
        self.last_attempt = now
        self.pending_since = None
        self.reason = None

    def reset(self) -> None:
        self.pending_since = None
        self.reason = None
        self.last_attempt = None


class ReceiverTimingGuard:
    """Confirm changes in relative ALSA queue delay, not acoustic phase.

    The caller supplies fresh, plausible, low-latency samples only. Fixed
    per-device queue differences are baselined instead of causing reset loops.
    """

    def __init__(self) -> None:
        self.baseline: dict[str, float] = {}
        self.confirmations = 0
        self.spread_ms: float | None = None

    def reset(self) -> None:
        self.baseline.clear()
        self.confirmations = 0
        self.spread_ms = None

    def observe(self, delays_ms: Mapping[str, float]) -> bool:
        if len(delays_ms) < 2:
            self.confirmations = 0
            self.spread_ms = None
            return False
        if set(delays_ms) != set(self.baseline):
            self.baseline = dict(delays_ms)
            self.confirmations = 0
            self.spread_ms = 0.0
            return False
        changes = [delays_ms[key] - self.baseline[key] for key in delays_ms]
        self.spread_ms = max(changes) - min(changes)
        if self.spread_ms >= RECEIVER_TIMING_DRIFT_MS:
            self.confirmations += 1
        else:
            self.confirmations = 0
        return self.confirmations >= RECEIVER_TIMING_CONFIRMATIONS
