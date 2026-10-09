"""Run the actual manager's async recovery paths with in-memory transports.

No Home Assistant server, radio network, hub command or filesystem is accessed.
These tests verify transport/lifecycle contracts, not acoustic synchronization.
"""
from __future__ import annotations

import ast
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


ROOT = Path(__file__).parent / "custom_components/aqara_m1s_zigbee_router"
SPEC = importlib.util.spec_from_file_location("m1s_cohort_policy", ROOT / "group_sync.py")
POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = POLICY
SPEC.loader.exec_module(POLICY)

# Keep the complete production manager and dataclass; replace only HA imports.
tree = ast.parse((ROOT / "media_group.py").read_text(encoding="utf-8"))
nodes = []
for node in tree.body:
    if isinstance(node, ast.Import):
        nodes.append(node)
    elif isinstance(node, ast.ImportFrom) and node.module in (
        "__future__", "array", "collections", "contextlib", "dataclasses", "typing", "urllib.parse"
    ):
        nodes.append(node)
    elif isinstance(node, ast.Assign):
        nodes.append(node)
    elif isinstance(node, ast.ClassDef) and node.name in (
        "GroupMember", "AqaraM1SMediaGroupManager"
    ):
        nodes.append(node)
module = types.ModuleType("m1s_cohort_manager_test")
sys.modules[module.__name__] = module
module.__dict__.update({
    "MediaType": types.SimpleNamespace(MUSIC="music"),
    "DOMAIN": "aqara_m1s_zigbee_router",
    "CohortAlignmentGate": POLICY.CohortAlignmentGate,
    "ReceiverTimingGuard": POLICY.ReceiverTimingGuard,
    "COHORT_ALIGNMENT_COOLDOWN_SECONDS": POLICY.COHORT_ALIGNMENT_COOLDOWN_SECONDS,
    "decide_group_sync_recovery": POLICY.decide_group_sync_recovery,
})
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / "media_group.py"), "exec"), module.__dict__)


class FakeWriter:
    def __init__(self):
        self.writes = []
        self.closed = False
        self.drain = AsyncMock()
        self.transport = types.SimpleNamespace(set_write_buffer_limits=Mock())

    def write(self, data):
        if self.closed:
            raise ConnectionError("closed writer")
        self.writes.append(data)

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass

    def get_extra_info(self, name):
        return None


class FakeHass:
    def __init__(self):
        self.tasks = []
        self.commands = []
        self.data = {}

    def async_create_background_task(self, coroutine, name=None):
        task = asyncio.create_task(coroutine, name=name)
        self.tasks.append(task)
        return task

    async_create_task = async_create_background_task

    async def async_add_executor_job(self, function, *args):
        self.commands.append(args)
        return function(*args)


class AlignmentPolicyTests(unittest.TestCase):
    def test_return_requests_are_coalesced_with_a_cooldown(self):
        gate = POLICY.CohortAlignmentGate()
        gate.mark_attempt(0.0)
        gate.request(10.0, "first")
        gate.request(20.0, "second")
        self.assertEqual(gate.reason, "first")
        self.assertFalse(gate.due(59.0, has_receivers=True, has_healthy=True))
        self.assertTrue(gate.due(60.0, has_receivers=True, has_healthy=True))
        gate.mark_attempt(60.0)
        self.assertFalse(gate.due(100.0, has_receivers=True, has_healthy=True))

    def test_no_healthy_audio_does_not_wait_for_cooldown(self):
        gate = POLICY.CohortAlignmentGate(last_attempt=10.0)
        gate.request(11.0, "restore")
        self.assertTrue(gate.due(11.0, has_receivers=True, has_healthy=False))
        self.assertFalse(gate.due(100.0, has_receivers=False, has_healthy=False))

    def test_six_hour_flapping_cannot_trigger_a_reset_storm(self):
        gate = POLICY.CohortAlignmentGate()
        gate.mark_attempt(0.0)
        attempts = []
        for second in range(1, 6 * 3600):
            gate.request(float(second), "flapping")
            if gate.due(float(second), has_receivers=True, has_healthy=True):
                attempts.append(second)
                gate.mark_attempt(float(second))
        self.assertTrue(attempts)
        self.assertTrue(all(b - a >= 60 for a, b in zip(attempts, attempts[1:])))

    def test_fixed_queue_differences_are_not_drift(self):
        guard = POLICY.ReceiverTimingGuard()
        for _ in range(100):
            self.assertFalse(guard.observe({"221": 200.0, "222": 900.0}))
        self.assertEqual(guard.spread_ms, 0.0)

    def test_three_relative_queue_changes_are_required(self):
        guard = POLICY.ReceiverTimingGuard()
        guard.observe({"221": 500.0, "222": 500.0})
        self.assertFalse(guard.observe({"221": 500.0, "222": 800.0}))
        self.assertFalse(guard.observe({"221": 500.0, "222": 800.0}))
        self.assertTrue(guard.observe({"221": 500.0, "222": 800.0}))

    def test_membership_change_or_clean_sample_resets_confirmation(self):
        guard = POLICY.ReceiverTimingGuard()
        guard.observe({"221": 500.0, "222": 500.0})
        guard.observe({"221": 500.0, "222": 800.0})
        self.assertFalse(guard.observe({"221": 500.0, "222": 500.0}))
        self.assertEqual(guard.confirmations, 0)
        guard.observe({"221": 500.0, "222": 800.0})
        self.assertFalse(guard.observe({"221": 500.0, "223": 800.0}))
        self.assertEqual(guard.confirmations, 0)


class ManagerAlignmentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 1000.0
        self.clock_patch = patch.object(module, "time", types.SimpleNamespace(monotonic=lambda: self.now))
        self.clock_patch.start()
        self.hass = FakeHass()
        self.manager = module.AqaraM1SMediaGroupManager(self.hass)
        self.manager._signal_update = Mock()
        self.manager._suspend_individual_for_group = AsyncMock()
        self.manager.desired_playing = True
        self.manager.ffmpeg = types.SimpleNamespace(returncode=None)
        self.manager.volume = 1.0
        self.manager._reset_live_gain()

    async def asyncTearDown(self):
        self.manager.desired_playing = False
        for member in list(self.manager.members.values()):
            await self.manager._detach_member(member.entry_id, stop_remote=False, new_state="idle")
        for task in self.hass.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.hass.tasks, return_exceptions=True)
        self.clock_patch.stop()

    def add_member(self, suffix, *, ready=False):
        member = module.GroupMember(
            entry_id=str(suffix), name="Aqara M1S Zigbee Router",
            client=types.SimpleNamespace(host=f"192.168.0.{suffix}", run_command=Mock(return_value="")),
            coordinator=types.SimpleNamespace(last_update_success=True),
            writer=FakeWriter(), generation=1, ready_for_fanout=ready,
            shared_cursor=100 if ready else None,
        )
        self.manager.members[member.entry_id] = member
        return member

    def request_due_alignment(self):
        now = module.time.monotonic()
        self.manager._cohort_alignment.request(now - 4.0, "test_rejoin")

    def source_queue(self):
        queue = asyncio.Queue()
        for index in range(50):
            queue.put_nowait(index.to_bytes(4, "little") * (module.CHUNK_BYTES // 4))
        return queue

    def mock_prepare(self, failed_id=None):
        async def prepare(member, *, initial):
            if member.entry_id == failed_id:
                member.prepare_failures += 1
                return False
            member.writer = FakeWriter()
            member.generation += 1
            member.ready_for_fanout = False
            return True
        self.manager._prepare_member = AsyncMock(side_effect=prepare)

    async def test_late_join_never_writes_history_or_claims_alignment(self):
        member = self.add_member(222)
        self.manager._pcm_history.extend((i, b"old") for i in range(100))
        member.prepare_failures = 3
        await self.manager._prime_late_join_member(member, member.generation)
        self.assertEqual(member.writer.writes, [])
        self.assertFalse(member.ready_for_fanout)
        self.assertIsNone(member.shared_cursor)
        self.assertEqual(member.prepare_failures, 3)
        self.assertIn("192.168.0.222", self.manager._cohort_alignment.reason)

    async def test_common_prefill_same_pcm_cursor_and_source_for_all_receivers(self):
        members = [self.add_member(221, ready=True), self.add_member(222, ready=True), self.add_member(223)]
        old_writers = [m.writer for m in members]
        self.manager._sequence = 100
        self.manager._pcm_history.append((99, b"old-history"))
        process = self.manager.ffmpeg
        self.request_due_alignment()
        self.mock_prepare()
        await self.manager._realign_receiver_cohort(self.source_queue(), self.manager._generation)
        self.assertIs(self.manager.ffmpeg, process)
        self.assertTrue(all(w.closed for w in old_writers))
        self.assertTrue(all(m.ready_for_fanout for m in members))
        self.assertEqual({m.shared_cursor for m in members}, {140})
        self.assertEqual(self.manager._sequence, 140)
        self.assertEqual(members[0].writer.writes, members[1].writer.writes)
        self.assertEqual(members[0].writer.writes, members[2].writer.writes)
        self.assertNotIn(b"old-history", members[0].writer.writes[0])
        self.assertFalse(self.manager._cohort_realigning)
        self.assertEqual(self.manager._receiver_resync_count, 1)

    async def test_one_failed_prepare_does_not_block_healthy_cohort(self):
        healthy = self.add_member(221, ready=True)
        failing = self.add_member(222)
        self.request_due_alignment()
        self.mock_prepare(failed_id="222")
        await self.manager._realign_receiver_cohort(self.source_queue(), self.manager._generation)
        self.assertTrue(healthy.ready_for_fanout)
        self.assertIsNone(failing.writer)
        self.assertFalse(failing.ready_for_fanout)

    async def test_one_failed_prefill_isolated_without_aborting_other_receiver(self):
        healthy = self.add_member(221)
        failing = self.add_member(222)
        failing.writer.drain.side_effect = ConnectionError("test network loss")
        await self.manager._prime_initial_cohort(self.source_queue(), self.manager._generation)
        self.assertTrue(healthy.ready_for_fanout)
        self.assertFalse(failing.ready_for_fanout)
        self.assertTrue(failing.detaching or failing.writer is None)

    async def test_stop_or_source_change_discards_pending_alignment(self):
        member = self.add_member(221, ready=True)
        self.request_due_alignment()
        old = member.writer
        self.manager.desired_playing = False
        await self.manager._realign_receiver_cohort(self.source_queue(), self.manager._generation)
        self.assertIs(member.writer, old)
        self.manager.desired_playing = True
        await self.manager._realign_receiver_cohort(self.source_queue(), self.manager._generation - 1)
        self.assertIs(member.writer, old)
        self.assertEqual(self.hass.commands, [])

    async def test_cooldown_does_not_touch_healthy_writers(self):
        healthy = self.add_member(221, ready=True)
        self.add_member(222)
        now = module.time.monotonic()
        self.manager._cohort_alignment.mark_attempt(now)
        self.manager._cohort_alignment.request(now - 4.0, "return")
        old = healthy.writer
        await self.manager._realign_receiver_cohort(self.source_queue(), self.manager._generation)
        self.assertIs(healthy.writer, old)
        self.assertEqual(self.hass.commands, [])

    async def test_empty_source_does_not_tear_down_healthy_audio(self):
        healthy = self.add_member(221, ready=True)
        self.request_due_alignment()
        old = healthy.writer
        await self.manager._realign_receiver_cohort(asyncio.Queue(), self.manager._generation)
        self.assertIs(healthy.writer, old)

    async def test_prefill_cannot_reclaim_a_priority_sound(self):
        healthy = self.add_member(221)
        sound = self.add_member(222)
        async def claim():
            await self.manager.async_claim_sound(sound.entry_id)
        sound.writer.drain.side_effect = claim
        await self.manager._prime_initial_cohort(self.source_queue(), self.manager._generation)
        self.assertTrue(healthy.ready_for_fanout)
        self.assertFalse(sound.ready_for_fanout)
        self.assertIsNone(sound.writer)
        self.assertEqual(sound.state, "playing_sound")

    async def test_duplicate_names_do_not_hide_hubs_in_diagnostics(self):
        self.add_member(221)
        self.add_member(222)
        attrs = self.manager.attributes()
        self.assertEqual(set(attrs["member_diagnostics_by_entry_id"]), {"221", "222"})
        self.assertEqual(len(attrs["active_hubs"]), 2)
        self.assertIn("192.168.0.221", attrs["active_hubs"][0])
        self.assertIn("192.168.0.222", attrs["active_hubs"][1])

    def set_health(self, member, delay, *, sample=None, **overrides):
        self.now += 0.001
        now = module.time.monotonic()
        member.aligned_since_monotonic = now - 40
        member.shared_cursor = self.manager._sequence
        member.last_receiver_health = {
            "stale": False, "alsa_state": "RUNNING", "tcp_established": True,
            "alsa_delay_frames": delay, "alsa_avail_frames": 100,
            "alsa_buffer_frames": 64000, "sample_monotonic": sample or now,
            "probe_duration_seconds": 0.01, **overrides,
        }

    async def test_valid_fresh_timing_changes_request_common_alignment(self):
        a, b = self.add_member(221, ready=True), self.add_member(222, ready=True)
        self.set_health(a, 16000)
        self.set_health(b, 16000)
        await self.manager._soft_receiver_resync_audit()
        for _ in range(3):
            self.set_health(a, 16000)
            self.set_health(b, 25600)
            await self.manager._soft_receiver_resync_audit()
        self.assertEqual(self.manager._cohort_alignment.reason, "confirmed_relative_alsa_queue_change")
        self.assertEqual(self.hass.commands, [])

    async def test_stale_slow_or_impossible_timing_never_requests_alignment(self):
        a, b = self.add_member(221, ready=True), self.add_member(222, ready=True)
        for invalid in (
            {"alsa_delay_frames": -15680}, {"alsa_avail_frames": 35840, "alsa_buffer_frames": 4480},
            {"alsa_state": "XRUN"}, {"probe_duration_seconds": 1.0},
            {"sample_monotonic": module.time.monotonic() - 30},
        ):
            self.manager._receiver_timing_guard.reset()
            for _ in range(5):
                self.set_health(a, 16000)
                self.set_health(b, 25600, **invalid)
                await self.manager._soft_receiver_resync_audit()
            self.assertIsNone(self.manager._cohort_alignment.reason, invalid)

    async def test_reused_health_snapshot_cannot_supply_three_confirmations(self):
        a, b = self.add_member(221, ready=True), self.add_member(222, ready=True)
        self.set_health(a, 16000)
        self.set_health(b, 16000)
        await self.manager._soft_receiver_resync_audit()
        self.set_health(a, 16000)
        self.set_health(b, 25600)
        for _ in range(10):
            await self.manager._soft_receiver_resync_audit()
        self.assertEqual(self.manager._receiver_timing_guard.confirmations, 1)
        self.assertIsNone(self.manager._cohort_alignment.reason)

    async def test_health_result_from_detached_generation_is_ignored(self):
        member = self.add_member(221, ready=True)
        async def read(_):
            await self.manager._detach_member(member.entry_id, stop_remote=False, new_state="idle")
            return {"stale": True, "reason": "obsolete"}
        self.manager._read_group_receiver_health = AsyncMock(side_effect=read)
        await self.manager._probe_group_receiver_health(member)
        self.assertIsNone(member.last_receiver_health)
        self.assertEqual(member.stale_health_samples, 0)

    async def test_real_preparation_stages_tcp_without_resetting_failure_history(self):
        member = self.add_member(222)
        member.writer = None
        member.prepare_failures = 4
        writer = FakeWriter()
        with patch.object(module.asyncio, "open_connection", AsyncMock(return_value=(None, writer))):
            prepared = await self.manager._prepare_member(member, initial=False)
        self.assertTrue(prepared)
        self.assertEqual(writer.writes, [])
        self.assertFalse(member.ready_for_fanout)
        self.assertEqual(member.prepare_failures, 4)

    async def test_priority_claim_while_connecting_closes_orphan_tcp(self):
        member = self.add_member(222)
        member.writer = None
        writer = FakeWriter()
        async def connect(*args):
            await self.manager.async_claim_individual(member.entry_id)
            return None, writer
        with patch.object(module.asyncio, "open_connection", AsyncMock(side_effect=connect)):
            with self.assertRaises(asyncio.CancelledError):
                await self.manager._prepare_member(member, initial=False)
        self.assertTrue(writer.closed)
        self.assertIsNone(member.writer)
        self.assertFalse(member.ready_for_fanout)

    async def test_two_real_writer_timeouts_only_quarantine_that_member(self):
        member = self.add_member(222, ready=True)
        self.manager._schedule_isolate_member = Mock()
        member.writer.drain.side_effect = asyncio.TimeoutError
        self.manager._pcm_history.extend((i, module.SILENCE_CHUNK) for i in range(100, 103))
        await asyncio.wait_for(self.manager._member_writer_loop(member, member.generation), timeout=1)
        self.assertEqual(member.consecutive_drain_timeouts, 2)
        self.manager._schedule_isolate_member.assert_called_once()
        self.assertIsNone(self.manager._cohort_alignment.reason)

    async def test_single_timeout_followed_by_success_keeps_receiver(self):
        member = self.add_member(222, ready=True)
        self.manager._schedule_isolate_member = Mock()
        drained = asyncio.Event()
        attempts = 0
        async def drain():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise asyncio.TimeoutError
            drained.set()
        member.writer.drain.side_effect = drain
        self.manager._pcm_history.extend((i, module.SILENCE_CHUNK) for i in range(100, 103))
        member.writer_task = self.hass.async_create_background_task(
            self.manager._member_writer_loop(member, member.generation), "test_writer"
        )
        await asyncio.wait_for(drained.wait(), timeout=1)
        await asyncio.sleep(0)
        self.assertEqual(member.consecutive_drain_timeouts, 0)
        self.manager._schedule_isolate_member.assert_not_called()
        self.assertIsNone(self.manager._cohort_alignment.reason)

    async def test_actual_broadcaster_rejoins_via_common_barrier_and_keeps_source(self):
        initial = self.add_member(221)
        self.manager._schedule_watchdog_restart = Mock()
        self.mock_prepare()
        data = module.SILENCE_CHUNK * 500
        reader = types.SimpleNamespace(read=AsyncMock(side_effect=[data, b""]))
        source = types.SimpleNamespace(returncode=None, stdout=reader)
        self.manager.ffmpeg = source
        returned = []
        original_fanout = self.manager._fanout_frame
        async def fanout(chunk, sequence):
            await original_fanout(chunk, sequence)
            if sequence == 60:
                member = self.add_member(222)
                returned.append(member)
                await self.manager._prime_late_join_member(member, member.generation)
            if returned and self.manager._receiver_resync_count == 0:
                self.assertFalse(returned[0].ready_for_fanout)
                self.assertEqual(returned[0].writer.writes, [])
        async def pace(sequence):
            self.now += 0.35
            for _ in range(5):
                await asyncio.sleep(0)
        self.manager._fanout_frame = fanout
        self.manager._pace_frame = pace
        await asyncio.wait_for(self.manager._broadcast_loop(source, self.manager._generation), timeout=30)
        self.assertIs(self.manager.ffmpeg, source)
        self.assertEqual(self.manager._receiver_resync_count, 1)
        self.assertTrue(initial.ready_for_fanout)
        self.assertTrue(returned[0].ready_for_fanout)
        self.assertFalse(self.manager._cohort_realigning)

    async def test_stop_during_cohort_preparation_does_not_admit_receivers(self):
        member = self.add_member(221, ready=True)
        self.request_due_alignment()
        started, release = asyncio.Event(), asyncio.Event()
        async def prepare(member, *, initial):
            member.writer = FakeWriter()
            started.set()
            await release.wait()
            return True
        self.manager._prepare_member = AsyncMock(side_effect=prepare)
        task = asyncio.create_task(self.manager._realign_receiver_cohort(self.source_queue(), self.manager._generation))
        await asyncio.wait_for(started.wait(), timeout=1)
        self.manager.desired_playing = False
        release.set()
        await asyncio.wait_for(task, timeout=1)
        self.assertFalse(member.ready_for_fanout)
        self.assertEqual(member.writer.writes, [])
        self.assertFalse(self.manager._cohort_realigning)

    async def test_new_play_intent_during_preparation_cannot_readmit_old_source(self):
        member = self.add_member(221, ready=True)
        self.request_due_alignment()
        async def prepare(member, *, initial):
            member.writer = FakeWriter()
            self.manager.next_media_intent("play_media")
            return True
        self.manager._prepare_member = AsyncMock(side_effect=prepare)
        await self.manager._realign_receiver_cohort(self.source_queue(), self.manager._generation)
        self.assertFalse(member.ready_for_fanout)
        self.assertEqual(member.writer.writes, [])
        self.assertEqual(self.manager._receiver_resync_count, 0)
        self.request_due_alignment()
        await self.manager._realign_receiver_cohort(self.source_queue(), self.manager._generation)
        self.assertFalse(member.ready_for_fanout)
        self.assertEqual(member.writer.writes, [])


if __name__ == "__main__":
    unittest.main()
