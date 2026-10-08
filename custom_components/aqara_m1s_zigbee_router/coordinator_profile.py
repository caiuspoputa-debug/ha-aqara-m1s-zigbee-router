"""Read-only Linux diagnostics for a Zigbee-only coordinator."""
from __future__ import annotations

import re

COORDINATOR_PLATFORMS = ["binary_sensor", "sensor"]
COORDINATOR_SENSOR_KEYS = ("wifi_ip", "mqtt_process", "telnet_process", "zigbee_transport")
COORDINATOR_OPTIONS = ["network_address", "change_wifi"]
DIAGNOSTICS_INTERVAL_SECONDS = 30.0

# No UART access, relay connection, file writes or service-management commands.
DIAGNOSTICS_COMMAND = (
    "( m=stopped; t=stopped; for f in /proc/[0-9]*/comm; do "
    "read -r c < \"$f\" 2>/dev/null || continue; "
    "case \"$c\" in mosquitto) m=running;; telnetd) t=running;; esac; done; "
    "echo M1S_DIAGNOSTICS_BEGIN; "
    "printf 'wifi_ip='; ifconfig wlan0 | sed -n 's/.*inet addr:\\([^ ]*\\).*/\\1/p'; "
    "echo \"mqtt_process=$m\"; echo \"telnet_process=$t\"; "
    "echo M1S_NETSTAT_BEGIN; netstat -ant; echo M1S_NETSTAT_END; "
    "echo M1S_DIAGNOSTICS_END )"
)


def coordinator_entity_unique_ids(entry_id: str) -> set[str]:
    return {f"{entry_id}_{key}" for key in (*COORDINATOR_SENSOR_KEYS, "hub_connectivity")}


def obsolete_coordinator_entities(entities, entry_id: str, domain: str) -> list[str]:
    """Remove only this integration's former per-hub entities, never the group."""
    keep = coordinator_entity_unique_ids(entry_id)
    prefix = f"{entry_id}_"
    return [entity.entity_id for entity in entities
            if entity.platform == domain and entity.unique_id.startswith(prefix)
            and entity.unique_id not in keep]


def parse_diagnostics(output: str) -> dict[str, str]:
    match = re.search(
        r"(?m)^M1S_DIAGNOSTICS_BEGIN\r?$\n(.*?)^M1S_DIAGNOSTICS_END\r?$",
        output, re.S,
    )
    if match is None:
        raise RuntimeError("Coordinator diagnostics response is incomplete")
    values = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key in COORDINATOR_SENSOR_KEYS:
            values[key] = value
    ip = values.get("wifi_ip", "")
    if not re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", ip) or any(int(part) > 255 for part in ip.split(".")):
        raise RuntimeError("Coordinator diagnostics contain no valid Wi-Fi IP")
    if any(values.get(key) not in {"running", "stopped"} for key in ("mqtt_process", "telnet_process")):
        raise RuntimeError("Coordinator process diagnostics are incomplete")
    sockets = re.search(r"(?m)^M1S_NETSTAT_BEGIN\r?$\n(.*?)^M1S_NETSTAT_END\r?$", match.group(1), re.S)
    if sockets is None or "Local Address" not in sockets.group(1):
        raise RuntimeError("Coordinator transport diagnostics are incomplete")
    transport = "stopped"
    for line in sockets.group(1).splitlines():
        fields = line.split()
        if len(fields) < 6 or fields[0] not in {"tcp", "tcp6"}:
            continue
        if fields[3].rsplit(":", 1)[-1] != "1886":
            continue
        if fields[5] == "ESTABLISHED":
            transport = "connected"
            break
        if fields[5] == "LISTEN":
            transport = "listening"
    values["zigbee_transport"] = transport
    return values


def read_diagnostics(client) -> dict[str, str]:
    return parse_diagnostics(client.run_command(DIAGNOSTICS_COMMAND, timeout=8, connect_timeout=2))
