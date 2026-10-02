"""Local WAV deletion safety tests; no HA instance or live hub required."""
import importlib.util
import base64
import pathlib
import re
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
        self.client.run_command = Mock(side_effect=self._remote_result)

    @staticmethod
    def _remote_result(command, **_kwargs):
        if "stage_prefix='__M1S_DELETE_STAGE_'" in command:
            return "__M1S_DELETE_STAGE_READY__"
        if "chunk_prefix='__M1S_DELETE_CHUNK_'" in command:
            return "__M1S_DELETE_CHUNK_OK__"
        if "tar -czf" in command:
            return (
                "__M1S_SOUND_DELETE_OK__:"
                "/data/m1s_sound_backups/sounds_before_delete_20261002_1.tgz"
            )
        return ""

    def test_backup_precedes_delete_and_returns_archive(self):
        paths = [
            "/data/musics/music-ch/custom.wav",
            "/data/musics/original/door bell.wav",
        ]
        backup = self.client.delete_sounds(paths)
        self.assertEqual(
            backup,
            "/data/m1s_sound_backups/sounds_before_delete_20261002_1.tgz",
        )
        commands = [call.args[0] for call in self.client.run_command.call_args_list]
        command = next(value for value in commands if "tar -czf" in value)
        self.assertLess(command.index("tar -czf"), command.index("while IFS= read"))
        self.assertIn('-T "$LIST"', command)
        self.assertNotIn(paths[0], command)
        self.assertNotIn(paths[1], command)
        encoded_chunks = [
            re.search(r"printf '%s' '([^']+)' >>", value).group(1)
            for value in commands
            if "printf '%s'" in value
        ]
        manifest = base64.b64decode("".join(encoded_chunks)).decode()
        self.assertEqual(
            manifest,
            "data/musics/music-ch/custom.wav\n"
            "data/musics/original/door bell.wav\n",
        )
        final_call = next(
            call
            for call in self.client.run_command.call_args_list
            if "tar -czf" in call.args[0]
        )
        self.assertEqual(
            final_call.kwargs["timeout"],
            client_module.UPLOAD_FINALIZE_TIMEOUT,
        )

    def test_missing_success_marker_is_failure(self):
        def failed_remote(command, **kwargs):
            if "tar -czf" in command:
                return "__M1S_SOUND_BACKUP_ERROR__"
            return self._remote_result(command, **kwargs)

        self.client.run_command.side_effect = failed_remote
        with self.assertRaises(IOError):
            self.client.delete_sound("/data/musics/music-ch/custom.wav")

    def test_many_files_use_bounded_chunk_commands(self):
        paths = [f"/data/musics/music-ch/file {index:02d}.wav" for index in range(64)]
        self.client.delete_sounds(paths)
        commands = [call.args[0] for call in self.client.run_command.call_args_list]
        self.assertGreater(sum("printf '%s'" in command for command in commands), 1)
        self.assertLess(max(map(len, commands)), 2048)
        final_command = next(command for command in commands if "tar -czf" in command)
        self.assertNotIn(paths[-1], final_command)

    def test_rejects_newline_in_path(self):
        with self.assertRaises(ValueError):
            self.client.delete_sound("/data/musics/music-ch/bad\nname.wav")
        self.client.run_command.assert_not_called()

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
        self.client.run_command.side_effect = None
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
