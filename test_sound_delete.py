"""Local WAV deletion safety tests; no HA instance or live hub required."""
import importlib.util
import base64
import pathlib
import re
import subprocess
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
        self._encoded_chunks = []
        self.client.run_command = Mock(side_effect=self._remote_result)

    def _remote_result(self, command, **_kwargs):
        if "stage_prefix='__M1S_DELETE_STAGE_'" in command:
            self._encoded_chunks = []
            return "__M1S_DELETE_STAGE_READY__"
        if "chunk_prefix='__M1S_DELETE_CHUNK_'" in command:
            match = re.search(r"printf '%s' '([^']+)' >>", command)
            if match:
                self._encoded_chunks.append(match.group(1))
            return "__M1S_DELETE_CHUNK_OK__"
        if "delete_prefix='__M1S_SOUND_DELETE_'" in command:
            manifest = base64.b64decode("".join(self._encoded_chunks)).decode()
            count = len([line for line in manifest.splitlines() if line])
            return f"__M1S_SOUND_DELETE_OK__:{count}"
        return ""

    def test_direct_delete_uses_validated_manifest_without_backup(self):
        paths = [
            "/data/musics/music-ch/custom.wav",
            "/data/musics/original/door bell.wav",
        ]
        deleted = self.client.delete_sounds(paths)
        self.assertEqual(deleted, 2)
        commands = [call.args[0] for call in self.client.run_command.call_args_list]
        command = next(value for value in commands if "delete_prefix=" in value)
        self.assertNotIn("tar -czf", command)
        self.assertNotIn("m1s_sound_backups", command)
        self.assertIn("data/musics/music-us/*", command)
        self.assertLess(command.index("validate_failed=0"), command.index("deleted=0"))
        syntax = subprocess.run(
            ["sh", "-n"],
            input=command,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
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
            if "delete_prefix=" in call.args[0]
        )
        self.assertEqual(
            final_call.kwargs["timeout"],
            client_module.SOUND_DELETE_FINALIZE_TIMEOUT,
        )

    def test_missing_success_marker_is_failure(self):
        def failed_remote(command, **kwargs):
            if "delete_prefix='__M1S_SOUND_DELETE_'" in command:
                return "__M1S_SOUND_DELETE_ERROR__:0"
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
        final_command = next(command for command in commands if "delete_prefix=" in command)
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
            "/data/musics/music-us/system.wav",
            "/data/musics/music-us/nested/system.WAV",
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
            "/data/musics/music-us/system.wav\n"
            "/data/musics/music-us/nested/system.wav\n"
            "/data/musics/original/b.wav\n"
        )
        self.assertEqual(
            self.client.list_sounds(),
            ["/data/musics/music-ch/a.wav", "/data/musics/original/b.wav"],
        )

    def test_system_sound_directory_is_not_managed_upload_space(self):
        self.assertFalse(
            self.client.is_managed_sound_path("/data/musics/music-us/system.wav")
        )
        self.assertTrue(
            self.client.is_managed_sound_path("/data/musics/music-ch/custom.wav")
        )

    def test_success_count_must_match_selection(self):
        def wrong_count(command, **kwargs):
            if "delete_prefix='__M1S_SOUND_DELETE_'" in command:
                return "__M1S_SOUND_DELETE_OK__:1"
            return self._remote_result(command, **kwargs)

        self.client.run_command.side_effect = wrong_count
        with self.assertRaises(IOError):
            self.client.delete_sounds(
                [
                    "/data/musics/music-ch/one.wav",
                    "/data/musics/music-ch/two.wav",
                ]
            )


if __name__ == "__main__":
    unittest.main()
