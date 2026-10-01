"""One persisted MQTT configuration for all hubs in this HA installation."""
from __future__ import annotations

import asyncio
import base64
import shlex
import time

from homeassistant.helpers.storage import Store

from .const import DOMAIN


def validate_settings(values):
    result = {key: str(values.get(key, "")) for key in ("host", "username", "password")}
    result["host"] = result["host"].strip()
    result["port"] = int(values.get("port", 1883))
    if not result["host"] or any(c.isspace() for c in result["host"]) or "://" in result["host"]:
        raise ValueError("invalid host")
    if not 1 <= result["port"] <= 65535:
        raise ValueError("invalid port")
    # The installed BusyBox publisher uses a one-byte MQTT remaining length
    # and shell character counts. Keep its existing protocol within bounds.
    for value in result.values():
        if isinstance(value, str) and (not value.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError("unsupported characters")
    if not result["username"] or not result["password"]:
        raise ValueError("credentials required")
    if len(result["username"]) + len(result["password"]) > 80:
        raise ValueError("credentials too long for hub publisher")
    return result


def probe_broker(settings):
    """Validate CONNACK using Paho; never include credentials in errors."""
    import paho.mqtt.client as mqtt

    accepted = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="m1s-check-" + str(time.monotonic_ns()), protocol=mqtt.MQTTv311)
    client.username_pw_set(settings["username"], settings["password"])
    client.connect_timeout = 5.0
    client.on_connect = lambda _c, _u, _f, reason, _p: accepted.append(reason == 0)
    try:
        client.connect(settings["host"], settings["port"], keepalive=15)
        deadline = time.monotonic() + 5
        while not accepted and time.monotonic() < deadline:
            if client.loop(timeout=0.25) != mqtt.MQTT_ERR_SUCCESS:
                break
        if accepted != [True]:
            raise ValueError("broker rejected connection")
    finally:
        client.disconnect()


def apply_to_hub(client, settings):
    """Back up and atomically replace only the existing MQTT configuration."""
    names = {"host": "BROKER_HOST", "port": "BROKER_PORT", "username": "MQTT_USERNAME", "password": "MQTT_PASSWORD"}
    content = "".join(f"{names[k]}={shlex.quote(str(settings[k]))}\n" for k in names)
    payload = base64.b64encode(content.encode()).decode()
    command = (
        "( umask 077; f=/data/m1s_button/m1s_button.conf; "
        "test -f \"$f\" && test -x /data/m1s_button/m1s_mqtt_publish.sh || exit 1; "
        "t=$(mktemp /data/m1s_button/.mqtt.XXXXXX) || exit 1; "
        "trap 'rm -f \"$t\"' EXIT; "
        f"printf '%s' '{payload}' | base64 -d > \"$t\" || exit 1; "
        "sh -n \"$t\" || exit 1; "
        "if cmp -s \"$t\" \"$f\"; then echo M1S_MQTT_SYNC_OK; exit 0; fi; "
        "cp -p \"$f\" \"$f.before_shared\" && chmod 600 \"$f.before_shared\" && "
        "chmod 600 \"$t\" && mv \"$t\" \"$f\" || exit 1; "
        "if [ -x /data/m1s_coordinator/mqtt_io_service.sh ]; then "
        "/data/m1s_coordinator/mqtt_io_service.sh restart "
        ">/tmp/m1s_mqtt_io_config_restart.log 2>&1 || exit 1; fi; "
        "echo M1S_MQTT_SYNC_OK )"
    )
    output = client.run_command(command, timeout=12)
    if "M1S_MQTT_SYNC_OK" not in output.splitlines():
        raise RuntimeError("MQTT configuration not applied")


class SharedMQTT:
    def __init__(self, hass):
        self.hass = hass
        self.store = Store(hass, 1, DOMAIN + ".shared_mqtt")
        self.lock = asyncio.Lock()
        self.loaded = False
        self.settings = None
        self.revision = 0

    async def load(self):
        async with self.lock:
            if not self.loaded:
                saved = await self.store.async_load()
                if saved:
                    self.settings = validate_settings(saved["settings"])
                    self.revision = saved.get("revision", 1)
                self.loaded = True
        return self

    async def save(self, values):
        settings = validate_settings(values)
        async with self.lock:
            await self.hass.async_add_executor_job(probe_broker, settings)
            revision = self.revision + 1
            await self.store.async_save({"settings": settings, "revision": revision})
            self.settings, self.revision = settings, revision


async def get_shared_mqtt(hass):
    data = hass.data.setdefault(DOMAIN, {})
    if "shared_mqtt" not in data:
        data["shared_mqtt"] = SharedMQTT(hass)
    return await data["shared_mqtt"].load()
