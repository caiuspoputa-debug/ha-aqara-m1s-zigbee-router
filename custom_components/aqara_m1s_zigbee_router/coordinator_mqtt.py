"""MQTT transport for role-specific M1S RGB, illuminance and telemetry IO."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback

from .const import CONF_MQTT_IO_CONFIRMED


_LOGGER = logging.getLogger(__name__)


def hub_io_base_topic(host: str) -> str:
    """Use the hub's current IP suffix, never a historical entity ID."""
    topic_id = str(host).strip().rsplit(".", 1)[-1]
    if not topic_id.isdigit() or not 0 <= int(topic_id) <= 255:
        raise ValueError("M1S host does not contain a valid IPv4 suffix")
    return f"m1s/{topic_id}/io"


coordinator_io_base_topic = hub_io_base_topic


def mqtt_availability_is_authoritative(client, mqtt_io) -> bool:
    """Return whether MQTT LWT owns this hub's availability state."""
    return mqtt_io is not None and (
        client.zigbee_role == "coordinator"
        or client.mqtt_io_confirmed
        or mqtt_io.seen
    )


def validate_state(payload: str) -> dict[str, Any]:
    """Validate the complete IO state published by either role's hub daemon."""
    state = json.loads(payload)
    if not isinstance(state, dict):
        raise ValueError("M1S IO state is not an object")
    if state.get("version") != 1 or state.get("capabilities") != 3:
        raise ValueError("M1S IO capability marker does not match")
    rgb = state.get("rgb")
    if (
        not isinstance(rgb, list)
        or len(rgb) != 3
        or any(type(value) is not int or not 0 <= value <= 255 for value in rgb)
    ):
        raise ValueError("M1S RGB state is invalid")
    rgb_valid = state.get("rgb_valid", True)
    if type(rgb_valid) is not bool:
        raise ValueError("M1S RGB validity is invalid")
    if type(state.get("valid")) is not bool:
        raise ValueError("M1S lux validity is invalid")
    for key, limit in (("raw", 4095), ("millivolts", 3600), ("lux", 65535)):
        value = state.get(key)
        if type(value) is not int or not 0 <= value <= limit:
            raise ValueError(f"M1S {key} state is invalid")
    role = state.get("role")
    if role is not None and role not in {"router", "coordinator"}:
        raise ValueError("M1S IO role is invalid")
    sound_mqtt = state.get("sound_mqtt")
    if sound_mqtt is not None and type(sound_mqtt) is not bool:
        raise ValueError("M1S MQTT sound capability is invalid")
    return state


def validate_telemetry(payload: str) -> dict[str, Any]:
    """Validate the retained diagnostic snapshot from the hub agent."""
    state = json.loads(payload)
    if not isinstance(state, dict):
        raise ValueError("M1S telemetry is not an object")
    temperature = state.get("temperature")
    if temperature is not None and (
        type(temperature) not in (int, float) or not 5 <= temperature <= 100
    ):
        raise ValueError("M1S temperature is invalid")
    address = state.get("wifi_ip")
    try:
        if not isinstance(address, str) or ipaddress.ip_address(address).version != 4:
            raise ValueError
    except ValueError as err:
        raise ValueError("M1S Wi-Fi address is invalid") from err
    for key in (
        "homekit_process",
        "mqtt_process",
        "telnet_process",
        "coordinator_process",
        "mqtt_io_process",
    ):
        if state.get(key) not in {"running", "stopped"}:
            raise ValueError(f"M1S {key} state is invalid")
    role = state.get("role", "coordinator")
    if role not in {"router", "coordinator"}:
        raise ValueError("M1S telemetry role is invalid")
    if role == "router" and state.get("jn5189_router") not in {
        "running",
        "check GPIO",
    }:
        raise ValueError("Router JN5189 state is invalid")
    return state


class M1SHubMQTTIO:
    """Own role-specific MQTT IO subscriptions without touching audio."""

    def __init__(self, hass: HomeAssistant, client, coordinator) -> None:
        self.hass = hass
        self.client = client
        self.coordinator = coordinator
        self.base_topic = hub_io_base_topic(client.host)
        self.available = False
        self.seen = bool(client.mqtt_io_confirmed)
        self.sound_supported = client.zigbee_role == "coordinator"
        self.telemetry: dict[str, Any] | None = None
        self._unsubscribers: list = []
        self._sound_lock = asyncio.Lock()
        self._sound_result: asyncio.Future | None = None
        self._refresh_task: asyncio.Task | None = None
        self._refresh_pending = False

    async def async_start(self) -> None:
        """Wait for HA MQTT and subscribe to retained hub state."""
        await mqtt.async_wait_for_mqtt_client(self.hass)
        subscriptions = [
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
                f"{self.base_topic}/availability",
                self._availability_message,
                qos=0,
            ),
        ]
        subscriptions.append(
            await mqtt.async_subscribe(
                self.hass,
                f"m1s/{self.client.host.rsplit('.', 1)[-1]}/sound/status",
                self._sound_status_message,
                qos=0,
            )
        )
        self._unsubscribers.extend(subscriptions)

    async def async_stop(self) -> None:
        """Remove subscriptions owned by this config entry."""
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        self._refresh_pending = False
        refresh_task = self._refresh_task
        self._refresh_task = None
        if refresh_task is not None and not refresh_task.done():
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass
        self.available = False
        self.telemetry = None
        if self._sound_result is not None and not self._sound_result.done():
            self._sound_result.cancel()
        self._sound_result = None

    async def async_set_rgb(self, red: int, green: int, blue: int) -> None:
        """Publish one non-retained RGB command for the role-specific daemon."""
        values = tuple(max(0, min(255, int(value))) for value in (red, green, blue))
        await mqtt.async_publish(
            self.hass,
            f"{self.base_topic}/rgb/set",
            ",".join(str(value) for value in values),
            qos=0,
            retain=False,
        )

    async def async_refresh_lux(self) -> None:
        """Request an immediate sample in addition to the hub's configured cycle."""
        await mqtt.async_publish(
            self.hass,
            f"{self.base_topic}/lux/refresh",
            "now",
            qos=0,
            retain=False,
        )

    async def async_prepare_sound(self, path: str) -> None:
        """Prepare the unchanged TCP/FFmpeg/aplay WAV pipeline through MQTT."""
        if not self.sound_supported:
            raise RuntimeError("Hub does not advertise MQTT WAV support")
        if not self.client.is_deletable_sound_path(path):
            raise ValueError("Sound path must be a WAV below /data/musics")
        await self._async_sound_command("prepare", path, "ready")

    async def async_stop_sound(self) -> None:
        """Stop only the dedicated local-sound pipeline through MQTT."""
        if not self.sound_supported:
            raise RuntimeError("Hub does not advertise MQTT WAV support")
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
                    raise RuntimeError(f"Hub sound command failed: {status}")
            finally:
                if self._sound_result is result:
                    self._sound_result = None

    @callback
    def _state_message(self, message) -> None:
        try:
            state = validate_state(message.payload)
        except (TypeError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.warning("Ignored invalid M1S MQTT state: %s", err)
            return
        published_role = state.get("role", "coordinator")
        if published_role != self.client.zigbee_role:
            _LOGGER.warning(
                "Ignored M1S MQTT state for role %s on %s entry",
                published_role,
                self.client.zigbee_role,
            )
            return
        self.sound_supported = (
            published_role == "coordinator" or state.get("sound_mqtt") is True
        )
        self._mark_seen()
        self.client.coordinator_io_state = state
        data = dict(self.coordinator.data or {})
        data["illuminance"] = (
            {key: state[key] for key in ("raw", "millivolts", "lux")}
            if state["valid"]
            else None
        )
        self.coordinator.data = data
        self._schedule_coordinator_refresh()

    @callback
    def _availability_message(self, message) -> None:
        online = str(message.payload).strip().lower() == "online"
        self.available = online
        if online:
            self._schedule_coordinator_refresh()
            return
        self.client.coordinator_io_state = None
        self.telemetry = None
        data = dict(self.coordinator.data or {})
        data["illuminance"] = None
        data["telemetry"] = None
        self.coordinator.data = data
        self._schedule_coordinator_refresh()

    @callback
    def _telemetry_message(self, message) -> None:
        try:
            telemetry = validate_telemetry(message.payload)
        except (TypeError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.warning("Ignored invalid M1S MQTT telemetry: %s", err)
            return
        published_role = telemetry.get("role", "coordinator")
        if published_role != self.client.zigbee_role:
            _LOGGER.warning(
                "Ignored M1S MQTT telemetry for role %s on %s entry",
                published_role,
                self.client.zigbee_role,
            )
            return
        self._mark_seen()
        self.telemetry = telemetry
        data = dict(self.coordinator.data or {})
        data["telemetry"] = telemetry
        self.coordinator.data = data
        self._schedule_coordinator_refresh()

    @callback
    def _schedule_coordinator_refresh(self) -> None:
        """Let the coordinator own availability after every MQTT change."""
        self._refresh_pending = True
        task = self._refresh_task
        if task is not None and not task.done():
            return
        self._refresh_task = self.hass.async_create_task(
            self._async_refresh_coordinator()
        )

    async def _async_refresh_coordinator(self) -> None:
        """Coalesce retained MQTT messages without losing the final state."""
        try:
            while self._refresh_pending:
                self._refresh_pending = False
                await self.coordinator.async_request_refresh()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.debug(
                "M1S MQTT availability refresh failed for %s: %s",
                self.client.host,
                err,
            )
        finally:
            self._refresh_task = None
            if self._refresh_pending:
                self._schedule_coordinator_refresh()

    @callback
    def _sound_status_message(self, message) -> None:
        result = self._sound_result
        if result is None or result.done():
            return
        status = str(message.payload).strip().lower()
        if status in {"ready", "stopped", "error"}:
            result.set_result(status)

    @callback
    def _mark_seen(self) -> None:
        """Remember that this entry uses the persistent on-hub MQTT transport."""
        self.seen = True
        self.client.mqtt_io_confirmed = True
        entry = self.coordinator.config_entry
        if entry is None or entry.data.get(CONF_MQTT_IO_CONFIRMED) is True:
            return
        data = dict(entry.data)
        data[CONF_MQTT_IO_CONFIRMED] = True
        self.hass.config_entries.async_update_entry(entry, data=data)


# Keep the previous internal name for existing imports and work files.
CoordinatorMQTTIO = M1SHubMQTTIO
