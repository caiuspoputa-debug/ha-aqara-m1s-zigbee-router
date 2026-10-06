"""Pure group synchronization recovery policy.

This module deliberately has no Home Assistant dependencies so transport-loss
decisions can be exercised with deterministic simulations.
"""

from __future__ import annotations

from dataclasses import dataclass


GROUP_HARD_SYNC_LOSS_MS = 1000
GROUP_DRAIN_TIMEOUT_CONFIRMATIONS = 2
GROUP_STALE_CONFIRMATIONS = 3


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
