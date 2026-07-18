from __future__ import annotations

from pathlib import PurePosixPath
import re

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import (
    DATA_CLIENTS,
    DATA_PLAYBACK_VOLUME,
    DATA_SELECTED_SOUND,
    DATA_SOUND_PLAYERS,
    DOMAIN,
)

FALLBACK_SOUNDS = [
    "/data/musics/music-scene/door_bell_1.wav",
    "/data/musics/music-scene/alarm.wav",
    "/data/musics/music-scene/arm_ok.wav",
    "/data/musics/music-scene/disarm.wav",
]


def label_for_path(path: str) -> str:
    p = PurePosixPath(path)
    parent = p.parent.name.replace("music-", "").replace("_", " ").title()
    name = p.stem.replace("_", " ").replace("-", " ").title()
    return f"Play {parent} {name}"


def key_for_path(path: str) -> str:
    key = path.replace("/data/musics/", "").replace("/", "_").replace(".", "_")
    return re.sub(r"[^a-zA-Z0-9_]+", "_", key).lower()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_PLAYBACK_VOLUME, {})
    hass.data[DOMAIN][DATA_PLAYBACK_VOLUME].setdefault(entry.entry_id, 50)

    client = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    sounds = await hass.async_add_executor_job(client.list_sounds)
    if not sounds:
        sounds = FALLBACK_SOUNDS

    entities = [
        AqaraM1SSelectedSoundButton(hass, entry, client),
        AqaraM1SDeleteSelectedSoundButton(hass, entry, client),
        AqaraM1SRefreshSoundsButton(hass, entry, client),
    ]
    entities += [AqaraM1SSoundButton(hass, entry, client, path) for path in sounds]
    async_add_entities(entities)


class AqaraM1SSelectedSoundButton(ButtonEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self._attr_name = "Play Selected Sound"
        self._attr_unique_id = f"{entry.entry_id}_play_selected_sound"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.client.host)},
            "name": entry.data.get("name", f"Aqara M1S {self.client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_press(self) -> None:
        path = self.hass.data[DOMAIN][DATA_SELECTED_SOUND].get(self.entry.entry_id)
        if not path:
            return
        volume = self.hass.data[DOMAIN][DATA_PLAYBACK_VOLUME].get(
            self.entry.entry_id, 50
        )
        player = self.hass.data[DOMAIN][DATA_SOUND_PLAYERS][self.entry.entry_id]
        await player.async_play(path, volume)


class AqaraM1SSoundButton(ButtonEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client, path: str) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.path = path
        self._attr_name = label_for_path(path)
        self._attr_unique_id = f"{entry.entry_id}_play_{key_for_path(path)}"
        self._attr_extra_state_attributes = {
            "file_path": path,
            "playback_route": "ffmpeg_to_aplay",
            "respects_playback_volume": True,
            "light_effect": False,
        }
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.client.host)},
            "name": entry.data.get("name", f"Aqara M1S {self.client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_press(self) -> None:
        volume = self.hass.data[DOMAIN][DATA_PLAYBACK_VOLUME].get(
            self.entry.entry_id, 50
        )
        player = self.hass.data[DOMAIN][DATA_SOUND_PLAYERS][self.entry.entry_id]
        await player.async_play(self.path, volume)


class AqaraM1SDeleteSelectedSoundButton(ButtonEntity):
    _attr_name = "Delete Selected Sound"
    _attr_icon = "mdi:file-remove"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self._attr_unique_id = f"{entry.entry_id}_delete_selected_sound"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.host)},
            "name": entry.data.get("name", f"Aqara M1S Router {client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_press(self) -> None:
        path = self.hass.data[DOMAIN][DATA_SELECTED_SOUND].get(self.entry.entry_id)
        if not path:
            return
        await self.hass.async_add_executor_job(self.client.delete_sound, path)
        await self.hass.config_entries.async_reload(self.entry.entry_id)


class AqaraM1SRefreshSoundsButton(ButtonEntity):
    _attr_name = "Refresh Sound List"
    _attr_icon = "mdi:refresh"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_refresh_sounds"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.host)},
            "name": entry.data.get("name", f"Aqara M1S Router {client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_press(self) -> None:
        await self.hass.config_entries.async_reload(self.entry.entry_id)
