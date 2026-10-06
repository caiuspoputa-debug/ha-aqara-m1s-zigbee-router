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


def _manager_method(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(GROUP_SOURCE.read_text(encoding="utf-8"))
    manager = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "AqaraM1SMediaGroupManager"
    )
    return next(
        node
        for node in manager.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def _standalone_manager_method(name: str):
    """Compile a dependency-free manager method for behavioral tests."""
    method = _manager_method(name)
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace: dict[str, object] = {}
    exec(compile(module, str(GROUP_SOURCE), "exec"), namespace)
    return namespace[name]


class GroupSyncLossSimulationTests(unittest.TestCase):
    def test_group_volume_preserves_hundredth_percent_precision(self):
        normalize = _standalone_manager_method("normalize_volume")

        self.assertEqual(normalize(0.0059), 0.0059)
        self.assertEqual(normalize(0.0060), 0.0060)
        self.assertEqual(normalize(0.0061), 0.0061)
        self.assertEqual(normalize(-1), 0.0)
        self.assertEqual(normalize(2), 1.0)

    def test_light_data_loss_keeps_every_receiver_untouched(self):
        for lag_ms in (35, 140, 350, 700, 999):
            decision = POLICY.decide_group_sync_recovery(shared_lag_ms=lag_ms)
            self.assertFalse(decision.requires_member_isolation, lag_ms)

    def test_one_short_drain_timeout_is_tolerated(self):
        decision = POLICY.decide_group_sync_recovery(
            consecutive_drain_timeouts=1
        )

        self.assertFalse(decision.requires_member_isolation)

    def test_two_drain_timeouts_quarantine_only_slow_member(self):
        decision = POLICY.decide_group_sync_recovery(
            consecutive_drain_timeouts=2
        )

        self.assertTrue(decision.requires_member_isolation)
        self.assertEqual(decision.trigger, "tcp_drain_timeouts")

    def test_confirmed_cursor_or_alsa_loss_requests_member_isolation(self):
        cursor = POLICY.decide_group_sync_recovery(shared_lag_ms=1000)
        unconfirmed_alsa = POLICY.decide_group_sync_recovery(stale_samples=2)
        confirmed_alsa = POLICY.decide_group_sync_recovery(stale_samples=3)

        self.assertTrue(cursor.requires_member_isolation)
        self.assertEqual(cursor.trigger, "shared_cursor_lag")
        self.assertFalse(unconfirmed_alsa.requires_member_isolation)
        self.assertTrue(confirmed_alsa.requires_member_isolation)
        self.assertEqual(confirmed_alsa.trigger, "alsa_stale")

    def test_automatic_fault_paths_never_pause_or_rebuild_healthy_cohort(self):
        source = GROUP_SOURCE.read_text(encoding="utf-8")
        writer = ast.unparse(_manager_method("_member_writer_loop"))
        reconcile = ast.unparse(_manager_method("_reconcile_loop"))
        health = ast.unparse(_manager_method("_probe_group_receiver_health"))

        self.assertNotIn("_schedule_receiver_cohort_resync", source)
        self.assertNotIn("_broadcast_pause_requested", source)
        self.assertNotIn("pause_rebuild_all_receivers", source)
        for method_source in (writer, reconcile, health):
            self.assertIn("_schedule_isolate_member", method_source)
            self.assertNotIn("_restart_stream_locked", method_source)
            self.assertNotIn("_stop_stream_locked", method_source)

    def test_failed_late_join_keeps_exponential_retry_history(self):
        prepare_source = ast.unparse(_manager_method("_prepare_member"))
        prime_position = prepare_source.index("await self._prime_late_join_member")
        reset_position = prepare_source.index(
            "self._set_member_retry(member, failed=False)"
        )

        self.assertGreater(reset_position, prime_position)

    def test_manual_resync_remains_explicit_full_timeline_restart(self):
        manual_source = ast.unparse(_manager_method("async_manual_resync"))

        self.assertIn("_restart_stream_locked", manual_source)


if __name__ == "__main__":
    unittest.main()
