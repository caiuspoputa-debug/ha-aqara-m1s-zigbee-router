from __future__ import annotations

import asyncio
from pathlib import PurePosixPath
import re

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from .const import (
    DATA_CLIENTS,
    DATA_PLAYBACK_VOLUME,
    DATA_SOUND_PLAYERS,
    DOMAIN,
    sound_list_signal,
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


def sound_button_unique_id(entry_id: str, path: str) -> str:
    return f"{entry_id}_play_{key_for_path(path)}"


def remove_stale_sound_button_registry_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
    wanted_paths: set[str],
    *,
    prune_missing_sound_buttons: bool,
) -> None:
    entity_registry = er.async_get(hass)
    wanted_unique_ids = {
        sound_button_unique_id(entry.entry_id, path) for path in wanted_paths
    }
    obsolete_unique_ids = {
        f"{entry.entry_id}_delete_selected_sound",
        f"{entry.entry_id}_play_selected_sound",
    }
    sound_button_prefix = f"{entry.entry_id}_play_"

    for registry_entry in list(
        er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    ):
        entity_id = registry_entry.entity_id
        unique_id = str(registry_entry.unique_id or "")
        if not entity_id.startswith("button."):
            continue
        if registry_entry.platform != DOMAIN:
            continue

        obsolete = unique_id in obsolete_unique_ids
        missing_sound = (
            prune_missing_sound_buttons
            and unique_id.startswith(sound_button_prefix)
            and unique_id not in wanted_unique_ids
        )
        if obsolete or missing_sound:
            entity_registry.async_remove(entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_PLAYBACK_VOLUME, {})
    hass.data[DOMAIN][DATA_PLAYBACK_VOLUME].setdefault(entry.entry_id, 50)

    client = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    listed_sounds: list[str] | None
    try:
        listed_sounds = await hass.async_add_executor_job(client.list_sounds)
    except (OSError, RuntimeError, TimeoutError):
        listed_sounds = None
        sounds = FALLBACK_SOUNDS
    else:
        sounds = listed_sounds or FALLBACK_SOUNDS

    remove_stale_sound_button_registry_entries(
        hass,
        entry,
        set(sounds),
        prune_missing_sound_buttons=listed_sounds is not None,
    )

    sound_buttons = {
        path: AqaraM1SSoundButton(hass, entry, client, path)
        for path in sounds
    }
    entities = [
        AqaraM1SRefreshSoundsButton(
            hass,
            entry,
            client,
            async_add_entities,
            sound_buttons,
        ),
    ]
    entities += list(sound_buttons.values())
    async_add_entities(entities)


class AqaraM1SSoundButton(ButtonEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client, path: str) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.path = path
        self._attr_name = label_for_path(path)
        self._attr_unique_id = sound_button_unique_id(entry.entry_id, path)
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


class AqaraM1SRefreshSoundsButton(ButtonEntity):
    _attr_name = "Refresh Sound List"
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client,
        async_add_entities: AddEntitiesCallback,
        sound_buttons: dict[str, AqaraM1SSoundButton],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self._async_add_entities = async_add_entities
        self._sound_buttons = sound_buttons
        self._refresh_lock = asyncio.Lock()
        self._attr_unique_id = f"{entry.entry_id}_refresh_sounds"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.host)},
            "name": entry.data.get("name", f"Aqara M1S Router {client.host}"),
            "manufacturer": "Aqara",
            "model": "M1S Gen 1 / JN5189 Router",
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                sound_list_signal(self.entry.entry_id),
                self._schedule_sound_refresh,
            )
        )

    def _schedule_sound_refresh(self) -> None:
        self.hass.async_create_task(self._async_refresh_sound_buttons())

    async def _async_refresh_sound_buttons(self) -> None:
        async with self._refresh_lock:
            listed_sounds: list[str] | None
            try:
                listed_sounds = await self.hass.async_add_executor_job(
                    self.client.list_sounds
                )
            except (OSError, RuntimeError, TimeoutError):
                return
            else:
                sounds = listed_sounds or FALLBACK_SOUNDS
            wanted = set(sounds)
            current = set(self._sound_buttons)

            for path in current - wanted:
                entity = self._sound_buttons.pop(path)
                await entity.async_remove()

            remove_stale_sound_button_registry_entries(
                self.hass,
                self.entry,
                wanted,
                prune_missing_sound_buttons=listed_sounds is not None,
            )

            additions = []
            for path in sorted(wanted - current):
                entity = AqaraM1SSoundButton(
                    self.hass,
                    self.entry,
                    self.client,
                    path,
                )
                self._sound_buttons[path] = entity
                additions.append(entity)
            if additions:
                self._async_add_entities(additions)

    async def async_press(self) -> None:
        async_dispatcher_send(
            self.hass,
            sound_list_signal(self.entry.entry_id),
        )
