"""Behavioral priority-WAV mute policy across sound player and local gain.

Both runtime controllers are real. Only HA scheduling, media transport, and the
hub's command acknowledgements are replaced; these tests never contact a hub.
"""
import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


ROOT = pathlib.Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
PACKAGE = "m1s_priority_mute_policy_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package
core = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
core.HomeAssistant = object
client = types.ModuleType(PACKAGE + ".client")
client.AqaraM1SClient = object
sys.modules[client.__name__] = client
spec = importlib.util.spec_from_file_location(PACKAGE + ".sound_player", ROOT / "sound_player.py")
sound = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sound
spec.loader.exec_module(sound)
local_audio = sys.modules[PACKAGE + ".local_audio"]


class PriorityMutePolicyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.jobs = {}
        self.start_error = None
        self.start_entered = None
        self.allow_start = None

        async def executor(fn, *args):
            return fn(*args)

        self.hass = types.SimpleNamespace(
            async_add_executor_job=executor, async_create_task=asyncio.create_task)
        self.client = types.SimpleNamespace(host="192.168.0.226", zigbee_role="router")
        self.audio = local_audio.AqaraM1SLocalAudio(self.hass, self.client)
        self.audio._provision = Mock()
        self.audio._run = Mock(return_value="M1S_AUDIO_IDLE\n")
        self.audio._ensure_gain = Mock(side_effect=self.ensure_gain)

        self.radio = types.SimpleNamespace(
            _attr_volume_level=0.27,
            _attr_is_volume_muted=True,
            _priority_sound_had_transport=False)
        self.radio._effective_gain = lambda: (
            0.0 if self.radio._attr_is_volume_muted else self.radio._attr_volume_level)

        async def suspend():
            self.events.append("suspend")
            return True

        async def resume(should_resume):
            self.assertIsNone(self.audio._sound_gain,
                              "temporary WAV gain must be removed before media resumes")
            self.assertEqual(self.audio.applied_level,
                             local_audio.gain_to_level(self.radio._effective_gain()),
                             "current media mute/volume must already be acknowledged")
            self.events.append(("resume", should_resume))

        async def claim(entry):
            self.events.append("claim")
            return False

        async def release(entry):
            self.assertIsNone(self.audio._sound_gain)
            self.events.append("release")

        self.radio.async_suspend_for_priority_sound = suspend
        self.radio.async_resume_after_priority_sound = resume
        self.radio.async_cleanup_priority_receiver = self.noop
        self.group = types.SimpleNamespace(
            muted=True, member_muted=True,
            async_claim_sound=claim, async_release_sound=release)
        self.audio.async_start_sound = self.start
        self.audio.async_start_url = self.start
        self.audio.async_sound_status = self.status
        self.audio.async_stop_sound = self.stop
        self.audio.async_cleanup_sound = self.cleanup
        self.player = sound.AqaraM1SSoundPlayer(
            self.hass, self.client, "living", self.radio, self.group, self.audio)
        self.interval = patch.object(sound, "SOUND_STATUS_INTERVAL", 0.001)
        self.interval.start()

    async def asyncTearDown(self):
        await asyncio.wait_for(self.player.async_stop(), timeout=1)
        await asyncio.wait_for(self.audio.async_shutdown(), timeout=1)
        self.interval.stop()

    async def noop(self, *args):
        pass

    def ensure_gain(self, level):
        self.events.append(("gain", level))
        return level

    async def start(self, source):
        if self.start_error:
            raise self.start_error
        if self.start_entered is not None:
            self.start_entered.set()
            await asyncio.wait_for(self.allow_start.wait(), timeout=1)
        token = f"{len(self.jobs) + 1:032x}"
        self.jobs[token] = ("running", None)
        self.events.append(("start", token, source))
        return token

    async def status(self, token):
        return self.jobs[token]

    async def stop(self, token):
        self.events.append(("stop", token))
        self.jobs[token] = ("done", 0)

    async def cleanup(self, token):
        self.events.append(("cleanup", token))

    async def finish(self):
        self.jobs[self.player._token] = ("done", 0)
        await asyncio.wait_for(self.player._watch_task, timeout=1)

    def assert_mute_unchanged(self, expected=True):
        self.assertEqual(self.radio._attr_is_volume_muted, expected)
        self.assertTrue(self.group.muted)
        self.assertTrue(self.group.member_muted)

    async def test_default_alert_is_audible_without_mutating_any_media_mute(self):
        await self.player.async_play("/data/musics/music-ch/bell.wav", volume_percent=50)
        self.assertEqual(self.audio.applied_level, local_audio.gain_to_level(0.5))
        self.assert_mute_unchanged()
        self.assertLess(self.events.index("suspend"),
                        self.events.index(("gain", local_audio.gain_to_level(0.5))))
        await self.finish()
        self.assert_mute_unchanged()
        self.assertLess(self.events.index(("gain", 0)), self.events.index(("resume", True)))
        self.assertLess(self.events.index(("resume", True)), self.events.index("release"))

    async def test_respect_mute_optout_keeps_muted_notification_silent(self):
        await self.player.async_play("/data/musics/bell.wav", volume_percent=50,
                                    respect_mute=True)
        self.assertEqual(self.audio.applied_level, 0)
        self.assert_mute_unchanged()
        await self.finish()

    async def test_muted_implicit_volume_uses_raw_slider_not_zero_effective_gain(self):
        await self.player.async_play("/data/musics/bell.wav", 99)
        self.assertEqual(self.audio.applied_level, local_audio.gain_to_level(0.27))
        self.assertEqual(self.radio._attr_volume_level, 0.27)
        await self.finish()
        self.assertEqual(self.audio.applied_level, 0)

    async def test_legacy_volume_is_fallback_when_slider_has_no_value(self):
        self.radio._attr_volume_level = None
        await self.player.async_play("/data/musics/bell.wav", 23)
        self.assertEqual(self.audio.applied_level, local_audio.gain_to_level(0.23))
        await self.finish()

    async def test_current_media_controls_cannot_silence_bypass_wav(self):
        await self.player.async_play("/data/musics/bell.wav", volume_percent=50)
        for muted, volume in ((False, 0.11), (True, 0.04), (True, 0.8)):
            self.radio._attr_is_volume_muted = muted
            self.radio._attr_volume_level = volume
            self.audio.request_gain(self.radio._effective_gain(), sound_muted=muted)
            await self.audio._gain_task
            self.assertEqual(self.audio.applied_level, local_audio.gain_to_level(0.5))
        await self.finish()
        self.assert_mute_unchanged()

    async def test_user_unmute_during_wav_survives_restore_with_current_volume(self):
        await self.player.async_play("/data/musics/bell.wav", volume_percent=50)
        self.radio._attr_is_volume_muted = False
        self.radio._attr_volume_level = 0.13
        self.audio.request_gain(0.13, sound_muted=False)
        await self.audio._gain_task
        await self.finish()
        self.assertFalse(self.radio._attr_is_volume_muted)
        self.assertEqual(self.audio.applied_level, local_audio.gain_to_level(0.13))

    async def test_zero_notification_volume_stays_silent_even_with_mute_bypass(self):
        await self.player.async_play("/data/musics/bell.wav", volume_percent=0)
        self.assertEqual(self.audio.applied_level, 0)
        await self.finish()

    async def test_replacement_keeps_override_and_restores_only_latest_token(self):
        await self.player.async_play("/data/musics/first.wav", volume_percent=50)
        first = self.player._token
        await self.player.async_play("/data/musics/second.wav", volume_percent=20)
        second = self.player._token
        self.assertNotEqual(first, second)
        self.assertIn(("stop", first), self.events)
        self.assertNotIn(("resume", True), self.events)
        self.assertNotIn("release", self.events)
        self.assertNotIn(("gain", 0), self.events)
        self.assertEqual(self.audio.applied_level, local_audio.gain_to_level(0.2))
        await self.finish()
        self.assertEqual(self.events.count(("resume", True)), 1)
        self.assertEqual(self.events.count("release"), 1)
        self.assert_mute_unchanged()

    async def test_implicit_volume_replacement_does_not_restore_between_wavs(self):
        await self.player.async_play("/data/musics/first.wav")
        self.radio._attr_volume_level = 0.19
        await self.player.async_play("/data/musics/second.wav")
        self.assertNotIn(("gain", 0), self.events)
        self.assertNotIn(("resume", True), self.events)
        self.assertEqual(self.audio.applied_level, local_audio.gain_to_level(0.19))
        await self.finish()
        self.assert_mute_unchanged()

    async def test_manual_stop_restores_muted_gain_before_resume(self):
        await self.player.async_play("/data/musics/bell.wav", volume_percent=50)
        token = self.player._token
        await self.player.async_stop()
        self.assertLess(self.events.index(("stop", token)), self.events.index(("gain", 0)))
        self.assertLess(self.events.index(("gain", 0)), self.events.index(("resume", True)))
        self.assert_mute_unchanged()

    async def test_start_failure_clears_gain_overlay_before_restoring_owners(self):
        self.start_error = RuntimeError("hub rejected WAV")
        with self.assertRaisesRegex(RuntimeError, "rejected"):
            await self.player.async_play("/data/musics/bell.wav", volume_percent=50)
        self.assertIsNone(self.audio._sound_gain)
        self.assertEqual(self.audio.applied_level, 0)
        self.assertLess(self.events.index(("gain", 0)), self.events.index(("resume", True)))
        self.assert_mute_unchanged()

    async def test_prepare_gain_failure_restores_media_without_starting_wav(self):
        def fail_notification_gain(level):
            if level != 0:
                raise OSError("gain not acknowledged")
            return self.ensure_gain(level)

        self.audio._ensure_gain.side_effect = fail_notification_gain
        with self.assertRaisesRegex(OSError, "not acknowledged"):
            await self.player.async_play("/data/musics/bell.wav", volume_percent=50)
        self.assertEqual(self.jobs, {})
        self.assertIsNone(self.audio._sound_gain)
        self.assertEqual(self.audio.applied_level, 0)
        self.assert_mute_unchanged()

    async def test_cancelled_start_settles_owned_token_before_clearing_override(self):
        self.start_entered, self.allow_start = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(self.player.async_play(
            "/data/musics/bell.wav", volume_percent=50))
        await asyncio.wait_for(self.start_entered.wait(), timeout=1)
        task.cancel()
        self.allow_start.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        stopped = next(i for i, e in enumerate(self.events)
                       if isinstance(e, tuple) and e[0] == "stop")
        self.assertLess(stopped, self.events.index(("gain", 0)))
        self.assertIsNone(self.audio._sound_gain)
        self.assert_mute_unchanged()

    async def test_url_announcement_uses_the_same_default_bypass_and_volume(self):
        await self.player.async_play_url("https://example.test/bell.wav", volume_percent=40)
        self.assertEqual(self.audio.applied_level, local_audio.gain_to_level(0.4))
        self.assert_mute_unchanged()
        await self.finish()

    async def test_url_respect_mute_optout_is_forwarded(self):
        await self.player.async_play_url("https://example.test/bell.wav", volume_percent=40,
                                        respect_mute=True)
        self.assertEqual(self.audio.applied_level, 0)
        await self.finish()

    async def test_low_level_default_still_respects_mute_for_explicit_callers(self):
        await self.audio.async_prepare_sound(0.5, muted=True)
        self.assertEqual(self.audio.applied_level, 0)
        await self.audio.async_restore_media(0)

    async def test_invalid_notification_options_never_interrupt_media(self):
        for method, source in (
                (self.player.async_play, "/data/musics/bell.wav"),
                (self.player.async_play_url, "https://example.test/bell.wav")):
            for percent in (True, -1, 101, float("nan"), float("inf"), "bad"):
                with self.subTest(method=method.__name__, percent=percent):
                    with self.assertRaises(ValueError):
                        await method(source, volume_percent=percent)
            for value in (None, 0, 1, "false", [], {}):
                with self.subTest(method=method.__name__, respect_mute=value):
                    with self.assertRaises((TypeError, ValueError)):
                        await method(source, respect_mute=value)
        self.assertEqual(self.events, [])
        self.audio._provision.assert_not_called()

    async def test_zero_media_slider_is_not_replaced_by_legacy_volume(self):
        self.radio._attr_volume_level = 0
        await self.player.async_play("/data/musics/bell.wav", 99)
        self.assertEqual(self.audio.applied_level, 0)
        await self.finish()


if __name__ == "__main__":
    unittest.main()
