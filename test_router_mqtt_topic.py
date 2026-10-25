"""MQTT IP migration regressions with isolated shell and HA stand-ins."""

import asyncio
import base64
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from shell_test_support import shell_command, shell_path

ROOT = Path(__file__).parent
COMPONENT = ROOT / "custom_components/aqara_m1s_zigbee_router"
SCRIPT = COMPONENT / "router_mqtt_topic_sync.sh"
spec = importlib.util.spec_from_file_location("topic_recovery_under_test", COMPONENT / "router_mqtt_topic.py")
topic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(topic)


class WrapperTests(unittest.TestCase):
    def client(self, **changes):
        fields = dict(host="192.168.0.210", zigbee_role="router", mqtt_io_confirmed=True,
                      run_isolated_command=Mock(return_value="M1S_ROUTER_TOPIC_SYNC_REPAIRED\n"))
        fields.update(changes)
        return types.SimpleNamespace(**fields)

    def test_repaired_topic_uses_isolated_client_and_short_lines(self):
        client = self.client()
        self.assertEqual(topic.ensure_router_mqtt_topic(client), "repaired")
        command = client.run_isolated_command.call_args.args[0]
        self.assertEqual(client.run_isolated_command.call_args.kwargs["timeout"], 45)
        self.assertIn("M1S_EXPECTED_IPV4=192.168.0.210", command)
        self.assertLess(max(map(len, command.splitlines())), 512)
        payload = "".join(re.findall(r"printf '%s' '([A-Za-z0-9+/=]+)'", command))
        self.assertEqual(base64.b64decode(payload), SCRIPT.read_bytes())

    def test_coordinator_never_receives_a_command(self):
        client = self.client(zigbee_role="coordinator")
        self.assertEqual(topic.ensure_router_mqtt_topic(client), "not_used")
        client.run_isolated_command.assert_not_called()

    def test_disabled_or_unconfirmed_agent_is_not_enabled(self):
        client = self.client(mqtt_io_confirmed=False)
        self.assertEqual(topic.ensure_router_mqtt_topic(client), "not_used")
        client.run_isolated_command.assert_not_called()

    def test_ready_and_legacy_runtime_are_accepted(self):
        for marker, expected in (("READY", "ready"), ("NOT_USED", "not_used")):
            self.assertEqual(topic.ensure_router_mqtt_topic(self.client(
                run_isolated_command=Mock(return_value="M1S_ROUTER_TOPIC_SYNC_" + marker))), expected)

    def test_unknown_echo_and_unconfirmed_output_are_rejected(self):
        for output in ("", "echo M1S_ROUTER_TOPIC_SYNC_READY", "M1S_ROUTER_TOPIC_SYNC_DEFERRED"):
            with self.assertRaises(RuntimeError):
                topic.ensure_router_mqtt_topic(self.client(run_isolated_command=Mock(return_value=output)))

    def test_invalid_host_is_rejected_before_transmission(self):
        for host in ("192.168.0.210;reboot", "not-an-ip", "192.168.0.210\n"):
            client = self.client(host=host)
            with self.assertRaises(ValueError):
                topic.ensure_router_mqtt_topic(client)
            client.run_isolated_command.assert_not_called()


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mqtt-ip-test-", dir=ROOT.parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = self.root / "data/m1s_router"
        self.base.mkdir(parents=True)
        (self.root / "tmp").mkdir()
        self.bin = self.root / "commands"
        self.bin.mkdir()
        self.conf = self.base / "mqtt_io.conf"
        self.conf.write_text("MQTT_IO_ENABLED=1\nTOPIC_ID=AUTO\n")
        self.runtime = self.root / "tmp/m1s_router_mqtt_io_runtime.conf"
        self.runtime.write_text("TOPIC_ID=46\n")
        self.log = self.root / "tmp/m1s_router_mqtt_io.log"
        self.log.write_text("MQTT connected and command topics subscribed\ninitial state, lux and telemetry published\n")
        self.write_executable(self.bin / "ifconfig", """#!/bin/sh
echo "inet addr:${TEST_CURRENT_IP:-192.168.0.210}  Bcast:192.168.0.255"
""")
        self.write_executable(self.bin / "netstat", """#!/bin/sh
printf '%s\n' "${TEST_LISTENER:-}"
""")
        self.write_executable(self.base / "mqtt_io_service.sh", """#!/bin/sh
root="$M1S_TOPIC_SYNC_ROOT"
case "$1" in
status) [ "${TEST_RUNNING:-1}" = 1 ] ;;
restart)
    echo restart >> "$root/restarts"
    [ "${TEST_RESTART_FAIL:-0}" = 0 ] || exit 1
    if [ "${TEST_UPDATE_TOPIC:-1}" = 1 ]; then
        printf 'TOPIC_ID=%s\n' "${M1S_EXPECTED_IPV4##*.}" > "$root/tmp/m1s_router_mqtt_io_runtime.conf"
    fi
    if [ "${TEST_FRESH_LOG:-1}" = 1 ]; then
        echo 'MQTT connected and command topics subscribed' >> "$root/tmp/m1s_router_mqtt_io.log"
        echo 'initial state, lux and telemetry published' >> "$root/tmp/m1s_router_mqtt_io.log"
    fi
    ;;
*) exit 1 ;;
esac
""")
        args = shell_command(shell_path(SCRIPT))
        args[0] = shutil.which(args[0]) or args[0]
        self.args = args
        self.environment = dict(os.environ, M1S_TOPIC_SYNC_ROOT=shell_path(self.root),
                                M1S_EXPECTED_IPV4="192.168.0.210", M1S_TOPIC_SYNC_WAIT_SECONDS="0")
        self.environment["PATH"] = shell_path(self.bin) + ":/usr/bin:/bin"

    def write_executable(self, path, content):
        path.write_text(content, newline="\n")
        path.chmod(0o755)

    def run_script(self, **environment):
        return subprocess.run(self.args, env=dict(self.environment, **environment),
                              capture_output=True, text=True, timeout=10)

    def assert_not_restarted(self):
        self.assertFalse((self.root / "restarts").exists())

    def test_ip_change_repairs_topic_and_confirms_new_publication(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("M1S_ROUTER_TOPIC_SYNC_REPAIRED", result.stdout)
        self.assertEqual(self.runtime.read_text(), "TOPIC_ID=210\n")
        self.assertEqual(self.conf.read_text(), "MQTT_IO_ENABLED=1\nTOPIC_ID=AUTO\n")
        self.assertEqual((self.root / "restarts").read_text(), "restart\n")
        self.assertFalse((self.root / "tmp/m1s_router_topic_sync.lock").exists())

    def test_correct_topic_is_idempotent(self):
        self.runtime.write_text("TOPIC_ID=210\n")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("M1S_ROUTER_TOPIC_SYNC_READY", result.stdout)
        self.assert_not_restarted()

    def test_disabled_agent_is_not_started(self):
        self.conf.write_text("MQTT_IO_ENABLED=0\nTOPIC_ID=AUTO\n")
        self.assertIn("M1S_ROUTER_TOPIC_SYNC_NOT_USED", self.run_script().stdout)
        self.assert_not_restarted()

    def test_explicit_topic_is_not_overwritten(self):
        self.conf.write_text("MQTT_IO_ENABLED=1\nTOPIC_ID=106\n")
        self.assertIn("M1S_ROUTER_TOPIC_SYNC_NOT_USED", self.run_script().stdout)
        self.assert_not_restarted()

    def test_missing_legacy_agent_is_skipped(self):
        self.conf.unlink()
        self.assertIn("M1S_ROUTER_TOPIC_SYNC_NOT_USED", self.run_script().stdout)
        self.assert_not_restarted()

    def test_dedicated_coordinator_marker_blocks_restart(self):
        directory = self.root / "data/m1s_coordinator"
        directory.mkdir()
        (directory / "dedicated_mode").touch()
        self.assertIn("M1S_ROUTER_TOPIC_SYNC_NOT_USED", self.run_script().stdout)
        self.assert_not_restarted()

    def test_live_coordinator_role_blocks_restart(self):
        directory = self.root / "data/m1s_coordinator"
        directory.mkdir()
        self.write_executable(directory / "coordinator_status.sh", "#!/bin/sh\necho role=coordinator\n")
        self.assertIn("M1S_ROUTER_TOPIC_SYNC_NOT_USED", self.run_script().stdout)
        self.assert_not_restarted()

    def test_unconfirmed_or_alias_address_does_not_restart(self):
        self.assertNotEqual(self.run_script(TEST_CURRENT_IP="192.168.0.46").returncode, 0)
        self.assert_not_restarted()

    def test_active_wav_receivers_and_uart_tunnel_are_deferred(self):
        for port in (12347, 12348, 1886):
            result = self.run_script(TEST_LISTENER="tcp 0 0 0.0.0.0:" + str(port) + " 0.0.0.0:* LISTEN")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("M1S_ROUTER_TOPIC_SYNC_DEFERRED", result.stdout)
            self.assert_not_restarted()

    def test_uart_maintenance_and_concurrent_recovery_are_deferred(self):
        (self.root / "tmp/m1s_router_mqtt_uart_maintenance").touch()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assert_not_restarted()
        (self.root / "tmp/m1s_router_mqtt_uart_maintenance").unlink()
        (self.root / "tmp/m1s_router_topic_sync.lock").mkdir()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assert_not_restarted()

    def test_old_log_markers_never_confirm_a_new_restart(self):
        result = self.run_script(TEST_FRESH_LOG="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("M1S_ROUTER_TOPIC_SYNC_REPAIRED", result.stdout)

    def test_wrong_runtime_topic_and_failed_restart_are_rejected(self):
        for changes in ({"TEST_UPDATE_TOPIC": "0"}, {"TEST_RESTART_FAIL": "1"}):
            result = self.run_script(**changes)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("M1S_ROUTER_TOPIC_SYNC_REPAIRED", result.stdout)

    def test_broker_button_identity_and_audio_files_are_preserved(self):
        protected = (self.root / "data/m1s_button/m1s_button.conf",
                     self.root / "data/m1s_network/network.conf", self.root / "data/musics/alert.wav")
        for path in protected:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("unchanged-local-fixture\n")
        self.assertEqual(self.run_script().returncode, 0)
        for path in protected:
            self.assertEqual(path.read_text(), "unchanged-local-fixture\n")


class CoordinatorRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import test_coordinator_profile as support
        self.support = support
        self.topic_module = support.load("router_mqtt_topic")

    def coordinator(self, settings=None, confirmed=True):
        client = types.SimpleNamespace(host="192.168.0.210", zigbee_role="router", mqtt_io_confirmed=confirmed)
        hass = types.SimpleNamespace(loop=types.SimpleNamespace(time=lambda: 100), data={},
                                     async_create_task=asyncio.create_task,
                                     async_add_executor_job=AsyncMock(side_effect=lambda fn, *args: fn(*args)))
        coordinator = self.support.coordinator_module.AqaraM1SRouterCoordinator(hass, client)
        coordinator._set_visual_availability = Mock()
        coordinator._schedule_lux_refresh = Mock()
        coordinator._schedule_post_online_cleanup = Mock()
        manager = types.SimpleNamespace(settings=settings, revision=1)
        self.enterContext(patch.object(self.support.coordinator_module, "async_detect_hub_connectivity",
                                      AsyncMock(return_value=(True, "telnet"))))
        self.enterContext(patch.object(self.support.shared_mqtt, "get_shared_mqtt", AsyncMock(return_value=manager)))
        return coordinator, manager

    async def test_reload_repairs_without_saved_shared_credentials(self):
        coordinator, _ = self.coordinator()
        with patch.object(self.topic_module, "ensure_router_mqtt_topic", return_value="repaired") as repair:
            result = await coordinator._async_update_data()
            self.assertTrue(result["online"])
            await coordinator._mqtt_task
            repair.assert_called_once_with(coordinator.client)
        self.assertEqual(coordinator.mqtt_sync_state, "applied")
        self.assertEqual(coordinator._mqtt_applied, (1, 1, "192.168.0.210"))

    async def test_success_is_not_repeated_on_every_poll(self):
        coordinator, _ = self.coordinator()
        with patch.object(self.topic_module, "ensure_router_mqtt_topic", return_value="ready") as repair:
            await coordinator._async_update_data()
            await coordinator._mqtt_task
            await coordinator._async_update_data()
            repair.assert_called_once()

    async def test_host_change_triggers_a_new_check(self):
        coordinator, _ = self.coordinator()
        with patch.object(self.topic_module, "ensure_router_mqtt_topic", return_value="ready") as repair:
            await coordinator._async_update_data()
            await coordinator._mqtt_task
            coordinator.client.host = "192.168.0.211"
            await coordinator._async_update_data()
            await coordinator._mqtt_task
            self.assertEqual(repair.call_count, 2)
        self.assertEqual(coordinator._mqtt_applied, (1, 1, "192.168.0.211"))

    async def test_failure_preserves_hub_availability_and_backs_off(self):
        coordinator, _ = self.coordinator()
        with patch.object(self.topic_module, "ensure_router_mqtt_topic", side_effect=RuntimeError("deferred")) as repair:
            result = await coordinator._async_update_data()
            await coordinator._mqtt_task
            self.assertTrue(result["online"])
            self.assertEqual(coordinator._mqtt_retry_at, 160)
            self.assertIsNone(coordinator._mqtt_applied)
            await coordinator._async_update_data()
            repair.assert_called_once()
        coordinator.hass.loop.time = lambda: 161
        with patch.object(self.topic_module, "ensure_router_mqtt_topic", return_value="repaired"):
            await coordinator._async_update_data()
            await coordinator._mqtt_task
        self.assertEqual(coordinator.mqtt_sync_state, "applied")

    async def test_shared_configuration_is_applied_before_recovery(self):
        coordinator, _ = self.coordinator(settings={"host": "192.168.0.20"})
        order = []
        with patch.object(self.support.shared_mqtt, "apply_to_hub", side_effect=lambda *_: order.append("settings")), \
             patch.object(self.topic_module, "ensure_router_mqtt_topic", side_effect=lambda *_: order.append("topic")):
            await coordinator._async_update_data()
            await coordinator._mqtt_task
        self.assertEqual(order, ["settings", "topic"])

    async def test_legacy_disabled_agent_does_not_schedule_recovery(self):
        coordinator, _ = self.coordinator(confirmed=False)
        await coordinator._async_update_data()
        self.assertIsNone(coordinator._mqtt_task)


if __name__ == "__main__":
    unittest.main()
