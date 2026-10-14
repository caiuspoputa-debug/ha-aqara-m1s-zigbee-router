"""Local gain protocol, safe deployment and unchanged transport contracts."""
import ast
import asyncio
import importlib.util
import hashlib
import pathlib
import struct
import subprocess
import types
import unittest
from unittest.mock import AsyncMock, Mock

from shell_test_support import shell_command, shell_path

ROOT = pathlib.Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
spec = importlib.util.spec_from_file_location("m1s_local_audio_unit", ROOT / "local_audio.py")
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)


class GainProtocolTests(unittest.TestCase):
    def test_gain_limits_and_smallest_positive_ui_step(self):
        self.assertEqual(audio.gain_to_level(0), 0)
        self.assertEqual(audio.gain_to_level(-1), 0)
        self.assertEqual(audio.gain_to_level(1), 1023)
        self.assertEqual(audio.gain_to_level(2), 1023)
        self.assertEqual(audio.gain_to_level(0.0001), 1)

    def test_audibly_confirmed_levels_and_fine_log_resolution(self):
        self.assertEqual(audio.gain_to_level(0.01), 512)
        self.assertEqual(audio.gain_to_level(0.02), 588)
        for gain in (0.0001, 0.0007, 0.01, 0.02, 0.5):
            actual = audio.level_to_gain(audio.gain_to_level(gain))
            self.assertLess(abs(actual - gain) / gain, 0.012)

    def test_nonfinite_values_never_become_full_volume(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                audio.gain_to_level(value)

    def test_only_hub_wavs_are_accepted(self):
        self.assertEqual(audio.safe_sound_path("/data/musics/music-ch/a b.wav"),
                         "/data/musics/music-ch/a b.wav")
        for path in ("/etc/passwd", "/data/musics/../other.wav", "file://a.wav", "a.wav",
                     "/data/musics/music-ch/a.mp3", "/data/musics/a\x00.wav"):
            with self.assertRaises(ValueError):
                audio.safe_sound_path(path)

    def test_echoed_shell_text_is_not_an_acknowledgement(self):
        self.assertIsNone(audio._gain_reply("# printf 'M1S_GAIN=588\\n'\n"))
        self.assertEqual(audio._gain_reply("# command\r\nM1S_GAIN=588\r\n#"), 588)

    def test_url_is_explicit_http_media_not_a_local_path_or_shell_command(self):
        self.assertEqual(audio.safe_sound_url("http://example.test/a.wav?x=1"),
                         "http://example.test/a.wav?x=1")
        for url in ("file:///etc/passwd", "-O file.wav", "http://\na.test/x", "relative.wav"):
            with self.assertRaises(ValueError):
                audio.safe_sound_url(url)

    def test_helper_is_static_little_endian_mips(self):
        data = (ROOT / "hub_audio/volume_ctl").read_bytes()
        self.assertEqual(data[:7], b"\x7fELF\x01\x01\x01")
        self.assertEqual(struct.unpack_from("<H", data, 18)[0], 8)
        offset = struct.unpack_from("<I", data, 28)[0]
        size, count = struct.unpack_from("<HH", data, 42)
        types_present = [struct.unpack_from("<I", data, offset + i * size)[0] for i in range(count)]
        self.assertNotIn(3, types_present)  # PT_INTERP: no hub libc/toolchain dependency.

    def test_pcm_gain_methods_are_identity_functions(self):
        for file, class_name in (("media_player.py", "AqaraM1SRadioPlayer"),
                                 ("media_group.py", "AqaraM1SMediaGroupManager")):
            tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
            fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_apply_live_pcm_gain")
            fn.decorator_list = []
            namespace = {}
            exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), file, "exec"), namespace)
            pcm = bytes(range(256)) * 17
            self.assertIs(namespace[fn.name](object(), pcm), pcm)

    def test_wav_number_is_the_media_volume_alias_not_a_restored_fifty_percent(self):
        tree = ast.parse((ROOT / "number.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AqaraM1SSoundPlaybackVolume")
        added = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_added_to_hass")
        self.assertNotIn("async_get_last_state", ast.unparse(added))
        fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "native_value")
        fn.decorator_list = []
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), "number.py", "exec"), namespace)
        entity = types.SimpleNamespace(radio_player=types.SimpleNamespace(_attr_volume_level=0.0007))
        self.assertEqual(namespace[fn.name](entity), 0.07)

    def test_sound_script_cannot_kill_native_services_or_unrelated_players(self):
        source = (ROOT / "hub_audio/sound.sh").read_text(encoding="ascii")
        self.assertNotIn("killall", source)
        self.assertNotIn("mha_basis", source)
        self.assertIn("$start", source)
        self.assertIn("$token", source)
        self.assertIn("aplay -D m1s_media", source)
        self.assertNotIn("nc -l", source)
        self.assertIn('aplay -D m1s_media -x 1 "$source"', source)
        self.assertLess(source.index("M1S_AUDIO_BUSY"), source.index("printf 'PENDING"))

    def test_sound_script_has_valid_posix_shell_syntax(self):
        result = subprocess.run(shell_command("-n", shell_path(ROOT / "hub_audio/sound.sh")),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class LocalControllerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls = []

        async def executor(fn, *args):
            return fn(*args)

        self.hass = types.SimpleNamespace(async_add_executor_job=executor,
                                          async_create_task=asyncio.create_task)
        self.controller = audio.AqaraM1SLocalAudio(self.hass,
            types.SimpleNamespace(host="test", zigbee_role="router"))
        self.controller._provision = Mock()
        self.controller._ensure_gain = Mock(side_effect=lambda level: self.calls.append(level) or level)

    async def asyncTearDown(self):
        await self.controller.async_shutdown()

    async def test_prepare_sets_volume_before_playback_and_provisions_once(self):
        await self.controller.async_prepare(0.02)
        await self.controller.async_prepare(0.01)
        self.controller._provision.assert_called_once()
        self.assertEqual(self.calls, [588, 512])

    async def test_rapid_slider_updates_coalesce_to_latest(self):
        await self.controller.async_prepare(0.02)
        self.calls.clear()
        for gain in (0.3, 0.4, 0.5, 0.01):
            self.controller.request_gain(gain)
        await self.controller._gain_task
        self.assertEqual(self.calls, [512])

    async def test_mute_preserves_prepared_runtime_and_does_not_restart(self):
        await self.controller.async_prepare(0.02)
        self.controller.request_gain(0)
        await self.controller._gain_task
        self.assertEqual(self.calls[-1], 0)
        self.controller._provision.assert_called_once()

    async def test_failed_volume_is_not_treated_as_applied(self):
        self.controller._ensure_gain.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            await self.controller.async_prepare(0.02)
        self.assertFalse(self.controller._ready)
        self.assertIsNone(self.controller.applied_level)

    async def test_failed_asset_install_is_reported_and_retried(self):
        self.controller._provision.side_effect = OSError("not enough hub space")
        with self.assertRaises(OSError):
            await self.controller.async_prepare(0.02)
        self.assertFalse(self.controller._ready)
        self.assertEqual(self.controller.last_error, "not enough hub space")
        self.controller._ensure_gain.assert_not_called()
        self.controller._provision.side_effect = None
        await self.controller.async_prepare(0.02)
        self.assertEqual(self.controller._provision.call_count, 2)
        self.assertIsNone(self.controller.last_error)

    async def test_nonfinite_prepare_is_rejected_before_install(self):
        with self.assertRaises(ValueError):
            await self.controller.async_prepare(float("nan"))
        self.controller._provision.assert_not_called()

    async def test_coordinator_never_receives_audio_assets(self):
        self.controller.client.zigbee_role = "coordinator"
        self.controller._provision = audio.AqaraM1SLocalAudio._provision.__get__(self.controller)
        with self.assertRaises(RuntimeError):
            await self.controller.async_prepare(0.02)

    def test_low_space_prevents_any_asset_upload(self):
        isolated = types.SimpleNamespace(disconnect=Mock())
        self.controller._isolated = Mock(return_value=isolated)
        self.controller._command = Mock(side_effect=lambda client, command:
            "M1S_FREE_KB=1024\n" if "df -k" in command else "")
        with self.assertRaisesRegex(RuntimeError, "8 MiB"):
            audio.AqaraM1SLocalAudio._provision(self.controller)
        commands = [call.args[1] for call in self.controller._command.call_args_list]
        self.assertFalse(any("printf '%s'" in command for command in commands))
        isolated.disconnect.assert_called_once()

    def test_matching_assets_are_not_rewritten(self):
        isolated = types.SimpleNamespace(disconnect=Mock())
        self.controller._isolated = Mock(return_value=isolated)

        def command(client, value):
            for name in audio.ASSETS:
                if value.startswith(f"sha256sum {audio.REMOTE_ROOT}/{name} "):
                    return hashlib.sha256((audio.ASSET_ROOT / name).read_bytes()).hexdigest()
            return ""

        self.controller._command = Mock(side_effect=command)
        audio.AqaraM1SLocalAudio._provision(self.controller)
        self.assertEqual(self.controller._command.call_count, 1 + len(audio.ASSETS))
        isolated.disconnect.assert_called_once()

    def test_corrupt_transfer_is_removed_without_installing_it(self):
        isolated = types.SimpleNamespace(disconnect=Mock())
        self.controller._isolated = Mock(return_value=isolated)
        self.controller._command = Mock(side_effect=lambda client, command:
            "M1S_FREE_KB=65536\n" if "df -k" in command else "")
        with self.assertRaisesRegex(RuntimeError, "transfer failed"):
            audio.AqaraM1SLocalAudio._provision(self.controller)
        commands = [call.args[1] for call in self.controller._command.call_args_list]
        self.assertTrue(commands[-1].startswith("rm -f " + audio.REMOTE_ROOT + "/volume_ctl."))
        self.assertFalse(any("&& mv " in command for command in commands))
        self.assertLessEqual(max(map(len, commands)), 1000)

    async def test_sound_status_validates_token_and_real_completed_record(self):
        self.controller._run = Mock(return_value="# command\r\nDONE:0\r\n#")
        self.assertEqual(await self.controller.async_sound_status("a" * 32), ("done", 0))
        with self.assertRaises(ValueError):
            await self.controller.async_stop_sound("; reboot")

    def test_audio_channel_is_reused_and_disconnect_does_not_close_uart(self):
        isolated = types.SimpleNamespace(disconnect=Mock(), close=Mock())
        self.controller._isolated = Mock(return_value=isolated)
        self.controller._command = Mock(return_value="reply")
        self.assertEqual(self.controller._run("get gain"), "reply")
        self.assertEqual(self.controller._run("start owned job"), "reply")
        self.controller._isolated.assert_called_once()
        isolated.disconnect.assert_not_called()
        self.controller._disconnect_control()
        isolated.disconnect.assert_called_once()
        isolated.close.assert_not_called()

    def test_failed_command_is_not_replayed_and_next_call_reconnects(self):
        first = types.SimpleNamespace(disconnect=Mock())
        second = types.SimpleNamespace(disconnect=Mock())
        self.controller._isolated = Mock(side_effect=[first, second])
        self.controller._command = Mock(side_effect=[TimeoutError("lost ack"), "reply"])
        with self.assertRaises(TimeoutError):
            self.controller._run("start once")
        self.assertEqual(self.controller._command.call_count, 1)
        first.disconnect.assert_called_once()
        self.assertEqual(self.controller._run("get status"), "reply")
        self.assertEqual(self.controller._isolated.call_count, 2)

    async def test_explicit_busy_reply_is_pre_start_not_an_ambiguous_ack(self):
        self.controller._run = Mock(return_value="M1S_AUDIO_BUSY\n")
        self.controller.async_stop_sound = AsyncMock()
        self.controller.async_cleanup_sound = AsyncMock()
        with self.assertRaises(audio.LocalAudioBusy):
            await self.controller.async_start_sound("/data/musics/test.wav")
        self.controller._run.assert_called_once()
        self.controller.async_stop_sound.assert_not_awaited()
        self.controller.async_cleanup_sound.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
