"""Reconcile an enabled Router MQTT agent with its current IPv4 address."""

import base64
import ipaddress
from pathlib import Path
import shlex


def ensure_router_mqtt_topic(client):
    """Repair only a stale AUTO topic; never enable an optional agent."""
    if getattr(client, "zigbee_role", "router") == "coordinator":
        return "not_used"
    if not getattr(client, "mqtt_io_confirmed", False):
        return "not_used"
    address = str(ipaddress.IPv4Address(client.host))
    script = Path(__file__).with_name("router_mqtt_topic_sync.sh").read_bytes()
    encoded = base64.b64encode(script).decode("ascii")
    # Do not send the complete >4 KB script to the interactive Telnet shell
    # in one burst: the hub can truncate pending input, including END markers.
    # Keep every transfer short and wait for its execution acknowledgement.
    commands = ["__m1s_topic_sync_payload=''"]
    for index in range(0, len(encoded), 400):
        chunk = encoded[index:index + 400]
        commands.append(
            '__m1s_topic_sync_payload="${__m1s_topic_sync_payload}"' + shlex.quote(chunk)
        )
    commands.append(
        "printf '%s' \"$__m1s_topic_sync_payload\" | base64 -d | "
        + "M1S_EXPECTED_IPV4=" + shlex.quote(address) + " /bin/sh"
    )
    output = client.run_isolated_commands(commands, timeout=45.0)
    lines = {line.strip() for line in output.splitlines()}
    if "M1S_ROUTER_TOPIC_SYNC_REPAIRED" in lines:
        return "repaired"
    if "M1S_ROUTER_TOPIC_SYNC_READY" in lines:
        return "ready"
    if "M1S_ROUTER_TOPIC_SYNC_NOT_USED" in lines:
        return "not_used"
    raise RuntimeError("Router MQTT topic recovery was not confirmed; retry later")
