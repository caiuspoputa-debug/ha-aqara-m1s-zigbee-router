"""Coordinator sideband tests with fake transport; no HA or hub required."""
import ast
import importlib.util
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
PACKAGE = "m1s_coordinator_io_test"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg
device = types.ModuleType(PACKAGE + ".device")
device.normalize_mac = lambda value: value
sys.modules[device.__name__] = device


def load(name):
    spec = importlib.util.spec_from_file_location(PACKAGE + "." + name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


io = load("coordinator_io")
client_module = load("client")
GOOD = dict(
    version=1,
    capabilities=3,
    rgb=[2, 3, 4],
    valid=True,
    raw=500,
    millivolts=439,
    lux=17,
)


class CoordinatorIOTests(unittest.TestCase):
    def setUp(self):
        self.client = client_module.AqaraM1SClient("192.0.2.1")
        self.client.zigbee_role = "coordinator"
        self.client.run_isolated_command = Mock(return_value=json.dumps(GOOD))
        self.client.run_command = Mock(
            side_effect=AssertionError("Main Telnet client must remain unused")
        )
        self.client._uart_send_locked = Mock(
            side_effect=AssertionError("Router UART must remain unused")
        )

    def test_rgb_uses_only_isolated_helper(self):
        self.client.set_rgb(2, 3, 4)
        command = self.client.run_isolated_command.call_args.args[0]
        self.assertEqual(
            command,
            f"test -x {io.HELPER} && {io.HELPER} rgb 2 3 4",
        )
        self.client.run_command.assert_not_called()
        self.client._uart_send_locked.assert_not_called()

    def test_isolated_command_disconnects_without_router_cleanup(self):
        client_type = client_module.AqaraM1SClient
        client = client_type("192.0.2.1")
        with (
            patch.object(client_type, "run_command", return_value="ok") as run,
            patch.object(client_type, "disconnect") as disconnect,
            patch.object(client_type, "close") as close,
        ):
            result = client.run_isolated_command("safe-command", timeout=4.0)
        self.assertEqual(result, "ok")
        run.assert_called_once_with("safe-command", timeout=4.0)
        disconnect.assert_called_once_with()
        close.assert_not_called()

    def test_lux_uses_one_start_and_one_get(self):
        with patch.object(client_module.time, "sleep") as sleep:
            result = self.client.read_illuminance()
        self.assertEqual(result, dict(raw=500, millivolts=439, lux=17))
        self.assertEqual(self.client.run_isolated_command.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_invalid_lux_is_unavailable_not_zero(self):
        self.client.run_isolated_command.return_value = json.dumps(
            dict(GOOD, valid=False, raw=0, millivolts=0, lux=0)
        )
        with patch.object(client_module.time, "sleep"):
            with self.assertRaises(TimeoutError):
                self.client.read_illuminance()

    def test_failure_clears_only_sideband_state(self):
        self.client.coordinator_io_state = GOOD
        self.client.run_isolated_command.side_effect = OSError("offline")
        with self.assertRaises(OSError):
            self.client.set_rgb(1, 2, 3)
        self.assertIsNone(self.client.coordinator_io_state)
        self.client.run_command.assert_not_called()
        self.client._uart_send_locked.assert_not_called()

    def test_protocol_and_ranges_are_strict(self):
        changes = [
            dict(version=2),
            dict(capabilities=1),
            dict(rgb=[1, 2]),
            dict(valid=1),
            dict(raw=4096),
            dict(millivolts=-1),
            dict(lux="17"),
        ]
        for change in changes:
            self.client.run_isolated_command.return_value = json.dumps(
                dict(GOOD, **change)
            )
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.client.set_rgb(1, 2, 3)

    def test_ambiguous_response_and_injection_are_rejected(self):
        self.client.run_isolated_command.return_value = (
            json.dumps(GOOD) + "\n" + json.dumps(GOOD)
        )
        with self.assertRaises(RuntimeError):
            io.request(self.client, "lux-get")
        self.client.run_isolated_command.reset_mock()
        with self.assertRaises(ValueError):
            io.request(self.client, "rgb", [1, 2, "3; reboot"])
        self.client.run_isolated_command.assert_not_called()

    def test_role_specific_lux_intervals(self):
        tree = ast.parse((ROOT / "coordinator.py").read_text(encoding="utf-8"))
        values = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    values[target.id] = node.value.value
        self.assertEqual(values["COORDINATOR_LUX_INTERVAL_SECONDS"], 60.0)
        self.assertEqual(values["LUX_INTERVAL_SECONDS"], 15.0)


if __name__ == "__main__":
    unittest.main()
