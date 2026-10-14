from __future__ import annotations

import asyncio
import logging
from pathlib import PurePosixPath
import re

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
)

from .const import (
    DATA_CLIENTS,
    DATA_COORDINATORS,
    DATA_PLAYBACK_VOLUME,
    DATA_SOUND_PLAYERS,
    DOMAIN,
    sound_list_signal,
)
from .device import device_info

_LOGGER = logging.getLogger(__name__)

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
    coordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    initially_online = coordinator.last_update_success
    listed_sounds: list[str] | None
    if initially_online:
        try:
            listed_sounds = await hass.async_add_executor_job(client.list_sounds)
        except (OSError, RuntimeError, TimeoutError):
            listed_sounds = None
            sounds = FALLBACK_SOUNDS
        else:
            sounds = listed_sounds
    else:
        # Do not block platform setup with Telnet retries while the hub is off.
        listed_sounds = None
        sounds = FALLBACK_SOUNDS

    remove_stale_sound_button_registry_entries(
        hass,
        entry,
        set(sounds),
        prune_missing_sound_buttons=listed_sounds is not None,
    )

    sound_buttons = {
        path: AqaraM1SSoundButton(hass, entry, client, coordinator, path)
        for path in sounds
    }
    # v0.30.0: preserve the v0.21.15 behavior. Upload/delete already reload
    # the config entry automatically, so the manual Refresh Sound List entity
    # is redundant. Remove an older registry entry if it still exists.
    entity_registry = er.async_get(hass)
    refresh_entity_id = entity_registry.async_get_entity_id(
        "button", DOMAIN, f"{entry.entry_id}_refresh_sounds"
    )
    if refresh_entity_id is not None:
        entity_registry.async_remove(refresh_entity_id)

    async_add_entities(list(sound_buttons.values()))
    inventory = AqaraM1SSoundInventory(
        hass, entry, client, coordinator, async_add_entities, sound_buttons,
        initially_online=initially_online,
        needs_refresh=listed_sounds is None,
    )
    inventory.start()
    entry.async_on_unload(inventory.close)


class AqaraM1SSoundButton(CoordinatorEntity, ButtonEntity):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client, coordinator, path: str
    ) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.client = client
        self.path = path
        self._attr_name = label_for_path(path)
        self._attr_unique_id = sound_button_unique_id(entry.entry_id, path)
        self._attr_extra_state_attributes = {
            "file_path": path,
            "playback_route": "hub_local_aplay",
            "respects_playback_volume": True,
            "light_effect": False,
        }
        self._attr_device_info = device_info(entry)

    async def async_press(self) -> None:
        volume = self.hass.data[DOMAIN][DATA_PLAYBACK_VOLUME].get(
            self.entry.entry_id, 50
        )
        player = self.hass.data[DOMAIN][DATA_SOUND_PLAYERS][self.entry.entry_id]
        await player.async_play(self.path, volume)


class AqaraM1SSoundInventory:
    """Keep sound entities current without adding a manual refresh button."""
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client,
        coordinator,
        async_add_entities: AddEntitiesCallback,
        sound_buttons: dict[str, AqaraM1SSoundButton],
        *,
        initially_online: bool,
        needs_refresh: bool,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.coordinator = coordinator
        self._async_add_entities = async_add_entities
        self._sound_buttons = sound_buttons
        self._was_online = initially_online
        self._needs_refresh = needs_refresh
        self._task: asyncio.Task | None = None
        self._unsubscribers = []
        self._closed = False

    def start(self) -> None:
        self._unsubscribers.append(
            async_dispatcher_connect(
                self.hass,
                sound_list_signal(self.entry.entry_id),
                self._schedule_sound_refresh,
            )
        )
        self._unsubscribers.append(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        self._handle_coordinator_update()

    @callback
    def close(self) -> None:
        self._closed = True
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        if self._task is not None:
            self._task.cancel()

    @callback
    def _handle_coordinator_update(self) -> None:
        online = self.coordinator.last_update_success
        if online and (not self._was_online or self._needs_refresh):
            self._schedule_sound_refresh()
        self._was_online = online

    @callback
    def _schedule_sound_refresh(self) -> None:
        if self._closed:
            return
        self._needs_refresh = True
        if self.coordinator.last_update_success and self._task is None:
            self._task = self.entry.async_create_background_task(
                self.hass, self._async_refresh_sound_buttons(),
                name=f"M1S {self.entry.entry_id} sound inventory",
                eager_start=False,
            )

    async def _async_refresh_sound_buttons(self) -> None:
        try:
            while self._needs_refresh and not self._closed:
                if not self.coordinator.last_update_success:
                    return
                self._needs_refresh = False
                try:
                    sounds = await self.hass.async_add_executor_job(self.client.list_sounds)
                except (OSError, RuntimeError, TimeoutError) as err:
                    # Keep existing buttons. Retry on a later coordinator update.
                    self._needs_refresh = True
                    _LOGGER.debug("M1S sound inventory refresh failed: %s", err)
                    return
                if self._closed or not self.coordinator.last_update_success:
                    self._needs_refresh = True
                    return

                wanted = set(sounds)
                current = set(self._sound_buttons)
                for path in current - wanted:
                    entity = self._sound_buttons[path]
                    await entity.async_remove()
                    del self._sound_buttons[path]

                remove_stale_sound_button_registry_entries(
                    self.hass, self.entry, wanted, prune_missing_sound_buttons=True,
                )

                additions = []
                for path in sorted(wanted - current):
                    entity = AqaraM1SSoundButton(
                        self.hass, self.entry, self.client, self.coordinator, path,
                    )
                    self._sound_buttons[path] = entity
                    additions.append(entity)
                if additions:
                    self._async_add_entities(additions)
        finally:
            self._task = None
