"""Priority, cancellation and resume tests for direct hub WAV playback."""
import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = pathlib.Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
PACKAGE = "m1s_sound_priority_test"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg
core = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
core.HomeAssistant = object
client = types.ModuleType(PACKAGE + ".client")
client.AqaraM1SClient = object
sys.modules[client.__name__] = client
spec = importlib.util.spec_from_file_location(PACKAGE + ".sound_player", ROOT / "sound_player.py")
sound = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sound
spec.loader.exec_module(sound)


class SoundPriorityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.token = "a" * 32
        self.hass = types.SimpleNamespace(async_create_task=asyncio.create_task)
        self.radio = types.SimpleNamespace(
            _effective_gain=Mock(return_value=0.0134),
            async_cleanup_priority_receiver=AsyncMock(),
            async_suspend_for_priority_sound=AsyncMock(side_effect=lambda: self.events.append("suspend") or True),
            async_resume_after_priority_sound=AsyncMock(side_effect=lambda resume: self.events.append(f"resume:{resume}")))
        self.group = types.SimpleNamespace(
            async_claim_sound=AsyncMock(side_effect=lambda entry: self.events.append("claim")),
            async_release_sound=AsyncMock(side_effect=lambda entry: self.events.append("release")))
        self.audio = types.SimpleNamespace(
            async_prepare=AsyncMock(side_effect=lambda gain: self.events.append("prepare")),
            async_start_sound=AsyncMock(side_effect=lambda path: self.events.append("start") or self.token),
            async_start_url=AsyncMock(side_effect=lambda url: self.events.append("start-url") or self.token),
            async_sound_status=AsyncMock(return_value=("done", 0)),
            async_stop_sound=AsyncMock(side_effect=lambda token: self.events.append("stop")),
            async_cleanup_sound=AsyncMock(side_effect=lambda token: self.events.append("cleanup")))
        self.player = sound.AqaraM1SSoundPlayer(self.hass,
            types.SimpleNamespace(host="test", zigbee_role="router"), "entry", self.radio, self.group, self.audio)
        self.delay = patch.object(sound, "SOUND_STATUS_INTERVAL", 0.001)
        self.delay.start()
        real_sleep = asyncio.sleep

        async def fast_sleep(seconds):
            await real_sleep(0.001 if seconds else 0)

        self.sleep = patch.object(sound.asyncio, "sleep", side_effect=fast_sleep)
        self.sleep.start()

    async def asyncTearDown(self):
        await self.player.async_stop()
        self.sleep.stop()
        self.delay.stop()

    async def test_local_wav_claims_suspends_and_resumes_without_ffmpeg(self):
        await self.player.async_play("/data/musics/music-ch/test.wav", 99)
        await self.player._watch_task
        self.assertEqual(self.events, ["claim", "suspend", "prepare", "start", "cleanup", "resume:True", "release"])
        self.audio.async_prepare.assert_awaited_once_with(0.0134)
        self.assertFalse(self.player._interruption_active)

    async def test_idle_hub_does_not_start_previously_stopped_radio(self):
        self.radio.async_suspend_for_priority_sound.side_effect = None
        self.radio.async_suspend_for_priority_sound.return_value = False
        await self.player.async_play("/data/musics/test.wav")
        await self.player._watch_task
        self.radio.async_resume_after_priority_sound.assert_awaited_once_with(False)

    async def test_start_error_releases_both_gates(self):
        self.audio.async_start_sound.side_effect = RuntimeError("rejected")
        with self.assertRaises(RuntimeError):
            await self.player.async_play("/data/musics/test.wav")
        self.radio.async_resume_after_priority_sound.assert_awaited_once_with(True)
        self.group.async_release_sound.assert_awaited_once_with("entry")

    async def test_suspension_error_still_releases_group_claim(self):
        self.radio.async_suspend_for_priority_sound.side_effect = RuntimeError("failed handover")
        with self.assertRaises(RuntimeError):
            await self.player.async_play("/data/musics/test.wav")
        self.group.async_release_sound.assert_awaited_once()

    async def test_invalid_path_is_rejected_before_interrupting_music(self):
        with self.assertRaises(ValueError):
            await self.player.async_play("/etc/other.wav")
        self.group.async_claim_sound.assert_not_awaited()

    async def test_wav_url_keeps_the_same_priority_and_shared_volume(self):
        await self.player.async_play_url("http://example.test/notice.wav")
        await self.player._watch_task
        self.audio.async_start_url.assert_awaited_once_with("http://example.test/notice.wav")
        self.audio.async_prepare.assert_awaited_once_with(0.0134)
        self.radio.async_resume_after_priority_sound.assert_awaited_once_with(True)

    async def test_invalid_url_cannot_preempt_audio(self):
        with self.assertRaises(ValueError):
            await self.player.async_play_url("file:///etc/other.wav")
        self.group.async_claim_sound.assert_not_awaited()

    async def test_coordinator_cannot_play_or_provision_audio(self):
        self.player.client.zigbee_role = "coordinator"
        with self.assertRaises(RuntimeError):
            await self.player.async_play("/data/musics/test.wav")
        self.audio.async_prepare.assert_not_awaited()

    async def test_replacing_wav_keeps_focus_until_the_new_sound_finishes(self):
        self.audio.async_sound_status.return_value = ("running", None)
        await self.player.async_play("/data/musics/first.wav")
        old = self.token
        self.token = "b" * 32
        await self.player.async_play("/data/musics/second.wav")
        self.audio.async_stop_sound.assert_awaited_once_with(old)
        self.group.async_claim_sound.assert_awaited_once()
        self.radio.async_resume_after_priority_sound.assert_not_awaited()
        self.audio.async_sound_status.return_value = ("done", 0)
        await self.player._watch_task
        self.radio.async_resume_after_priority_sound.assert_awaited_once_with(True)

    async def test_manual_stop_kills_only_its_job_then_restores_priority(self):
        self.audio.async_sound_status.return_value = ("running", None)
        await self.player.async_play("/data/musics/test.wav")
        await self.player.async_stop()
        self.audio.async_stop_sound.assert_awaited_once_with(self.token)
        self.radio.async_resume_after_priority_sound.assert_awaited_once_with(True)

    async def test_missing_or_failed_job_does_not_hold_audio_forever(self):
        self.audio.async_sound_status.return_value = ("missing", None)
        await self.player.async_play("/data/musics/test.wav")
        await self.player._watch_task
        self.group.async_release_sound.assert_awaited_once()

    async def test_repeated_status_failures_stop_job_and_release_priority(self):
        self.audio.async_sound_status.side_effect = OSError("offline")
        await self.player.async_play("/data/musics/test.wav")
        await self.player._watch_task
        self.audio.async_stop_sound.assert_awaited_once_with(self.token)
        self.group.async_release_sound.assert_awaited_once()

    async def test_url_timeout_with_failed_stop_still_releases_priority(self):
        self.audio.async_sound_status.return_value = ("downloading", None)
        self.audio.async_stop_sound.side_effect = OSError("offline")
        with patch.object(sound, "SOUND_DOWNLOAD_TIMEOUT", 0):
            await self.player.async_play_url("http://example.test/notice.wav")
            await self.player._watch_task
        self.assertFalse(self.player._interruption_active)
        self.group.async_release_sound.assert_awaited_once()

    async def test_resume_failure_still_releases_group_claim(self):
        self.radio.async_resume_after_priority_sound.side_effect = OSError("offline")
        await self.player.async_play("/data/musics/test.wav")
        await self.player._watch_task
        self.assertFalse(self.player._interruption_active)
        self.group.async_release_sound.assert_awaited_once()

    async def test_cancellation_during_remote_start_settles_and_stops_owned_job(self):
        entered, finish = asyncio.Event(), asyncio.Event()

        async def delayed_start(path):
            entered.set()
            await finish.wait()
            return self.token

        self.audio.async_start_sound.side_effect = delayed_start
        task = asyncio.create_task(self.player.async_play("/data/musics/test.wav"))
        await entered.wait()
        task.cancel()
        finish.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.audio.async_stop_sound.assert_awaited_once_with(self.token)
        self.group.async_release_sound.assert_awaited_once()

    async def test_idle_hub_skips_settle_but_still_applies_gain_and_priority(self):
        self.radio._priority_sound_had_transport = False
        self.radio.async_suspend_for_priority_sound.side_effect = None
        self.radio.async_suspend_for_priority_sound.return_value = False
        await self.player.async_play("/data/musics/test.wav")
        self.assertFalse(any(call.args == (0.25,) for call in sound.asyncio.sleep.call_args_list))
        self.audio.async_prepare.assert_awaited_once_with(0.0134)
        self.assertEqual(self.events[:3], ["claim", "prepare", "start"])
        await self.player._watch_task
        self.radio.async_resume_after_priority_sound.assert_awaited_once_with(False)

    async def test_active_group_retains_settle_even_without_individual_radio(self):
        self.radio._priority_sound_had_transport = False
        self.group.async_claim_sound.side_effect = None
        self.group.async_claim_sound.return_value = True
        await self.player.async_play("/data/musics/test.wav")
        self.assertTrue(any(call.args == (0.25,) for call in sound.asyncio.sleep.call_args_list))
        await self.player._watch_task

    async def test_busy_rejection_cleans_residual_receiver_then_starts_once(self):
        self.audio.async_start_sound.side_effect = [sound.LocalAudioBusy("busy"), self.token]
        await self.player.async_play("/data/musics/test.wav")
        await self.player._watch_task
        self.radio.async_cleanup_priority_receiver.assert_awaited_once()
        self.assertEqual(self.audio.async_start_sound.await_count, 2)
        self.audio.async_prepare.assert_awaited_once_with(0.0134)
        self.group.async_claim_sound.assert_awaited_once()

    async def test_second_busy_rejection_is_not_retried_again(self):
        self.audio.async_start_sound.side_effect = sound.LocalAudioBusy("busy")
        with self.assertRaises(sound.LocalAudioBusy):
            await self.player.async_play("/data/musics/test.wav")
        self.assertEqual(self.audio.async_start_sound.await_count, 2)
        self.group.async_release_sound.assert_awaited_once()

    async def test_ambiguous_start_failure_never_replays_audio(self):
        self.audio.async_start_sound.side_effect = TimeoutError("lost ack")
        with self.assertRaises(TimeoutError):
            await self.player.async_play("/data/musics/test.wav")
        self.audio.async_start_sound.assert_awaited_once()
        self.radio.async_cleanup_priority_receiver.assert_not_awaited()

    async def test_idle_hub_cannot_start_wav_when_volume_is_not_confirmed(self):
        self.radio._priority_sound_had_transport = False
        self.audio.async_prepare.side_effect = RuntimeError("gain not confirmed")
        with self.assertRaises(RuntimeError):
            await self.player.async_play("/data/musics/test.wav")
        self.audio.async_start_sound.assert_not_awaited()
        self.group.async_release_sound.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
