"""Coordinator-only regressions using small HA stand-ins, without a live hub."""
import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = pathlib.Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
PACKAGE = "m1s_profile_tests"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg


def module(name, **attrs):
    result = types.ModuleType(name)
    result.__dict__.update(attrs)
    sys.modules[name] = result
    return result


class FakeCoordinatorBase:
    @classmethod
    def __class_getitem__(cls, value):
        return cls

    def __init__(self, hass, *, config_entry=None, **kwargs):
        self.hass, self.config_entry = hass, config_entry
        self.data = None
        self.last_update_success = True

    def async_set_updated_data(self, data):
        self.data = data
        self.last_update_success = True

    async def async_shutdown(self):
        pass


class FakeCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def available(self):
        return self.coordinator.last_update_success


class FakeConfigFlow:
    def __init_subclass__(cls, **kwargs):
        pass


class FakeOptionsFlow:
    def __init__(self, entry):
        self.config_entry = entry

    def async_show_menu(self, **kwargs):
        return kwargs

    def async_abort(self, **kwargs):
        return kwargs


ha = module("homeassistant")
components = module("homeassistant.components")
components.mqtt = module("homeassistant.components.mqtt", async_subscribe=AsyncMock())
module("homeassistant.components.device_automation", DEVICE_TRIGGER_BASE_SCHEMA=Mock())
module("homeassistant.components.sensor", SensorDeviceClass=types.SimpleNamespace(TEMPERATURE="temperature", ILLUMINANCE="illuminance"),
       SensorEntity=type("SensorEntity", (), {}), SensorStateClass=types.SimpleNamespace(MEASUREMENT="measurement"))
module("homeassistant.components.binary_sensor", BinarySensorEntity=type("BinarySensorEntity", (), {}),
       BinarySensorDeviceClass=types.SimpleNamespace(CONNECTIVITY="connectivity"))
config_entries = module("homeassistant.config_entries", ConfigEntry=object, ConfigFlow=FakeConfigFlow,
                        OptionsFlow=FakeOptionsFlow, OptionsFlowWithConfigEntry=FakeOptionsFlow)
ha.config_entries = config_entries
module("homeassistant.const", CONF_HOST="host", CONF_PASSWORD="password", CONF_PORT="port", CONF_USERNAME="username",
       CONF_DEVICE_ID="device_id", CONF_DOMAIN="domain", CONF_PLATFORM="platform", CONF_TYPE="type",
       LIGHT_LUX="lx", UnitOfTemperature=types.SimpleNamespace(CELSIUS="C"))
module("homeassistant.core", HomeAssistant=object, ServiceCall=object, CALLBACK_TYPE=object, callback=lambda fn: fn)
module("homeassistant.exceptions", HomeAssistantError=RuntimeError)
helpers = module("homeassistant.helpers")
dr = module("homeassistant.helpers.device_registry", async_get=Mock(), async_entries_for_config_entry=Mock())
er = module("homeassistant.helpers.entity_registry", async_get=Mock(), async_entries_for_config_entry=Mock())
helpers.device_registry, helpers.entity_registry = dr, er
module("homeassistant.helpers.dispatcher", async_dispatcher_send=Mock())
module("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=FakeCoordinatorBase,
       UpdateFailed=type("UpdateFailed", (RuntimeError,), {}), CoordinatorEntity=FakeCoordinatorEntity)
module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
module("homeassistant.helpers.storage", Store=Mock())
module("homeassistant.helpers.trigger", TriggerActionType=object, TriggerInfo=object)
selector = module("homeassistant.helpers.selector")
for name in ("BooleanSelector", "FileSelector", "FileSelectorConfig", "NumberSelector", "NumberSelectorConfig",
             "SelectSelector", "SelectSelectorConfig", "TextSelector", "TextSelectorConfig"):
    setattr(selector, name, Mock())
selector.NumberSelectorMode = types.SimpleNamespace(BOX="box")
selector.SelectSelectorMode = types.SimpleNamespace(DROPDOWN="dropdown", LIST="list")
selector.TextSelectorType = types.SimpleNamespace(PASSWORD="password")
module("voluptuous", Schema=Mock(), Required=Mock(), Optional=Mock(), All=Mock(), Coerce=Mock(), Range=Mock(), In=Mock())


def load(name, filename=None):
    fullname = PACKAGE if filename == "__init__.py" else PACKAGE + "." + name
    spec = importlib.util.spec_from_file_location(fullname, ROOT / (filename or name + ".py"))
    result = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = result
    spec.loader.exec_module(result)
    return result


const = load("const")
device = load("device")
profile = load("coordinator_profile")
client_module = load("client")
mqtt_bridge = module(PACKAGE + ".coordinator_mqtt", M1SHubMQTTIO=Mock(), async_detect_hub_connectivity=AsyncMock())
coordinator_module = load("coordinator")
sensor_module = load("sensor")
shared_mqtt = load("shared_mqtt")
module(PACKAGE + ".media_group", AqaraM1SMediaGroupManager=Mock())
module(PACKAGE + ".media_player", AqaraM1SRadioPlayer=Mock())
module(PACKAGE + ".sound_player", AqaraM1SSoundPlayer=Mock())
module(PACKAGE + ".sound_upload", destination_for_filename=Mock(), read_uploaded_sound=Mock(), read_uploaded_sounds=Mock())
integration = load("integration", "__init__.py")
flow_module = load("config_flow")
trigger_module = load("device_trigger")

GOOD_DIAGNOSTICS = """M1S_DIAGNOSTICS_BEGIN
wifi_ip=192.168.0.220
mqtt_process=running
telnet_process=running
M1S_NETSTAT_BEGIN
Proto Recv-Q Send-Q Local Address Foreign Address State
tcp 0 0 0.0.0.0:1886 0.0.0.0:* LISTEN
tcp 0 0 192.168.0.220:1886 192.168.0.250:60666 ESTABLISHED
M1S_NETSTAT_END
M1S_DIAGNOSTICS_END
"""


def entry(role="coordinator", entry_id="coordinator220"):
    return types.SimpleNamespace(entry_id=entry_id, unique_id="mac:00:11:22:33:44:55",
                                 title="Test", data={"host": "192.168.0.220", "name": "Test", "zigbee_role": role}, options={})


def registry_entity(key, owner="coordinator220", platform=const.DOMAIN):
    return types.SimpleNamespace(entity_id="sensor." + key, platform=platform, unique_id=owner + "_" + key)


class ProfileTests(unittest.TestCase):
    def test_keep_only_live_per_hub_entities(self):
        keys = [*profile.COORDINATOR_SENSOR_KEYS, "hub_connectivity", "radio", "ring_light", "illuminance_raw",
                "temperature", "homekit_process", "mqtt_configuration", "sound_playback_volume", "sound_button_abc"]
        entities = [registry_entity(key) for key in keys]
        entities += [registry_entity("radio", owner="router221"), registry_entity("radio", platform="another_integration")]
        entities.append(types.SimpleNamespace(entity_id="media_player.group", platform=const.DOMAIN,
                                             unique_id="aqara_m1s_media_group"))
        removed = profile.obsolete_coordinator_entities(entities, "coordinator220", const.DOMAIN)
        self.assertEqual(set(removed), {"sensor." + key for key in keys if key not in (*profile.COORDINATOR_SENSOR_KEYS, "hub_connectivity")})
        self.assertNotIn("media_player.group", removed)

    def test_diagnostics_ignore_shell_echo(self):
        output = "# echo M1S_DIAGNOSTICS_BEGIN; echo wifi_ip=garbage; echo M1S_DIAGNOSTICS_END\n" + GOOD_DIAGNOSTICS
        values = profile.parse_diagnostics(output)
        self.assertEqual(values["wifi_ip"], "192.168.0.220")
        self.assertEqual(values["zigbee_transport"], "connected")

    def test_incomplete_and_invalid_diagnostics_are_rejected(self):
        for value in ("", GOOD_DIAGNOSTICS.replace("M1S_DIAGNOSTICS_END", ""),
                      GOOD_DIAGNOSTICS.replace("192.168.0.220", "999.168.0.220"),
                      GOOD_DIAGNOSTICS.replace("M1S_NETSTAT_END", ""),
                      GOOD_DIAGNOSTICS.replace("telnet_process=running", "telnet_process=unknown")):
            with self.assertRaises(RuntimeError):
                profile.parse_diagnostics(value)

    def test_transport_requires_local_port_not_an_outgoing_connection(self):
        output = GOOD_DIAGNOSTICS.replace("192.168.0.220:1886 192.168.0.250:60666", "192.168.0.220:60666 192.168.0.250:1886")
        self.assertEqual(profile.parse_diagnostics(output)["zigbee_transport"], "listening")
        output = output.replace("tcp 0 0 0.0.0.0:1886 0.0.0.0:* LISTEN", "")
        self.assertEqual(profile.parse_diagnostics(output)["zigbee_transport"], "stopped")

    def test_stopped_processes_are_not_reported_running(self):
        output = GOOD_DIAGNOSTICS.replace("process=running", "process=stopped")
        values = profile.parse_diagnostics(output)
        self.assertEqual(values["mqtt_process"], "stopped")
        self.assertEqual(values["telnet_process"], "stopped")
        self.assertIn('/proc/[0-9]*/comm', profile.DIAGNOSTICS_COMMAND)
        self.assertNotIn('ps w', profile.DIAGNOSTICS_COMMAND)

    def test_diagnostics_use_only_read_only_linux_commands(self):
        client = Mock()
        client.run_command.return_value = GOOD_DIAGNOSTICS
        self.assertEqual(profile.read_diagnostics(client)["mqtt_process"], "running")
        command = client.run_command.call_args.args[0]
        self.assertLess(len(command), 800)
        for forbidden in ("/dev/tty", "coordinator_on", "coordinator_off", "mqtt_io_service", "aplay", "kill", " > "):
            self.assertNotIn(forbidden, command)

    def test_unknown_role_keeps_setup_fallback_possible(self):
        client = client_module.AqaraM1SClient("192.168.0.220")
        client.run_command = Mock(return_value="unexpected response")
        with self.assertRaises(RuntimeError):
            client.coordinator_runtime_status()
        client.run_command.return_value = "role=router\nstate=UNAVAILABLE\n"
        self.assertEqual(client.coordinator_runtime_status()["role"], "router")

    def test_shared_mqtt_never_writes_to_coordinator(self):
        client = types.SimpleNamespace(zigbee_role="coordinator", run_command=Mock())
        shared_mqtt.apply_to_hub(client, {})
        client.run_command.assert_not_called()


class OptionsTests(unittest.IsolatedAsyncioTestCase):
    def make_flow(self, role="coordinator", stored_role=None):
        item = entry(stored_role or role)
        client = Mock(zigbee_role=role)
        client.coordinator_runtime_status.return_value = {"role": role}
        client.list_sounds.return_value = []
        flow = flow_module.AqaraM1SZigbeeRouterOptionsFlow(item)
        flow.hass = types.SimpleNamespace(data={const.DOMAIN: {const.DATA_CLIENTS: {item.entry_id: client}}},
                                          async_add_executor_job=AsyncMock(side_effect=lambda fn, *args: fn(*args)))
        return flow, client

    async def test_coordinator_menu_is_exactly_two_items_without_hub_calls(self):
        flow, client = self.make_flow()
        result = await flow.async_step_init()
        self.assertEqual(result["menu_options"], ["network_address", "change_wifi"])
        flow.hass.async_add_executor_job.assert_not_awaited()
        client.list_sounds.assert_not_called()

    async def test_saved_role_preserved_when_runtime_is_unavailable(self):
        flow, client = self.make_flow("router", "coordinator")
        self.assertEqual((await flow.async_step_init())["menu_options"], list(profile.COORDINATOR_OPTIONS))
        client.coordinator_runtime_status.assert_not_called()

    async def test_sound_and_rejoin_steps_blocked_even_when_invoked_directly(self):
        flow, client = self.make_flow()
        for name in ("shared_mqtt", "upload_sound", "delete_sound", "confirm_delete_sound", "rejoin_zigbee"):
            result = await getattr(flow, "async_step_" + name)({"confirm": True})
            self.assertEqual(result["reason"], "coordinator_only")
        flow.hass.async_add_executor_job.assert_not_awaited()

    async def test_router_menu_keeps_media_and_shared_mqtt(self):
        flow, client = self.make_flow("router")
        result = await flow.async_step_init()
        self.assertEqual(result["menu_options"], ["shared_mqtt", "network_address", "change_wifi", "upload_sound", "rejoin_zigbee", "finish"])
        client.list_sounds.assert_called_once()


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def make_coordinator(self):
        client = types.SimpleNamespace(host="192.168.0.220", zigbee_role="coordinator", mqtt_io_confirmed=False)
        hass = types.SimpleNamespace(loop=asyncio.get_running_loop(), data={}, async_create_task=asyncio.create_task,
                                     async_add_executor_job=AsyncMock(return_value=profile.parse_diagnostics(GOOD_DIAGNOSTICS)))
        coord = coordinator_module.AqaraM1SRouterCoordinator(hass, client)
        coord._set_visual_availability = Mock()
        return coord, hass

    async def test_coordinator_refresh_has_no_mqtt_or_uart_work(self):
        coord, hass = self.make_coordinator()
        with patch.object(coordinator_module, "async_detect_hub_connectivity", AsyncMock(return_value=(True, "telnet"))), \
                patch.object(shared_mqtt, "get_shared_mqtt", AsyncMock()) as manager:
            coord.data = await coord._async_update_data()
            await coord._diagnostics_task
            manager.assert_not_awaited()
        self.assertEqual(coord.data["coordinator_diagnostics"]["wifi_ip"], "192.168.0.220")
        self.assertIsNone(coord._lux_task)
        self.assertIsNone(coord._post_online_task)
        self.assertIsNone(coord._mqtt_task)

    async def test_diagnostics_refresh_is_throttled(self):
        coord, hass = self.make_coordinator()
        coord._was_online, coord._online_generation = True, 1
        coord.data = {"online_generation": 1}
        coord._schedule_diagnostics_refresh()
        await coord._diagnostics_task
        coord._schedule_diagnostics_refresh()
        hass.async_add_executor_job.assert_awaited_once()

    async def test_failed_diagnostics_do_not_set_hub_offline(self):
        coord, hass = self.make_coordinator()
        coord._was_online, coord._online_generation = True, 1
        coord.data = {"online": True}
        hass.async_add_executor_job.side_effect = RuntimeError("diagnostics failed")
        await coord._async_refresh_diagnostics(1)
        self.assertTrue(coord.data["online"])
        self.assertIsNone(coord.data["coordinator_diagnostics"])

    async def test_result_after_disconnect_or_new_generation_is_ignored(self):
        coord, hass = self.make_coordinator()
        coord.data = {"online": False}
        coord._was_online, coord._online_generation = False, 1
        await coord._async_refresh_diagnostics(1)
        self.assertEqual(coord.data, {"online": False})
        coord._was_online, coord._online_generation = True, 2
        await coord._async_refresh_diagnostics(1)
        self.assertEqual(coord.data, {"online": False})

    async def test_coordinator_sensor_platform_exposes_four_live_diagnostics(self):
        coord, hass = self.make_coordinator()
        item = entry()
        hass.data = {const.DOMAIN: {const.DATA_CLIENTS: {item.entry_id: coord.client},
                                  const.DATA_COORDINATORS: {item.entry_id: coord}}}
        reg = Mock()
        reg.async_get_entity_id.return_value = None
        er.async_get.return_value = reg
        added = Mock()
        await sensor_module.async_setup_entry(hass, item, added)
        sensors = added.call_args.args[0]
        self.assertEqual({sensor._attr_unique_id for sensor in sensors},
                         {item.entry_id + "_" + key for key in profile.COORDINATOR_SENSOR_KEYS})
        self.assertFalse(sensors[0].available)
        coord.data = {"coordinator_diagnostics": profile.parse_diagnostics(GOOD_DIAGNOSTICS)}
        self.assertTrue(sensors[0].available)
        self.assertEqual(sensors[0].native_value, "192.168.0.220")


class TriggerTests(unittest.IsolatedAsyncioTestCase):
    async def test_coordinator_has_no_physical_button_triggers(self):
        with patch.object(trigger_module, "_entry_for_device", return_value=entry()):
            self.assertEqual(await trigger_module.async_get_triggers(object(), "device220"), [])

    async def test_old_coordinator_trigger_cannot_subscribe_to_auxiliary_mqtt(self):
        with patch.object(trigger_module, "_entry_for_device", return_value=entry()), \
                patch.object(trigger_module.mqtt, "async_subscribe", AsyncMock()) as subscribe:
            with self.assertRaisesRegex(ValueError, "Zigbee-only"):
                await trigger_module.async_attach_trigger(object(), {"device_id": "device220"}, Mock(), {})
            subscribe.assert_not_awaited()

    async def test_router_physical_button_triggers_are_preserved(self):
        with patch.object(trigger_module, "_entry_for_device", return_value=entry("router")):
            triggers = await trigger_module.async_get_triggers(object(), "device221")
        self.assertEqual({trigger["subtype"] for trigger in triggers}, set(const.BUTTON_ACTIONS))


class SetupTests(unittest.IsolatedAsyncioTestCase):
    async def setup_integration(self, role="coordinator", offline=False):
        item = entry(role)
        client = Mock(zigbee_role=role)
        client.host = item.data["host"]
        client.network_status.return_value = {"wifi_mac": "00:11:22:33:44:55", "button_topic_id": "220"}
        client.coordinator_runtime_status.return_value = {"role": role, "mqtt_io_enabled": "1"}
        if offline:
            client.coordinator_runtime_status.side_effect = OSError("offline")
        coord = types.SimpleNamespace(last_update_success=False, async_refresh=AsyncMock(), async_start_watchdog=Mock(), async_shutdown=AsyncMock())
        handlers = {}
        hass = types.SimpleNamespace(data={}, async_add_executor_job=AsyncMock(side_effect=lambda fn, *args: fn(*args)),
                                     config_entries=types.SimpleNamespace(async_forward_entry_setups=AsyncMock(), async_unload_platforms=AsyncMock(return_value=True)),
                                     services=types.SimpleNamespace(has_service=lambda domain, name: name in handlers,
                                                                    async_register=lambda domain, name, handler: handlers.__setitem__(name, handler)))

        def update_entry(target, **kwargs):
            for key, value in kwargs.items():
                setattr(target, key, value)

        hass.config_entries.async_update_entry = Mock(side_effect=update_entry)
        identifier = device.device_identifier(item)
        dev = types.SimpleNamespace(id="device220", name="Test - 192.168.0.220", name_by_user=None, identifiers={identifier})
        registry = Mock()
        registry.async_get_device.return_value = dev
        registry.async_get_or_create.return_value = dev
        dr.async_get.return_value = registry
        dr.async_entries_for_config_entry.return_value = [dev]
        entities = Mock()
        entities.async_get_entity_id.return_value = None
        er.async_get.return_value = entities
        er.async_entries_for_config_entry.return_value = [registry_entity("radio"), registry_entity("wifi_ip")]
        group = types.SimpleNamespace(register_member=Mock(), members={}, unregister_member=AsyncMock(), async_shutdown=AsyncMock())
        mqtt = types.SimpleNamespace(async_start=AsyncMock(), async_stop=AsyncMock())
        radio = Mock()
        sound = types.SimpleNamespace(async_play=AsyncMock(), async_stop=AsyncMock())
        patches = [patch.object(integration, "AqaraM1SClient", return_value=client),
                   patch.object(integration, "AqaraM1SRouterCoordinator", return_value=coord),
                   patch.object(integration, "AqaraM1SMediaGroupManager", return_value=group),
                   patch.object(integration, "M1SHubMQTTIO", return_value=mqtt),
                   patch.object(integration, "AqaraM1SRadioPlayer", return_value=radio),
                   patch.object(integration, "AqaraM1SSoundPlayer", return_value=sound)]
        constructors = []
        for patcher in patches:
            constructors.append(patcher.start())
            self.addCleanup(patcher.stop)
        self.assertTrue(await integration.async_setup_entry(hass, item))
        return types.SimpleNamespace(hass=hass, entry=item, client=client, coordinator=coord, group=group,
                                     mqtt=mqtt, handlers=handlers, constructors=constructors, entities=entities, sound=sound)

    async def test_coordinator_does_not_construct_any_media_or_mqtt_runtime(self):
        context = await self.setup_integration()
        for constructor in context.constructors[2:]:
            constructor.assert_not_called()
        context.client.ensure_fast_button_polling.assert_not_called()
        context.hass.config_entries.async_forward_entry_setups.assert_awaited_with(context.entry, ["binary_sensor", "sensor"])
        context.entities.async_remove.assert_called_once_with("sensor.radio")
        self.assertNotIn(const.DATA_MEDIA_GROUP, context.hass.data[const.DOMAIN])
        self.assertFalse(context.client.mqtt_io_confirmed)

    async def test_offline_coordinator_still_uses_restricted_profile(self):
        context = await self.setup_integration(offline=True)
        self.assertEqual(context.client.zigbee_role, "coordinator")
        context.hass.config_entries.async_forward_entry_setups.assert_awaited_with(context.entry, ["binary_sensor", "sensor"])
        context.constructors[4].assert_not_called()

    async def test_old_sound_actions_fail_before_read_or_play(self):
        context = await self.setup_integration()
        context.hass.async_add_executor_job.reset_mock()
        for service in ("play_url", "play_sound", "upload_sound", "delete_sound", "refresh_sounds"):
            with self.assertRaisesRegex(RuntimeError, "Zigbee-only"):
                await context.handlers[service](types.SimpleNamespace(data={"host": "192.168.0.220", "confirm": True}))
        context.hass.async_add_executor_job.assert_not_awaited()

    async def test_router_still_constructs_and_registers_media_runtime(self):
        context = await self.setup_integration("router")
        for constructor in context.constructors[2:]:
            constructor.assert_called_once()
        context.client.ensure_fast_button_polling.assert_called_once()
        context.group.register_member.assert_called_once()
        context.mqtt.async_start.assert_awaited_once()
        context.entities.async_remove.assert_not_called()
        context.hass.config_entries.async_forward_entry_setups.assert_awaited_with(context.entry, integration.PLATFORMS)
        await context.handlers["play_sound"](types.SimpleNamespace(data={"host": "192.168.0.220", "path": "/data/musics/music-ch/test.wav"}))
        context.sound.async_play.assert_awaited_once()

    async def test_coordinator_unload_does_not_touch_router_group(self):
        context = await self.setup_integration()
        context.group.members = {"router221": object()}
        context.hass.data[const.DOMAIN][const.DATA_MEDIA_GROUP] = context.group
        self.assertTrue(await integration.async_unload_entry(context.hass, context.entry))
        context.group.unregister_member.assert_not_awaited()
        context.group.async_shutdown.assert_not_awaited()
        context.hass.config_entries.async_unload_platforms.assert_awaited_with(context.entry, ["binary_sensor", "sensor"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
