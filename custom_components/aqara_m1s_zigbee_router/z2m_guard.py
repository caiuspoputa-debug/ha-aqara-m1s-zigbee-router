"""Home Assistant owns add-on recovery; Z2M never supervises its own start."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import logging
import re
import time

from .const import DOMAIN
from .rcp_readiness import read_snapshot, restart_runtime, probe_rcp

_LOGGER = logging.getLogger(__name__)
DATA_GUARDS = "z2m_guards"
POLL_SECONDS = 5
START_TIMEOUT = 90
MAX_ATTEMPTS = 3


def validate_settings(settings):
    values = {"enabled": bool(settings.get("enabled", False)),
              "paused": bool(settings.get("paused", False)),
              "addon_slug": str(settings.get("addon_slug", "")).strip(),
              "base_topic": str(settings.get("base_topic", "zigbee2mqtt")).strip().rstrip("/"),
              "rcp_port": int(settings.get("rcp_port", 1886))}
    if values["enabled"] and not re.fullmatch(r"[a-zA-Z0-9_-]+", values["addon_slug"]):
        raise ValueError("Select the exact Zigbee2MQTT add-on slug")
    if not values["base_topic"] or any(c in values["base_topic"] for c in "+#\x00"):
        raise ValueError("Invalid MQTT base topic")
    if not 1 <= values["rcp_port"] <= 65535:
        raise ValueError("Invalid RCP port")
    return values


class SupervisorBackend:
    def __init__(self, hass):
        self.hass = hass

    async def command(self, path, method="get", payload=None):
        # Use HA's existing authenticated Supervisor session; no token is
        # copied into this integration or its options/storage/logs.
        from homeassistant.components.hassio.const import DATA_COMPONENT
        backend = self.hass.data.get(DATA_COMPONENT)
        if backend is None:
            raise RuntimeError("Home Assistant Supervisor is unavailable")
        response = await backend.send_command(path, method=method, payload=payload, timeout=30)
        if response.get("result") != "ok":
            raise RuntimeError("Supervisor rejected the operation")
        return response.get("data", {})

    async def info(self, slug):
        return await self.command(f"/addons/{slug}/info")

    async def options(self, slug, values):
        await self.command(f"/addons/{slug}/options", "post", values)

    async def start(self, slug):
        await self.command(f"/addons/{slug}/start", "post")

    async def stop(self, slug):
        await self.command(f"/addons/{slug}/stop", "post")


class Z2MGuard:
    def __init__(self, hass, entry, client, *, backend=None, store=None):
        self.hass, self.entry, self.client = hass, entry, client
        self.backend = backend or SupervisorBackend(hass)
        if store is None:
            from homeassistant.helpers.storage import Store
            store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.z2m_guard")
        self.store = store
        self.settings = validate_settings({})
        self.saved = {}
        self.phase = "disabled"
        self.reason = "not_configured"
        self.boot_id = None
        self.runtime_id = None
        self.probe_result = None
        self.bridge_online = False
        self._allow_online = False
        self._online_since_start = False
        self._pending = True  # Restart/preflight after HA reload as well.
        self._reset_done = False
        self._probe_runtime_id = None
        self._candidate = None
        self._candidate_since = 0.0
        self._started_at = None
        self._attempts = 0
        self._retry_at = 0.0
        self._was_running = False
        self._task = None
        self._unsubscribe = None
        self._listeners = set()
        self._lock = asyncio.Lock()
        self._closed = False
        self.clock = time.monotonic
        self._validated_slug = None

    @property
    def ready(self):
        return self.phase == "running" and self.bridge_online

    @property
    def attributes(self):
        return {"phase": self.phase, "reason": self.reason,
                "addon_slug": self.settings["addon_slug"],
                "automatic_recovery": self.settings["enabled"] and not self.settings["paused"],
                "attempts": self._attempts, "boot_id": self.boot_id,
                "rcp_preflight": self.probe_result,
                "radio_over_air_verified": False}

    def listen(self, callback):
        self._listeners.add(callback)
        return lambda: self._listeners.discard(callback)

    def _state(self, phase, reason):
        changed = (self.phase, self.reason) != (phase, reason)
        self.phase, self.reason = phase, reason
        if changed:
            _LOGGER.info("M1S Z2M supervision host=%s phase=%s reason=%s",
                         self.client.host, phase, reason)
        for callback in tuple(self._listeners):
            callback()

    async def _save(self):
        await self.store.async_save({"settings": self.settings, "saved": self.saved})

    async def async_initialize(self):
        data = await self.store.async_load() or {}
        self.settings = validate_settings(data.get("settings", {}))
        self.saved = data.get("saved", {})
        if self.settings["enabled"]:
            await self._subscribe()
        self._task = self.entry.async_create_background_task(
            self.hass, self._loop(), name="M1S Zigbee2MQTT recovery supervisor")

    async def _subscribe(self):
        from homeassistant.components import mqtt
        from homeassistant.core import callback
        if self._unsubscribe:
            self._unsubscribe()
        topic = self.settings["base_topic"] + "/bridge/state"

        @callback
        def receive(message):
            if self._closed or not self.settings["enabled"] or topic != self.settings["base_topic"] + "/bridge/state":
                return
            try:
                payload = message.payload
                value = json.loads(payload) if payload.startswith("{") else {"state": payload}
                online = value.get("state") == "online"
            except (ValueError, TypeError, AttributeError):
                return
            if online and (not self._allow_online or getattr(message, "retain", False)):
                # A retained online value cannot acknowledge THIS startup.
                if not self._allow_online:
                    self.hass.async_create_task(self._offline())
                return
            self.bridge_online = online
            if online:
                self._online_since_start = True
            for callback in tuple(self._listeners):
                callback()

        self._unsubscribe = await mqtt.async_subscribe(self.hass, topic, receive, qos=1)

    async def _offline(self):
        from homeassistant.components import mqtt
        self.bridge_online = False
        if not self._mqtt_connected():
            return
        await mqtt.async_publish(self.hass, self.settings["base_topic"] + "/bridge/state",
                                 json.dumps({"state": "offline"}), qos=1, retain=True)

    def _mqtt_connected(self):
        from homeassistant.components import mqtt
        try:
            return mqtt.is_connected(self.hass)
        except (KeyError, AttributeError):
            return False

    async def async_configure(self, settings):
        values = validate_settings(settings)
        async with self._lock:
            if values["enabled"]:
                for guard in self.hass.data.get(DOMAIN, {}).get(DATA_GUARDS, {}).values():
                    if guard is not self and guard.settings["enabled"] and guard.settings["addon_slug"] == values["addon_slug"]:
                        raise ValueError("This add-on is already managed by another coordinator")
                info = await self.backend.info(values["addon_slug"])
                if "zigbee2mqtt" not in str(info.get("name", "")).lower().replace(" ", ""):
                    raise ValueError("Selected add-on is not Zigbee2MQTT")
            if self.saved and (not values["enabled"] or values["addon_slug"] != self.settings["addon_slug"]):
                await self._restore_supervisor()
            self.settings = values
            self._validated_slug = None
            self._pending = True
            self._reset_done = False
            self._probe_runtime_id = None
            self._candidate = None
            self._started_at = None
            self._attempts = 0
            self._retry_at = 0
            self._allow_online = False
            await self._save()
            if self._unsubscribe:
                self._unsubscribe()
                self._unsubscribe = None
            if values["enabled"]:
                try:
                    await self._subscribe()
                    await self._take_ownership()
                except Exception:
                    # An incomplete configuration must not start an add-on
                    # later, after the UI has reported a configuration error.
                    self.settings["paused"] = True
                    await self._save()
                    self._state("fault", "configuration_failed_automatic_start_paused")
                    raise
                self._state("paused" if values["paused"] else "waiting", "configuration_saved")
            else:
                self._state("disabled", "supervision_disabled")

    async def _take_ownership(self):
        slug = self.settings["addon_slug"]
        for guard in self.hass.data.get(DOMAIN, {}).get(DATA_GUARDS, {}).values():
            if guard is not self and guard.settings["enabled"] and guard.settings["addon_slug"] == slug:
                raise RuntimeError("addon_has_multiple_coordinator_supervisors")
        info = await self.backend.info(slug)
        if "zigbee2mqtt" not in str(info.get("name", "")).lower().replace(" ", ""):
            self._validated_slug = None
            raise RuntimeError("configured_addon_is_not_zigbee2mqtt")
        self._validated_slug = slug
        if not self.saved:
            if info.get("boot") not in {"auto", "manual"} or not isinstance(info.get("watchdog"), bool):
                raise RuntimeError("supervisor_start_policy_unconfirmed")
            self.saved = {"slug": slug, "boot": info["boot"], "watchdog": info["watchdog"]}
            await self._save()  # Persist rollback BEFORE changing Supervisor.
        if self.saved["slug"] != slug:
            raise RuntimeError("supervisor_ownership_mismatch")
        if info.get("boot") != "manual" or info.get("watchdog") is not False:
            await self.backend.options(slug, {"boot": "manual", "watchdog": False})
            info = await self.backend.info(slug)
            if info.get("boot") != "manual" or info.get("watchdog") is not False:
                raise RuntimeError("cannot_gate_supervisor_restarts")
        return info

    async def _restore_supervisor(self):
        await self.backend.options(self.saved["slug"], {key: self.saved[key] for key in ("boot", "watchdog")})
        restored = await self.backend.info(self.saved["slug"])
        if any(restored.get(key) != self.saved[key] for key in ("boot", "watchdog")):
            raise RuntimeError("supervisor_original_policy_restore_unconfirmed")
        self.saved = {}
        await self._save()

    async def _ensure_stopped(self, info):
        self._allow_online = False
        await self._offline()
        if info.get("state") == "stopped":
            return True
        await self.backend.stop(self.settings["addon_slug"])
        check = await self.backend.info(self.settings["addon_slug"])
        return check.get("state") == "stopped"

    def _invalidate(self):
        self._pending = True
        self._reset_done = False
        self._probe_runtime_id = None
        self._candidate = None
        self._started_at = None
        self.probe_result = None
        self._allow_online = False

    async def async_tick(self):
        async with self._lock:
            if not self.settings["enabled"]:
                return
            info = await self._take_ownership()
            if not self._mqtt_connected():
                self._invalidate()
                await self._ensure_stopped(info)
                self._state("waiting", "mqtt_disconnected")
                return
            if self.settings["paused"]:
                await self._ensure_stopped(info)
                self._state("paused", "automatic_start_paused")
                return
            now = self.clock()
            try:
                snapshot = await self.hass.async_add_executor_job(
                    read_snapshot, self.client, self.settings["rcp_port"])
            except Exception as exc:
                self._invalidate()
                self._was_running = False
                stopped = await self._ensure_stopped(info)
                self._state("waiting" if stopped else "stopping", str(exc))
                return

            if self.boot_id != snapshot.boot_id:
                self._attempts = 0
                self._retry_at = 0
                self.boot_id = snapshot.boot_id
            if self.runtime_id is not None and snapshot.runtime_id != self.runtime_id:
                self._invalidate()
            self.runtime_id = snapshot.runtime_id
            running = info.get("state") == "started"

            if not self._pending:
                if not running:
                    # With the hub healthy we cannot distinguish a manual stop
                    # from every process exit. Prefer an explicit pause to
                    # fighting the user's Stop button.
                    self.settings["paused"] = True
                    await self._save()
                    await self._offline()
                    self._state("paused", "addon_stopped_while_coordinator_healthy")
                elif snapshot.connections != 1:
                    self._invalidate()
                    await self._ensure_stopped(info)
                    self._state("waiting", "z2m_transport_session_missing_or_ambiguous")
                elif not self.bridge_online:
                    self._invalidate()
                    await self._ensure_stopped(info)
                    self._state("waiting", "bridge_reported_offline")
                else:
                    self._attempts = 0
                    self._state("running", "rcp_initialized_and_fresh_bridge_online")
                return

            if self._started_at is not None:
                if running and snapshot.connections == 1 and self._online_since_start and self.bridge_online:
                    self._pending = False
                    self._started_at = None
                    self._state("running", "rcp_initialized_and_fresh_bridge_online")
                    return
                if now - self._started_at < START_TIMEOUT:
                    self._state("starting", "waiting_for_fresh_bridge_online_and_transport")
                    return
                self._invalidate()
                await self._ensure_stopped(info)
                self._retry_at = now + min(60, 5 * 2 ** self._attempts)
                self._state("waiting", "z2m_start_confirmation_timeout")
                return

            if not await self._ensure_stopped(info):
                self._state("stopping", "waiting_for_supervisor_stop_confirmation")
                return
            if now < self._retry_at:
                self._state("waiting", "retry_backoff")
                return
            if self._attempts >= MAX_ATTEMPTS and not self._reset_done:
                self._state("fault", "retry_limit_reached_use_configure_to_resume")
                return
            if snapshot.connections:
                self._state("waiting", "rcp_port_has_another_client_no_probe_or_reset")
                return
            if not self._reset_done:
                self._attempts += 1
                self._candidate = None
                self._state("preparing", "restarting_rcp_runtime_with_z2m_stopped")
                try:
                    await self.hass.async_add_executor_job(restart_runtime, self.client)
                except Exception:
                    self._retry_at = now + min(60, 5 * 2 ** self._attempts)
                    raise
                self._reset_done = True
                # coordinator_on starts a new relay; establish its identity
                # on the next poll, rather than invalidating our own reset.
                self.runtime_id = None
                return
            if self._candidate != snapshot.runtime_id:
                self._candidate = snapshot.runtime_id
                self._candidate_since = now
                self._state("stabilizing", "waiting_for_second_fresh_runtime_sample")
                return
            if now - self._candidate_since < POLL_SECONDS:
                return
            self._state("probing", "exclusive_spinel_and_phy_preflight")
            try:
                # Re-check Supervisor immediately before taking radio ownership.
                check = await self.backend.info(self.settings["addon_slug"])
                if check.get("state") != "stopped":
                    raise RuntimeError("addon_started_during_preflight")
                if self._probe_runtime_id != snapshot.runtime_id:
                    self.probe_result = await self.hass.async_add_executor_job(
                        probe_rcp, self.client.host, self.settings["rcp_port"])
                    self._probe_runtime_id = snapshot.runtime_id
                after = await self.hass.async_add_executor_job(
                    read_snapshot, self.client, self.settings["rcp_port"])
                if after.runtime_id != snapshot.runtime_id:
                    raise RuntimeError("runtime_changed_during_preflight")
                # The active probe has CLOSED its socket. Wait for the relay
                # to remove it before handing this single-client port to Z2M.
                if after.connections:
                    self._state("handover", "waiting_for_probe_socket_close")
                    return
                self._online_since_start = False
                self.bridge_online = False
                self._allow_online = True
                self._started_at = self.clock()
                await self.backend.start(self.settings["addon_slug"])
                self._state("starting", "waiting_for_fresh_bridge_online_and_transport")
            except Exception:
                self._invalidate()
                self._retry_at = now + min(60, 5 * 2 ** self._attempts)
                raise

    async def _loop(self):
        while not self._closed:
            try:
                await self.async_tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Failed reads/publishes/stop commands must never grant start.
                self._allow_online = False
                self.bridge_online = False
                with suppress(Exception):
                    if self.settings["enabled"] and self._validated_slug == self.settings["addon_slug"]:
                        await self.backend.stop(self.settings["addon_slug"])
                        await self._offline()
                self._state("fault", str(exc))
            await asyncio.sleep(POLL_SECONDS)

    async def async_shutdown(self):
        self._closed = True
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        # Keep boot=manual/watchdog=false on unload: otherwise HA restarting
        # would silently remove the gate. Disable in Configure to restore them.
