"""Local WAV deletion safety tests; no HA instance or live hub required."""
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import Mock

ROOT = pathlib.Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
PACKAGE = "m1s_sound_delete_test"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg
device = types.ModuleType(PACKAGE + ".device")
device.normalize_mac = lambda value: value
sys.modules[device.__name__] = device


def load(name):
    spec = importlib.util.spec_from_file_location(PACKAGE + "." + name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


client_module = load("client")


class SoundDeleteTests(unittest.TestCase):
    def setUp(self):
        self.client = client_module.AqaraM1SClient("192.0.2.1")
        self.client.run_command = Mock(
            return_value="__M1S_SOUND_DELETE_OK__:/data/m1s_sound_backups/test.tgz"
        )

    def test_backup_precedes_delete_and_returns_archive(self):
        paths = [
            "/data/musics/music-ch/custom.wav",
            "/data/musics/original/door bell.wav",
        ]
        backup = self.client.delete_sounds(paths)
        self.assertEqual(backup, "/data/m1s_sound_backups/test.tgz")
        command = self.client.run_command.call_args.args[0]
        self.assertLess(command.index("tar -czf"), command.index("rm -f"))
        self.assertIn("data/musics/music-ch/custom.wav", command)
        self.assertIn("'/data/musics/original/door bell.wav'", command)
        self.assertEqual(
            self.client.run_command.call_args.kwargs["timeout"],
            client_module.UPLOAD_FINALIZE_TIMEOUT,
        )

    def test_missing_success_marker_is_failure(self):
        self.client.run_command.return_value = "tar: write error"
        with self.assertRaises(IOError):
            self.client.delete_sound("/data/musics/music-ch/custom.wav")

    def test_rejects_unsafe_paths_before_transport(self):
        unsafe = [
            "relative.wav",
            "/tmp/outside.wav",
            "/data/musics/../secret.wav",
            "/data/musics/file.mp3",
            "/data/musics",
        ]
        for path in unsafe:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.client.delete_sound(path)
        self.client.run_command.assert_not_called()

    def test_empty_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            self.client.delete_sounds([])
        self.client.run_command.assert_not_called()

    def test_list_sounds_filters_and_deduplicates(self):
        self.client.run_command.return_value = (
            "/data/musics/music-ch/a.wav\n"
            "/tmp/not-a-sound.wav\n"
            "/data/musics/music-ch/a.wav\n"
            "/data/musics/music-us/b.mp3\n"
            "/data/musics/original/b.wav\n"
        )
        self.assertEqual(
            self.client.list_sounds(),
            ["/data/musics/music-ch/a.wav", "/data/musics/original/b.wav"],
        )


if __name__ == "__main__":
    unittest.main()
