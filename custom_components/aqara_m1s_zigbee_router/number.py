from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_CLIENTS,
    DATA_COORDINATORS,
    DATA_PLAYBACK_VOLUME,
    DATA_RADIO_PLAYERS,
    DOMAIN,
    radio_volume_signal,
)
from .device import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_PLAYBACK_VOLUME, {})

    client = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    coordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]

    async_add_entities(
        [
            AqaraM1SSoundPlaybackVolume(
                hass,
                entry,
                client,
                coordinator,
            ),
        ]
    )


class AqaraM1SSoundPlaybackVolume(
    CoordinatorEntity,
    RestoreEntity,
    NumberEntity,
):
    """Compatibility entity for the same volume used by WAV and all hub media."""

    _attr_name = "Hub Volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 0.01
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client,
        coordinator,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self.hass = hass
        self.entry = entry
        self.client = client

        self._attr_unique_id = f"{entry.entry_id}_sound_playback_volume"
        self.radio_player = hass.data[DOMAIN][DATA_RADIO_PLAYERS][entry.entry_id]
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> float:
        return round(float(self.radio_player._attr_volume_level or 0.0) * 100, 2)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # The media entity restores the authoritative value. The old independent
        # WAV default (50%) must never overwrite a previously quiet radio volume.
        self.async_on_remove(async_dispatcher_connect(
            self.hass, radio_volume_signal(self.entry.entry_id), self.async_write_ha_state))
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        await self.radio_player.async_set_volume_level(float(value) / 100)
        self.async_write_ha_state()


