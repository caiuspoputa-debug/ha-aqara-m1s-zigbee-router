"""Local sideband tests with fake transport; no HA or live hub required."""
import importlib.util
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
PACKAGE = "m1s_io_test"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg
device = types.ModuleType(PACKAGE + ".device")
device.normalize_mac = lambda value: value
sys.modules[device.__name__] = device


def load(name):
    spec = importlib.util.spec_from_file_location(PACKAGE + "." + name, ROOT / (name + ".py"))
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


class Tests(unittest.TestCase):
    def setUp(self):
        self.client = client_module.AqaraM1SClient("192.0.2.1")
        self.client.zigbee_role = "coordinator"
        self.client.run_command = Mock(return_value=json.dumps(GOOD))
        self.client._uart_send_locked = Mock(
            side_effect=AssertionError("No coordinator UART writes")
        )
        self.client._connect_uart_locked = Mock(
            side_effect=AssertionError("No second UART connection")
        )

    def test_rgb_routes_to_sideband(self):
        self.client.set_rgb(2, 3, 4)
        self.assertEqual(self.client.coordinator_io_state, GOOD)
        self.assertEqual(
            self.client.run_command.call_args.args[0],
            io.HELPER + " rgb 2 3 4",
        )
        self.client._uart_send_locked.assert_not_called()

    def test_failure_never_falls_back_to_uart(self):
        self.client.run_command.side_effect = OSError("unavailable")
        with self.assertRaises(RuntimeError):
            self.client.set_rgb(1, 2, 3)
        self.assertIsNone(self.client.coordinator_io_state)
        self.assertEqual(self.client.run_command.call_count, 2)
        self.client._uart_send_locked.assert_not_called()

    def test_relay_transport_fallback(self):
        self.client.run_command.side_effect = [
            RuntimeError("wrapper unavailable"),
            json.dumps(GOOD),
        ]
        self.client.set_rgb(2, 3, 4)
        self.assertEqual(
            self.client.run_command.call_args.args[0],
            io.RELAY + " --io rgb 2 3 4",
        )
        self.client._uart_send_locked.assert_not_called()

    def test_legacy_helper_rejected(self):
        self.client.run_command.return_value = "Usage: UART PORT"
        with self.assertRaises(RuntimeError):
            self.client.set_rgb(1, 2, 3)
        self.assertIsNone(self.client.coordinator_io_state)

    def test_lux_success(self):
        with patch.object(client_module.time, "sleep"):
            result = self.client.read_illuminance()
        self.assertEqual(result, dict(raw=500, millivolts=439, lux=17))
        self.assertEqual(self.client.run_command.call_count, 2)
        self.client._connect_uart_locked.assert_not_called()

    def test_lux_invalid_is_not_zero(self):
        self.client.run_command.return_value = json.dumps(
            dict(GOOD, valid=False, raw=0, millivolts=0, lux=0)
        )
        with patch.object(client_module.time, "sleep"):
            with self.assertRaises(TimeoutError):
                self.client.read_illuminance()
        self.assertEqual(self.client.run_command.call_count, 2)

    def test_bad_response_types_and_ranges(self):
        changes = [
            dict(error="timeout"),
            dict(version=2),
            dict(rgb=[1, 2]),
            dict(rgb=[True, 1, 2]),
            dict(raw=5000),
            dict(valid=1),
            dict(millivolts=-1),
            dict(lux="1"),
        ]
        for change in changes:
            self.client.run_command.return_value = json.dumps(dict(GOOD, **change))
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.client.set_rgb(1, 2, 3)

    def test_ambiguous_response_rejected(self):
        self.client.run_command.return_value = (
            json.dumps(GOOD) + "\n" + json.dumps(GOOD)
        )
        with self.assertRaises(RuntimeError):
            io.request(self.client, "state")

    def test_no_command_injection(self):
        with self.assertRaises(ValueError):
            io.request(self.client, "rgb", [1, 2, "3; reboot"])
        with self.assertRaises(ValueError):
            io.request(self.client, "state; reboot")
        self.client.run_command.assert_not_called()

    def test_router_rgb_unchanged(self):
        self.client.zigbee_role = "router"
        self.client._uart_send_locked = Mock()
        self.client.set_rgb(2, 3, 4)
        self.client._uart_send_locked.assert_called_once_with(
            bytes([0xA5, 2, 3, 4, 0xA0])
        )
        self.client.run_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
