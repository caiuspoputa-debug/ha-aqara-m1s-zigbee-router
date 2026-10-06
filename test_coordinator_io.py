"""Coordinator MQTT IO tests; no Home Assistant runtime or hub required."""
import asyncio
import importlib.util
import json
import pathlib
import socket
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
    role="coordinator",
    rgb=[2, 3, 4],
    valid=True,
    raw=500,
    millivolts=439,
    lux=17,
)


class FakeCoordinator:
    def __init__(self, entry=None):
        self.data = {"online": True, "online_generation": 1}
        self.config_entry = entry
        self.refresh_count = 0

    def async_set_updated_data(self, data):
        raise AssertionError("MQTT callbacks must not mark an update successful")

    async def async_request_refresh(self):
        self.refresh_count += 1


class CoordinatorMQTTTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.entry = types.SimpleNamespace(data={})
        self.client = types.SimpleNamespace(
            host="192.168.0.220",
            zigbee_role="coordinator",
            mqtt_io_confirmed=False,
            coordinator_io_state=None,
            check_online=Mock(),
        )
        self.coordinator = FakeCoordinator(self.entry)
        config_entries = types.SimpleNamespace(
            async_update_entry=lambda entry, data: setattr(entry, "data", data)
        )
        self.hass = types.SimpleNamespace(
            loop=asyncio.get_running_loop(),
            config_entries=config_entries,
            async_create_task=asyncio.create_task,
        )
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
                "m1s/220/io/availability",
                "m1s/220/sound/status",
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
        await self.bridge._refresh_task
        self.assertTrue(self.bridge.available)
        self.assertTrue(self.client.mqtt_io_confirmed)
        self.assertTrue(self.entry.data["mqtt_io_confirmed"])
        self.assertEqual(self.client.coordinator_io_state, GOOD)
        self.assertEqual(
            self.coordinator.data["illuminance"],
            {"raw": 500, "millivolts": 439, "lux": 17},
        )
        self.assertEqual(self.coordinator.refresh_count, 1)

    async def test_retained_state_cannot_override_offline_availability(self):
        self.bridge._state_message(
            types.SimpleNamespace(payload=json.dumps(GOOD), retain=True)
        )
        await self.bridge._refresh_task
        self.assertFalse(self.bridge.available)
        self.assertEqual(self.client.coordinator_io_state, GOOD)
        self.assertEqual(self.coordinator.refresh_count, 1)

    async def test_telemetry_updates_all_coordinator_diagnostics(self):
        telemetry = {
            "role": "coordinator",
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
        await self.bridge._refresh_task
        self.assertEqual(self.bridge.telemetry, telemetry)
        self.assertEqual(self.coordinator.data["telemetry"], telemetry)
        self.assertEqual(self.coordinator.refresh_count, 1)

    async def test_offline_clears_only_optional_io(self):
        self.bridge._state_message(types.SimpleNamespace(payload=json.dumps(GOOD)))
        self.bridge._availability_message(types.SimpleNamespace(payload="offline"))
        await self.bridge._refresh_task
        self.assertFalse(self.bridge.available)
        self.assertIsNone(self.client.coordinator_io_state)
        self.assertIsNone(self.coordinator.data["illuminance"])
        self.assertTrue(self.coordinator.data["online"])
        self.assertEqual(self.coordinator.refresh_count, 1)

    async def test_online_availability_requests_coordinator_refresh(self):
        self.bridge._availability_message(types.SimpleNamespace(payload="online"))
        await self.bridge._refresh_task
        self.assertTrue(self.bridge.available)
        self.assertEqual(self.coordinator.refresh_count, 1)

    async def test_mqtt_online_proves_hub_connectivity_without_telnet(self):
        mqtt_io = types.SimpleNamespace(available=True)
        self.hass.async_add_executor_job = AsyncMock()
        online, source = await coordinator_mqtt.async_detect_hub_connectivity(
            self.hass, self.client, mqtt_io
        )
        self.assertTrue(online)
        self.assertEqual(source, "mqtt")
        self.hass.async_add_executor_job.assert_not_awaited()

    async def test_telnet_is_fallback_when_mqtt_is_not_online(self):
        mqtt_io = types.SimpleNamespace(available=False)
        self.hass.async_add_executor_job = AsyncMock(return_value=True)
        online, source = await coordinator_mqtt.async_detect_hub_connectivity(
            self.hass, self.client, mqtt_io
        )
        self.assertTrue(online)
        self.assertEqual(source, "telnet")
        self.hass.async_add_executor_job.assert_awaited_once_with(
            self.client.check_online
        )

    async def test_hub_is_offline_only_when_mqtt_and_telnet_are_both_down(self):
        mqtt_io = types.SimpleNamespace(available=False)
        self.hass.async_add_executor_job = AsyncMock(return_value=False)
        online, source = await coordinator_mqtt.async_detect_hub_connectivity(
            self.hass, self.client, mqtt_io
        )
        self.assertFalse(online)
        self.assertEqual(source, "none")

    async def test_protocol_and_ranges_are_strict(self):
        changes = [
            dict(version=2),
            dict(capabilities=1),
            dict(rgb=[1, 2]),
            dict(valid=1),
            dict(raw=4096),
            dict(millivolts=-1),
            dict(lux="17"),
            dict(sound_mqtt="yes"),
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

    async def test_close_never_stops_coordinator_uart_relay(self):
        coordinator = client_module.AqaraM1SClient("192.168.0.220")
        coordinator.zigbee_role = "coordinator"
        coordinator._close_uart_locked = Mock()
        coordinator._run_command_locked = Mock()
        coordinator._close_locked = Mock()

        coordinator.close()

        coordinator._close_uart_locked.assert_called_once_with()
        coordinator._run_command_locked.assert_not_called()
        coordinator._close_locked.assert_called_once_with()

        router = client_module.AqaraM1SClient("192.168.0.221")
        router.zigbee_role = "router"
        router._close_uart_locked = Mock()
        router._run_command_locked = Mock()
        router._close_locked = Mock()

        router.close()

        router._run_command_locked.assert_called_once_with(
            client_module.UART_STOP_COMMAND
        )

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

    async def test_router_subscribes_sound_status_and_requires_capability(self):
        entry = types.SimpleNamespace(data={})
        client = types.SimpleNamespace(
            host="192.168.0.221",
            zigbee_role="router",
            mqtt_io_confirmed=False,
            coordinator_io_state=None,
        )
        coordinator = FakeCoordinator(entry)
        bridge = coordinator_mqtt.M1SHubMQTTIO(self.hass, client, coordinator)
        unsubscribers = [Mock(), Mock(), Mock(), Mock()]
        mqtt.async_wait_for_mqtt_client = AsyncMock()
        mqtt.async_subscribe = AsyncMock(side_effect=unsubscribers)
        mqtt.async_publish = AsyncMock()

        await bridge.async_start()
        topics = [call.args[1] for call in mqtt.async_subscribe.call_args_list]
        self.assertEqual(
            topics,
            [
                "m1s/221/io/state",
                "m1s/221/telemetry",
                "m1s/221/io/availability",
                "m1s/221/sound/status",
            ],
        )
        self.assertFalse(bridge.sound_supported)
        with self.assertRaisesRegex(RuntimeError, "does not advertise"):
            await bridge.async_prepare_sound("/data/musics/test.wav")
        with self.assertRaisesRegex(RuntimeError, "does not advertise"):
            await bridge.async_stop_sound()
        await bridge.async_stop()

    async def test_router_state_and_telemetry_confirm_only_router_role(self):
        entry = types.SimpleNamespace(data={})
        client = types.SimpleNamespace(
            host="192.168.0.221",
            zigbee_role="router",
            mqtt_io_confirmed=False,
            coordinator_io_state=None,
        )
        coordinator = FakeCoordinator(entry)
        bridge = coordinator_mqtt.M1SHubMQTTIO(self.hass, client, coordinator)
        bridge._state_message(types.SimpleNamespace(payload=json.dumps(GOOD)))
        self.assertFalse(bridge.available)
        self.assertFalse(client.mqtt_io_confirmed)

        router_state = dict(
            GOOD,
            role="router",
            rgb_valid=False,
            sound_mqtt=True,
        )
        bridge._state_message(types.SimpleNamespace(payload=json.dumps(router_state)))
        await bridge._refresh_task
        self.assertTrue(bridge.available)
        self.assertTrue(bridge.sound_supported)
        self.assertTrue(client.mqtt_io_confirmed)
        self.assertEqual(client.coordinator_io_state, router_state)

        router_telemetry = {
            "role": "router",
            "temperature": 29.0,
            "wifi_ip": "192.168.0.221",
            "homekit_process": "running",
            "mqtt_process": "running",
            "telnet_process": "running",
            "coordinator_process": "stopped",
            "mqtt_io_process": "running",
            "jn5189_router": "running",
        }
        bridge._telemetry_message(
            types.SimpleNamespace(payload=json.dumps(router_telemetry))
        )
        await bridge._refresh_task
        self.assertEqual(bridge.telemetry, router_telemetry)

    async def test_router_rejoin_pauses_and_resumes_persistent_uart_owner(self):
        client = client_module.AqaraM1SClient("192.168.0.221")
        client.mqtt_io_confirmed = True
        uart = Mock()
        uart.recv.side_effect = [socket.timeout(), client_module.UART_RESPONSE_REJOIN]
        client._connect_uart_locked = Mock(return_value=uart)
        client._close_uart_locked = Mock()
        client.run_command = Mock(
            side_effect=["__M1S_ROUTER_MQTT_PAUSED__", "ROUTER_MQTT_IO_UART_RESUMED"]
        )

        client.rejoin_zigbee_network()

        self.assertIn("uart-pause", client.run_command.call_args_list[0].args[0])
        self.assertIn("uart-resume", client.run_command.call_args_list[1].args[0])
        uart.sendall.assert_called_once_with(client_module.UART_REQUEST_REJOIN)

    async def test_uart_guard_allows_only_explicit_maintenance_window(self):
        self.assertIn(client_module.ROUTER_MQTT_UART_MAINTENANCE, client_module.UART_START_COMMAND)
        self.assertIn(client_module.ROUTER_MQTT_IO_OWNER_MARKER, client_module.UART_START_COMMAND)

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
