"""Exercise production TCP batching with fake transports, not acoustic claims."""
from __future__ import annotations

import ast
import asyncio
import logging
import time
import types
import unittest
from unittest.mock import AsyncMock, Mock

from test_audio_link_guard import SOURCE, evaluated_constants
from test_group_cohort_alignment import FakeHass, FakeWriter, module


def single_helpers(player, writer):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    watch = next(node for node in ast.walk(tree)
                 if isinstance(node, ast.AsyncFunctionDef) and node.name == "_watch_ffmpeg")
    helpers = [node for node in watch.body if isinstance(node, ast.AsyncFunctionDef)
               and node.name in ("_flush_pcm_batch", "_write_chunk_to_hub")]
    factory = ast.parse('''
def factory(self, writer):
    pending_pcm = bytearray()
    transport_periods = 0
    consecutive_drain_timeouts = 0
    last_tcp_drain_timed_out = False
    generation = 1
    session = 1
    process = type("Process", (), {"pid": 99})()
    _rebuild_receiver_and_resync = self.recover
''').body[0]
    factory.body.extend(helpers)
    factory.body.extend(ast.parse(
        "return _write_chunk_to_hub, _flush_pcm_batch, pending_pcm"
    ).body)
    namespace = dict(evaluated_constants(), asyncio=asyncio, time=time,
                     next_batch_boundary=module.next_batch_boundary,
                     _LOGGER=logging.getLogger(__name__))
    namespace.pop("__builtins__", None)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[factory], type_ignores=[])),
                 str(SOURCE), "exec"), namespace)
    return namespace["factory"](player, writer)


async def settle(predicate):
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0.001)
    raise AssertionError("transport did not reach expected state")


class GroupBatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass = FakeHass()
        self.manager = module.AqaraM1SMediaGroupManager(self.hass)
        self.manager._signal_update = Mock()
        self.manager._schedule_isolate_member = Mock()
        self.manager.desired_playing = True
        self.manager.ffmpeg = types.SimpleNamespace(returncode=None)
        self.members = []
        for host in range(221, 227):
            member = module.GroupMember(
                entry_id=str(host), name=str(host),
                client=types.SimpleNamespace(host=f"192.168.0.{host}"),
                coordinator=types.SimpleNamespace(last_update_success=True),
                writer=FakeWriter(), generation=1, ready_for_fanout=True,
                shared_cursor=0,
            )
            self.manager.members[member.entry_id] = member
            self.members.append(member)
            self.manager._start_member_writer(member, member.generation)

    async def asyncTearDown(self):
        self.manager.desired_playing = False
        for member in self.members:
            member.generation += 1
        for task in self.hass.tasks:
            task.cancel()
        await asyncio.gather(*self.hass.tasks, return_exceptions=True)

    async def feed(self, count):
        chunks = []
        for _ in range(count):
            seq = self.manager._sequence
            chunk = seq.to_bytes(4, "little") * (module.CHUNK_BYTES // 4)
            chunks.append(chunk)
            await self.manager._fanout_frame(chunk, seq)
            self.manager._sequence += 1
            await asyncio.sleep(0)
        return b"".join(chunks)

    async def test_all_six_receive_identical_ordered_common_bursts(self):
        expected = await self.feed(60)
        await settle(lambda: all(len(m.writer.writes) == 20 for m in self.members))
        for member in self.members:
            self.assertEqual(b"".join(member.writer.writes), expected)
            self.assertEqual([len(b) for b in member.writer.writes], [13440] * 20)
            self.assertEqual(member.shared_cursor, 60)
        self.assertEqual(self.manager._sequence, 60)
        self.manager._schedule_isolate_member.assert_not_called()

    async def test_no_partial_write_before_common_boundary(self):
        await self.feed(2)
        await asyncio.sleep(0.01)
        self.assertTrue(all(m.writer.writes == [] for m in self.members))
        self.assertTrue(all(m.lag_since_monotonic is None for m in self.members))
        await self.feed(1)
        await settle(lambda: all(len(m.writer.writes) == 1 for m in self.members))

    async def test_eof_flushes_short_tail_identically(self):
        expected = await self.feed(19)
        await self.manager._flush_fanout_tail(self.manager._generation)
        await settle(lambda: all(m.shared_cursor == 19 for m in self.members))
        for member in self.members:
            self.assertEqual(b"".join(member.writer.writes), expected)
            self.assertEqual([len(b) for b in member.writer.writes], [13440] * 6 + [4480])

    async def test_muted_member_still_receives_the_identical_common_timeline(self):
        self.members[0].muted_in_group = True
        expected = await self.feed(3)
        await settle(lambda: all(m.writer.writes for m in self.members))
        self.assertEqual(self.members[0].writer.writes, [expected])
        self.assertEqual(self.members[1].writer.writes, [expected])

    async def test_old_generation_and_stop_do_not_release_tail(self):
        await self.feed(2)
        await self.manager._flush_fanout_tail(self.manager._generation - 1)
        self.manager.desired_playing = False
        await self.manager._flush_fanout_tail(self.manager._generation)
        self.assertTrue(all(m.writer.writes == [] for m in self.members))

    async def test_slow_member_does_not_block_healthy_bursts(self):
        blocked = asyncio.Event()
        self.members[0].writer.drain.side_effect = blocked.wait
        expected = await self.feed(60)
        await settle(lambda: all(len(m.writer.writes) == 20 for m in self.members[1:]))
        for member in self.members[1:]:
            self.assertEqual(b"".join(member.writer.writes), expected)
        self.assertEqual(self.manager._sequence, 60)
        self.assertEqual(len(self.members[0].writer.writes), 1)

    async def test_cohort_origin_not_zero_preserves_common_phase(self):
        for member in self.members:
            member.generation += 1
        for task in self.hass.tasks:
            task.cancel()
        await asyncio.gather(*self.hass.tasks, return_exceptions=True)
        self.manager._sequence = 40
        self.manager._transport_batch_origin = 40
        self.manager._transport_released_sequence = 40
        for member in self.members:
            member.shared_cursor = 40
            self.manager._start_member_writer(member, member.generation)
        await self.feed(2)
        self.assertTrue(all(m.writer.writes == [] for m in self.members))
        await self.feed(1)
        await settle(lambda: all(m.shared_cursor == 43 for m in self.members))


class SingleBatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.writer = FakeWriter()
        self.player = types.SimpleNamespace(
            _expected_transport_stop=Mock(return_value=None),
            _apply_live_pcm_gain=Mock(side_effect=lambda pcm: pcm),
            recover=AsyncMock(), entity_id="media_player.test",
            client=types.SimpleNamespace(host="192.168.0.221"),
        )
        self.write, self.flush, self.pending = single_helpers(self.player, self.writer)
        self.chunk = bytes([123]) * 4480

    async def test_first_three_chunks_one_write_gain_still_per_period(self):
        for _ in range(2):
            await self.write(self.chunk, stage="playout")
        self.assertEqual(self.writer.writes, [])
        await self.write(self.chunk, stage="playout")
        self.assertEqual(self.writer.writes, [self.chunk * 3])
        self.assertEqual(self.player._apply_live_pcm_gain.call_count, 3)
        self.assertEqual(self.pending, b"")

    async def test_single_matches_group_fixed_105_ms_cycle(self):
        for _ in range(60):
            await self.write(self.chunk, stage="playout")
        self.assertEqual([len(data) // 4480 for data in self.writer.writes],
                         [3] * 20)
        self.assertEqual(b"".join(self.writer.writes), self.chunk * 60)
        self.assertEqual(self.player._apply_live_pcm_gain.call_count, 60)

    async def test_tail_flush_is_idempotent_and_ordered(self):
        for i in range(19):
            await self.write(bytes([i]) * 4480, stage="playout")
        await self.flush(stage="end_of_media")
        await self.flush(stage="end_of_media")
        self.assertEqual([len(data) for data in self.writer.writes], [13440] * 6 + [4480])
        self.assertEqual(b"".join(self.writer.writes),
                         b"".join(bytes([i]) * 4480 for i in range(19)))

    async def test_injected_silence_preserves_transport_lengths(self):
        self.player._apply_live_pcm_gain.side_effect = lambda pcm: bytes(len(pcm))
        for _ in range(3):
            await self.write(self.chunk, stage="playout")
        self.assertEqual(self.writer.writes, [bytes(13440)])

    async def test_expected_teardown_discards_pending_not_writes(self):
        await self.write(self.chunk, stage="playout")
        self.player._expected_transport_stop.return_value = "source_changed"
        await self.flush(stage="end_of_media")
        self.assertEqual(self.writer.writes, [])
        self.assertEqual(self.pending, b"")

    async def test_socket_failure_does_not_replay_old_batch_on_recovery(self):
        self.writer.closed = True
        for _ in range(3):
            await self.write(self.chunk, stage="playout")
        self.player.recover.assert_awaited_once()
        self.assertEqual(self.pending, b"")
        self.writer.closed = False
        await self.flush(stage="end_of_media")
        self.assertEqual(self.writer.writes, [])

    async def test_timeout_does_not_duplicate_already_written_bytes(self):
        self.writer.drain.side_effect = asyncio.TimeoutError
        for _ in range(6):
            await self.write(self.chunk, stage="playout")
        self.assertEqual(self.writer.writes, [self.chunk * 3] * 2)
        self.player.recover.assert_awaited_once()
        self.assertEqual(self.pending, b"")


class TransportContractTests(unittest.TestCase):
    def test_105_ms_boundaries_are_exact_for_over_eight_hours(self):
        origin = 123456789
        cursor = origin
        for batch in range(1, 300001):
            end = module.next_batch_boundary(cursor, origin, 35, 105)
            self.assertEqual(end - cursor, 3)
            self.assertEqual((end - origin) * 35, batch * 105)
            cursor = end

    def test_diagnostics_report_fixed_105_ms_for_both_paths(self):
        group = module.AqaraM1SMediaGroupManager(FakeHass()).attributes()
        self.assertEqual([group[key] for key in
                          ("tcp_batch_ms", "tcp_batch_min_ms", "tcp_batch_max_ms")],
                         [105, 105, 105])
        self.assertEqual(group["tcp_batch_periods"], 3)
        self.assertEqual(group["tcp_batch_bytes"], 13440)
        values = evaluated_constants()
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        expected = {"single_tcp_batch_ms": 105, "single_tcp_batch_min_ms": 105,
                    "single_tcp_batch_max_ms": 105, "single_tcp_batch_periods": 3,
                    "single_tcp_batch_bytes": 13440}
        found = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, expression in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value in expected:
                        found[key.value] = eval(compile(ast.Expression(expression), str(SOURCE), "eval"), values)
        self.assertEqual(found, expected)

    def test_integer_boundaries_do_not_accumulate_rounding_drift(self):
        cursor = 0
        for batch in range(1, 100001):
            end = module.next_batch_boundary(cursor, 0, 35, 300)
            self.assertIn(end - cursor, (8, 9))
            self.assertGreaterEqual(end * 35, batch * 300)
            self.assertLess(end * 35 - batch * 300, 35)
            cursor = end
        self.assertEqual(cursor * 35, 30000000 + (35 - 30000000 % 35) % 35)

    def test_large_cohort_origin_has_identical_boundary_schedule(self):
        origin = 123456789
        cursor = origin
        result = []
        for _ in range(7):
            end = module.next_batch_boundary(cursor, origin, 35, 300)
            result.append(end - cursor)
            cursor = end
        self.assertEqual(result, [9, 9, 8, 9, 8, 9, 8])
        self.assertEqual((cursor - origin) * 35, 2100)

    def test_batch_fits_existing_watermarks_and_prefill(self):
        values = evaluated_constants()
        self.assertEqual(values["SINGLE_TRANSPORT_BATCH_CHUNKS"], module.GROUP_TRANSPORT_BATCH_CHUNKS)
        self.assertEqual(values["SINGLE_TRANSPORT_TARGET_MS"], 105)
        self.assertEqual(module.GROUP_TRANSPORT_BATCH_CHUNKS, 3)
        self.assertLess(13440, values["SINGLE_WRITE_HIGH_WATER_BYTES"])
        self.assertLess(0.105, values["SINGLE_REMOTE_PREFILL_SECONDS"])
        self.assertEqual(values["SINGLE_TRANSPORT_TARGET_MS"], module.GROUP_TRANSPORT_TARGET_MS)
        self.assertEqual(module.CHUNK_SECONDS, 0.035)
        self.assertFalse(module.ADAPTIVE_SYNC_ENABLED)

    def test_source_rebuffer_and_recovery_clear_pending_before_await(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        for name in ("_stop_receiver_for_source_rebuffer", "_rebuild_receiver_and_resync"):
            method = next(node for node in ast.walk(tree)
                          if isinstance(node, ast.AsyncFunctionDef) and node.name == name)
            source = ast.unparse(method)
            self.assertLess(source.index("pending_pcm.clear()"), source.index("await "))


if __name__ == "__main__":
    unittest.main()
