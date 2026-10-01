from __future__ import annotations

import asyncio
import logging

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_CLIENTS,
    DATA_COORDINATOR_MQTT,
    DATA_COORDINATORS,
    DOMAIN,
)
from .device import device_info


_LOGGER = logging.getLogger(__name__)
RECONNECT_RESTORE_DELAY_SECONDS = 2.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    async_add_entities([
        AqaraM1SRouterRingLight(
            hass,
            entry,
            client,
            hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id],
            hass.data[DOMAIN][DATA_COORDINATOR_MQTT].get(entry.entry_id),
        )
    ])


class AqaraM1SRouterRingLight(CoordinatorEntity, RestoreEntity, LightEntity):
    _attr_name = "Ring Light"
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_should_poll = False

    @property
    def available(self):
        if self.client.zigbee_role == "coordinator" or self.client.mqtt_io_confirmed:
            return (
                super().available
                and self.coordinator_mqtt is not None
                and self.coordinator_mqtt.available
                and self.client.coordinator_io_state is not None
            )
        return super().available

    @property
    def is_on(self):
        if self.client.zigbee_role == "coordinator" or self.client.mqtt_io_confirmed:
            state = self.client.coordinator_io_state
            if state and state.get("rgb_valid", True):
                return bool(any(state["rgb"]))
        return self._attr_is_on

    def __init__(self, hass, entry, client, coordinator, coordinator_mqtt) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.client = client
        self.coordinator_mqtt = coordinator_mqtt
        self._attr_unique_id = f"{entry.entry_id}_ring_light"
        self._attr_is_on = False
        self._attr_brightness = 64
        self._attr_rgb_color = (255, 0, 0)
        self._restore_task: asyncio.Task | None = None
        self._online_generation = (coordinator.data or {}).get(
            "online_generation", 0
        )
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored = await self.async_get_last_state()
        if restored is not None:
            if restored.attributes.get("brightness") is not None:
                self._attr_brightness = int(restored.attributes["brightness"])
            rgb = restored.attributes.get("rgb_color")
            if rgb and len(rgb) == 3:
                self._attr_rgb_color = tuple(int(value) for value in rgb)
        # Setup physically turns off the red boot light. Restore only the last
        # chosen color and brightness, never a stale ON state.
        self._attr_is_on = False

    def _handle_coordinator_update(self) -> None:
        if self.client.zigbee_role == "coordinator" or self.client.mqtt_io_confirmed:
            state = self.client.coordinator_io_state
            if state and state.get("rgb_valid", True):
                self._attr_is_on = bool(any(state["rgb"]))
                if self._attr_is_on:
                    peak = max(state["rgb"])
                    self._attr_brightness = peak
                    self._attr_rgb_color = tuple(
                        round(value * 255 / peak) for value in state["rgb"]
                    )
            super()._handle_coordinator_update()
            return
        generation = (self.coordinator.data or {}).get(
            "online_generation", 0
        )
        if generation != self._online_generation:
            previous_generation = self._online_generation
            self._online_generation = generation
            if previous_generation > 0 and generation > previous_generation:
                self._schedule_reconnect_restore(generation)
        super()._handle_coordinator_update()

    def _schedule_reconnect_restore(self, generation: int) -> None:
        task = self._restore_task
        if task is not None and not task.done():
            task.cancel()
        self._restore_task = self.hass.async_create_task(
            self._async_restore_after_reconnect(generation)
        )

    async def _async_restore_after_reconnect(self, generation: int) -> None:
        """Restore the last requested Router ring state after a real reconnect."""
        try:
            await asyncio.sleep(RECONNECT_RESTORE_DELAY_SECONDS)
            if (
                self.client.zigbee_role == "coordinator"
                or self.client.mqtt_io_confirmed
                or generation != self._online_generation
                or not self.coordinator.last_update_success
            ):
                return

            if self._attr_is_on:
                brightness = self._attr_brightness or 255
                red, green, blue = self._attr_rgb_color or (255, 255, 255)
                rgb = (
                    round(red * brightness / 255),
                    round(green * brightness / 255),
                    round(blue * brightness / 255),
                )
            else:
                rgb = (0, 0, 0)

            await self.hass.async_add_executor_job(self.client.set_rgb, *rgb)
            self.async_write_ha_state()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.debug(
                "Could not restore Aqara M1S ring state after reconnect host=%s: %s",
                self.client.host,
                err,
            )
        finally:
            if self._restore_task is asyncio.current_task():
                self._restore_task = None

    async def async_will_remove_from_hass(self) -> None:
        task = self._restore_task
        self._restore_task = None
        if task is not None and not task.done():
            task.cancel()
        await super().async_will_remove_from_hass()

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_RGB_COLOR in kwargs:
            self._attr_rgb_color = tuple(int(v) for v in kwargs[ATTR_RGB_COLOR])
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = max(1, min(255, int(kwargs[ATTR_BRIGHTNESS])))
        brightness = self._attr_brightness or 255
        red, green, blue = self._attr_rgb_color or (255, 255, 255)
        rgb = (
            round(red * brightness / 255),
            round(green * brightness / 255),
            round(blue * brightness / 255),
        )
        if self.client.zigbee_role == "coordinator" or self.client.mqtt_io_confirmed:
            if self.coordinator_mqtt is None:
                raise RuntimeError("M1S MQTT IO is not configured")
            if not self.coordinator_mqtt.available:
                raise RuntimeError("M1S MQTT IO is unavailable")
            await self.coordinator_mqtt.async_set_rgb(*rgb)
        else:
            await self.hass.async_add_executor_job(self.client.set_rgb, *rgb)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        if self.client.zigbee_role == "coordinator" or self.client.mqtt_io_confirmed:
            if self.coordinator_mqtt is None:
                raise RuntimeError("M1S MQTT IO is not configured")
            if not self.coordinator_mqtt.available:
                raise RuntimeError("M1S MQTT IO is unavailable")
            await self.coordinator_mqtt.async_set_rgb(0, 0, 0)
        else:
            await self.hass.async_add_executor_job(self.client.set_rgb, 0, 0, 0)
        self._attr_is_on = False
        self.async_write_ha_state()
