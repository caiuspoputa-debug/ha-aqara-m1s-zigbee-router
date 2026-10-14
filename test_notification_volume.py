"""Notification migration and unchanged receiver gain-before-start contracts."""
import ast
from copy import deepcopy
from pathlib import Path
import types
import unittest

import yaml

ROOT = Path(__file__).parent
COMPONENT = ROOT / "custom_components/aqara_m1s_zigbee_router"


class NotificationVolumeTests(unittest.TestCase):
    def test_main_gain_ignores_retired_trim_and_preserves_mute_zero_and_precision(self):
        tree = ast.parse((COMPONENT / "media_player.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "AqaraM1SRadioPlayer")
        fn = deepcopy(next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                           and node.name == "_effective_gain"))
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), "gain", "exec"), namespace)
        for muted, volume, expected in ((False, 0, 0), (False, 0.0001, 0.0001),
                                       (False, 0.01, 0.01), (True, 0.5, 0)):
            player = types.SimpleNamespace(_attr_is_volume_muted=muted,
                _attr_volume_level=volume, _fine_volume_trim_percent=1)
            self.assertEqual(namespace[fn.name](player), expected)
        self.assertNotIn("set_fine_volume_trim_percent", ast.unparse(tree))

    def test_no_fine_volume_entity_is_created(self):
        tree = ast.parse((COMPONENT / "number.py").read_text(encoding="utf-8"))
        self.assertEqual([node.name for node in tree.body if isinstance(node, ast.ClassDef)],
                         ["AqaraM1SSoundPlaybackVolume"])
        self.assertNotIn("Fine Volume Trim", ast.unparse(tree))

    def test_receiver_starts_confirm_canonical_gain_before_remote_play(self):
        for file, cls_name, method in (
            ("media_player.py", "AqaraM1SRadioPlayer", "_start_locked"),
            ("media_group.py", "AqaraM1SMediaGroupManager", "_prepare_member")):
            tree = ast.parse((COMPONENT / file).read_text(encoding="utf-8"))
            cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls_name)
            fn = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == method)
            source = ast.unparse(fn)
            self.assertLess(source.index("local_audio.async_prepare("), source.index("REMOTE_START", source.index("local_audio.async_prepare(")))

    def test_service_exposes_explicit_percent_not_a_global_volume_write(self):
        services = yaml.safe_load((COMPONENT / "services.yaml").read_text(encoding="utf-8"))
        selector = services["play_sound"]["fields"]["volume_percent"]["selector"]["number"]
        self.assertEqual((selector["min"], selector["max"], selector["step"]), (0, 100, 0.01))

    def test_doorbells_never_change_shared_volume_before_or_after_wav(self):
        for room, host in (("Living", "192.168.0.226"), ("Dormitor", "192.168.0.222")):
            text = (ROOT / "automations" / f"Sonerie_{room}_Cedare_Inainte_Volum_03716.yaml").read_text(encoding="utf-8")
            self.assertNotIn("number.set_value", text)
            data = yaml.safe_load(text)
            calls = []

            def walk(value):
                if isinstance(value, dict):
                    if value.get("action") == "aqara_m1s_zigbee_router.play_sound":
                        calls.append(value)
                    for item in value.values():
                        walk(item)
                elif isinstance(value, list):
                    for item in value:
                        walk(item)

            walk(data["actions"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["data"]["host"], host)
            self.assertIn("file_path", calls[0]["data"]["path"])
            self.assertIn("volume_percent", calls[0]["data"])
            self.assertEqual(data["mode"], "single")
            self.assertEqual(data["max_exceeded"], "silent")


if __name__ == "__main__":
    unittest.main()
