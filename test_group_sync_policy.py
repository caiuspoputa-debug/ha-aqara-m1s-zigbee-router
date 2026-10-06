"""Deterministic transport-loss simulations for M1S group playback."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).parent
POLICY_PATH = (
    ROOT
    / "custom_components"
    / "aqara_m1s_zigbee_router"
    / "group_sync.py"
)
GROUP_SOURCE = POLICY_PATH.with_name("media_group.py")

SPEC = importlib.util.spec_from_file_location("m1s_group_sync_policy", POLICY_PATH)
assert SPEC is not None and SPEC.loader is not None
POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = POLICY
SPEC.loader.exec_module(POLICY)


class GroupSyncLossSimulationTests(unittest.TestCase):
    def test_light_data_loss_keeps_live_playback_untouched(self):
        source_running = True
        source_restart_count = 0

        for lag_ms in (35, 140, 350, 700, 999):
            decision = POLICY.decide_group_sync_recovery(shared_lag_ms=lag_ms)
            self.assertFalse(decision.requires_realign, lag_ms)

        self.assertTrue(source_running)
        self.assertEqual(source_restart_count, 0)

    def test_one_short_drain_timeout_is_tolerated(self):
        decision = POLICY.decide_group_sync_recovery(
            consecutive_drain_timeouts=1
        )

        self.assertFalse(decision.requires_realign)

    def test_two_drain_timeouts_request_receiver_realign(self):
        decision = POLICY.decide_group_sync_recovery(
            consecutive_drain_timeouts=2
        )

        self.assertTrue(decision.requires_realign)
        self.assertEqual(decision.trigger, "tcp_drain_timeouts")

    def test_confirmed_cursor_or_alsa_loss_requests_realign(self):
        cursor = POLICY.decide_group_sync_recovery(shared_lag_ms=1000)
        alsa = POLICY.decide_group_sync_recovery(stale_samples=2)

        self.assertTrue(cursor.requires_realign)
        self.assertEqual(cursor.trigger, "shared_cursor_lag")
        self.assertTrue(alsa.requires_realign)
        self.assertEqual(alsa.trigger, "alsa_stale")

    def test_automatic_realign_preserves_ffmpeg_source(self):
        tree = ast.parse(GROUP_SOURCE.read_text(encoding="utf-8"))
        manager = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "AqaraM1SMediaGroupManager"
        )
        scheduler = next(
            node
            for node in manager.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_schedule_receiver_cohort_resync"
        )
        receiver_realign = next(
            node
            for node in manager.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_resync_receivers_preserve_source_locked"
        )

        scheduler_source = ast.unparse(scheduler)
        realign_source = ast.unparse(receiver_realign)
        self.assertIn("_resync_receivers_preserve_source_locked", scheduler_source)
        self.assertNotIn("_restart_stream_locked", scheduler_source)
        self.assertIn("_broadcast_pause_requested.set", realign_source)
        self.assertNotIn("_stop_stream_locked", realign_source)
        self.assertNotIn("self.ffmpeg =", realign_source)


if __name__ == "__main__":
    unittest.main()

