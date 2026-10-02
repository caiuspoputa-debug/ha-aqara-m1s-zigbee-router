"""Local sound-storage reserve tests; no HA instance or live hub required."""
import base64
import importlib.util
import io
import pathlib
import re
import subprocess
import sys
import types
import unittest
import wave
from unittest.mock import Mock


ROOT = pathlib.Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
PACKAGE = "m1s_sound_storage_test"
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


def valid_wav(frame_count: int = 320) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(4)
        wav.setframerate(32000)
        wav.writeframes(b"\0" * frame_count * 4)
    return output.getvalue()


class SoundStorageTests(unittest.TestCase):
    def setUp(self):
        self.client = client_module.AqaraM1SClient("192.0.2.1")
        self._chunks: list[str] = []
        self.capacity_status = "OK"
        self.available = 20 * 1024 * 1024
        self.growth = 3 * 1024 * 1024
        self.projected = self.available - self.growth
        self.client.run_command = Mock(side_effect=self._remote_result)

    def _remote_result(self, command, **_kwargs):
        if "capacity_stage_prefix=" in command:
            self._chunks = []
            return "__M1S_SOUND_CAPACITY_STAGE_READY__"
        if "capacity_chunk_prefix=" in command:
            match = re.search(r"printf '%s' '([^']+)' >>", command)
            if match:
                self._chunks.append(match.group(1))
            return "__M1S_SOUND_CAPACITY_CHUNK_OK__"
        if "capacity_prefix=" in command:
            return (
                f"__M1S_SOUND_CAPACITY_{self.capacity_status}__|"
                f"{self.available}|{self.growth}|{self.projected}|"
                f"{client_module.SOUND_STORAGE_MIN_FREE_BYTES}"
            )
        return ""

    def test_batch_capacity_manifest_accounts_for_replacements(self):
        uploads = [
            ("/data/musics/music-ch/one.wav", 1_234),
            ("/data/musics/music-ch/two with space.wav", 5_678),
        ]
        result = self.client.validate_sound_upload_capacity(uploads)
        self.assertEqual(result["projected_bytes"], self.projected)

        commands = [call.args[0] for call in self.client.run_command.call_args_list]
        final_command = next(command for command in commands if "capacity_prefix=" in command)
        self.assertIn("growth=$((growth + size - existing))", final_command)
        self.assertIn(str(client_module.SOUND_STORAGE_MIN_FREE_BYTES), final_command)
        self.assertNotIn("one.wav", final_command)
        syntax = subprocess.run(
            ["sh", "-n"],
            input=final_command,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

        manifest = base64.b64decode("".join(self._chunks)).decode()
        self.assertEqual(
            manifest,
            "1234\t/data/musics/music-ch/one.wav\n"
            "5678\t/data/musics/music-ch/two with space.wav\n",
        )

    def test_batch_is_refused_when_projected_free_is_below_reserve(self):
        self.capacity_status = "LOW"
        self.available = 9 * 1024 * 1024
        self.growth = 2 * 1024 * 1024
        self.projected = self.available - self.growth
        with self.assertRaises(client_module.SoundStorageError) as raised:
            self.client.validate_sound_upload_capacity(
                [("/data/musics/music-ch/new.wav", self.growth)]
            )
        self.assertEqual(raised.exception.projected_bytes, self.projected)
        self.assertEqual(
            raised.exception.reserve_bytes,
            client_module.SOUND_STORAGE_MIN_FREE_BYTES,
        )

    def test_upload_batch_preflights_once_before_first_file(self):
        wav_one = valid_wav(320)
        wav_two = valid_wav(640)
        self.client._sound_upload_capacity_locked = Mock(return_value={})
        self.client._upload_sound_tcp_locked = Mock()
        self.client._upload_sound_base64_locked = Mock()
        progress = Mock()

        self.client.upload_sounds(
            [
                ("/data/musics/music-ch/one.wav", wav_one),
                ("/data/musics/music-ch/two.wav", wav_two),
            ],
            progress,
        )

        self.client._sound_upload_capacity_locked.assert_called_once_with(
            [
                ("/data/musics/music-ch/one.wav", len(wav_one)),
                ("/data/musics/music-ch/two.wav", len(wav_two)),
            ]
        )
        self.assertEqual(self.client._upload_sound_tcp_locked.call_count, 2)
        self.client._upload_sound_base64_locked.assert_not_called()
        self.assertEqual(progress.call_count, 2)

    def test_failed_preflight_writes_no_file(self):
        self.client._sound_upload_capacity_locked = Mock(
            side_effect=client_module.SoundStorageError("low space")
        )
        self.client._upload_sound_tcp_locked = Mock()
        self.client._upload_sound_base64_locked = Mock()

        with self.assertRaises(client_module.SoundStorageError):
            self.client.upload_sounds(
                [("/data/musics/music-ch/one.wav", valid_wav())]
            )

        self.client._upload_sound_tcp_locked.assert_not_called()
        self.client._upload_sound_base64_locked.assert_not_called()

    def test_base64_fallback_uses_fast_chunks_and_reports_progress(self):
        content = valid_wav(4096)
        self.client.run_command = Mock(side_effect=["", "__M1S_UPLOAD_OK__"])
        self.client._run_upload_chunk_locked = Mock(return_value="")
        progress = Mock()

        self.client._upload_sound_base64_locked(
            "/data/musics/music-ch/fallback.wav",
            content,
            progress,
        )

        encoded_size = len(base64.b64encode(content))
        expected_chunks = (
            encoded_size + client_module.UPLOAD_BASE64_CHUNK_SIZE - 1
        ) // client_module.UPLOAD_BASE64_CHUNK_SIZE
        self.assertEqual(
            self.client._run_upload_chunk_locked.call_count,
            expected_chunks,
        )
        self.assertEqual(progress.call_args_list[-1].args, (len(content),))
        self.assertGreater(progress.call_count, 1)

    def test_capacity_rejects_system_folder_and_empty_batch(self):
        with self.assertRaises(ValueError):
            self.client.validate_sound_upload_capacity([])
        with self.assertRaises(ValueError):
            self.client.validate_sound_upload_capacity(
                [("/data/musics/music-us/system.wav", 100)]
            )
        self.client.run_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
