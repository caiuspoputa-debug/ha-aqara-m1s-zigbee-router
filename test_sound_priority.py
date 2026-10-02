"""Stored-WAV priority tests for the Coordinator MQTT transport."""
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

homeassistant = types.ModuleType("homeassistant")
core = types.ModuleType("homeassistant.core")
core.HomeAssistant = object
homeassistant.core = core
sys.modules["homeassistant"] = homeassistant
sys.modules["homeassistant.core"] = core


def load(name):
    spec = importlib.util.spec_from_file_location(PACKAGE + "." + name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


const = load("const")
client_module = types.ModuleType(PACKAGE + ".client")
client_module.AqaraM1SClient = object
sys.modules[client_module.__name__] = client_module
sound_player = load("sound_player")


class FakeStderr:
    def __init__(self):
        self.lines = [b"out_time_ms=1000\n", b""]

    async def readline(self):
        return self.lines.pop(0)


class FakeProcess:
    pid = 123

    def __init__(self):
        self.returncode = None
        self.stderr = FakeStderr()

    async def wait(self):
        self.returncode = 0
        return 0

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


class SoundPriorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_wav_stops_media_then_resumes_it_after_mqtt_playback(self):
        events = []
        sleep_delays = []
        bridge = types.SimpleNamespace(
            async_prepare_sound=AsyncMock(side_effect=lambda path: events.append("prepare")),
            async_stop_sound=AsyncMock(side_effect=lambda: events.append("stop")),
        )
        hass = types.SimpleNamespace(
            data={const.DOMAIN: {const.DATA_COORDINATOR_MQTT: {"entry": bridge}}},
            loop=asyncio.get_running_loop(),
            async_create_task=asyncio.create_task,
        )
        client = types.SimpleNamespace(
            host="192.168.0.220",
            zigbee_role="coordinator",
        )
        radio = types.SimpleNamespace(
            async_suspend_for_priority_sound=AsyncMock(
                side_effect=lambda: events.append("suspend") or True
            ),
            async_resume_after_priority_sound=AsyncMock(
                side_effect=lambda resume: events.append(f"resume:{resume}")
            ),
        )
        group = types.SimpleNamespace(
            async_claim_sound=AsyncMock(side_effect=lambda entry: events.append("claim")),
            async_release_sound=AsyncMock(side_effect=lambda entry: events.append("release")),
        )
        player = sound_player.AqaraM1SSoundPlayer(
            hass, client, "entry", radio, group
        )
        process = FakeProcess()

        real_sleep = asyncio.sleep

        async def fast_sleep(delay):
            sleep_delays.append(delay)
            await real_sleep(0)

        with (
            patch.object(sound_player.asyncio, "sleep", side_effect=fast_sleep),
            patch.object(
                sound_player.asyncio,
                "create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            patch.object(player, "_try_set_ffmpeg_priority", return_value=False),
        ):
            await player.async_play("/data/musics/music-ch/test.wav", 50)
            watch = player._watch_task
            self.assertIsNotNone(watch)
            await watch

        self.assertEqual(
            events,
            ["claim", "suspend", "prepare", "stop", "resume:True", "release"],
        )
        bridge.async_prepare_sound.assert_awaited_once_with(
            "/data/musics/music-ch/test.wav"
        )
        bridge.async_stop_sound.assert_awaited_once_with()
        self.assertEqual(sound_player.SOUND_END_CUSHION_SECONDS, 0.5)
        self.assertIn(0.5, sleep_delays)

    async def test_router_with_advertised_support_uses_mqtt_for_wav(self):
        events = []
        bridge = types.SimpleNamespace(
            available=True,
            sound_supported=True,
            async_prepare_sound=AsyncMock(
                side_effect=lambda path: events.append("prepare")
            ),
            async_stop_sound=AsyncMock(side_effect=lambda: events.append("stop")),
        )
        executor = AsyncMock(
            side_effect=AssertionError("Telnet fallback must not run")
        )
        hass = types.SimpleNamespace(
            data={const.DOMAIN: {const.DATA_COORDINATOR_MQTT: {"entry": bridge}}},
            loop=asyncio.get_running_loop(),
            async_create_task=asyncio.create_task,
            async_add_executor_job=executor,
        )
        client = types.SimpleNamespace(
            host="192.168.0.222",
            zigbee_role="router",
        )
        radio = types.SimpleNamespace(
            async_suspend_for_priority_sound=AsyncMock(return_value=False),
            async_resume_after_priority_sound=AsyncMock(),
        )
        group = types.SimpleNamespace(
            async_claim_sound=AsyncMock(),
            async_release_sound=AsyncMock(),
        )
        player = sound_player.AqaraM1SSoundPlayer(
            hass, client, "entry", radio, group
        )
        process = FakeProcess()

        real_sleep = asyncio.sleep

        async def fast_sleep(delay):
            await real_sleep(0)

        with (
            patch.object(sound_player.asyncio, "sleep", side_effect=fast_sleep),
            patch.object(
                sound_player.asyncio,
                "create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            patch.object(player, "_try_set_ffmpeg_priority", return_value=False),
        ):
            await player.async_play("/data/musics/music-ch/test.wav", 50)
            watch = player._watch_task
            self.assertIsNotNone(watch)
            await watch

        self.assertEqual(events, ["prepare", "stop"])
        bridge.async_prepare_sound.assert_awaited_once()
        bridge.async_stop_sound.assert_awaited_once()
        executor.assert_not_awaited()

    async def test_router_without_advertised_support_keeps_telnet_wav(self):
        bridge = types.SimpleNamespace(
            available=True,
            sound_supported=False,
            async_prepare_sound=AsyncMock(),
            async_stop_sound=AsyncMock(),
        )
        run_command = Mock()
        executor = AsyncMock()
        hass = types.SimpleNamespace(
            data={const.DOMAIN: {const.DATA_COORDINATOR_MQTT: {"entry": bridge}}},
            loop=asyncio.get_running_loop(),
            async_create_task=asyncio.create_task,
            async_add_executor_job=executor,
        )
        client = types.SimpleNamespace(
            host="192.168.0.221",
            zigbee_role="router",
            run_command=run_command,
        )
        radio = types.SimpleNamespace(
            async_suspend_for_priority_sound=AsyncMock(return_value=False),
            async_resume_after_priority_sound=AsyncMock(),
        )
        group = types.SimpleNamespace(
            async_claim_sound=AsyncMock(),
            async_release_sound=AsyncMock(),
        )
        player = sound_player.AqaraM1SSoundPlayer(
            hass, client, "entry", radio, group
        )
        process = FakeProcess()

        real_sleep = asyncio.sleep

        async def fast_sleep(delay):
            await real_sleep(0)

        with (
            patch.object(sound_player.asyncio, "sleep", side_effect=fast_sleep),
            patch.object(
                sound_player.asyncio,
                "create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            patch.object(player, "_try_set_ffmpeg_priority", return_value=False),
        ):
            await player.async_play("/data/musics/music-ch/test.wav", 50)
            watch = player._watch_task
            self.assertIsNotNone(watch)
            await watch

        bridge.async_prepare_sound.assert_not_awaited()
        bridge.async_stop_sound.assert_not_awaited()
        self.assertEqual(executor.await_count, 2)
        self.assertEqual(
            executor.await_args_list[0].args,
            (
                run_command,
                sound_player.remote_start_command(
                    "/data/musics/music-ch/test.wav"
                ),
            ),
        )
        self.assertEqual(
            executor.await_args_list[1].args,
            (run_command, sound_player.REMOTE_STOP_COMMAND),
        )


if __name__ == "__main__":
    unittest.main()
