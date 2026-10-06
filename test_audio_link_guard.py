"""Regression tests for the individual and group audio transports."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).parent
SOURCE = (
    ROOT
    / "custom_components"
    / "aqara_m1s_zigbee_router"
    / "media_player.py"
)
GROUP_SOURCE = SOURCE.with_name("media_group.py")
MEDIA_PLAYER_SHA256 = "1f8953bb3c9ecde01876d8b08492b27395c163b56f53aa68789e215d7624c2a8"
MEDIA_GROUP_SHA256 = "be908398f72fe5db5e56537962061731a1a14d3525ddb42fc17d4aa1433cc89d"


def evaluated_constants(source: Path = SOURCE) -> dict[str, object]:
    """Evaluate simple module constants without importing Home Assistant."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    namespace: dict[str, object] = {
        "__builtins__": {"int": int, "max": max},
    }
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            namespace[target.id] = eval(
                compile(ast.Expression(node.value), str(source), "eval"),
                namespace,
                namespace,
            )
        except (NameError, TypeError, ValueError):
            continue
    return namespace


class AudioCleanShutdownTests(unittest.TestCase):
    def test_remote_commands_are_scoped_short_and_shell_valid(self):
        values = evaluated_constants()
        start = str(values["REMOTE_START_COMMAND"])
        stop = str(values["REMOTE_STOP_COMMAND"])

        # The stock Telnet shell accepts a command line up to roughly 1024
        # bytes. Keep the proven receiver command below 1000 with margin for LF.
        self.assertLessEqual(len(start), 1000)
        self.assertLessEqual(len(stop), 1000)
        self.assertIn("nc -l -p 12346", start)
        self.assertIn("aplay -t raw -f S32_LE -c 1 -r 32000", start)
        self.assertIn("--buffer-time=2000000", start)
        self.assertIn("--period-time=35000", start)
        self.assertIn("renice -3", start)
        self.assertNotIn("killall", start)
        self.assertNotIn("killall", stop)
        self.assertNotIn("audio_guard", start)
        self.assertNotIn("/proc/$NPID", start)

        for command in (start, stop):
            checked = subprocess.run(
                ["sh", "-n", "-c", command],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_shutdown_pre_stops_remote_before_local_writer(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        radio_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "AqaraM1SRadioPlayer"
        )
        shutdown = next(
            node
            for node in radio_class.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_shutdown"
        )
        source = ast.unparse(shutdown)

        self.assertLess(source.index("REMOTE_STOP_COMMAND"), source.index("self._stop_locked"))
        self.assertIn("remote_cleanup=False", source)

    def test_no_active_polling_guard_was_added(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("REMOTE_GUARD", source)
        self.assertNotIn("idle_ticks", source)
        self.assertNotIn("m1s_audio_guard", source)

    def test_individual_buffering_and_rebase_diagnostics_are_exposed(self):
        source = SOURCE.read_text(encoding="utf-8")

        self.assertIn("self._attr_state = MediaPlayerState.BUFFERING", source)
        self.assertIn('"single_last_playout_rebase_lag_ms"', source)
        self.assertIn('"single_last_playout_rebase_cause"', source)
        self.assertIn('"single_last_tcp_drain_ms"', source)
        self.assertIn('likely_cause = "tcp_drain_timeout"', source)
        self.assertIn('likely_cause = "ha_scheduler_or_other_await"', source)

    def test_group_latest_request_wins_before_and_after_media_resolution(self):
        tree = ast.parse(GROUP_SOURCE.read_text(encoding="utf-8"))
        entity_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "AqaraM1SMediaGroup"
        )
        play = next(
            node
            for node in entity_class.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "async_play_media"
        )
        source = ast.unparse(play)

        self.assertLess(
            source.index("next_media_intent"),
            source.index("async_resolve_media"),
        )
        self.assertIn("intent_generation=intent_generation", source)

    def test_group_stop_releases_individual_players(self):
        tree = ast.parse(GROUP_SOURCE.read_text(encoding="utf-8"))
        manager_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "AqaraM1SMediaGroupManager"
        )
        stop = next(
            node
            for node in manager_class.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_stop"
        )
        reset = next(
            node
            for node in manager_class.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "async_force_reset"
        )

        self.assertIn("_resume_suspended_individuals", ast.unparse(stop))
        self.assertIn("_resume_suspended_individuals", ast.unparse(reset))

    def test_group_recovery_is_bounded_and_member_scoped(self):
        values = evaluated_constants(GROUP_SOURCE)
        source = GROUP_SOURCE.read_text(encoding="utf-8")

        self.assertEqual(values["STARTUP_RESTORE_MAX_WAIT_SECONDS"], 30.0)
        self.assertEqual(values["GROUP_RECEIVER_STALE_CONFIRMATIONS"], 3)
        self.assertFalse(values["ADAPTIVE_SYNC_ENABLED"])
        self.assertFalse(values["PERIODIC_RECEIVER_RESYNC_ENABLED"])
        self.assertIn("confirmed stale ALSA receiver", source)
        self.assertIn("timeout_partial_cohort", source)
        self.assertIn('"source_rebuffering"', source)

    def test_group_transport_matches_v0370_reviewed_baseline(self):
        actual = hashlib.sha256(GROUP_SOURCE.read_bytes()).hexdigest()
        self.assertEqual(actual, MEDIA_GROUP_SHA256)

    def test_individual_transport_matches_v0370_reviewed_baseline(self):
        actual = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        self.assertEqual(actual, MEDIA_PLAYER_SHA256)


if __name__ == "__main__":
    unittest.main()
