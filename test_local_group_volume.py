"""Local group gain never changes the source, sequence, buffers or receiver jobs."""
import asyncio
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_group_cohort_alignment import FakeHass, FakeWriter, module


class LocalGroupVolumeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass = FakeHass()
        self.manager = module.AqaraM1SMediaGroupManager(self.hass)
        self.manager._signal_update = Mock()
        self.manager._generation = 7
        self.manager._sequence = 900
        self.manager.ffmpeg = types.SimpleNamespace(pid=123, returncode=None)
        self.manager.desired_playing = True
        self.players = {}
        self.hass.data[module.DOMAIN] = {module.DATA_RADIO_PLAYERS: self.players}
        self.controls = []
        for name in ("one", "two"):
            player = types.SimpleNamespace(volume=0.05)
            player._effective_gain = lambda p=player: p.volume
            player._update_shared_volume_level = lambda value, p=player: setattr(p, "volume", value)
            self.players[name] = player
            control = types.SimpleNamespace(async_prepare=AsyncMock(), request_gain=Mock())
            self.controls.append(control)
            member = module.GroupMember(name, name, types.SimpleNamespace(host=name),
                types.SimpleNamespace(last_update_success=True), writer=FakeWriter(),
                generation=1, ready_for_fanout=True, shared_cursor=900, local_audio=control)
            self.manager.members[name] = member
        self.dispatch = patch.object(module, "async_dispatcher_send", Mock(), create=True)
        self.signal = patch.object(module, "media_group_volume_signal", lambda: "volume", create=True)
        self.dispatch.start()
        self.signal.start()

    def tearDown(self):
        self.dispatch.stop()
        self.signal.stop()

    async def test_group_slider_updates_canonical_hub_volumes_without_transport_changes(self):
        old_process = self.manager.ffmpeg
        old_writers = [m.writer for m in self.manager.members.values()]
        await self.manager.async_set_volume(0.0123)
        self.assertEqual([p.volume for p in self.players.values()], [0.0123, 0.0123])
        for control in self.controls:
            control.request_gain.assert_called_once_with(0.0123)
        self.assertEqual(self.manager._sequence, 900)
        self.assertEqual(self.manager._generation, 7)
        self.assertIs(self.manager.ffmpeg, old_process)
        self.assertEqual([m.writer for m in self.manager.members.values()], old_writers)
        self.assertTrue(all(m.writer.writes == [] for m in self.manager.members.values()))

    async def test_muting_keeps_pcm_and_receivers_active(self):
        await self.manager.async_set_muted(True)
        for control in self.controls:
            control.request_gain.assert_called_once_with(0.0)
        member = self.manager.members["one"]
        pcm = b"a" * module.CHUNK_BYTES
        self.assertIs(self.manager._member_chunk(member, pcm), pcm)
        self.assertEqual(self.manager._sequence, 900)

    async def test_only_one_member_is_muted(self):
        self.manager.set_member_muted("one", True)
        self.controls[0].request_gain.assert_called_once_with(0.0)
        self.controls[1].request_gain.assert_not_called()

    async def test_late_rejoin_preserves_a_manual_per_hub_volume_override(self):
        await self.manager.async_set_volume(0.02)
        self.players["one"].volume = 0.01
        member = self.manager.members["one"]
        self.manager._sync_member_volume(member)
        self.assertEqual(self.manager._member_local_gain(member), 0.01)

    async def test_group_slider_does_not_overwrite_independent_player(self):
        self.manager.individual_intent.add("one")
        await self.manager.async_set_volume(0.02)
        self.assertEqual(self.players["one"].volume, 0.05)
        self.controls[0].request_gain.assert_not_called()


if __name__ == "__main__":
    unittest.main()
