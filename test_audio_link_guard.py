"""Regression tests for clean individual-audio shutdown."""

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
MEDIA_GROUP_SHA256 = "33da7a17f7b782e7eca6baad5dc690c7e294d9dca6c6ec140cacec23726378a8"


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

    def test_group_transport_is_byte_identical_to_v0362(self):
        group_source = SOURCE.with_name("media_group.py")
        actual = hashlib.sha256(group_source.read_bytes()).hexdigest()
        self.assertEqual(actual, MEDIA_GROUP_SHA256)


if __name__ == "__main__":
    unittest.main()
