"""MQTT transport for Coordinator-only RGB and illuminance sideband IO."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback


_LOGGER = logging.getLogger(__name__)


def coordinator_io_base_topic(host: str) -> str:
    """Use the Coordinator's current IP suffix, never a historical entity ID."""
    topic_id = str(host).strip().rsplit(".", 1)[-1]
    if not topic_id.isdigit() or not 0 <= int(topic_id) <= 255:
        raise ValueError("Coordinator host does not contain a valid IPv4 suffix")
    return f"m1s/{topic_id}/io"


def validate_state(payload: str) -> dict[str, Any]:
    """Validate the complete M1S_IO_V2 state published by the hub daemon."""
    state = json.loads(payload)
    if not isinstance(state, dict):
        raise ValueError("Coordinator IO state is not an object")
    if state.get("version") != 1 or state.get("capabilities") != 3:
        raise ValueError("Coordinator IO capability marker does not match")
    rgb = state.get("rgb")
    if (
        not isinstance(rgb, list)
        or len(rgb) != 3
        or any(type(value) is not int or not 0 <= value <= 255 for value in rgb)
    ):
        raise ValueError("Coordinator RGB state is invalid")
    if type(state.get("valid")) is not bool:
        raise ValueError("Coordinator lux validity is invalid")
    for key, limit in (("raw", 4095), ("millivolts", 3600), ("lux", 65535)):
        value = state.get(key)
        if type(value) is not int or not 0 <= value <= limit:
            raise ValueError(f"Coordinator {key} state is invalid")
    return state


def validate_telemetry(payload: str) -> dict[str, Any]:
    """Validate the retained diagnostic snapshot from the hub agent."""
    state = json.loads(payload)
    if not isinstance(state, dict):
        raise ValueError("Coordinator telemetry is not an object")
    temperature = state.get("temperature")
    if temperature is not None and (
        type(temperature) not in (int, float) or not 5 <= temperature <= 100
    ):
        raise ValueError("Coordinator temperature is invalid")
    address = state.get("wifi_ip")
    try:
        if not isinstance(address, str) or ipaddress.ip_address(address).version != 4:
            raise ValueError
    except ValueError as err:
        raise ValueError("Coordinator Wi-Fi address is invalid") from err
    for key in (
        "homekit_process",
        "mqtt_process",
        "telnet_process",
        "coordinator_process",
        "mqtt_io_process",
    ):
        if state.get(key) not in {"running", "stopped"}:
            raise ValueError(f"Coordinator {key} state is invalid")
    return state


class CoordinatorMQTTIO:
    """Own Coordinator MQTT subscriptions without touching Telnet or UART."""

    def __init__(self, hass: HomeAssistant, client, coordinator) -> None:
        self.hass = hass
        self.client = client
        self.coordinator = coordinator
        self.base_topic = coordinator_io_base_topic(client.host)
        self.available = False
        self.telemetry: dict[str, Any] | None = None
        self._unsubscribers: list = []
        self._sound_lock = asyncio.Lock()
        self._sound_result: asyncio.Future | None = None

    async def async_start(self) -> None:
        """Wait for HA MQTT and subscribe to retained hub state."""
        await mqtt.async_wait_for_mqtt_client(self.hass)
        self._unsubscribers.extend(
            [
                await mqtt.async_subscribe(
                    self.hass,
                    f"{self.base_topic}/state",
                    self._state_message,
                    qos=0,
                ),
                await mqtt.async_subscribe(
                    self.hass,
                    f"m1s/{self.client.host.rsplit('.', 1)[-1]}/telemetry",
                    self._telemetry_message,
                    qos=0,
                ),
                await mqtt.async_subscribe(
                    self.hass,
                    f"m1s/{self.client.host.rsplit('.', 1)[-1]}/sound/status",
                    self._sound_status_message,
                    qos=0,
                ),
                await mqtt.async_subscribe(
                    self.hass,
                    f"{self.base_topic}/availability",
                    self._availability_message,
                    qos=0,
                ),
            ]
        )

    async def async_stop(self) -> None:
        """Remove subscriptions owned by this config entry."""
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        self.available = False
        self.telemetry = None
        if self._sound_result is not None and not self._sound_result.done():
            self._sound_result.cancel()
        self._sound_result = None

    async def async_set_rgb(self, red: int, green: int, blue: int) -> None:
        """Publish one non-retained RGB command for the Coordinator daemon."""
        values = tuple(max(0, min(255, int(value))) for value in (red, green, blue))
        await mqtt.async_publish(
            self.hass,
            f"{self.base_topic}/rgb/set",
            ",".join(str(value) for value in values),
            qos=0,
            retain=False,
        )

    async def async_refresh_lux(self) -> None:
        """Request an immediate sample in addition to the hub's 60-second cycle."""
        await mqtt.async_publish(
            self.hass,
            f"{self.base_topic}/lux/refresh",
            "now",
            qos=0,
            retain=False,
        )

    async def async_prepare_sound(self, path: str) -> None:
        """Prepare the unchanged TCP/FFmpeg/aplay WAV pipeline through MQTT."""
        if not self.client.is_deletable_sound_path(path):
            raise ValueError("Sound path must be a WAV below /data/musics")
        await self._async_sound_command("prepare", path, "ready")

    async def async_stop_sound(self) -> None:
        """Stop only the dedicated local-sound pipeline through MQTT."""
        await self._async_sound_command("stop", "stop", "stopped")

    async def _async_sound_command(
        self, command: str, payload: str, expected: str
    ) -> None:
        topic_id = self.client.host.rsplit(".", 1)[-1]
        async with self._sound_lock:
            result = self.hass.loop.create_future()
            self._sound_result = result
            try:
                await mqtt.async_publish(
                    self.hass,
                    f"m1s/{topic_id}/sound/{command}",
                    payload,
                    qos=0,
                    retain=False,
                )
                status = await asyncio.wait_for(result, timeout=5.0)
                if status != expected:
                    raise RuntimeError(f"Coordinator sound command failed: {status}")
            finally:
                if self._sound_result is result:
                    self._sound_result = None

    @callback
    def _state_message(self, message) -> None:
        try:
            state = validate_state(message.payload)
        except (TypeError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.warning("Ignored invalid Coordinator MQTT state: %s", err)
            return
        self.client.coordinator_io_state = state
        self.available = True
        data = dict(self.coordinator.data or {})
        data["illuminance"] = (
            {key: state[key] for key in ("raw", "millivolts", "lux")}
            if state["valid"]
            else None
        )
        self.coordinator.async_set_updated_data(data)

    @callback
    def _availability_message(self, message) -> None:
        online = str(message.payload).strip().lower() == "online"
        self.available = online
        if online:
            return
        self.client.coordinator_io_state = None
        self.telemetry = None
        data = dict(self.coordinator.data or {})
        data["illuminance"] = None
        data["telemetry"] = None
        self.coordinator.async_set_updated_data(data)

    @callback
    def _telemetry_message(self, message) -> None:
        try:
            telemetry = validate_telemetry(message.payload)
        except (TypeError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.warning("Ignored invalid Coordinator MQTT telemetry: %s", err)
            return
        self.telemetry = telemetry
        data = dict(self.coordinator.data or {})
        data["telemetry"] = telemetry
        self.coordinator.async_set_updated_data(data)

    @callback
    def _sound_status_message(self, message) -> None:
        result = self._sound_result
        if result is None or result.done():
            return
        status = str(message.payload).strip().lower()
        if status in {"ready", "stopped", "error"}:
            result.set_result(status)
