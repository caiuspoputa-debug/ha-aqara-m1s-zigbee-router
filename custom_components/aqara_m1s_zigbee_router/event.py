from __future__ import annotations

from homeassistant.components import mqtt
from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BUTTON_ACTIONS, DATA_CLIENTS, DOMAIN, button_topic_for_host


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    async_add_entities([AqaraM1SPhysicalButtonEvent(entry, client)])


class AqaraM1SPhysicalButtonEvent(EventEntity):
    """Expose the last physical-button action and keep device triggers usable."""

    _attr_name = "Physical Button"
    _attr_icon = "mdi:gesture-tap-button"
    _attr_event_types = list(BUTTON_ACTIONS)

    def __init__(self, entry: ConfigEntry, client) -> None:
        self.entry = entry
        self.client = client
        self._attr_unique_id = f"{entry.entry_id}_physical_button"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.host)},
            "name": entry.data.get("name", f"Aqara M1S {client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        topic = button_topic_for_host(self.client.host)

        async def _message_received(msg) -> None:
            payload = msg.payload
            if isinstance(payload, bytes):
                payload = payload.decode(errors="replace")
            action = str(payload).strip()
            if action not in BUTTON_ACTIONS:
                return
            self._trigger_event(action, {"topic": topic, "host": self.client.host})
            self.async_write_ha_state()

        unsubscribe = await mqtt.async_subscribe(
            self.hass, topic, _message_received, qos=0
        )
        self.async_on_remove(unsubscribe)
