"""Recovery regressions, including an actual TCP Spinel emulator (no hardware)."""
import asyncio
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
PACKAGE = "guard_regressions"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package


def load(name):
    spec = importlib.util.spec_from_file_location(PACKAGE + "." + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


load("const")
rcp = load("rcp_readiness")
guard_module = load("z2m_guard")
BOOT = "11111111-2222-3333-4444-555555555555"


def diagnostics(**changes):
    fields = dict(role="coordinator", state="ON", enabled="1", port="1886",
                  gpio33="1", gpio18="0", boot_id=BOOT, relay_id="123:456",
                  relays="1", uart_owner="1", stock="0")
    fields.update(changes)
    return "M1S_READY_BEGIN\n" + "\n".join(f"{k}={v}" for k, v in fields.items()) + "\n" + """M1S_SOCKETS_BEGIN
Proto Recv-Q Send-Q Local Address Foreign Address State
tcp 0 0 0.0.0.0:1886 0.0.0.0:* LISTEN
M1S_SOCKETS_END
M1S_READY_END
"""


class PreflightTests(unittest.TestCase):
    def test_snapshot_requires_every_prerequisite(self):
        self.assertEqual(rcp.parse_snapshot(diagnostics(), 1886).connections, 0)
        for key, value in dict(state="OFF", enabled="0", gpio33="0", gpio18="1", role="router",
                               relays="0", uart_owner="0", stock="1", port="6638").items():
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                rcp.parse_snapshot(diagnostics(**{key: value}), 1886)

    def test_snapshot_rejects_incomplete_duplicate_or_stale_identity(self):
        for output in ("state=ON", diagnostics().replace("M1S_READY_END", ""),
                       diagnostics().replace("relays=1", "relays=1\nrelays=1"),
                       diagnostics(boot_id=""), diagnostics(relay_id="")):
            with self.assertRaises(RuntimeError):
                rcp.parse_snapshot(output, 1886)

    def test_snapshot_does_not_count_remote_destination_port(self):
        output = diagnostics().replace("M1S_SOCKETS_END", "tcp 0 0 192.168.0.220:45000 192.168.0.250:1886 ESTABLISHED\nM1S_SOCKETS_END")
        self.assertEqual(rcp.parse_snapshot(output, 1886).connections, 0)
        output = output.replace("M1S_SOCKETS_END", "tcp 0 0 192.168.0.220:1886 192.168.0.250:45000 ESTABLISHED\nM1S_SOCKETS_END")
        self.assertEqual(rcp.parse_snapshot(output, 1886).connections, 1)

    def test_readiness_command_is_passive_and_does_not_require_aux_mqtt(self):
        command = rcp.snapshot_command()
        self.assertNotIn("/dev/tcp", command)
        self.assertNotIn("mqtt_io_service", command)
        self.assertNotIn("coordinator_on.sh", command)
        self.assertNotIn("cat /dev/ttyS1", command)

    def test_hdlc_fragmentation_escaping_crc(self):
        self.assertEqual(rcp.fcs(b"123456789") ^ 0xffff, 0x906e)
        original = b"\x81\x06\x02\x7e\x7d\x11\x13\xf8"
        encoded = rcp.hdlc(original)
        decoder = rcp.Frames()
        frames = []
        for byte in encoded:
            frames.extend(decoder.feed(bytes([byte])))
        self.assertEqual(frames, [original])
        bad = bytearray(encoded)
        bad[2] ^= 1
        self.assertEqual(rcp.Frames().feed(bytes(bad)), [])

    def test_integer_bounds(self):
        for value in (0, 127, 128, 0x120b, 0xffffffff):
            self.assertEqual(rcp.unpack(rcp.packed(value))[0], value)
        for value in (b"", b"\x80", b"\x80" * 6):
            with self.assertRaises(RuntimeError):
                rcp.unpack(value)

    def test_real_tcp_probe_and_socket_release(self):
        self.run_emulator()

    def test_wrong_firmware_is_rejected_without_phy_changes(self):
        self.run_emulator(firmware=b"unrelated\0", error="firmware", expected_phy=[])

    def test_phy_enable_failure_still_disables_radio(self):
        self.run_emulator(reject_enable=True, error="rcp_status", expected_phy=[1, 0])

    def run_emulator(self, firmware=b"OPENTHREAD/0.01.00; JN_5189; M1S_IO_V2\0", reject_enable=False,
                     error=None, expected_phy=None):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(3)
        port = listener.getsockname()[1]
        writes, server_errors, closed = [], [], threading.Event()

        def server():
            try:
                with listener.accept()[0] as connection:
                    connection.settimeout(3)
                    decoder, enabled = rcp.Frames(), 0
                    while True:
                        chunk = connection.recv(1024)
                        if not chunk:
                            closed.set()
                            break
                        for frame in decoder.feed(chunk):
                            command, offset = rcp.unpack(frame, 1)
                            prop, offset = rcp.unpack(frame, offset)
                            values = {1: b"\x04\x03", 2: firmware, 3: b"\x03", 0x20: bytes([enabled])}
                            reply_prop = prop
                            if command == 3:
                                enabled = frame[offset]
                                writes.append(enabled)
                                values[0x20] = bytes([enabled])
                                if enabled and reject_enable:
                                    reply_prop, values[0] = 0, b"\x03"
                            response = rcp.hdlc(bytes((frame[0], 6)) + rcp.packed(reply_prop) + values[reply_prop])
                            # Include an unsolicited valid packet and split TCP
                            # arbitrarily; transaction IDs must still match.
                            connection.sendall(rcp.hdlc(b"\x80\x06\x00\x70") + response[:3])
                            connection.sendall(response[3:])
            except Exception as exc:
                server_errors.append(exc)
            finally:
                listener.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        if error:
            with self.assertRaisesRegex(RuntimeError, error):
                rcp.probe_rcp("127.0.0.1", port, timeout=2)
        else:
            result = rcp.probe_rcp("127.0.0.1", port, timeout=2)
            self.assertEqual(result["phy_test"], "passed")
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(server_errors, [])
        self.assertTrue(closed.is_set())
        self.assertEqual(writes, [1, 0] if expected_phy is None else expected_phy)


class Backend:
    def __init__(self):
        self.data = dict(name="Zigbee2MQTT M1S ZoH", state="started", boot="auto", watchdog=True)
        self.events = []

    async def info(self, slug):
        return dict(self.data)

    async def options(self, slug, values):
        self.events.append(("options", dict(values)))
        self.data.update(values)

    async def stop(self, slug):
        self.events.append(("stop",))
        self.data["state"] = "stopped"

    async def start(self, slug):
        self.events.append(("start",))
        self.data["state"] = "started"


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 0
        self.backend = Backend()
        self.store = types.SimpleNamespace(async_save=AsyncMock(), async_load=AsyncMock(return_value=None))
        self.hass = types.SimpleNamespace(data={}, async_add_executor_job=AsyncMock(side_effect=lambda f, *args: f(*args)))
        self.client = types.SimpleNamespace(host="hub")
        self.guard = guard_module.Z2MGuard(self.hass, types.SimpleNamespace(entry_id="entry"), self.client,
                                         backend=self.backend, store=self.store)
        self.guard.settings = guard_module.validate_settings(dict(enabled=True, addon_slug="local_zigbee2mqtt"))
        self.guard._offline = AsyncMock(side_effect=self.offline)
        self.guard._subscribe = AsyncMock()
        self.guard._mqtt_connected = Mock(return_value=True)
        self.snapshot = rcp.Snapshot(BOOT, BOOT + ":123:456", 1886, 0)
        self.read = self.enterContext(patch.object(guard_module, "read_snapshot", side_effect=lambda *a: self.snapshot))
        self.reset = self.enterContext(patch.object(guard_module, "restart_runtime"))
        self.probe = self.enterContext(patch.object(guard_module, "probe_rcp", return_value={"phy_test": "passed"}))
        self.guard.clock = lambda: self.now

    def offline(self):
        self.guard.bridge_online = False

    async def tick(self, advance=6):
        self.now += advance
        await self.guard.async_tick()

    async def start(self):
        await self.tick()  # stop, reset
        await self.tick()  # fresh baseline
        await self.tick()  # probe, start
        self.assertEqual(self.guard.phase, "starting")
        self.snapshot = rcp.Snapshot(BOOT, BOOT + ":123:456", 1886, 1)
        self.guard._online_since_start = True
        self.guard.bridge_online = True
        await self.tick()
        self.assertTrue(self.guard.ready)

    async def test_stop_reset_probe_start_order_and_no_fixed_boot_delay(self):
        def reset(*args):
            self.assertEqual(self.backend.data["state"], "stopped")
        self.reset.side_effect = reset
        def probe(*args):
            self.assertEqual(self.backend.data["state"], "stopped")
            self.assertTrue(self.reset.called)
            return {"phy_test": "passed"}
        self.probe.side_effect = probe
        await self.start()
        self.assertEqual([event[0] for event in self.backend.events], ["options", "stop", "start"])
        self.assertEqual(self.backend.data["boot"], "manual")
        self.assertFalse(self.backend.data["watchdog"])

    async def test_offline_stops_even_before_radio_preflight(self):
        self.read.side_effect = OSError("hub_offline")
        await self.tick()
        self.assertEqual(self.backend.data["state"], "stopped")
        self.assertEqual(self.guard.phase, "waiting")
        self.reset.assert_not_called()
        self.probe.assert_not_called()

    async def test_no_reset_or_probe_when_port_owned_by_another_client(self):
        self.snapshot = rcp.Snapshot(BOOT, BOOT + ":123:456", 1886, 1)
        await self.tick()
        self.reset.assert_not_called()
        self.probe.assert_not_called()

    async def test_stop_confirmation_required_before_reset(self):
        async def stop(slug):
            pass
        self.backend.stop = stop
        await self.tick()
        self.assertEqual(self.guard.phase, "stopping")
        self.reset.assert_not_called()

    async def test_cached_bridge_online_cannot_finish_startup(self):
        await self.tick()
        await self.tick()
        await self.tick()
        self.guard.bridge_online = True
        self.snapshot = rcp.Snapshot(BOOT, BOOT + ":123:456", 1886, 1)
        await self.tick()
        self.assertFalse(self.guard.ready)
        self.assertEqual(self.guard.phase, "starting")

    async def test_online_without_transport_cannot_finish_startup(self):
        await self.tick()
        await self.tick()
        await self.tick()
        self.guard.bridge_online = self.guard._online_since_start = True
        await self.tick()
        self.assertFalse(self.guard.ready)

    async def test_manual_stop_pauses_and_is_persisted(self):
        await self.start()
        self.backend.data["state"] = "stopped"
        await self.tick()
        self.assertTrue(self.guard.settings["paused"])
        self.assertEqual(self.guard.phase, "paused")
        await self.tick()
        self.assertEqual(sum(event[0] == "start" for event in self.backend.events), 1)

    async def test_power_loss_then_return_recovers_without_manual_restart(self):
        await self.start()
        self.read.side_effect = OSError("unreachable")
        await self.tick()
        self.assertFalse(self.guard.ready)
        self.assertEqual(self.backend.data["state"], "stopped")
        self.read.side_effect = lambda *a: self.snapshot
        self.snapshot = rcp.Snapshot(BOOT, BOOT + ":123:456", 1886, 0)
        await self.tick()
        await self.tick()
        await self.tick()
        self.assertEqual(self.guard.phase, "starting")
        self.assertEqual(sum(event[0] == "start" for event in self.backend.events), 2)

    async def test_relay_restart_without_hub_reboot_stops_and_revalidates(self):
        await self.start()
        self.snapshot = rcp.Snapshot(BOOT, BOOT + ":999:1000", 1886, 1)
        await self.tick()
        self.assertFalse(self.guard.ready)
        self.assertEqual(self.backend.data["state"], "stopped")

    async def test_start_timeout_stops_and_retries_with_limit(self):
        for attempt in range(3):
            await self.tick(100)
            await self.tick()
            await self.tick()
            self.assertEqual(self.guard.phase, "starting")
            await self.tick(100)
            self.assertEqual(self.backend.data["state"], "stopped")
        await self.tick(100)
        self.assertEqual(self.guard.phase, "fault")
        self.assertIn("retry_limit", self.guard.reason)

    async def test_failed_phy_probe_never_starts_addon(self):
        self.probe.side_effect = RuntimeError("phy_rejected")
        await self.tick()
        await self.tick()
        with self.assertRaisesRegex(RuntimeError, "phy_rejected"):
            await self.tick()
        self.assertNotIn(("start",), self.backend.events)
        self.assertFalse(self.guard._allow_online)

    async def test_disable_restores_only_original_supervisor_policy(self):
        await self.tick()
        await self.guard.async_configure(dict(enabled=False))
        self.assertEqual(self.backend.data["boot"], "auto")
        self.assertTrue(self.backend.data["watchdog"])
        self.assertFalse(self.guard.saved)

    async def test_paused_never_preflights_or_starts(self):
        self.guard.settings["paused"] = True
        await self.tick()
        self.reset.assert_not_called()
        self.probe.assert_not_called()
        self.assertEqual(self.backend.data["state"], "stopped")

    async def test_unload_does_not_reenable_watchdog_or_change_boot_policy(self):
        await self.tick()
        before = list(self.backend.events)
        await self.guard.async_shutdown()
        self.assertEqual(self.backend.events, before)

    async def test_disabled_is_inert(self):
        self.guard.settings["enabled"] = False
        await self.tick()
        self.assertFalse(self.backend.events)
        self.read.assert_not_called()

    async def test_mqtt_disconnected_stops_and_never_probes(self):
        self.guard._mqtt_connected.return_value = False
        await self.tick()
        self.assertEqual(self.backend.data["state"], "stopped")
        self.assertEqual(self.guard.reason, "mqtt_disconnected")
        self.probe.assert_not_called()

    async def test_incomplete_configuration_pauses_automatic_start(self):
        self.guard._subscribe.side_effect = RuntimeError("subscription failed")
        with self.assertRaisesRegex(RuntimeError, "subscription failed"):
            await self.guard.async_configure(self.guard.settings)
        self.assertTrue(self.guard.settings["paused"])
        await self.tick()
        self.assertNotIn(("start",), self.backend.events)

    async def test_second_controller_cannot_claim_same_addon(self):
        other = types.SimpleNamespace(settings=self.guard.settings.copy())
        self.hass.data[guard_module.DOMAIN] = {guard_module.DATA_GUARDS: {"other": other}}
        with self.assertRaisesRegex(ValueError, "already managed"):
            await self.guard.async_configure(self.guard.settings)

    async def test_retained_online_is_not_a_start_acknowledgement(self):
        callbacks = []
        mqtt = types.ModuleType("homeassistant.components.mqtt")
        mqtt.async_subscribe = AsyncMock(side_effect=lambda hass, topic, callback, **kw: callbacks.append(callback) or Mock())
        components = types.ModuleType("homeassistant.components")
        components.mqtt = mqtt
        core = types.ModuleType("homeassistant.core")
        core.callback = lambda function: function
        ha = types.ModuleType("homeassistant")
        ha.components = components
        with patch.dict(sys.modules, {"homeassistant": ha, "homeassistant.components": components,
                                     "homeassistant.components.mqtt": mqtt, "homeassistant.core": core}):
            await guard_module.Z2MGuard._subscribe(self.guard)
        self.guard._allow_online = True
        callbacks[0](types.SimpleNamespace(payload='{"state":"online"}', retain=True))
        self.assertFalse(self.guard._online_since_start)
        callbacks[0](types.SimpleNamespace(payload='{"state":"online"}', retain=False))
        self.assertTrue(self.guard._online_since_start)
        self.assertTrue(self.guard.bridge_online)

    async def test_handover_wait_does_not_repeat_radio_probe(self):
        await self.tick()
        await self.tick()
        before = self.snapshot
        connected = rcp.Snapshot(BOOT, before.runtime_id, 1886, 1)
        self.read.side_effect = [before, connected]
        await self.tick()
        self.assertEqual(self.guard.phase, "handover")
        self.read.side_effect = lambda *a: before
        await self.tick()
        self.assertEqual(self.guard.phase, "starting")
        self.probe.assert_called_once()

    async def test_runtime_change_during_probe_never_starts_z2m(self):
        await self.tick()
        await self.tick()
        self.read.side_effect = [self.snapshot, rcp.Snapshot(BOOT, BOOT + ":new", 1886, 0)]
        with self.assertRaisesRegex(RuntimeError, "runtime_changed"):
            await self.tick()
        self.assertNotIn(("start",), self.backend.events)

    async def test_unknown_supervisor_policy_cannot_start(self):
        self.backend.data.pop("watchdog")
        with self.assertRaisesRegex(RuntimeError, "policy_unconfirmed"):
            await self.tick()
        self.reset.assert_not_called()

    async def test_error_state_is_not_confirmation_of_stop(self):
        self.backend.data["state"] = "error"
        self.backend.stop = AsyncMock()
        await self.tick()
        self.assertEqual(self.guard.phase, "stopping")
        self.reset.assert_not_called()

    async def test_new_boot_resets_retry_limit(self):
        await self.tick()
        self.guard._attempts = 3
        self.guard._reset_done = False
        new_boot = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.snapshot = rcp.Snapshot(new_boot, new_boot + ":1:2", 1886, 0)
        await self.tick()
        self.assertEqual(self.guard._attempts, 1)
        self.assertEqual(self.guard.phase, "preparing")

    async def test_supervisor_adapter_uses_only_selected_slug(self):
        target = AsyncMock()
        target.send_command.return_value = {"result": "ok", "data": {"state": "stopped"}}
        const = types.ModuleType("homeassistant.components.hassio.const")
        const.DATA_COMPONENT = "hassio"
        hassio = types.ModuleType("homeassistant.components.hassio")
        hassio.const = const
        with patch.dict(sys.modules, {"homeassistant.components.hassio": hassio,
                                     "homeassistant.components.hassio.const": const}):
            backend = guard_module.SupervisorBackend(types.SimpleNamespace(data={"hassio": target}))
            await backend.stop("local_zigbee2mqtt")
        target.send_command.assert_awaited_once_with("/addons/local_zigbee2mqtt/stop", method="post", payload=None, timeout=30)


if __name__ == "__main__":
    unittest.main()
