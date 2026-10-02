"""Local sound-storage reserve tests; no HA instance or live hub required."""
import importlib.util
import io
import pathlib
import socket
import subprocess
import sys
import threading
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
        self.capacity_status = "OK"
        self.available = 20 * 1024 * 1024
        self.growth = 3 * 1024 * 1024
        self.projected = self.available - self.growth
        self.client.run_command = Mock(side_effect=self._remote_result)

    def _remote_result(self, command, **_kwargs):
        if "capacity_prefix=" in command:
            return (
                f"__M1S_SOUND_CAPACITY_{self.capacity_status}__|"
                f"{self.available}|{self.growth}|{self.projected}|"
                f"{client_module.SOUND_STORAGE_MIN_FREE_BYTES}"
            )
        return ""

    def test_single_capacity_check_accounts_for_replacement(self):
        uploads = [("/data/musics/music-ch/two with space.wav", 5_678)]
        result = self.client.validate_sound_upload_capacity(uploads)
        self.assertEqual(result["projected_bytes"], self.projected)

        commands = [call.args[0] for call in self.client.run_command.call_args_list]
        final_command = next(command for command in commands if "capacity_prefix=" in command)
        self.assertIn("growth=$((requested - existing))", final_command)
        self.assertIn("two with space.wav", final_command)
        self.assertIn(str(client_module.SOUND_STORAGE_MIN_FREE_BYTES), final_command)
        syntax = subprocess.run(
            ["sh", "-n"],
            input=final_command,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

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

    def test_upload_preflights_once_before_file(self):
        wav_one = valid_wav(320)
        self.client._sound_upload_capacity_locked = Mock(return_value={})
        self.client._upload_sound_tcp_locked = Mock()
        self.client._upload_sound_base64_locked = Mock()
        progress = Mock()

        self.client.upload_sounds(
            [("/data/musics/music-ch/one.wav", wav_one)],
            progress,
        )

        self.client._sound_upload_capacity_locked.assert_called_once_with(
            [("/data/musics/music-ch/one.wav", len(wav_one))]
        )
        self.client._upload_sound_tcp_locked.assert_called_once()
        self.client._upload_sound_base64_locked.assert_not_called()
        progress.assert_called_once_with(len(wav_one), len(wav_one))

    def test_multiple_uploads_are_rejected_before_remote_write(self):
        with self.assertRaisesRegex(ValueError, "one WAV"):
            self.client.validate_sound_upload_capacity(
                [
                    ("/data/musics/music-ch/one.wav", 100),
                    ("/data/musics/music-ch/two.wav", 200),
                ]
            )
        self.client.run_command.assert_not_called()

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

    def test_tcp_upload_transfers_real_socket_chunks_and_reports_progress(self):
        content = valid_wav(100_000)
        received = bytearray()
        ready = threading.Event()
        finished = threading.Event()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def receive_payload():
            ready.set()
            connection, _address = listener.accept()
            with connection:
                while chunk := connection.recv(8192):
                    received.extend(chunk)
            listener.close()
            finished.set()

        thread = threading.Thread(target=receive_payload, daemon=True)
        thread.start()
        ready.wait(1)

        original_port = client_module.UPLOAD_PORT
        client_module.UPLOAD_PORT = port
        self.client.host = "127.0.0.1"
        self.client.run_command = Mock(
            side_effect=["__M1S_UPLOAD_LISTEN__", "__M1S_UPLOAD_OK__"]
        )
        progress = Mock()
        try:
            self.client._upload_sound_tcp_locked(
                "/data/musics/music-ch/socket-test.wav",
                content,
                progress,
            )
        finally:
            client_module.UPLOAD_PORT = original_port

        self.assertTrue(finished.wait(2), "socket receiver did not finish")
        thread.join(2)
        self.assertEqual(bytes(received), content)
        self.assertGreater(progress.call_count, 2)
        self.assertEqual(progress.call_args_list[-1].args, (len(content),))

    def test_fallback_progress_never_moves_backwards(self):
        content = valid_wav(20_000)
        self.client._sound_upload_capacity_locked = Mock(return_value={})

        def fail_tcp(_destination, payload, report):
            report(len(payload) // 2)
            raise ConnectionError("probe failure")

        def complete_fallback(_destination, payload, report):
            report(len(payload) // 4)
            report(len(payload))

        self.client._upload_sound_tcp_locked = Mock(side_effect=fail_tcp)
        self.client._upload_sound_base64_locked = Mock(
            side_effect=complete_fallback
        )
        reported: list[int] = []

        self.client.upload_sounds(
            [("/data/musics/music-ch/fallback.wav", content)],
            lambda current, _total: reported.append(current),
        )

        self.assertEqual(reported[-1], len(content))
        self.assertEqual(reported, sorted(reported))

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
