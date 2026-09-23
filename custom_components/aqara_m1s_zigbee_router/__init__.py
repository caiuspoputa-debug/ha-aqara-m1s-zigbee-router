from __future__ import annotations

import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import AqaraM1SClient
from .const import (
    CONF_BUTTON_TOPIC_ID,
    CONF_DEVICE_MAC,
    DATA_CLIENTS,
    DATA_COORDINATORS,
    DATA_PLAYBACK_VOLUME,
    DATA_RADIO_PLAYERS,
    DATA_MEDIA_GROUP,
    DATA_SOUND_PLAYERS,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DOMAIN,
    SERVICE_PLAY_SOUND,
    SERVICE_PLAY_URL,
    SERVICE_RUN_COMMAND,
    SERVICE_UPLOAD_SOUND,
    SERVICE_DELETE_SOUND,
    SERVICE_REFRESH_SOUNDS,
    SERVICE_RESET_MEDIA_GROUP,
    SERVICE_RESYNC_MEDIA_GROUP,
    SERVICE_UPDATE_MEDIA_METADATA,
    sound_list_signal,
)
from .device import device_identifier, entry_title_with_host
from .coordinator import AqaraM1SRouterCoordinator
from .media_group import AqaraM1SMediaGroupManager
from .media_player import AqaraM1SRadioPlayer
from .sound_player import AqaraM1SSoundPlayer
from .sound_upload import destination_for_filename, read_uploaded_sound

PLATFORMS = [
    "binary_sensor",
    "button",
    "event",
    "light",
    "media_player",
    "number",
    "sensor",
    "switch",
]


_OFFLINE_SUFFIXES = (" (🔴 Indisponibil)", " (Indisponibil)")
_TRAILING_IPV4_RE = re.compile(r"\s+-\s+(?:\d{1,3}\.){3}\d{1,3}$")


def _split_availability_suffix(name: str) -> tuple[str, str]:
    value = str(name).strip()
    for suffix in _OFFLINE_SUFFIXES:
        if value.endswith(suffix):
            return value[: -len(suffix)].rstrip(), suffix
    return value, ""


def _remove_trailing_ip(name: str) -> str:
    """Remove only an IP previously appended by this integration."""
    base_name, suffix = _split_availability_suffix(name)
    base_name = _TRAILING_IPV4_RE.sub("", base_name).rstrip()
    return f"{base_name}{suffix}"


def _device_name_with_host(name: str, host: str) -> str:
    """Keep the friendly name while appending exactly one hub IPv4 address."""
    base_name, suffix = _split_availability_suffix(name)
    base_name = _TRAILING_IPV4_RE.sub("", base_name).rstrip()
    base_name = base_name or "Aqara M1S Zigbee Router"
    return f"{base_name} - {host}{suffix}" if host else f"{base_name}{suffix}"


def _parse_wifi_ipv4(text: str) -> str | None:
    for address in re.findall(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", text):
        if not address.startswith("127.") and all(
            0 <= int(part) <= 255 for part in address.split(".")
        ):
            return address
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    username = entry.data.get(
        CONF_USERNAME,
        DEFAULT_USERNAME,
    )
    password = entry.data.get(
        CONF_PASSWORD,
        DEFAULT_PASSWORD,
    )

    # Prefix titles with the real address so the integration entries are shown
    # in IP order. The device row separately keeps the friendly "name - IP".
    sorted_entry_title = entry_title_with_host(
        entry.data.get("name", entry.title), host
    )
    if sorted_entry_title != entry.title:
        hass.config_entries.async_update_entry(entry, title=sorted_entry_title)

    client = AqaraM1SClient(
        host=host,
        port=port,
        username=username,
        password=password,
    )
    try:
        network_status = await hass.async_add_executor_job(client.network_status)
    except Exception:
        network_status = None
    if network_status is not None:
        # v0.21.15: only migrate the physical-button watcher timing. Failures
        # here must never block the rest of the integration from loading.
        try:
            await hass.async_add_executor_job(client.ensure_fast_button_polling)
        except Exception:
            pass

        updated_data = dict(entry.data)
        updated_data[CONF_DEVICE_MAC] = network_status["wifi_mac"]
        updated_data[CONF_BUTTON_TOPIC_ID] = network_status.get("button_topic_id", "")
        if updated_data != dict(entry.data) or entry.unique_id != f"mac:{network_status['wifi_mac']}":
            hass.config_entries.async_update_entry(
                entry,
                data=updated_data,
                unique_id=f"mac:{network_status['wifi_mac']}",
            )
    coordinator = AqaraM1SRouterCoordinator(hass, client, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_CLIENTS, {})
    hass.data[DOMAIN].setdefault(
        DATA_COORDINATORS,
        {},
    )
    hass.data[DOMAIN].setdefault(
        DATA_PLAYBACK_VOLUME,
        {},
    )
    hass.data[DOMAIN].setdefault(
        DATA_RADIO_PLAYERS,
        {},
    )
    hass.data[DOMAIN].setdefault(
        DATA_SOUND_PLAYERS,
        {},
    )
    if DATA_MEDIA_GROUP not in hass.data[DOMAIN]:
        hass.data[DOMAIN][DATA_MEDIA_GROUP] = AqaraM1SMediaGroupManager(hass)

    hass.data[DOMAIN][DATA_CLIENTS][
        entry.entry_id
    ] = client
    hass.data[DOMAIN][DATA_COORDINATORS][
        entry.entry_id
    ] = coordinator
    hass.data[DOMAIN][DATA_PLAYBACK_VOLUME][
        entry.entry_id
    ] = 50
    radio_player = AqaraM1SRadioPlayer(
        hass, entry, client, coordinator
    )
    hass.data[DOMAIN][DATA_RADIO_PLAYERS][entry.entry_id] = radio_player
    group_manager = hass.data[DOMAIN][DATA_MEDIA_GROUP]
    group_manager.register_member(
        entry.entry_id,
        entry.data.get("name", f"Aqara M1S {host}"),
        client,
        coordinator,
    )
    radio_player.set_group_manager(group_manager)
    hass.data[DOMAIN][DATA_SOUND_PLAYERS][entry.entry_id] = AqaraM1SSoundPlayer(
        hass, client, entry.entry_id, radio_player, group_manager
    )

    device_registry = dr.async_get(hass)
    stable_identifier = device_identifier(entry)
    legacy_device = device_registry.async_get_device(identifiers={(DOMAIN, host)})
    stable_device = device_registry.async_get_device(identifiers={stable_identifier})
    if (
        legacy_device is not None
        and stable_identifier not in legacy_device.identifiers
        and stable_device is None
    ):
        device_registry.async_update_device(
            legacy_device.id,
            new_identifiers={stable_identifier},
        )
    device_name = _device_name_with_host(
        entry.data.get("name", f"Aqara M1S Router {host}"),
        host,
    )
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={stable_identifier},
        name=device_name,
        manufacturer="Aqara",
        model="M1S Gen 1 / JN5189 Router",
    )
    device_updates = {}
    if device.name != device_name:
        device_updates["name"] = device_name
    if device.name_by_user:
        visible_name = _device_name_with_host(device.name_by_user, host)
        if device.name_by_user != visible_name:
            device_updates["name_by_user"] = visible_name
    if device_updates:
        device_registry.async_update_device(device.id, **device_updates)

    entity_registry = er.async_get(hass)

    # Clean up old IP-based device-registry rows that can remain after the hub
    # has already moved to its stable MAC identifier. Preserve any entities by
    # moving them to the canonical MAC device before removing the stale device.
    for legacy_entry in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        if legacy_entry.id == device.id:
            continue
        domain_identifiers = {
            identifier
            for identifier in legacy_entry.identifiers
            if identifier[0] == DOMAIN
        }
        if not domain_identifiers or not all(
            _parse_wifi_ipv4(identifier[1]) == identifier[1]
            for identifier in domain_identifiers
        ):
            continue
        for entity_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            if entity_entry.device_id == legacy_entry.id:
                entity_registry.async_update_entity(
                    entity_entry.entity_id, device_id=device.id
                )
        device_registry.async_remove_device(legacy_entry.id)

    obsolete_select_id = entity_registry.async_get_entity_id(
        "select",
        DOMAIN,
        f"{entry.entry_id}_sound_select",
    )
    if obsolete_select_id is not None:
        entity_registry.async_remove(obsolete_select_id)

    # Remove the legacy absolute fine-volume Number entities from v0.5.0-v0.5.5.
    # v0.5.9 reintroduces only an individual *trim* control with a new unique ID
    # (*_radio_fine_trim), so the old entity must not be revived accidentally.
    obsolete_number_unique_ids = (
        f"{entry.entry_id}_radio_fine_volume",
        "aqara_m1s_media_group_fine_volume",
    )
    for unique_id in obsolete_number_unique_ids:
        obsolete_number_id = entity_registry.async_get_entity_id(
            "number", DOMAIN, unique_id
        )
        if obsolete_number_id is not None:
            entity_registry.async_remove(obsolete_number_id)

    # This integration is intentionally allowed to load while the physical hub
    # is offline.  async_config_entry_first_refresh() would raise
    # ConfigEntryNotReady and move reconnect handling into Home Assistant's
    # setup retry/backoff, which makes a hub powered on later appear only after
    # a long delay or a manual Reload.  A normal refresh records the initial
    # availability state without aborting the config entry setup.
    await coordinator.async_refresh()
    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    # Entity platforms can write their plain device_info name during setup.
    # Re-apply one live wlan0 IP after all platforms are loaded; the integration
    # title above deliberately stays without an IP.
    visible_ip = host
    if coordinator.last_update_success:
        try:
            wifi_output = await hass.async_add_executor_job(
                client.run_command,
                "ifconfig wlan0 | grep 'inet addr'",
            )
            visible_ip = _parse_wifi_ipv4(wifi_output) or host
        except Exception:
            visible_ip = host

    device = device_registry.async_get_device(identifiers={stable_identifier})
    if device is not None:
        device_updates = {}
        desired_name = _device_name_with_host(
            entry.data.get("name", f"Aqara M1S Router {host}"),
            visible_ip,
        )
        if device.name != desired_name:
            device_updates["name"] = desired_name
        if device.name_by_user:
            desired_user_name = _device_name_with_host(
                device.name_by_user, visible_ip
            )
            if device.name_by_user != desired_user_name:
                device_updates["name_by_user"] = desired_user_name
        if device_updates:
            device_registry.async_update_device(device.id, **device_updates)

    # Run an explicit connectivity watchdog that is independent of coordinator
    # listeners.  This guarantees power-off detection and automatic recovery
    # after a cold boot without requiring an integration Reload.
    coordinator.async_start_watchdog()

    async def _get_target(
        call: ServiceCall,
    ) -> tuple[str, AqaraM1SClient]:
        call_host = call.data.get("host")
        if call_host:
            for configured_entry_id, configured_client in hass.data[
                DOMAIN
            ][DATA_CLIENTS].items():
                if configured_client.host == call_host:
                    return configured_entry_id, configured_client
            return entry.entry_id, AqaraM1SClient(
                host=call_host,
                port=call.data.get(
                    "port",
                    DEFAULT_PORT,
                ),
                username=call.data.get(
                    "username",
                    DEFAULT_USERNAME,
                ),
                password=call.data.get(
                    "password",
                    DEFAULT_PASSWORD,
                ),
            )
        return entry.entry_id, hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]

    async def play_url(call: ServiceCall) -> None:
        selected_entry_id, selected_client = await _get_target(call)
        url = call.data["url"]
        sound_player = hass.data[DOMAIN][DATA_SOUND_PLAYERS].get(selected_entry_id)
        if sound_player is not None:
            await sound_player.async_play_url(url)
            return
        # Fallback for an ad-hoc host that is not a configured integration entry.
        command = (
            f'wget -q "{url}" '
            "-O /tmp/ha_audio.wav "
            "&& (aplay -x 1 /tmp/ha_audio.wav & "
            "APID=$!; renice -3 -p \"$APID\" "
            ">/tmp/aqara_m1s_play_url_aplay_renice.log 2>&1 || true; "
            "wait \"$APID\")"
        )
        await hass.async_add_executor_job(selected_client.run_command, command)

    async def play_sound(
        call: ServiceCall,
    ) -> None:
        selected_entry_id, selected_client = await _get_target(call)
        path = call.data["path"]
        sound_player = hass.data[DOMAIN][DATA_SOUND_PLAYERS][selected_entry_id]
        await sound_player.async_play(
            path,
            hass.data[DOMAIN][DATA_PLAYBACK_VOLUME].get(selected_entry_id, 50),
        )

    async def run_command(
        call: ServiceCall,
    ) -> None:
        _, selected_client = await _get_target(call)
        await hass.async_add_executor_job(
            selected_client.run_command,
            call.data["command"],
        )

    async def upload_sound(call: ServiceCall) -> None:
        selected_entry_id, selected_client = await _get_target(call)
        source = call.data["source"]
        filename, content = await hass.async_add_executor_job(
            read_uploaded_sound, hass, source
        )
        destination = destination_for_filename(filename)
        await hass.async_add_executor_job(
            selected_client.upload_sound, destination, content
        )
        async_dispatcher_send(hass, sound_list_signal(selected_entry_id))

    async def delete_sound(call: ServiceCall) -> None:
        selected_entry_id, selected_client = await _get_target(call)
        await hass.async_add_executor_job(
            selected_client.delete_sound, call.data["path"]
        )
        async_dispatcher_send(hass, sound_list_signal(selected_entry_id))

    async def refresh_sounds(call: ServiceCall) -> None:
        selected_entry_id, _ = await _get_target(call)
        async_dispatcher_send(hass, sound_list_signal(selected_entry_id))

    async def reset_media_group(call: ServiceCall) -> None:
        """Hard-reset only the shared M1S group audio transport."""
        group_manager = hass.data[DOMAIN].get(DATA_MEDIA_GROUP)
        if group_manager is not None:
            await group_manager.async_force_reset(reason="service_reset")

    async def resync_media_group(call: ServiceCall) -> None:
        """Manually realign the shared M1S group audio transport."""
        group_manager = hass.data[DOMAIN].get(DATA_MEDIA_GROUP)
        if group_manager is not None:
            await group_manager.async_manual_resync(reason="service_resync")

    async def update_media_metadata(call: ServiceCall) -> None:
        """Update display metadata for the exact active stream, without transport commands."""
        entity_id = str(call.data.get("entity_id") or "").strip()
        expected_media_id = str(call.data.get("expected_media_content_id") or "").strip()
        title = call.data.get("title")
        artist = call.data.get("artist")
        channel = call.data.get("channel")
        if not entity_id or not expected_media_id:
            return

        group_manager = hass.data[DOMAIN].get(DATA_MEDIA_GROUP)
        group_entity = getattr(group_manager, "entity", None)
        if group_entity is not None and entity_id == group_entity.entity_id:
            group_manager.update_external_metadata(
                expected_media_id, title, artist, channel
            )
            return

        for player in hass.data[DOMAIN].get(DATA_RADIO_PLAYERS, {}).values():
            if entity_id == player.entity_id:
                player.update_external_metadata(
                    expected_media_id, title, artist, channel
                )
                return

    if not hass.services.has_service(DOMAIN, SERVICE_PLAY_URL):
        hass.services.async_register(DOMAIN, SERVICE_PLAY_URL, play_url)
        hass.services.async_register(DOMAIN, SERVICE_PLAY_SOUND, play_sound)
        hass.services.async_register(DOMAIN, SERVICE_RUN_COMMAND, run_command)
        hass.services.async_register(DOMAIN, SERVICE_UPLOAD_SOUND, upload_sound)
        hass.services.async_register(DOMAIN, SERVICE_DELETE_SOUND, delete_sound)
        hass.services.async_register(DOMAIN, SERVICE_REFRESH_SOUNDS, refresh_sounds)
        hass.services.async_register(DOMAIN, SERVICE_RESET_MEDIA_GROUP, reset_media_group)
        hass.services.async_register(DOMAIN, SERVICE_RESYNC_MEDIA_GROUP, resync_media_group)
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_MEDIA_METADATA):
        hass.services.async_register(
            DOMAIN, SERVICE_UPDATE_MEDIA_METADATA, update_media_metadata
        )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    unloaded = (
        await hass.config_entries.async_unload_platforms(
            entry,
            PLATFORMS,
        )
    )
    if not unloaded:
        return False

    group_manager = hass.data[DOMAIN].get(DATA_MEDIA_GROUP)
    if group_manager is not None:
        await group_manager.unregister_member(entry.entry_id)
        if not group_manager.members:
            await group_manager.async_shutdown()
            hass.data[DOMAIN].pop(DATA_MEDIA_GROUP, None)

    coordinator = hass.data[DOMAIN][DATA_COORDINATORS].pop(
        entry.entry_id, None
    )
    if coordinator is not None:
        await coordinator.async_shutdown()

    hass.data[DOMAIN][DATA_RADIO_PLAYERS].pop(entry.entry_id, None)

    sound_player = hass.data[DOMAIN][DATA_SOUND_PLAYERS].pop(
        entry.entry_id,
        None,
    )
    if sound_player:
        await sound_player.async_stop()

    telnet_client = hass.data[DOMAIN][DATA_CLIENTS].pop(
        entry.entry_id,
        None,
    )
    if telnet_client:
        await hass.async_add_executor_job(telnet_client.close)
    hass.data[DOMAIN][DATA_PLAYBACK_VOLUME].pop(
        entry.entry_id,
        None,
    )
    return True
