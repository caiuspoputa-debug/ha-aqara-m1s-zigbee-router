"""Sound recovery lifecycle tests with HA stand-ins; no network or hub writes."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
PACKAGE = "m1s_inventory_tests"


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    sys.modules[name] = result
    return result


class FakeCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.removed = False

    async def async_remove(self):
        self.removed = True


module("homeassistant")
module("homeassistant.components")
module("homeassistant.components.button", ButtonEntity=type("ButtonEntity", (), {}))
module("homeassistant.config_entries", ConfigEntry=object)
module("homeassistant.core", HomeAssistant=object, callback=lambda function: function)
helpers = module("homeassistant.helpers")
registry_api = module("homeassistant.helpers.entity_registry")
helpers.entity_registry = registry_api
module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
module("homeassistant.helpers.update_coordinator", CoordinatorEntity=FakeCoordinatorEntity)
dispatcher = module("homeassistant.helpers.dispatcher", async_dispatcher_connect=Mock())
module(PACKAGE, __path__=[str(ROOT)])
module(PACKAGE + ".device", device_info=lambda entry: {"identifiers": {entry.entry_id}})


def load(name):
    specification = importlib.util.spec_from_file_location(PACKAGE + "." + name, ROOT / (name + ".py"))
    result = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = result
    specification.loader.exec_module(result)
    return result


const = load("const")
buttons = load("button")


class FakeRegistry:
    def __init__(self):
        self.entries = []
        self.removed = []

    def async_get_entity_id(self, domain, platform, unique_id):
        return next((item.entity_id for item in self.entries
                     if item.unique_id == unique_id and item.platform == platform
                     and item.entity_id.startswith(domain + ".")), None)

    def async_remove(self, entity_id):
        self.removed.append(entity_id)
        self.entries = [item for item in self.entries if item.entity_id != entity_id]


registry_api.async_get = lambda hass: hass.registry
registry_api.async_entries_for_config_entry = lambda registry, entry_id: [
    item for item in registry.entries if item.config_entry_id == entry_id
]


def connect_signal(hass, signal, callback):
    listeners = hass.signals.setdefault(signal, [])
    listeners.append(callback)
    return lambda: listeners.remove(callback)


dispatcher.async_dispatcher_connect = connect_signal
buttons.async_dispatcher_connect = connect_signal


class FakeCoordinator:
    def __init__(self, online):
        self.last_update_success = online
        self.listeners = []

    def async_add_listener(self, callback):
        self.listeners.append(callback)
        return lambda: self.listeners.remove(callback)

    def update(self, online):
        self.last_update_success = online
        for listener in list(self.listeners):
            listener()


class FakeEntry:
    entry_id = "router"

    def __init__(self):
        self.unload_callbacks = []

    def async_on_unload(self, callback):
        self.unload_callbacks.append(callback)

    def async_create_background_task(self, hass, coro, *, name, eager_start):
        assert eager_start is False
        task = asyncio.create_task(coro, name=name)
        hass.tasks.append(task)
        return task

    def unload(self):
        for callback in self.unload_callbacks:
            callback()


class FakeHass:
    def __init__(self, client, coordinator):
        self.registry = FakeRegistry()
        self.data = {const.DOMAIN: {
            const.DATA_CLIENTS: {"router": client},
            const.DATA_COORDINATORS: {"router": coordinator},
        }}
        self.tasks = []
        self.signals = {}
        self.added = []
        self.executor_gate = None

    async def async_add_executor_job(self, function, *args):
        if self.executor_gate is not None:
            await self.executor_gate.wait()
        return function(*args)

    def add_entities(self, entities):
        self.added.extend(entities)

    def signal(self):
        signal = const.sound_list_signal("router")
        for listener in list(self.signals.get(signal, [])):
            listener()

    async def drain(self):
        for _ in range(3):
            pending = [task for task in self.tasks if not task.done()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=False)
            await asyncio.sleep(0)


class SoundInventoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = types.SimpleNamespace(list_sounds=Mock(return_value=[]))
        self.coordinator = FakeCoordinator(False)
        self.entry = FakeEntry()
        self.hass = FakeHass(self.client, self.coordinator)
        self.full = [f"/data/musics/music-scene/welcome_{index}.wav" for index in range(1, 11)]
        self.full += [buttons.FALLBACK_SOUNDS[0], buttons.FALLBACK_SOUNDS[2], buttons.FALLBACK_SOUNDS[3]]
        self.full += ["/data/musics/music-ch/custom.wav"]

    async def asyncTearDown(self):
        self.entry.unload()
        if self.hass.tasks:
            await asyncio.gather(*self.hass.tasks, return_exceptions=True)

    async def setup_buttons(self):
        await buttons.async_setup_entry(self.hass, self.entry, self.hass.add_entities)

    def active_paths(self):
        return {entity.path for entity in self.hass.added if not entity.removed}

    def stale_entry(self, path):
        item = types.SimpleNamespace(
            config_entry_id="router", platform=const.DOMAIN,
            entity_id="button.existing_sound",
            unique_id=buttons.sound_button_unique_id("router", path),
        )
        self.hass.registry.entries.append(item)
        return item

    async def test_offline_start_recovers_all_sounds_without_reload(self):
        existing = self.stale_entry(self.full[0])
        self.client.list_sounds.return_value = self.full
        await self.setup_buttons()
        self.client.list_sounds.assert_not_called()
        self.assertNotIn(existing.entity_id, self.hass.registry.removed)
        self.assertEqual(self.active_paths(), set(buttons.FALLBACK_SOUNDS))
        self.coordinator.update(True)
        await self.hass.drain()
        self.assertEqual(self.active_paths(), set(self.full))
        self.assertNotIn(existing.entity_id, self.hass.registry.removed)
        revived = next(entity for entity in self.hass.added if entity.path == self.full[0])
        self.assertEqual(revived._attr_unique_id, existing.unique_id)
        self.assertEqual(self.client.list_sounds.call_count, 1)

    async def test_online_initial_scan_failure_retries_until_success(self):
        self.coordinator.last_update_success = True
        self.client.list_sounds.side_effect = [OSError("booting"), OSError("booting"), self.full]
        await self.setup_buttons()
        await self.hass.drain()
        self.assertEqual(self.active_paths(), set(buttons.FALLBACK_SOUNDS))
        self.coordinator.update(True)
        await self.hass.drain()
        self.assertEqual(self.active_paths(), set(self.full))
        self.assertEqual(self.client.list_sounds.call_count, 3)

    async def test_successful_online_setup_is_not_rescanned_on_each_sensor_update(self):
        self.coordinator.last_update_success = True
        self.client.list_sounds.return_value = self.full
        await self.setup_buttons()
        for _ in range(10):
            self.coordinator.update(True)
        await self.hass.drain()
        self.assertEqual(self.client.list_sounds.call_count, 1)
        self.assertEqual(self.active_paths(), set(self.full))

    async def test_reconnect_refreshes_inventory(self):
        self.coordinator.last_update_success = True
        self.client.list_sounds.return_value = self.full[:3]
        await self.setup_buttons()
        self.coordinator.update(False)
        self.client.list_sounds.return_value = self.full
        self.coordinator.update(True)
        await self.hass.drain()
        self.assertEqual(self.active_paths(), set(self.full))

    async def test_failed_scan_does_not_remove_existing_entities(self):
        self.coordinator.last_update_success = True
        self.client.list_sounds.return_value = self.full
        await self.setup_buttons()
        existing = self.stale_entry(self.full[0])
        self.client.list_sounds.side_effect = OSError("incomplete scan")
        self.hass.signal()
        await self.hass.drain()
        self.assertEqual(self.active_paths(), set(self.full))
        self.assertNotIn(existing.entity_id, self.hass.registry.removed)
        self.client.list_sounds.side_effect = None
        self.coordinator.update(True)
        await self.hass.drain()
        self.assertEqual(self.client.list_sounds.call_count, 3)

    async def test_confirmed_empty_inventory_does_not_create_nonexistent_sounds(self):
        self.coordinator.last_update_success = True
        existing = self.stale_entry(self.full[0])
        await self.setup_buttons()
        self.assertEqual(self.active_paths(), set())
        self.assertIn(existing.entity_id, self.hass.registry.removed)

    async def test_confirmed_deletion_removes_only_missing_sound(self):
        self.coordinator.last_update_success = True
        self.client.list_sounds.return_value = self.full
        await self.setup_buttons()
        self.client.list_sounds.return_value = self.full[1:]
        self.hass.signal()
        await self.hass.drain()
        self.assertEqual(self.active_paths(), set(self.full[1:]))

    async def test_events_during_scan_are_coalesced_without_losing_last_refresh(self):
        self.coordinator.last_update_success = True
        self.client.list_sounds.return_value = self.full
        await self.setup_buttons()
        gate = self.hass.executor_gate = asyncio.Event()
        self.hass.signal()
        await asyncio.sleep(0)
        for _ in range(5):
            self.hass.signal()
        self.assertEqual(self.client.list_sounds.call_count, 1)
        self.assertEqual(len(self.hass.tasks), 1)
        gate.set()
        await self.hass.drain()
        self.assertEqual(self.client.list_sounds.call_count, 3)
        self.assertEqual(self.active_paths(), set(self.full))

    async def test_unload_cancels_pending_scan_and_unsubscribes(self):
        self.client.list_sounds.return_value = self.full
        await self.setup_buttons()
        self.hass.executor_gate = asyncio.Event()
        self.coordinator.update(True)
        await asyncio.sleep(0)
        self.entry.unload()
        await asyncio.gather(*self.hass.tasks, return_exceptions=True)
        self.assertEqual(self.coordinator.listeners, [])
        self.assertFalse(any(self.hass.signals.values()))
        self.client.list_sounds.assert_not_called()
        self.assertEqual(self.active_paths(), set(buttons.FALLBACK_SOUNDS))
        self.coordinator.update(True)
        self.hass.signal()
        self.assertEqual(len(self.hass.tasks), 1)

    async def test_disconnect_during_scan_does_not_apply_result(self):
        self.client.list_sounds.return_value = self.full
        await self.setup_buttons()
        gate = self.hass.executor_gate = asyncio.Event()
        self.coordinator.update(True)
        await asyncio.sleep(0)
        self.coordinator.update(False)
        gate.set()
        await self.hass.drain()
        self.assertEqual(self.active_paths(), set(buttons.FALLBACK_SOUNDS))
        self.coordinator.update(True)
        await self.hass.drain()
        self.assertEqual(self.active_paths(), set(self.full))

    async def test_no_manual_refresh_entity_or_extra_helper(self):
        self.hass.registry.entries.append(types.SimpleNamespace(
            config_entry_id="router", platform=const.DOMAIN,
            entity_id="button.old_refresh", unique_id="router_refresh_sounds",
        ))
        await self.setup_buttons()
        self.assertIn("button.old_refresh", self.hass.registry.removed)
        self.assertTrue(all(hasattr(entity, "path") for entity in self.hass.added))


if __name__ == "__main__":
    unittest.main()
