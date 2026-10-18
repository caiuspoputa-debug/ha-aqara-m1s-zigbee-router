from __future__ import annotations

import re

from homeassistant.const import CONF_HOST
from homeassistant.helpers import device_registry as dr

from .const import CONF_DEVICE_MAC, CONF_ZIGBEE_ROLE, DOMAIN

_OFFLINE_SUFFIXES = (" (🔴 Indisponibil)", " (Indisponibil)")
_TRAILING_IPV4_RE = re.compile(r"\s+-\s+(?:\d{1,3}\.){3}\d{1,3}$")
_LEADING_IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}\s+-\s+")


def normalize_mac(value: str | None) -> str:
    """Normalize a Wi-Fi MAC returned by the hub."""
    compact = re.sub(r"[^0-9a-fA-F]", "", str(value or ""))
    if len(compact) != 12:
        return ""
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2)).lower()


def device_identifier(entry) -> tuple[str, str]:
    """Use physical identity when available and retain legacy host fallback."""
    mac = normalize_mac(entry.data.get(CONF_DEVICE_MAC))
    if mac:
        return (DOMAIN, f"mac:{mac}")
    return (DOMAIN, str(entry.data.get(CONF_HOST, "")))


def async_get_entry_device(
    registry: dr.DeviceRegistry,
    config_entry_id: str,
    identifier: tuple[str, str],
) -> dr.DeviceEntry | None:
    """Resolve only this entry's device, including on pre-2026.8 Core."""
    scoped_lookup = getattr(registry, "async_get_device_by_identifier", None)
    if callable(scoped_lookup):
        return scoped_lookup(identifier, config_entry_id)
    # Older Core has no scoped lookup method. Its public entry enumerator
    # provides the same ownership boundary without the deprecated global API.
    return next(
        (device for device in dr.async_entries_for_config_entry(registry, config_entry_id)
         if identifier in device.identifiers),
        None,
    )


def device_name_with_host(name: str, host: str) -> str:
    """Append exactly one current IPv4 address to the friendly name."""
    value = str(name).strip()
    suffix = ""
    for candidate in _OFFLINE_SUFFIXES:
        if value.endswith(candidate):
            value = value[: -len(candidate)].rstrip()
            suffix = candidate
            break
    value = _TRAILING_IPV4_RE.sub("", value).rstrip()
    value = value or "Aqara M1S Zigbee Router"
    return f"{value} - {host}{suffix}" if host else f"{value}{suffix}"


def entry_title_with_host(name: str, host: str) -> str:
    """Prefix config-entry titles with IPv4 so Home Assistant sorts by address."""
    value = str(name).strip()
    suffix = ""
    for candidate in _OFFLINE_SUFFIXES:
        if value.endswith(candidate):
            value = value[: -len(candidate)].rstrip()
            suffix = candidate
            break
    value = _LEADING_IPV4_RE.sub("", value).strip()
    value = _TRAILING_IPV4_RE.sub("", value).strip()
    value = value or "Aqara M1S Zigbee Router"
    return f"{host} - {value}{suffix}" if host else f"{value}{suffix}"


def device_info(entry) -> dict:
    host = str(entry.data.get(CONF_HOST, ""))
    role = entry.data.get(CONF_ZIGBEE_ROLE, "router")
    return {
        "identifiers": {device_identifier(entry)},
        "name": device_name_with_host(
            entry.data.get("name", f"Aqara M1S Router {host}"), host
        ),
        "manufacturer": "Aqara",
        "model": (
            "M1S Gen 1 / JN5189 Coordinator"
            if role == "coordinator"
            else "M1S Gen 1 / JN5189 Router"
        ),
    }
