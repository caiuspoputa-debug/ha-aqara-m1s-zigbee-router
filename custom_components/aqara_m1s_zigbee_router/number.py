from __future__ import annotations

import re

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
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_CLIENTS,
    DATA_COORDINATORS,
    DATA_PLAYBACK_VOLUME,
    DOMAIN,
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
    async_add_entities(
        [
            AqaraM1SSoundPlaybackVolume(
                hass,
                entry,
                client,
                hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id],
            )
        ]
    )


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
            try:
                output = (
                    await self.hass.async_add_executor_job(
                        self.client.run_command,
                        "getprop persist.sys.volume",
                    )
                )
                matches = re.findall(
                    r"(?<!\d)(\d{1,3})(?!\d)",
                    output,
                )
                if matches:
                    value = int(matches[-1])
            except Exception:
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
