from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DATA_COORDINATORS, DATA_RADIO_PLAYERS, DOMAIN, MEDIA_GROUP_ID, media_group_signal

_LOGGER = logging.getLogger(__name__)


class AqaraM1SMediaGroupManager:
    """Shared dynamic membership and command fan-out for all configured hubs."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.selected: set[str] = set()
        self.entity: AqaraM1SMediaGroup | None = None

    def set_selected(self, entry_id: str, selected: bool) -> None:
        if selected:
            self.selected.add(entry_id)
        else:
            self.selected.discard(entry_id)
        async_dispatcher_send(self.hass, media_group_signal())

    def players(self, *, available_only: bool = False) -> list[Any]:
        domain_data = self.hass.data.get(DOMAIN, {})
        players = domain_data.get(DATA_RADIO_PLAYERS, {})
        coordinators = domain_data.get(DATA_COORDINATORS, {})
        result = []
        for entry_id in tuple(self.selected):
            player = players.get(entry_id)
            if player is None:
                continue
            if available_only:
                coordinator = coordinators.get(entry_id)
                if coordinator is None or not coordinator.last_update_success:
                    continue
            result.append(player)
        return result

    async def run_selected(self, method: str, *args: Any, available_only: bool = True, **kwargs: Any) -> int:
        players = self.players(available_only=available_only)
        if not players:
            return 0
        results = await asyncio.gather(
            *(getattr(player, method)(*args, **kwargs) for player in players),
            return_exceptions=True,
        )
        ok = 0
        for player, result in zip(players, results):
            if isinstance(result, Exception):
                _LOGGER.warning(
                    "Media group skipped hub %s during %s: %s",
                    player.client.host,
                    method,
                    result,
                )
            else:
                ok += 1
        return ok

    async def async_member_enabled(self, entry_id: str) -> None:
        self.set_selected(entry_id, True)
        entity = self.entity
        if entity is None or entity.state != MediaPlayerState.PLAYING:
            return
        player = self.hass.data.get(DOMAIN, {}).get(DATA_RADIO_PLAYERS, {}).get(entry_id)
        coordinator = self.hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {}).get(entry_id)
        if player is None or coordinator is None or not coordinator.last_update_success:
            return
        try:
            await player.async_set_volume_level(entity.volume_level or 0.0)
            if entity.last_media_id:
                await player.async_play_media(
                    entity.last_media_type,
                    entity.last_media_id,
                    extra={"title": entity.media_title},
                )
            else:
                await player.async_media_play()
        except Exception as err:
            _LOGGER.warning("Could not add hub %s to active media group: %s", player.client.host, err)

    async def async_member_disabled(self, entry_id: str) -> None:
        player = self.hass.data.get(DOMAIN, {}).get(DATA_RADIO_PLAYERS, {}).get(entry_id)
        self.set_selected(entry_id, False)
        if player is not None:
            try:
                await player.async_media_stop()
            except Exception as err:
                _LOGGER.warning("Could not stop removed group member %s: %s", player.client.host, err)


class AqaraM1SMediaGroup(MediaPlayerEntity, RestoreEntity):
    """One resilient media-player entity controlling selected M1S hubs."""

    _attr_name = "M1S Media Group"
    _attr_unique_id = MEDIA_GROUP_ID
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_should_poll = True
    _attr_volume_step = 0.001
    _attr_supported_features = (
        MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(self, hass: HomeAssistant, manager: AqaraM1SMediaGroupManager) -> None:
        self.hass = hass
        self.manager = manager
        manager.entity = self
        self._attr_state = MediaPlayerState.IDLE
        self._attr_volume_level = 0.05
        self._attr_is_volume_muted = False
        self._attr_media_content_type = MediaType.MUSIC
        self._attr_media_title = None
        self.last_media_id: str | None = None
        self.last_media_type: str = MediaType.MUSIC

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last:
            attrs = last.attributes
            try:
                self._attr_volume_level = max(0.0, min(1.0, float(attrs.get("volume_level", 0.05))))
            except (TypeError, ValueError):
                pass
            self._attr_is_volume_muted = bool(attrs.get("is_volume_muted", False))
            self.last_media_id = attrs.get("last_media_id") or attrs.get("media_content_id")
            self.last_media_type = attrs.get("last_media_type") or attrs.get("media_content_type") or MediaType.MUSIC
            self._attr_media_content_id = self.last_media_id
            self._attr_media_content_type = self.last_media_type
            self._attr_media_title = attrs.get("last_media_title") or attrs.get("media_title")
        self.async_on_remove(async_dispatcher_connect(self.hass, media_group_signal(), self._schedule_refresh))
        await self.async_update()

    def _schedule_refresh(self) -> None:
        self.schedule_update_ha_state(force_refresh=True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        selected = []
        offline = []
        domain_data = self.hass.data.get(DOMAIN, {})
        players = domain_data.get(DATA_RADIO_PLAYERS, {})
        coordinators = domain_data.get(DATA_COORDINATORS, {})
        for entry_id in sorted(self.manager.selected):
            player = players.get(entry_id)
            if player is None:
                continue
            selected.append(player.client.host)
            coordinator = coordinators.get(entry_id)
            if coordinator is None or not coordinator.last_update_success:
                offline.append(player.client.host)
        return {
            "selected_hubs": selected,
            "offline_hubs_skipped": offline,
            "last_media_id": self.last_media_id,
            "last_media_type": self.last_media_type,
            "last_media_title": self._attr_media_title,
            "volume_level": self._attr_volume_level,
            "is_volume_muted": self._attr_is_volume_muted,
        }

    @property
    def available(self) -> bool:
        return bool(self.manager.players(available_only=True))

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ):
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def async_update(self) -> None:
        players = self.manager.players(available_only=True)
        if any(player.state == MediaPlayerState.PLAYING for player in players):
            self._attr_state = MediaPlayerState.PLAYING
        elif players:
            self._attr_state = MediaPlayerState.IDLE
        else:
            self._attr_state = MediaPlayerState.IDLE

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        self.last_media_id = media_id
        self.last_media_type = media_type or MediaType.MUSIC
        self._attr_media_content_id = media_id
        self._attr_media_content_type = self.last_media_type
        extra = kwargs.get("extra") or {}
        if isinstance(extra, dict) and extra.get("title"):
            self._attr_media_title = extra["title"]
        ok = await self.manager.run_selected(
            "async_play_media",
            self.last_media_type,
            media_id,
            available_only=True,
            **kwargs,
        )
        self._attr_state = MediaPlayerState.PLAYING if ok else MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def async_media_play(self) -> None:
        if self.last_media_id:
            await self.async_play_media(
                self.last_media_type,
                self.last_media_id,
                extra={"title": self._attr_media_title},
            )
            return
        ok = await self.manager.run_selected("async_media_play", available_only=True)
        self._attr_state = MediaPlayerState.PLAYING if ok else MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def async_media_stop(self) -> None:
        await self.manager.run_selected("async_media_stop", available_only=False)
        self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        await self.async_media_stop()

    @staticmethod
    def _normalize_volume(volume: float) -> float:
        volume = max(0.0, min(1.0, float(volume)))
        if volume <= 0.04:
            return round(volume * 1000.0) / 1000.0
        return round(volume * 100.0) / 100.0

    async def async_set_volume_level(self, volume: float) -> None:
        volume = self._normalize_volume(volume)
        self._attr_volume_level = volume
        self._attr_is_volume_muted = volume == 0.0
        await self.manager.run_selected("async_set_volume_level", volume, available_only=True)
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, media_group_signal())

    async def async_volume_up(self) -> None:
        current = self._attr_volume_level or 0.0
        await self.async_set_volume_level(current + (0.001 if current < 0.04 else 0.01))

    async def async_volume_down(self) -> None:
        current = self._attr_volume_level or 0.0
        await self.async_set_volume_level(current - (0.001 if current <= 0.04 else 0.01))

    async def async_mute_volume(self, mute: bool) -> None:
        self._attr_is_volume_muted = bool(mute)
        await self.manager.run_selected("async_mute_volume", bool(mute), available_only=True)
        self.async_write_ha_state()
