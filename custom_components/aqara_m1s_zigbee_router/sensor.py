from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_CLIENTS,
    DATA_COORDINATORS,
    DATA_MQTT_CLIENTS,
    DOMAIN,
    MQTT_TOPIC_ZIGBEE,
)


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


def parse_wifi_ip(text: str):
    for address in re.findall(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", text):
        if not address.startswith("127.") and all(0 <= int(x) <= 255 for x in address.split(".")):
            return address
    return None


def _coerce_number(value: Any):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _find_illuminance_resource(node: Any, inherited_did: str | None = None):
    if isinstance(node, dict):
        did = node.get("did", inherited_did)
        if node.get("res_name") == "0.3.85" and did == "lumi.0":
            return _coerce_number(node.get("value"))
        for value in node.values():
            result = _find_illuminance_resource(value, did)
            if result is not None:
                return result
    elif isinstance(node, list):
        for item in node:
            result = _find_illuminance_resource(item, inherited_did)
            if result is not None:
                return result
    return None


SENSORS = [
    SensorDef("temperature", "Temperature", "getprop persist.sys.temperature", last_number,
              UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    SensorDef("volume", "Volume Property", "getprop persist.sys.volume", last_number, PERCENTAGE),
    SensorDef("uptime", "Uptime Seconds", "cat /proc/uptime | cut -d ' ' -f1", last_number, "s"),
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
    client = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    coordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    mqtt_client = hass.data[DOMAIN][DATA_MQTT_CLIENTS][entry.entry_id]
    entities = [
        AqaraM1SRouterSensor(hass, entry, client, coordinator, definition)
        for definition in SENSORS
    ]
    entities.append(AqaraM1SRouterIlluminanceRawSensor(entry, mqtt_client))
    async_add_entities(entities, True)


class AqaraM1SRouterSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, hass, entry, client, coordinator, definition: SensorDef) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.client = client
        self.definition = definition
        self._attr_name = definition.name
        self._attr_unique_id = f"{entry.entry_id}_{definition.key}"
        self._attr_native_unit_of_measurement = definition.unit
        self._attr_device_class = definition.device_class
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.host)},
            "name": entry.data.get("name", f"Aqara M1S Router {client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_update(self) -> None:
        try:
            output = await self.hass.async_add_executor_job(
                self.client.run_command, self.definition.command
            )
            self._attr_native_value = self.definition.parser(output)
        except Exception:
            self._attr_native_value = None


class AqaraM1SRouterIlluminanceRawSensor(SensorEntity):
    _attr_name = "Illuminance Raw"
    _attr_icon = "mdi:brightness-5"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, mqtt_client) -> None:
        self.entry = entry
        self.mqtt_client = mqtt_client
        self._attr_unique_id = f"{entry.entry_id}_illuminance_raw"
        self._attr_available = mqtt_client.connected
        self._attr_device_info = {
            "identifiers": {(DOMAIN, mqtt_client.host)},
            "name": entry.data.get("name", f"Aqara M1S Router {mqtt_client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.mqtt_client.add_message_listener(self._handle_message))
        self.async_on_remove(self.mqtt_client.add_status_listener(self._handle_status))
        self._attr_available = self.mqtt_client.connected
        self.async_write_ha_state()

    def _handle_status(self, connected: bool) -> None:
        self._attr_available = connected
        self.async_write_ha_state()

    def _handle_message(self, topic: str, raw_payload: bytes) -> None:
        if topic != MQTT_TOPIC_ZIGBEE:
            return
        try:
            payload = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        value = _find_illuminance_resource(payload)
        if value is not None:
            self._attr_native_value = value
            self.async_write_ha_state()
