"""Isolated regression tests; no Home Assistant runtime or real hub required."""
import asyncio
import ast
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parent
stored = {}

class Store:
    def __init__(self, *args): pass
    async def async_load(self): return stored.get('value')
    async def async_save(self, value): stored['value'] = value

for name in ('homeassistant', 'homeassistant.helpers', 'homeassistant.helpers.storage', 'm1stest', 'm1stest.const'):
    sys.modules[name] = types.ModuleType(name)
sys.modules['homeassistant.helpers.storage'].Store = Store
sys.modules['m1stest.const'].DOMAIN = 'aqara_m1s_zigbee_router'
spec = importlib.util.spec_from_file_location('m1stest.shared_mqtt', ROOT / 'custom_components/aqara_m1s_zigbee_router/shared_mqtt.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.modules['m1stest.shared_mqtt'] = module
SETTINGS = dict(host='192.168.0.109', port=1883, username='hub', password="a'$(false);b")

class Hass:
    def __init__(self):
        self.data = {}
        self.loop = types.SimpleNamespace(time=lambda: 100)
    async def async_add_executor_job(self, fn, *args): return fn(*args)

class Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): stored.clear()

    async def test_global_persistence_and_failed_validation(self):
        hass = Hass()
        a, b = await asyncio.gather(module.get_shared_mqtt(hass), module.get_shared_mqtt(hass))
        self.assertIs(a, b)
        with patch.object(module, 'probe_broker'):
            await a.save(SETTINGS)
        self.assertEqual(b.settings, SETTINGS)
        with patch.object(module, 'probe_broker', side_effect=OSError('rejected')):
            with self.assertRaises(OSError): await a.save(dict(SETTINGS, host='other'))
        self.assertEqual(a.settings, SETTINGS)
        restored = await module.get_shared_mqtt(Hass())
        self.assertEqual(restored.settings, SETTINGS)

    async def test_invalid_settings(self):
        for change in ({'host': ''}, {'port': 0}, {'password': '\n'}, {'password': 'x'*81}, {'username': ''}):
            with self.assertRaises(ValueError): module.validate_settings(dict(SETTINGS, **change))

    async def test_paho_accept_and_reject(self):
        import paho.mqtt.client as mqtt
        class Fake:
            accepted = True
            def __init__(self, *args, **kwargs): pass
            def username_pw_set(self, *args): pass
            def connect(self, *args, **kwargs): pass
            def loop(self, **kwargs):
                self.on_connect(self, None, None, 0 if self.accepted else 5, None)
                return mqtt.MQTT_ERR_SUCCESS
            def disconnect(self): pass
        with patch.object(mqtt, 'Client', Fake):
            module.probe_broker(SETTINGS)
            Fake.accepted = False
            with self.assertRaises(ValueError): module.probe_broker(SETTINGS)

    async def test_atomic_shell_write_backup_and_idempotence(self):
        shell = pathlib.Path('C:/Program Files/Git/bin/bash.exe')
        if not shell.exists(): self.skipTest('Git bash unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            config = root / 'm1s_button.conf'
            config.write_text('OLD=1\n')
            (root / 'm1s_mqtt_publish.sh').write_text('#!/bin/sh\n')
            unix = '/'+str(root).replace('\\', '/').replace(':', '', 1)
            class Client:
                def run_command(self, command, **kwargs):
                    command = command.replace('/data/m1s_button', unix)
                    result = subprocess.run([str(shell), '-c', command], capture_output=True, text=True)
                    return result.stdout
            module.apply_to_hub(Client(), SETTINGS)
            self.assertEqual((root / 'm1s_button.conf.before_shared').read_text(), 'OLD=1\n')
            content = config.read_text()
            result = subprocess.run([str(shell), '-c', f'. "{unix}/m1s_button.conf"; printf "%s" "$MQTT_PASSWORD"'], capture_output=True, text=True)
            self.assertEqual(result.stdout, SETTINGS['password'])
            module.apply_to_hub(Client(), SETTINGS)
            self.assertEqual(config.read_text(), content)
            self.assertEqual((root / 'm1s_button.conf.before_shared').read_text(), 'OLD=1\n')

    async def test_missing_hub_runtime_is_failure(self):
        class Client:
            def run_command(self, *args, **kwargs): return ''
        with self.assertRaises(RuntimeError): module.apply_to_hub(Client(), SETTINGS)

    async def test_sync_failure_retry_and_recovery(self):
        tree = ast.parse((ROOT / 'custom_components/aqara_m1s_zigbee_router/coordinator.py').read_text(encoding='utf-8'))
        original = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        method = next(n for n in original.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_sync_shared_mqtt')
        namespace = {'__name__': 'm1stest.coordinator', '__package__': 'm1stest'}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<sync>', 'exec'), namespace)
        coordinator = types.SimpleNamespace(hass=Hass(), client=object(), _mqtt_applied=None)
        manager = types.SimpleNamespace(settings=SETTINGS)
        with patch.object(module, 'apply_to_hub', side_effect=OSError('offline')):
            await namespace['_sync_shared_mqtt'](coordinator, manager, (1, 1))
        self.assertEqual(coordinator.mqtt_sync_state, 'failed')
        self.assertEqual(coordinator._mqtt_retry_at, 160)
        self.assertIsNone(coordinator._mqtt_applied)
        with patch.object(module, 'apply_to_hub'):
            await namespace['_sync_shared_mqtt'](coordinator, manager, (1, 2))
        self.assertEqual(coordinator.mqtt_sync_state, 'applied')
        self.assertEqual(coordinator._mqtt_applied, (1, 2))

    async def test_storage_failure_preserves_active_config(self):
        manager = await module.get_shared_mqtt(Hass())
        with patch.object(module, 'probe_broker'):
            await manager.save(SETTINGS)
            with patch.object(manager.store, 'async_save', side_effect=OSError('disk')):
                with self.assertRaises(OSError): await manager.save(dict(SETTINGS, host='other'))
        self.assertEqual(manager.settings, SETTINGS)
        self.assertEqual(manager.revision, 1)

if __name__ == '__main__': unittest.main()
