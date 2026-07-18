from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_CLIENTS, DATA_COORDINATORS, DOMAIN


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
    async_add_entities([
        AqaraM1SRouterSensor(hass, entry, client, coordinator, definition)
        for definition in SENSORS
    ], True)


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
