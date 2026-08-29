from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_CLIENTS, DATA_COORDINATORS, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    coordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    async_add_entities([AqaraM1SHubConnectivity(entry, client, coordinator)])


class AqaraM1SHubConnectivity(CoordinatorEntity, BinarySensorEntity):
    """Explicit hub connectivity state that itself always stays readable."""

    _attr_name = "Hub Connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:lan-connect"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, client, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_hub_connectivity"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.host)},
            "name": entry.data.get("name", f"Aqara M1S {client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    @property
    def available(self) -> bool:
        # This diagnostic entity must remain available precisely so it can say
        # Disconnected while all hub-dependent controls become unavailable.
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success)
