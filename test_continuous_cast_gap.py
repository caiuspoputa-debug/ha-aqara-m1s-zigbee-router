"""Exercise the real individual Cast gap branch without HA or a physical hub."""
from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path
import re
import time
import types
import unittest
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlsplit

from test_audio_link_guard import SOURCE, evaluated_constants


ROOT = SOURCE.parent
source_tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
watch = next(node for node in ast.walk(source_tree)
             if isinstance(node, ast.AsyncFunctionDef) and node.name == "_watch_ffmpeg")
icy_tree = ast.parse((ROOT / "icy_metadata.py").read_text(encoding="utf-8"))
classifier = next(node for node in icy_tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "is_continuous_cast_url")
classifier_namespace = {"re": re, "urlsplit": urlsplit}
exec(compile(ast.Module(body=[classifier], type_ignores=[]), str(ROOT / "icy_metadata.py"), "exec"), classifier_namespace)
is_continuous_cast_url = classifier_namespace["is_continuous_cast_url"]


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []
        self.on_sleep = None

    def monotonic(self):
        return self.now

    async def sleep(self, delay):
        self.now += delay
        self.sleeps.append(delay)
        if self.on_sleep:
            self.on_sleep(len(self.sleeps))
        await asyncio.sleep(0)


class Writer:
    def __init__(self):
        self.writes = []
        self.hub_tail = bytearray(b"previous-hub-tail")
        self.closed = False
        self.drain = AsyncMock()

    def write(self, data):
        if self.closed:
            raise ConnectionError("writer closed")
        self.writes.append(data)
        self.hub_tail.extend(data)


def production_gap(player, writer, queue, done, process, clock, media_url):
    """Compile production helpers AND the actual dispatch branch, not a copy."""
    helpers = [node for node in watch.body if isinstance(node, ast.AsyncFunctionDef)
               and node.name in ("_stop_receiver_for_source_rebuffer", "_flush_pcm_batch",
                                 "_write_chunk_to_hub", "_wait_for_continuous_cast_pcm")]
    gap_branch = next(node for node in ast.walk(watch)
                      if isinstance(node, ast.If)
                      and ast.unparse(node.test) == "not rebuffering and queue.empty() and (not producer_done.is_set())")
    factory = ast.parse('''
def factory(self, writer, queue, producer_done, process, media_url):
    generation = 1
    session = 41
    pending_pcm = bytearray()
    transport_periods = 0
    consecutive_drain_timeouts = 0
    last_tcp_drain_timed_out = False
    health_task = None
    receiver_stopped_for_rebuffer = False
    rebuffering = False
    rebuffer_events = 0
    producer_error = None
    last_source_progress_monotonic = time.monotonic()
    next_send_monotonic = time.monotonic()
    continuous_cast_source = is_continuous_cast_url(media_url)
    _rebuild_receiver_and_resync = self.recover
    def set_error(error):
        nonlocal producer_error
        producer_error = error
''').body[0]
    factory.body.extend(helpers)
    dispatch = ast.parse('''
async def dispatch():
    nonlocal rebuffering, rebuffer_events, last_source_progress_monotonic, next_send_monotonic
    while True:
        pass
    return rebuffering, receiver_stopped_for_rebuffer, next_send_monotonic
''').body[0]
    dispatch.body[1].body = [gap_branch, ast.Break()]
    factory.body.append(dispatch)
    factory.body.extend(ast.parse(
        "return dispatch, _write_chunk_to_hub, _flush_pcm_batch, pending_pcm, set_error"
    ).body)
    batch_tree = ast.parse((ROOT / "audio_batch.py").read_text(encoding="utf-8"))
    batch_namespace = {}
    exec(compile(batch_tree, str(ROOT / "audio_batch.py"), "exec"), batch_namespace)
    namespace = dict(evaluated_constants(),
                     asyncio=types.SimpleNamespace(sleep=clock.sleep, wait_for=asyncio.wait_for,
                                                   QueueEmpty=asyncio.QueueEmpty, TimeoutError=asyncio.TimeoutError),
                     time=clock, _LOGGER=logging.getLogger(__name__),
                     MediaPlayerState=types.SimpleNamespace(BUFFERING="buffering"),
                     is_continuous_cast_url=is_continuous_cast_url,
                     next_batch_boundary=batch_namespace["next_batch_boundary"])
    namespace.pop("__builtins__", None)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[factory], type_ignores=[])),
                 str(SOURCE), "exec"), namespace)
    return namespace["factory"](player, writer, queue, done, process, media_url)


class ContinuousCastClassificationTests(unittest.TestCase):
    def test_exact_continuous_bridge_across_hosts_and_ports(self):
        for url in ("http://192.168.0.20:8098/stream/individual-1/41.wav",
                    "http://another-ha:9000/stream/media_player%2Etest/999.wav?key=value",
                    "https://[fd00::20]:8080/stream/group/1.WAV/"):
            self.assertTrue(is_continuous_cast_url(url), url)

    def test_ordinary_radio_local_and_legacy_finite_streams_unchanged(self):
        for url in ("http://radio.test/live", "http://radio.test/music.wav",
                    "http://host/audio/token/key/4", "file:///stream/test/1.wav",
                    "http://host/stream/test/not-a-serial.wav",
                    "http://host/some/stream/test/1.wav", ""):
            self.assertFalse(is_continuous_cast_url(url), url)


class ContinuousCastGapTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = Clock()
        self.writer = Writer()
        self.process = object()
        self.queue = asyncio.Queue()
        self.done = asyncio.Event()
        self.generation = 1

        def stop_command(command):
            # A receiver STOP really discards already-queued audible tail.
            self.writer.hub_tail.clear()

        async def executor(function, *args):
            return function(*args)

        async def close_writer(writer, **kwargs):
            writer.closed = True

        self.player = types.SimpleNamespace(
            _ffmpeg=self.process, _stream_writer=self.writer, _shutting_down=False,
            _generation_is_current=lambda generation: generation == self.generation,
            _expected_transport_stop=lambda generation: None if generation == self.generation else "superseded",
            _apply_live_pcm_gain=lambda chunk: chunk,
            _close_writer_bounded=AsyncMock(side_effect=close_writer),
            client=types.SimpleNamespace(host="192.168.0.205", run_command=Mock(side_effect=stop_command)),
            hass=types.SimpleNamespace(async_add_executor_job=executor),
            entity_id="media_player.cezara", recover=AsyncMock(),
            async_write_ha_state=Mock(),
        )

    def make(self, cast=True):
        url = "http://192.168.0.20:8098/stream/cezara/1.wav" if cast else "http://radio.test/live"
        return production_gap(self.player, self.writer, self.queue, self.done, self.process, self.clock, url)

    async def test_short_gap_flushes_every_tail_byte_and_retains_original_clock(self):
        gap, write, flush, pending, _ = self.make()
        tail = b"A" * 4480
        successor = b"B" * 4480
        await write(tail, stage="playout")
        await write(tail, stage="playout")
        self.assertEqual(self.writer.writes, [])

        def produce(count):
            self.assertEqual(self.writer.writes, [tail * 2], "tail must be sent before waiting")
            if count == 3:
                self.queue.put_nowait(successor)
        self.clock.on_sleep = produce
        rebuffering, stopped, clock = await gap()
        self.assertFalse(rebuffering)
        self.assertFalse(stopped)
        self.assertEqual(clock, 100.0)
        self.assertEqual(self.clock.sleeps, [0.035] * 3)
        await write(self.queue.get_nowait(), stage="playout")
        await flush(stage="end_of_media")
        self.assertEqual(b"".join(self.writer.writes), tail * 2 + successor)
        self.assertEqual(self.writer.hub_tail, b"previous-hub-tail" + tail * 2 + successor)
        self.player.client.run_command.assert_not_called()
        self.player._close_writer_bounded.assert_not_awaited()
        self.player.recover.assert_not_awaited()
        self.assertEqual(pending, b"")

    async def test_producer_eof_exits_without_waiting_or_restart(self):
        gap, write, _, _, _ = self.make()
        await write(b"A" * 4480, stage="playout")
        self.clock.on_sleep = lambda count: self.done.set()
        await gap()
        self.assertEqual(self.clock.sleeps, [0.035])
        self.assertEqual(self.writer.writes, [b"A" * 4480])
        self.player.client.run_command.assert_not_called()

    async def test_existing_five_second_source_failure_remains_a_failure(self):
        gap, _, _, _, _ = self.make()
        with self.assertRaisesRegex(RuntimeError, "PCM source stalled for more than 5.0s"):
            await gap()
        self.assertGreater(self.clock.now - 100.0, 5.0)
        self.assertLessEqual(self.clock.now - 100.0, 5.0351)
        self.player.client.run_command.assert_not_called()

    async def test_producer_error_propagates_into_existing_watcher_recovery(self):
        gap, _, _, _, set_error = self.make()
        self.clock.on_sleep = lambda count: set_error(ConnectionError("source failed"))
        with self.assertRaisesRegex(ConnectionError, "source failed"):
            await gap()

    async def test_manual_stop_new_generation_shutdown_and_new_writer_win(self):
        for reason in ("generation", "process", "shutdown", "writer"):
            with self.subTest(reason=reason):
                self.setUp()
                gap, write, _, _, _ = self.make()
                await write(b"A" * 4480, stage="playout")
                def supersede(count):
                    if reason == "generation": self.generation = 2
                    if reason == "process": self.player._ffmpeg = object()
                    if reason == "shutdown": self.player._shutting_down = True
                    if reason == "writer": self.player._stream_writer = Writer()
                    self.queue.put_nowait(b"stale-successor")
                self.clock.on_sleep = supersede
                await gap()
                self.assertEqual(self.writer.writes, [b"A" * 4480])
                self.assertEqual(self.queue.get_nowait(), b"stale-successor")
                self.player.client.run_command.assert_not_called()

    async def test_cancellation_during_tail_flush_never_enters_gap_wait(self):
        gap, write, _, _, _ = self.make()
        await write(b"A" * 4480, stage="playout")
        async def replace():
            self.generation = 2
        self.writer.drain.side_effect = replace
        await gap()
        self.assertEqual(self.clock.sleeps, [])
        self.player.client.run_command.assert_not_called()

    async def test_real_tcp_failure_keeps_existing_recovery_path(self):
        gap, write, _, _, _ = self.make()
        await write(b"A" * 4480, stage="playout")
        self.writer.closed = True
        self.clock.on_sleep = lambda count: self.done.set()
        await gap()
        self.player.recover.assert_awaited_once()

    async def test_original_radio_branch_reproduces_destructive_tail_clear(self):
        gap, write, _, pending, _ = self.make(cast=False)
        await write(b"A" * 4480, stage="playout")
        rebuffering, stopped, _ = await gap()
        self.assertTrue(rebuffering)
        self.assertTrue(stopped)
        self.assertEqual(pending, b"")
        self.assertEqual(self.writer.hub_tail, b"")
        self.assertEqual(self.writer.writes, [])
        self.player.client.run_command.assert_called_once()
        self.player._close_writer_bounded.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
