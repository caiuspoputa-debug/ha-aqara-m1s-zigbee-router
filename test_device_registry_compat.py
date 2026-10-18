"""Entry-scoped device identity regressions, without Home Assistant or a hub."""

from __future__ import annotations

from dataclasses import dataclass
import types
import unittest
from unittest.mock import Mock, patch

import test_coordinator_profile as support


DOMAIN = support.const.DOMAIN
OWNER = "coordinator220"
FOREIGN_OWNER = "foreign-entry"
HOST = "192.168.0.220"
MAC = "00:11:22:33:44:55"
IP_IDENTIFIER = (DOMAIN, HOST)
MAC_IDENTIFIER = (DOMAIN, "mac:" + MAC)


@dataclass
class RegistryDevice:
    id: str
    identifiers: set[tuple[str, str]]
    config_entries: set[str]
    name: str = "Living - 192.168.0.220"
    name_by_user: str | None = None


@dataclass
class RegistryEntity:
    entity_id: str
    device_id: str
    config_entry_id: str = OWNER
    platform: str = DOMAIN
    unique_id: str = OWNER + "_radio"


class LegacyRegistry:
    """Older registry with the deprecated unscoped lookup deliberately forbidden."""

    def __init__(self, devices=()):
        self.devices = {device.id: device for device in devices}
        self.deprecated_accesses = 0
        self.updated = []
        self.removed = []

    @property
    def async_get_device(self):
        self.deprecated_accesses += 1
        raise AssertionError("Deprecated unscoped device lookup was accessed")

    def async_update_device(self, device_id, **updates):
        device = self.devices[device_id]
        self.updated.append((device_id, updates))
        for key, value in updates.items():
            setattr(device, "identifiers" if key == "new_identifiers" else key, value)
        return device

    def async_get_or_create(self, *, config_entry_id, identifiers, **metadata):
        for device in self.devices.values():
            if config_entry_id in device.config_entries and device.identifiers & identifiers:
                return device
        device = RegistryDevice(
            "created-" + config_entry_id, set(identifiers), {config_entry_id}, metadata["name"]
        )
        self.devices[device.id] = device
        return device

    def async_remove_device(self, device_id):
        self.removed.append(device_id)
        del self.devices[device_id]


class CurrentRegistry(LegacyRegistry):
    def __init__(self, devices=()):
        super().__init__(devices)
        self.lookup_calls = []

    def async_get_device_by_identifier(self, identifier, config_entry_id):
        self.lookup_calls.append((identifier, config_entry_id))
        return next(
            (
                device
                for device in self.devices.values()
                if identifier in device.identifiers and config_entry_id in device.config_entries
            ),
            None,
        )


class EntityRegistry:
    def __init__(self, entities=()):
        self.entities = {entity.entity_id: entity for entity in entities}
        self.updated = []

    def async_get_entity_id(self, *args):
        return None

    def async_update_entity(self, entity_id, **updates):
        entity = self.entities[entity_id]
        self.updated.append((entity_id, updates))
        for key, value in updates.items():
            setattr(entity, key, value)
        return entity

    def async_remove(self, entity_id):
        del self.entities[entity_id]


def entry_devices(registry, config_entry_id):
    return [device for device in registry.devices.values() if config_entry_id in device.config_entries]


def entry_entities(registry, config_entry_id):
    return [entity for entity in registry.entities.values() if entity.config_entry_id == config_entry_id]


class DeviceLookupCompatibilityTests(unittest.TestCase):
    def test_current_api_scopes_colliding_ip_and_mac_identifiers(self):
        for identifier in (IP_IDENTIFIER, MAC_IDENTIFIER):
            with self.subTest(identifier=identifier):
                foreign = RegistryDevice("foreign", {identifier}, {FOREIGN_OWNER})
                own = RegistryDevice("own", {identifier}, {OWNER})
                registry = CurrentRegistry([foreign, own])
                with patch.object(support.device.dr, "async_entries_for_config_entry") as enumerate_devices:
                    result = support.device.async_get_entry_device(registry, OWNER, identifier)
                self.assertIs(result, own)
                self.assertEqual(registry.lookup_calls, [(identifier, OWNER)])
                enumerate_devices.assert_not_called()
                self.assertEqual(registry.deprecated_accesses, 0)

    def test_current_api_missing_own_device_does_not_return_foreign_collision(self):
        foreign = RegistryDevice("foreign", {MAC_IDENTIFIER}, {FOREIGN_OWNER})
        registry = CurrentRegistry([foreign])
        self.assertIsNone(support.device.async_get_entry_device(registry, OWNER, MAC_IDENTIFIER))
        self.assertEqual(registry.lookup_calls, [(MAC_IDENTIFIER, OWNER)])
        self.assertEqual(registry.deprecated_accesses, 0)

    def test_current_api_empty_registry_returns_none(self):
        registry = CurrentRegistry()
        self.assertIsNone(support.device.async_get_entry_device(registry, OWNER, IP_IDENTIFIER))
        self.assertEqual(registry.deprecated_accesses, 0)

    def test_old_ha_uses_scoped_enumeration_for_ip_and_mac_collisions(self):
        for identifier in (IP_IDENTIFIER, MAC_IDENTIFIER):
            with self.subTest(identifier=identifier):
                foreign = RegistryDevice("foreign", {identifier}, {FOREIGN_OWNER})
                own = RegistryDevice("own", {identifier}, {OWNER})
                registry = LegacyRegistry([foreign, own])
                with patch.object(support.device.dr, "async_entries_for_config_entry", side_effect=entry_devices) as enumerate_devices:
                    result = support.device.async_get_entry_device(registry, OWNER, identifier)
                self.assertIs(result, own)
                enumerate_devices.assert_called_once_with(registry, OWNER)
                self.assertEqual(registry.deprecated_accesses, 0)

    def test_old_ha_foreign_only_and_nonmatching_own_devices_return_none(self):
        registry = LegacyRegistry([
            RegistryDevice("foreign", {MAC_IDENTIFIER}, {FOREIGN_OWNER}),
            RegistryDevice("own-other", {(DOMAIN, "192.168.0.221")}, {OWNER}),
        ])
        with patch.object(support.device.dr, "async_entries_for_config_entry", side_effect=entry_devices):
            self.assertIsNone(support.device.async_get_entry_device(registry, OWNER, MAC_IDENTIFIER))
        self.assertEqual(registry.deprecated_accesses, 0)

    def test_noncallable_current_lookup_uses_old_ha_fallback(self):
        own = RegistryDevice("own", {MAC_IDENTIFIER}, {OWNER})
        registry = LegacyRegistry([own])
        registry.async_get_device_by_identifier = None
        with patch.object(support.device.dr, "async_entries_for_config_entry", side_effect=entry_devices):
            self.assertIs(support.device.async_get_entry_device(registry, OWNER, MAC_IDENTIFIER), own)
        self.assertEqual(registry.deprecated_accesses, 0)


class DeviceRegistrySetupTests(unittest.IsolatedAsyncioTestCase):
    async def setup_with_registries(self, registry, entities):
        with patch.object(support.dr, "async_get", side_effect=lambda hass: registry), \
             patch.object(support.dr, "async_entries_for_config_entry", side_effect=entry_devices), \
             patch.object(support.er, "async_get", side_effect=lambda hass: entities), \
             patch.object(support.er, "async_entries_for_config_entry", side_effect=entry_entities):
            return await support.SetupTests.setup_integration(self, "router")

    async def test_ip_to_mac_migration_keeps_device_id_user_name_and_entity_link(self):
        for registry_type in (CurrentRegistry, LegacyRegistry):
            with self.subTest(registry_type=registry_type.__name__):
                foreign_ip = RegistryDevice("foreign-ip", {IP_IDENTIFIER}, {FOREIGN_OWNER}, name="Foreign IP")
                foreign_mac = RegistryDevice("foreign-mac", {MAC_IDENTIFIER}, {FOREIGN_OWNER}, name="Foreign MAC")
                own = RegistryDevice("own-existing-id", {IP_IDENTIFIER}, {OWNER}, name_by_user="Paul Living")
                registry = registry_type([foreign_ip, foreign_mac, own])
                entity = RegistryEntity("media_player.living", own.id)
                entities = EntityRegistry([entity])

                await self.setup_with_registries(registry, entities)

                self.assertIs(registry.devices["own-existing-id"], own)
                self.assertEqual(own.identifiers, {MAC_IDENTIFIER})
                self.assertEqual(own.name_by_user, "Paul Living - " + HOST)
                self.assertEqual(entity.device_id, "own-existing-id")
                self.assertEqual(entities.updated, [])
                self.assertEqual(foreign_ip.identifiers, {IP_IDENTIFIER})
                self.assertEqual(foreign_mac.identifiers, {MAC_IDENTIFIER})
                self.assertEqual(foreign_ip.name, "Foreign IP")
                self.assertEqual(foreign_mac.name, "Foreign MAC")
                self.assertFalse(any(device_id.startswith("foreign") for device_id, _ in registry.updated))
                self.assertEqual(registry.removed, [])
                self.assertEqual(registry.deprecated_accesses, 0)

    async def test_stale_own_ip_device_links_move_to_own_mac_device_only(self):
        own_mac = RegistryDevice("own-mac", {MAC_IDENTIFIER}, {OWNER}, name_by_user="Custom Living")
        own_legacy = RegistryDevice("own-old-ip", {IP_IDENTIFIER}, {OWNER})
        foreign = RegistryDevice("foreign", {IP_IDENTIFIER, MAC_IDENTIFIER}, {FOREIGN_OWNER})
        registry = CurrentRegistry([foreign, own_mac, own_legacy])
        own_entity = RegistryEntity("media_player.living", own_legacy.id)
        foreign_entity = RegistryEntity("media_player.foreign", foreign.id, FOREIGN_OWNER)
        entities = EntityRegistry([own_entity, foreign_entity])

        await self.setup_with_registries(registry, entities)

        self.assertEqual(own_entity.device_id, own_mac.id)
        self.assertEqual(foreign_entity.device_id, foreign.id)
        self.assertEqual(entities.updated, [(own_entity.entity_id, {"device_id": own_mac.id})])
        self.assertEqual(registry.removed, [own_legacy.id])
        self.assertIs(registry.devices[foreign.id], foreign)
        self.assertEqual(own_mac.name_by_user, "Custom Living - " + HOST)
        self.assertEqual(registry.deprecated_accesses, 0)

    async def test_setup_with_only_foreign_collisions_creates_own_device(self):
        foreign = RegistryDevice("foreign", {IP_IDENTIFIER, MAC_IDENTIFIER}, {FOREIGN_OWNER}, name_by_user="Foreign custom")
        registry = CurrentRegistry([foreign])
        entities = EntityRegistry()

        await self.setup_with_registries(registry, entities)

        self.assertEqual(set(registry.devices), {foreign.id, "created-" + OWNER})
        own = registry.devices["created-" + OWNER]
        self.assertEqual(own.config_entries, {OWNER})
        self.assertEqual(own.identifiers, {MAC_IDENTIFIER})
        self.assertEqual(foreign.name_by_user, "Foreign custom")
        self.assertEqual(registry.removed, [])
        self.assertEqual(registry.deprecated_accesses, 0)


class VisualAvailabilityRegistryTests(unittest.TestCase):
    def test_offline_and_online_names_update_only_the_config_entry_device(self):
        for registry_type in (CurrentRegistry, LegacyRegistry):
            with self.subTest(registry_type=registry_type.__name__):
                item = support.entry("router")
                item.data[support.const.CONF_DEVICE_MAC] = MAC
                foreign = RegistryDevice("foreign", {MAC_IDENTIFIER}, {FOREIGN_OWNER}, name="Foreign untouched")
                own = RegistryDevice("own", {MAC_IDENTIFIER}, {OWNER}, name="Living")
                registry = registry_type([foreign, own])

                def update_entry(target, **values):
                    for key, value in values.items():
                        setattr(target, key, value)

                hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(async_update_entry=Mock(side_effect=update_entry)))
                client = types.SimpleNamespace(host=HOST)
                coordinator = support.coordinator_module.AqaraM1SRouterCoordinator(hass, client, item)
                with patch.object(support.coordinator_module.dr, "async_get", return_value=registry), \
                     patch.object(support.device.dr, "async_entries_for_config_entry", side_effect=entry_devices):
                    coordinator._set_visual_availability(False)
                    self.assertEqual(own.name, "Living" + support.coordinator_module.OFFLINE_NAME_SUFFIX)
                    coordinator._set_visual_availability(True)
                self.assertEqual(own.name, "Living")
                self.assertEqual(foreign.name, "Foreign untouched")
                self.assertEqual([device_id for device_id, _ in registry.updated], [own.id, own.id])
                self.assertEqual(registry.deprecated_accesses, 0)

    def test_missing_own_device_does_not_rename_a_foreign_collision(self):
        item = support.entry("router")
        item.data[support.const.CONF_DEVICE_MAC] = MAC
        foreign = RegistryDevice("foreign", {MAC_IDENTIFIER}, {FOREIGN_OWNER}, name="Foreign untouched")
        registry = CurrentRegistry([foreign])
        hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(async_update_entry=Mock()))
        coordinator = support.coordinator_module.AqaraM1SRouterCoordinator(hass, types.SimpleNamespace(host=HOST), item)
        with patch.object(support.coordinator_module.dr, "async_get", return_value=registry):
            coordinator._set_visual_availability(False)
        self.assertEqual(foreign.name, "Foreign untouched")
        self.assertEqual(registry.updated, [])
        self.assertEqual(registry.deprecated_accesses, 0)


class SingularOwnerDevice:
    """Interim HA device whose obsolete plural owner property must not be read."""

    def __init__(self, config_entry_id):
        self.config_entry_id = config_entry_id
        self.deprecated_owner_reads = 0

    @property
    def config_entries(self):
        self.deprecated_owner_reads += 1
        raise AssertionError("Deprecated DeviceEntry.config_entries was accessed")


class DeviceTriggerOwnerCompatibilityTests(unittest.TestCase):
    def test_modern_domain_helper_resolves_own_entry_without_legacy_lookup(self):
        item = support.entry("router")
        item.domain = DOMAIN
        own_device = SingularOwnerDevice(OWNER)
        hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(async_get_entry=Mock()))
        with patch.object(support.trigger_module.dr, "async_get_device_and_config_entry_for_domain",
                          return_value=(own_device, item), create=True) as resolve_owner, \
             patch.object(support.trigger_module.dr, "async_get") as legacy_registry:
            self.assertIs(support.trigger_module._entry_for_device(hass, "own-device"), item)
        resolve_owner.assert_called_once_with(hass, "own-device", domain=DOMAIN)
        legacy_registry.assert_not_called()
        hass.config_entries.async_get_entry.assert_not_called()
        self.assertEqual(own_device.deprecated_owner_reads, 0)

    def test_modern_missing_device_does_not_fall_back_to_unscoped_owner_search(self):
        hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(async_get_entry=Mock()))
        with patch.object(support.trigger_module.dr, "async_get_device_and_config_entry_for_domain",
                          return_value=(None, None), create=True) as resolve_owner, \
             patch.object(support.trigger_module.dr, "async_get") as legacy_registry:
            self.assertIsNone(support.trigger_module._entry_for_device(hass, "missing"))
        resolve_owner.assert_called_once_with(hass, "missing", domain=DOMAIN)
        legacy_registry.assert_not_called()
        hass.config_entries.async_get_entry.assert_not_called()

    def test_interim_singular_owner_avoids_plural_deprecation(self):
        item = support.entry("router")
        item.domain = DOMAIN
        own_device = SingularOwnerDevice(OWNER)
        registry = types.SimpleNamespace(async_get=Mock(return_value=own_device))
        hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(async_get_entry=Mock(return_value=item)))
        with patch.object(support.trigger_module.dr, "async_get_device_and_config_entry_for_domain", None, create=True), \
             patch.object(support.trigger_module.dr, "async_get", return_value=registry):
            self.assertIs(support.trigger_module._entry_for_device(hass, "own-device"), item)
        registry.async_get.assert_called_once_with("own-device")
        hass.config_entries.async_get_entry.assert_called_once_with(OWNER)
        self.assertEqual(own_device.deprecated_owner_reads, 0)

    def test_interim_owner_none_is_not_replaced_by_obsolete_plural_owners(self):
        own_device = SingularOwnerDevice(None)
        registry = types.SimpleNamespace(async_get=Mock(return_value=own_device))
        hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(async_get_entry=Mock()))
        with patch.object(support.trigger_module.dr, "async_get_device_and_config_entry_for_domain", None, create=True), \
             patch.object(support.trigger_module.dr, "async_get", return_value=registry):
            self.assertIsNone(support.trigger_module._entry_for_device(hass, "unowned"))
        hass.config_entries.async_get_entry.assert_not_called()
        self.assertEqual(own_device.deprecated_owner_reads, 0)

    def test_true_old_ha_plural_fallback_skips_other_domains(self):
        item = support.entry("router")
        item.domain = DOMAIN
        foreign = types.SimpleNamespace(entry_id=FOREIGN_OWNER, domain="other_integration")
        old_device = types.SimpleNamespace(config_entries=[FOREIGN_OWNER, OWNER])
        registry = types.SimpleNamespace(async_get=Mock(return_value=old_device))
        entries = {FOREIGN_OWNER: foreign, OWNER: item}
        hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(async_get_entry=Mock(side_effect=entries.get)))
        with patch.object(support.trigger_module.dr, "async_get_device_and_config_entry_for_domain", None, create=True), \
             patch.object(support.trigger_module.dr, "async_get", return_value=registry):
            self.assertIs(support.trigger_module._entry_for_device(hass, "old-device"), item)
        self.assertEqual([args.args[0] for args in hass.config_entries.async_get_entry.call_args_list],
                         [FOREIGN_OWNER, OWNER])

    def test_true_old_ha_missing_device_returns_none(self):
        registry = types.SimpleNamespace(async_get=Mock(return_value=None))
        hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(async_get_entry=Mock()))
        with patch.object(support.trigger_module.dr, "async_get_device_and_config_entry_for_domain", None, create=True), \
             patch.object(support.trigger_module.dr, "async_get", return_value=registry):
            self.assertIsNone(support.trigger_module._entry_for_device(hass, "missing"))
        hass.config_entries.async_get_entry.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
