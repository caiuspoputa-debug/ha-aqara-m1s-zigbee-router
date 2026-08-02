from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import mqtt
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .const import DOMAIN

CONF_SUBTYPE = "subtype"
ACTIONS = ("click", "double_click", "triple_click", "quadruple_click", "five_click", "hold")
TRIGGER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLATFORM): "device",
        vol.Required(CONF_DOMAIN): DOMAIN,
        vol.Required(CONF_DEVICE_ID): str,
        vol.Required(CONF_TYPE): "button_action",
        vol.Required(CONF_SUBTYPE): vol.In(ACTIONS),
    }
)


def _entry_for_device(hass: HomeAssistant, device_id: str):
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN:
            return entry
    return None


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    if _entry_for_device(hass, device_id) is None:
        return []
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: "button_action",
            CONF_SUBTYPE: action,
        }
        for action in ACTIONS
    ]


async def async_get_trigger_capabilities(hass: HomeAssistant, config: dict[str, Any]) -> dict[str, vol.Schema]:
    return {"extra_fields": vol.Schema({})}


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    config = TRIGGER_SCHEMA(config)
    entry = _entry_for_device(hass, config[CONF_DEVICE_ID])
    if entry is None:
        raise ValueError("Aqara M1S config entry not found for device")
    host = str(entry.data["host"])
    hub_id = host.rsplit(".", 1)[-1]
    topic = f"m1s/{hub_id}/button/action"
    wanted = config[CONF_SUBTYPE]

    async def _message_received(msg) -> None:
        payload = msg.payload.decode() if isinstance(msg.payload, bytes) else str(msg.payload)
        if payload.strip() != wanted:
            return
        variables = {
            "trigger": {
                "platform": "device",
                "domain": DOMAIN,
                "device_id": config[CONF_DEVICE_ID],
                "type": config[CONF_TYPE],
                "subtype": wanted,
                "topic": topic,
                "payload": payload.strip(),
                "description": f"Aqara M1S physical button: {wanted}",
            }
        }
        hass.async_run_hass_job(action, variables)

    return await mqtt.async_subscribe(hass, topic, _message_received, qos=0)
