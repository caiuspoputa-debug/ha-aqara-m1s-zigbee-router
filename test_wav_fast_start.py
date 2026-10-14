"""Idle/active/in-flight handovers exercise the production priority methods."""
import ast
import asyncio
import logging
import types
import unittest
from unittest.mock import AsyncMock, Mock

from test_audio_link_guard import SOURCE
from test_group_cohort_alignment import FakeHass, module

tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AqaraM1SRadioPlayer")
methods = [n for n in cls.body if isinstance(n, ast.AsyncFunctionDef)
           and n.name in ("async_suspend_for_priority_sound", "async_cleanup_priority_receiver")]
namespace = {"asyncio": asyncio, "_LOGGER": logging.getLogger(__name__)}
exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), str(SOURCE), "exec"), namespace)


class RadioHandoverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.radio = types.SimpleNamespace(
            _shutting_down=False, _lock=asyncio.Lock(), _ffmpeg=None,
            _stream_writer=None, _watch_task=None, _resume_after_reconnect=False,
            _media_url=None, entity_id="test", client=types.SimpleNamespace(host="test"),
            _next_play_generation=Mock(return_value=2), _cancel_recovery_tasks_now=Mock(),
            _stop_locked=AsyncMock(), _priority_sound_suspended=False,
        )

    async def test_idle_hub_reserves_priority_without_remote_stop(self):
        resume = await namespace["async_suspend_for_priority_sound"](self.radio)
        self.assertFalse(resume)
        self.assertTrue(self.radio._priority_sound_suspended)
        self.assertFalse(self.radio._priority_sound_had_transport)
        self.radio._stop_locked.assert_awaited_once_with(
            update_state=True, reason="priority_sound", remote_cleanup=False)

    async def test_running_radio_keeps_scoped_stop_and_resume_intent(self):
        self.radio._ffmpeg = object()
        self.radio._media_url = "http://example.test/radio"
        self.radio._resume_after_reconnect = True
        self.assertTrue(await namespace["async_suspend_for_priority_sound"](self.radio))
        self.assertTrue(self.radio._priority_sound_had_transport)
        self.radio._stop_locked.assert_awaited_once_with(
            update_state=True, reason="priority_sound", remote_cleanup=True)

    async def test_in_flight_start_is_not_mistaken_for_idle(self):
        await self.radio._lock.acquire()
        entered = asyncio.Event()
        self.radio._next_play_generation.side_effect = lambda reason: entered.set() or 2
        task = asyncio.create_task(namespace["async_suspend_for_priority_sound"](self.radio))
        await entered.wait()
        self.assertTrue(self.radio._priority_sound_suspended)
        self.radio._lock.release()
        await task
        self.assertTrue(self.radio._priority_sound_had_transport)
        self.assertTrue(self.radio._stop_locked.await_args.kwargs["remote_cleanup"])

    async def test_busy_fallback_requires_priority_ownership(self):
        with self.assertRaises(RuntimeError):
            await namespace["async_cleanup_priority_receiver"](self.radio)
        self.radio._stop_locked.assert_not_awaited()


class GroupHandoverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass = FakeHass()
        self.manager = module.AqaraM1SMediaGroupManager(self.hass)
        self.manager._signal_update = Mock()
        self.manager._detach_member = AsyncMock()
        self.member = module.GroupMember("hub", "Hub", types.SimpleNamespace(host="test"),
                                         types.SimpleNamespace(last_update_success=True))
        self.manager.members["hub"] = self.member

    async def test_idle_group_does_not_request_remote_stop(self):
        self.assertFalse(await self.manager.async_claim_sound("hub"))
        self.assertIn("hub", self.manager.sound_intent)
        self.manager._detach_member.assert_awaited_once_with(
            "hub", stop_remote=False, new_state="playing_sound")

    async def test_group_preparation_is_treated_as_active_handover(self):
        self.member.prepare_task = types.SimpleNamespace(done=lambda: False)
        self.assertTrue(await self.manager.async_claim_sound("hub"))
        self.manager._detach_member.assert_awaited_once_with(
            "hub", stop_remote=True, new_state="playing_sound")


if __name__ == "__main__":
    unittest.main()
