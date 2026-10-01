from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import LIGHT_LUX, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_CLIENTS,
    DATA_COORDINATOR_MQTT,
    DATA_COORDINATORS,
    DOMAIN,
)
from .device import device_info


@dataclass
class SensorDef:
    key: str
    name: str
    command: str
    parser: Callable[[str], str | int | float | None]
    unit: str | None = None
    device_class: str | None = None


def last_number(text: str):
    values = re.findall(r"(?<![\d.])-?\d+(?:\.\d+)?", text)
    if not values:
        return None
    value = float(values[-1])
    return int(value) if value.is_integer() else value


def parse_temperature(text: str):
    # The M1S exposes its valid hub temperature through this Android property.
    # Ignore shell-echo numbers such as the "2" from 2>/dev/null and reject the
    # known bogus thermal-zone value of 1 °C.
    values = [float(value) for value in re.findall(r"(?<![\d.])-?\d+(?:\.\d+)?", text)]
    plausible = [value for value in values if 5 <= value <= 100]
    if not plausible:
        return None
    value = plausible[-1]
    return int(value) if value.is_integer() else round(value, 1)


def parse_wifi_ip(text: str):
    for address in re.findall(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", text):
        if not address.startswith("127.") and all(0 <= int(x) <= 255 for x in address.split(".")):
            return address
    return None


SENSORS = [
    SensorDef(
        "temperature",
        "Hub Temperature",
        "getprop persist.sys.temperature 2>/dev/null",
        parse_temperature,
        UnitOfTemperature.CELSIUS,
        SensorDeviceClass.TEMPERATURE,
    ),
    SensorDef("wifi_ip", "WiFi IP", "ifconfig wlan0 | grep 'inet addr'", parse_wifi_ip),
    SensorDef("homekit_process", "HomeKit Process", "ps w | grep homekitserver | grep -v grep",
              lambda value: "running" if "homekitserver" in value else "stopped"),
    SensorDef("mqtt_process", "MQTT Process", "ps w | grep mosquitto | grep -v grep",
              lambda value: "running" if "mosquitto" in value else "stopped"),
    SensorDef("telnet_process", "Telnet Process", "ps w | grep telnetd | grep -v grep",
              lambda value: "running" if "telnetd" in value else "stopped"),
    SensorDef("jn5189_router", "JN5189 Router", "cat /sys/class/gpio/gpio33/value; cat /sys/class/gpio/gpio18/value",
              lambda value: "running" if re.search(r"\b1\s+0\b", value.replace("\r", " ").replace("\n", " ")) else "check GPIO"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entity_registry = er.async_get(hass)
    obsolete_entity_id = entity_registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_volume",
    )
    if obsolete_entity_id is not None:
        entity_registry.async_remove(obsolete_entity_id)

    obsolete_uptime_id = entity_registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_uptime",
    )
    if obsolete_uptime_id is not None:
        entity_registry.async_remove(obsolete_uptime_id)

    client = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    coordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    entities = [
        AqaraM1SRouterSensor(
            hass,
            entry,
            client,
            coordinator,
            definition,
            hass.data[DOMAIN][DATA_COORDINATOR_MQTT].get(entry.entry_id),
        )
        for definition in SENSORS
        if client.zigbee_role != "coordinator" or definition.key != "jn5189_router"
    ]
    entities.append(AqaraM1SMQTTSyncSensor(entry, coordinator))
    entities.append(
        AqaraM1SRouterIlluminanceSensor(
            entry,
            client,
            coordinator,
            hass.data[DOMAIN][DATA_COORDINATOR_MQTT].get(entry.entry_id),
        )
    )
    async_add_entities(entities, coordinator.last_update_success)


class AqaraM1SMQTTSyncSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "MQTT configuration"
    _attr_should_poll = False
    _attr_entity_category = "diagnostic"

    def __init__(self, entry, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_mqtt_configuration"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self):
        return self.coordinator.mqtt_sync_state


class AqaraM1SRouterSensor(CoordinatorEntity, SensorEntity):
    def __init__(
        self,
        hass,
        entry,
        client,
        coordinator,
        definition: SensorDef,
        coordinator_mqtt,
    ) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.client = client
        self.definition = definition
        self.coordinator_mqtt = coordinator_mqtt
        self._was_online = coordinator.last_update_success
        self._attr_name = definition.name
        self._attr_unique_id = f"{entry.entry_id}_{definition.key}"
        self._attr_native_unit_of_measurement = definition.unit
        self._attr_device_class = definition.device_class
        self._attr_device_info = device_info(entry)

    @property
    def available(self):
        if self.client.zigbee_role == "coordinator" or self.client.mqtt_io_confirmed:
            return (
                super().available
                and self.coordinator_mqtt is not None
                and self.coordinator_mqtt.available
                and self.coordinator_mqtt.telemetry is not None
            )
        return super().available

    async def async_update(self) -> None:
        if self.client.zigbee_role == "coordinator" or self.client.mqtt_io_confirmed:
            self._apply_coordinator_telemetry()
            return
        try:
            output = await self.hass.async_add_executor_job(
                self.client.run_command, self.definition.command
            )
            self._attr_native_value = self.definition.parser(output)
        except Exception:
            self._attr_native_value = None

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.client.zigbee_role == "coordinator" or self.client.mqtt_io_confirmed:
            self._apply_coordinator_telemetry()
            self.async_write_ha_state()
            return
        online = self.coordinator.last_update_success
        if online and not self._was_online:
            self.hass.async_create_task(self._async_refresh_after_reconnect())
        self._was_online = online
        super()._handle_coordinator_update()

    def _apply_coordinator_telemetry(self) -> None:
        telemetry = (
            self.coordinator_mqtt.telemetry
            if self.coordinator_mqtt is not None
            else None
        )
        if not isinstance(telemetry, dict):
            self._attr_native_value = None
            return
        key = self.definition.key
        if key == "temperature":
            self._attr_native_value = telemetry.get("temperature")
        elif key == "wifi_ip":
            self._attr_native_value = telemetry.get("wifi_ip")
        elif key in {
            "homekit_process",
            "mqtt_process",
            "telnet_process",
            "jn5189_router",
        }:
            self._attr_native_value = telemetry.get(key)
        else:
            self._attr_native_value = None

    async def _async_refresh_after_reconnect(self) -> None:
        await self.async_update()
        if self.entity_id is not None:
            self.async_write_ha_state()


class AqaraM1SRouterIlluminanceSensor(CoordinatorEntity, SensorEntity):
    @property
    def available(self):
        if self.client.zigbee_role == "coordinator" or self.client.mqtt_io_confirmed:
            return (
                super().available
                and self.coordinator_mqtt is not None
                and self.coordinator_mqtt.available
                and self.client.coordinator_io_state is not None
                and isinstance((self.coordinator.data or {}).get("illuminance"), dict)
            )
        return super().available

    _attr_name = "Illuminance"
    _attr_icon = "mdi:brightness-5"
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = LIGHT_LUX
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, client, coordinator, coordinator_mqtt) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.client = client
        self.coordinator_mqtt = coordinator_mqtt
        # Preserve the v0.1.3 unique ID so the existing registry entity is
        # upgraded in place instead of leaving a duplicate orphan.
        self._attr_unique_id = f"{entry.entry_id}_illuminance_raw"
        self._attr_device_info = device_info(entry)
        self._apply_coordinator_data()

    def _apply_coordinator_data(self) -> None:
        data = self.coordinator.data or {}
        reading = data.get("illuminance")
        if not isinstance(reading, dict):
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        self._attr_native_value = reading.get("lux")
        self._attr_extra_state_attributes = {
            "adc_raw": reading.get("raw"),
            "millivolts": reading.get("millivolts"),
            "source": (
                "JN5189 Coordinator M1S_IO_V2 via MQTT"
                if self.client.zigbee_role == "coordinator"
                else (
                    "JN5189 Router A6 via MQTT"
                    if self.client.mqtt_io_confirmed
                    else "JN5189 UART A6"
                )
            ),
        }

    def _handle_coordinator_update(self) -> None:
        self._apply_coordinator_data()
        self.async_write_ha_state()
