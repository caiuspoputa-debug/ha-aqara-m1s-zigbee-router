"""Real pipe backpressure and production group-stop lifecycle regression tests."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_group_cohort_alignment import FakeHass, FakeWriter, module


class GroupCleanStopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass = FakeHass()
        self.manager = module.AqaraM1SMediaGroupManager(self.hass)
        self.manager._signal_update = Mock()
        self.children = []

    async def asyncTearDown(self):
        for task in self.hass.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.hass.tasks, return_exceptions=True)
        for child in self.children:
            if child.returncode is None:
                with suppress(ProcessLookupError):
                    child.kill()
            await asyncio.wait_for(asyncio.gather(
                child.stdout.read(), child.stderr.read(), child.wait()), timeout=3)

    async def full_pipe_child(self):
        child = await asyncio.create_subprocess_exec(
            sys.executable, "-c",
            "import os,time; os.write(1,b'x'*1048576); os.write(2,b'e'*1048576); time.sleep(60)",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        self.children.append(child)
        for _ in range(300):
            if child.stdout._paused:
                return child
            await asyncio.sleep(0.01)
        self.fail("subprocess pipe never reached backpressure")

    async def test_unread_pipe_reproduces_wait_stall_after_terminate(self):
        child = await self.full_pipe_child()
        child.terminate()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(child.wait(), timeout=0.1)
        await asyncio.wait_for(asyncio.gather(
            child.stdout.read(), child.stderr.read(), child.wait()), timeout=2)
        self.assertIsNotNone(child.returncode)

    async def test_real_full_pipe_stop_reaps_without_forced_reset(self):
        self.manager.ffmpeg = await self.full_pipe_child()
        child = self.manager.ffmpeg
        with self.assertNoLogs(module._LOGGER, level="WARNING"):
            await asyncio.wait_for(self.manager._stop_stream_locked(
                stop_members=False, reason="user_stop"), timeout=2)
        self.assertIsNone(self.manager.ffmpeg)
        self.assertIsNotNone(child.returncode)
        self.assertTrue(child.stdout.at_eof())
        self.assertTrue(child.stderr.at_eof())

    async def test_existing_pipe_consumers_cancel_before_discard_readers(self):
        child = await self.full_pipe_child()
        producer_done = asyncio.Event()
        stderr_done = asyncio.Event()
        async def producer():
            try:
                await child.stdout.read(4480)
                await asyncio.Event().wait()
            finally:
                producer_done.set()
        async def broadcaster():
            task = asyncio.create_task(producer())
            try:
                await asyncio.Event().wait()
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        async def stderr_consumer():
            try:
                await child.stderr.read(4480)
            finally:
                stderr_done.set()
        self.manager.ffmpeg = child
        self.manager.broadcast_task = self.hass.async_create_background_task(broadcaster())
        self.manager.stderr_task = self.hass.async_create_background_task(stderr_consumer())
        await asyncio.sleep(0.02)
        with self.assertNoLogs(module._LOGGER, level="WARNING"):
            await asyncio.wait_for(self.manager._stop_stream_locked(
                stop_members=False, reason="source_change"), timeout=2)
        self.assertTrue(producer_done.is_set())
        self.assertTrue(stderr_done.is_set())
        self.assertTrue(child.stdout.at_eof())
        self.assertTrue(child.stderr.at_eof())

    async def test_user_stop_silences_hub_then_reaps_real_child(self):
        child = await self.full_pipe_child()
        self.manager.ffmpeg = child
        self.manager.desired_playing = True
        self.manager.async_force_reset = AsyncMock()
        self.manager._resume_suspended_individuals = AsyncMock()
        writer = FakeWriter()
        def remote_stop(command):
            self.assertIsNone(child.returncode)
            self.assertEqual(command, module.GROUP_STOP_COMMAND)
            return ""
        member = module.GroupMember(
            entry_id="221", name="Balcon",
            client=types.SimpleNamespace(host="192.168.0.221", run_command=remote_stop),
            coordinator=types.SimpleNamespace(last_update_success=True),
            writer=writer, generation=1, ready_for_fanout=True, shared_cursor=10,
        )
        self.manager.members[member.entry_id] = member
        with self.assertNoLogs(module._LOGGER, level="WARNING"):
            await asyncio.wait_for(self.manager.async_stop(), timeout=2)
        self.manager.async_force_reset.assert_not_awaited()
        self.assertFalse(self.manager.desired_playing)
        self.assertIsNone(self.manager.ffmpeg)
        self.assertIsNone(member.writer)
        self.assertTrue(writer.closed)
        self.assertIsNotNone(child.returncode)

    def stubborn_process(self):
        exited = asyncio.Event()
        terminated = asyncio.Event()
        child = types.SimpleNamespace(pid=123, returncode=None)
        child.stdout = types.SimpleNamespace(read=AsyncMock(return_value=b""))
        child.stderr = types.SimpleNamespace(read=AsyncMock(return_value=b""))
        def terminate():
            terminated.set()
        def kill():
            child.returncode = -9
            exited.set()
        async def wait():
            await exited.wait()
            return child.returncode
        child.terminate = Mock(side_effect=terminate)
        child.kill = Mock(side_effect=kill)
        child.wait = AsyncMock(side_effect=wait)
        return child, terminated

    async def test_genuinely_stubborn_child_is_killed_and_reaped(self):
        child, _ = self.stubborn_process()
        self.manager.ffmpeg = child
        with patch.object(module, "GROUP_FFMPEG_TERMINATE_TIMEOUT", 0.02):
            await asyncio.wait_for(self.manager._stop_stream_locked(
                stop_members=False, reason="user_stop"), timeout=1)
        child.kill.assert_called_once()
        self.assertEqual(child.returncode, -9)
        self.assertIsNone(self.manager.ffmpeg)

    async def test_cancellation_of_stop_cannot_orphan_child(self):
        child, terminated = self.stubborn_process()
        self.manager.ffmpeg = child
        stop = asyncio.create_task(self.manager._stop_stream_locked(
            stop_members=False, reason="user_stop"))
        await asyncio.wait_for(terminated.wait(), timeout=1)
        stop.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(stop, timeout=1)
        child.kill.assert_called_once()
        self.assertEqual(child.returncode, -9)
        self.assertIsNone(self.manager.ffmpeg)


if __name__ == "__main__":
    unittest.main()
