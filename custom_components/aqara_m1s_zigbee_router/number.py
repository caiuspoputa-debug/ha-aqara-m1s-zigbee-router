from __future__ import annotations

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_CLIENTS,
    DATA_COORDINATORS,
    DATA_PLAYBACK_VOLUME,
    DATA_RADIO_PLAYERS,
    DATA_MEDIA_GROUP,
    DOMAIN,
    radio_volume_signal,
    media_group_volume_signal,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(
        DATA_PLAYBACK_VOLUME,
        {},
    )

    client = hass.data[DOMAIN][DATA_CLIENTS][
        entry.entry_id
    ]
    coordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    radio_player = hass.data[DOMAIN][DATA_RADIO_PLAYERS][entry.entry_id]

    entities = [
        AqaraM1SSoundPlaybackVolume(
            hass,
            entry,
            client,
            coordinator,
        ),
        AqaraM1SRadioFineVolume(
            entry,
            client,
            coordinator,
            radio_player,
        ),
    ]
    manager = hass.data[DOMAIN][DATA_MEDIA_GROUP]
    if not manager.volume_entity_added:
        manager.volume_entity_added = True
        entities.append(AqaraM1SGroupFineVolume(manager))
    async_add_entities(entities)


class AqaraM1SSoundPlaybackVolume(
    CoordinatorEntity,
    RestoreEntity,
    NumberEntity,
):
    _attr_name = "Sound Playback Volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
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

        self._attr_unique_id = (
            f"{entry.entry_id}"
            "_sound_playback_volume"
        )
        self._attr_native_value = 50
        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, self.client.host)
            },
            "name": entry.data.get(
                "name",
                (
                    "Aqara M1S "
                    f"{self.client.host}"
                ),
            ),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        restored = await self.async_get_last_state()
        value = None

        if restored is not None:
            try:
                value = int(float(restored.state))
            except (TypeError, ValueError):
                value = None

        if value is None:
            value = 50

        value = max(1, min(100, value))
        self._attr_native_value = value
        self.hass.data.setdefault(DOMAIN, {})
        self.hass.data[DOMAIN].setdefault(
            DATA_PLAYBACK_VOLUME,
            {},
        )
        self.hass.data[DOMAIN][
            DATA_PLAYBACK_VOLUME
        ][self.entry.entry_id] = value
        self.async_write_ha_state()

    async def async_set_native_value(
        self,
        value: float,
    ) -> None:
        safe_value = max(
            1,
            min(100, int(round(value))),
        )
        self._attr_native_value = safe_value
        self.hass.data.setdefault(DOMAIN, {})
        self.hass.data[DOMAIN].setdefault(
            DATA_PLAYBACK_VOLUME,
            {},
        )
        self.hass.data[DOMAIN][
            DATA_PLAYBACK_VOLUME
        ][self.entry.entry_id] = safe_value
        self.async_write_ha_state()


class AqaraM1SRadioFineVolume(
    CoordinatorEntity,
    NumberEntity,
):
    """Precise individual-player volume slider from 0% to 100% in 0.2% steps."""

    _attr_name = "Media Player Volume 0-100% - Step 0.2%"
    _attr_icon = "mdi:volume-low"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 0.2
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        client,
        coordinator,
        radio_player,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self.entry = entry
        self.client = client
        self.radio_player = radio_player
        self._attr_unique_id = f"{entry.entry_id}_radio_fine_volume"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.client.host)},
            "name": entry.data.get(
                "name",
                f"Aqara M1S {self.client.host}",
            ),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    @property
    def native_value(self) -> float:
        """Return current individual-player volume as a 0-100 percentage."""
        volume_level = self.radio_player.volume_level or 0.0
        return round(min(100.0, max(0.0, volume_level * 100.0)), 1)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                radio_volume_signal(self.entry.entry_id),
                self._handle_radio_volume_update,
            )
        )

    def _handle_radio_volume_update(self) -> None:
        """Refresh the fine-volume entity from any dispatcher thread."""
        # Dispatcher callbacks are not guaranteed to run in Home Assistant's
        # event-loop thread. schedule_update_ha_state() is the thread-safe API;
        # calling async_write_ha_state() here is rejected by recent HA versions.
        self.schedule_update_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set individual-player volume between 0% and 100% in 0.2% steps."""
        safe_percent = round(round(max(0.0, min(100.0, float(value))) / 0.2) * 0.2, 1)
        await self.radio_player.async_set_volume_level(safe_percent / 100.0)
        self.async_write_ha_state()


class AqaraM1SGroupFineVolume(NumberEntity):
    """Precise shared-group volume slider from 0% to 100% in 0.2% steps."""

    _attr_name = "M1S Media Group Volume 0-100% - Step 0.2%"
    _attr_unique_id = "aqara_m1s_media_group_fine_volume"
    _attr_icon = "mdi:volume-low"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 0.2
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False

    def __init__(self, manager) -> None:
        self.manager = manager

    @property
    def native_value(self) -> float:
        return round(min(100.0, max(0.0, self.manager.volume * 100.0)), 1)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                media_group_volume_signal(),
                self._handle_update,
            )
        )

    def _handle_update(self) -> None:
        self.schedule_update_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        self.manager.volume_entity_added = False
        await super().async_will_remove_from_hass()

    async def async_set_native_value(self, value: float) -> None:
        safe_percent = round(round(max(0.0, min(100.0, float(value))) / 0.2) * 0.2, 1)
        await self.manager.async_set_volume(safe_percent / 100.0)
        self.async_write_ha_state()
