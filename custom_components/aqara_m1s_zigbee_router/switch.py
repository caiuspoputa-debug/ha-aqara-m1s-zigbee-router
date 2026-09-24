from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_CLIENTS, DATA_COORDINATORS, DATA_MEDIA_GROUP, DOMAIN
from .device import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    coordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    manager = hass.data[DOMAIN][DATA_MEDIA_GROUP]
    entities = [
        AqaraM1SMediaGroupMemberSwitch(entry, client, coordinator, manager)
    ]
    if client.zigbee_role == "coordinator":
        status = await hass.async_add_executor_job(client.coordinator_runtime_status)
        entities.append(
            AqaraM1SCoordinatorRadioSwitch(entry, client, coordinator, status)
        )
    async_add_entities(entities)


class AqaraM1SCoordinatorRadioSwitch(CoordinatorEntity, SwitchEntity):
    """Control the persisted JN5189 Coordinator RCP radio state."""

    _attr_name = "Zigbee Coordinator"
    _attr_icon = "mdi:zigbee"
    _attr_should_poll = False

    def __init__(self, entry, client, coordinator, status) -> None:
        super().__init__(coordinator)
        self.client = client
        self._attr_unique_id = f"{entry.entry_id}_coordinator_radio"
        self._attr_device_info = device_info(entry)
        self._attr_is_on = (
            status.get("enabled") == "1" and status.get("state") == "ON"
        )

    async def async_turn_on(self, **kwargs) -> None:
        status = await self.hass.async_add_executor_job(
            self.client.set_coordinator_enabled, True
        )
        self._attr_is_on = status.get("state") == "ON"
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        status = await self.hass.async_add_executor_job(
            self.client.set_coordinator_enabled, False
        )
        self._attr_is_on = status.get("state") == "ON"
        self.async_write_ha_state()


class AqaraM1SMediaGroupMemberSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Include or exclude one hub from the shared media group."""

    _attr_name = "Include in M1S Media Group"
    _attr_icon = "mdi:speaker-multiple"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, client, coordinator, manager) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.client = client
        self.manager = manager
        self._attr_unique_id = f"{entry.entry_id}_media_group_member"
        self._attr_is_on = True
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self._attr_is_on = last is None or last.state == "on"
        self.manager.set_selected(self.entry.entry_id, self._attr_is_on)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()
        await self.manager.async_member_enabled(self.entry.entry_id)

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
        await self.manager.async_member_disabled(self.entry.entry_id)
