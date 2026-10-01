"""Coordinator MQTT IO tests; no Home Assistant runtime or hub required."""
import asyncio
import importlib.util
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


ROOT = pathlib.Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
PACKAGE = "m1s_coordinator_mqtt_test"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg
device = types.ModuleType(PACKAGE + ".device")
device.normalize_mac = lambda value: value
sys.modules[device.__name__] = device

homeassistant = types.ModuleType("homeassistant")
components = types.ModuleType("homeassistant.components")
mqtt = types.ModuleType("homeassistant.components.mqtt")
core = types.ModuleType("homeassistant.core")
core.HomeAssistant = object
core.callback = lambda function: function
components.mqtt = mqtt
homeassistant.components = components
sys.modules["homeassistant"] = homeassistant
sys.modules["homeassistant.components"] = components
sys.modules["homeassistant.components.mqtt"] = mqtt
sys.modules["homeassistant.core"] = core


def load(name):
    spec = importlib.util.spec_from_file_location(PACKAGE + "." + name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


coordinator_mqtt = load("coordinator_mqtt")
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


class FakeCoordinator:
    def __init__(self):
        self.data = {"online": True, "online_generation": 1}

    def async_set_updated_data(self, data):
        self.data = data


class CoordinatorMQTTTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = types.SimpleNamespace(
            host="192.168.0.220",
            coordinator_io_state=None,
        )
        self.coordinator = FakeCoordinator()
        self.hass = types.SimpleNamespace(loop=asyncio.get_running_loop())
        self.bridge = coordinator_mqtt.CoordinatorMQTTIO(
            self.hass, self.client, self.coordinator
        )

    async def test_current_ip_defines_topics(self):
        self.assertEqual(self.bridge.base_topic, "m1s/220/io")
        self.assertEqual(
            coordinator_mqtt.coordinator_io_base_topic("192.168.0.220"),
            "m1s/220/io",
        )

    async def test_subscribe_and_rgb_publish(self):
        unsubscribers = [Mock(), Mock(), Mock(), Mock()]
        mqtt.async_wait_for_mqtt_client = AsyncMock()
        mqtt.async_subscribe = AsyncMock(side_effect=unsubscribers)
        mqtt.async_publish = AsyncMock()
        await self.bridge.async_start()
        topics = [call.args[1] for call in mqtt.async_subscribe.call_args_list]
        self.assertEqual(
            topics,
            [
                "m1s/220/io/state",
                "m1s/220/telemetry",
                "m1s/220/sound/status",
                "m1s/220/io/availability",
            ],
        )
        await self.bridge.async_set_rgb(2, 3, 4)
        mqtt.async_publish.assert_awaited_with(
            self.bridge.hass,
            "m1s/220/io/rgb/set",
            "2,3,4",
            qos=0,
            retain=False,
        )
        await self.bridge.async_stop()
        for unsubscribe in unsubscribers:
            unsubscribe.assert_called_once_with()

    async def test_local_sound_prepare_uses_mqtt_and_waits_for_ready(self):
        mqtt.async_publish = AsyncMock()
        self.client.is_deletable_sound_path = Mock(return_value=True)

        task = asyncio.create_task(
            self.bridge.async_prepare_sound("/data/musics/music-ch/test.wav")
        )
        await asyncio.sleep(0)
        self.bridge._sound_status_message(types.SimpleNamespace(payload="ready"))
        await task

        mqtt.async_publish.assert_awaited_with(
            self.bridge.hass,
            "m1s/220/sound/prepare",
            "/data/musics/music-ch/test.wav",
            qos=0,
            retain=False,
        )

    async def test_state_updates_rgb_and_lux(self):
        self.bridge._state_message(types.SimpleNamespace(payload=json.dumps(GOOD)))
        self.assertTrue(self.bridge.available)
        self.assertEqual(self.client.coordinator_io_state, GOOD)
        self.assertEqual(
            self.coordinator.data["illuminance"],
            {"raw": 500, "millivolts": 439, "lux": 17},
        )

    async def test_telemetry_updates_all_coordinator_diagnostics(self):
        telemetry = {
            "temperature": 29.0,
            "wifi_ip": "192.168.0.220",
            "homekit_process": "running",
            "mqtt_process": "running",
            "telnet_process": "running",
            "coordinator_process": "running",
            "mqtt_io_process": "running",
        }
        self.bridge._telemetry_message(
            types.SimpleNamespace(payload=json.dumps(telemetry))
        )
        self.assertEqual(self.bridge.telemetry, telemetry)
        self.assertEqual(self.coordinator.data["telemetry"], telemetry)

    async def test_offline_clears_only_optional_io(self):
        self.bridge._state_message(types.SimpleNamespace(payload=json.dumps(GOOD)))
        self.bridge._availability_message(types.SimpleNamespace(payload="offline"))
        self.assertFalse(self.bridge.available)
        self.assertIsNone(self.client.coordinator_io_state)
        self.assertIsNone(self.coordinator.data["illuminance"])
        self.assertTrue(self.coordinator.data["online"])

    async def test_protocol_and_ranges_are_strict(self):
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
            with self.subTest(change=change), self.assertRaises(ValueError):
                coordinator_mqtt.validate_state(json.dumps(dict(GOOD, **change)))

    async def test_client_blocks_coordinator_telnet_sideband(self):
        client = client_module.AqaraM1SClient("192.168.0.220")
        client.zigbee_role = "coordinator"
        client.run_isolated_command = Mock(
            side_effect=AssertionError("Coordinator Telnet must remain unused")
        )
        client.run_command = Mock(
            side_effect=AssertionError("Coordinator Telnet must remain unused")
        )
        with self.assertRaisesRegex(RuntimeError, "MQTT-only"):
            client.set_rgb(1, 2, 3)
        with self.assertRaisesRegex(RuntimeError, "MQTT-only"):
            client.read_illuminance()
        client.run_isolated_command.assert_not_called()
        client.run_command.assert_not_called()

    async def test_online_probe_retries_transient_telnet_accept_delays(self):
        client = client_module.AqaraM1SClient("192.168.0.220")
        connected = Mock()
        with (
            patch.object(
                client_module.socket,
                "create_connection",
                side_effect=[OSError("busy"), OSError("busy"), connected],
            ) as create_connection,
            patch.object(client_module.time, "sleep") as sleep,
        ):
            self.assertTrue(client.check_online())
        self.assertEqual(create_connection.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        connected.close.assert_called_once_with()

    async def test_online_probe_reports_offline_after_all_attempts_fail(self):
        client = client_module.AqaraM1SClient("192.168.0.220")
        with (
            patch.object(
                client_module.socket,
                "create_connection",
                side_effect=OSError("offline"),
            ) as create_connection,
            patch.object(client_module.time, "sleep") as sleep,
        ):
            self.assertFalse(client.check_online())
        self.assertEqual(create_connection.call_count, 3)
        self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
