from __future__ import annotations

import base64
from pathlib import Path

from homeassistant.components import button, light, media_player, number, select, sensor
from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from .client import AqaraM1SClient
from .const import (
    DATA_CLIENTS,
    DATA_COORDINATORS,
    DATA_PLAYBACK_VOLUME,
    DATA_RADIO_PLAYERS,
    DATA_SELECTED_SOUND,
    DATA_SOUND_MAP,
    DATA_SOUND_PLAYERS,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DOMAIN,
    MANAGED_SOUND_ROOT,
    SERVICE_PLAY_SOUND,
    SERVICE_PLAY_URL,
    SERVICE_RUN_COMMAND,
    SERVICE_UPLOAD_SOUND,
    SERVICE_DELETE_SOUND,
    SERVICE_REFRESH_SOUNDS,
)
from .coordinator import AqaraM1SRouterCoordinator
from .sound_player import AqaraM1SSoundPlayer

PLATFORMS = [
    button.DOMAIN,
    light.DOMAIN,
    media_player.DOMAIN,
    number.DOMAIN,
    sensor.DOMAIN,
    select.DOMAIN,
]



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

    client = AqaraM1SClient(
        host=host,
        port=port,
        username=username,
        password=password,
    )
    coordinator = AqaraM1SRouterCoordinator(hass, client)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_CLIENTS, {})
    hass.data[DOMAIN].setdefault(
        DATA_COORDINATORS,
        {},
    )
    hass.data[DOMAIN].setdefault(
        DATA_SELECTED_SOUND,
        {},
    )
    hass.data[DOMAIN].setdefault(
        DATA_SOUND_MAP,
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

    hass.data[DOMAIN][DATA_CLIENTS][
        entry.entry_id
    ] = client
    hass.data[DOMAIN][DATA_COORDINATORS][
        entry.entry_id
    ] = coordinator
    hass.data[DOMAIN][DATA_SELECTED_SOUND][
        entry.entry_id
    ] = (
        "/data/musics/music-scene/"
        "door_bell_1.wav"
    )
    hass.data[DOMAIN][DATA_SOUND_MAP][
        entry.entry_id
    ] = {}
    hass.data[DOMAIN][DATA_PLAYBACK_VOLUME][
        entry.entry_id
    ] = 50
    hass.data[DOMAIN][DATA_SOUND_PLAYERS][entry.entry_id] = AqaraM1SSoundPlayer(
        hass, client
    )

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, host)},
        name=entry.data.get(
            "name",
            f"Aqara M1S Router {host}",
        ),
        manufacturer="Aqara",
        model="M1S Gen 1 / JN5189 Router",
    )

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

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
        _, selected_client = await _get_target(call)
        url = call.data["url"]
        command = (
            f'wget -q "{url}" '
            "-O /tmp/ha_audio.wav "
            "&& aplay -x 1 /tmp/ha_audio.wav"
        )
        await hass.async_add_executor_job(
            selected_client.run_command,
            command,
        )

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

        def _read_source() -> tuple[str, bytes]:
            value = source
            if isinstance(value, dict):
                if value.get("content"):
                    encoded = str(value["content"]).split(",", 1)[-1]
                    filename = str(value.get("filename") or "sound.wav")
                    return filename, base64.b64decode(encoded, validate=True)
                value = value.get("path") or value.get("file")
            if not isinstance(value, str):
                raise ValueError("The file selector did not return a readable file")
            if value.startswith("data:audio/") and "," in value:
                return "sound.wav", base64.b64decode(
                    value.split(",", 1)[1], validate=True
                )

            # The Home Assistant file selector returns an upload UUID, not a
            # filesystem path. Consume that temporary upload inside its
            # required context manager and keep the original filename.
            try:
                with process_uploaded_file(hass, value) as uploaded_path:
                    return uploaded_path.name, uploaded_path.read_bytes()
            except ValueError:
                pass

            # Retain path input for automations that explicitly use an allowed
            # Home Assistant directory.
            path = Path(value)
            if not hass.config.is_allowed_path(str(path)):
                raise ValueError("The selected WAV path is not allowed by Home Assistant")
            return path.name, path.read_bytes()

        filename, content = await hass.async_add_executor_job(_read_source)
        if len(content) > 20 * 1024 * 1024:
            raise ValueError("WAV file is larger than the 20 MiB safety limit")
        safe_filename = Path(filename).name
        if not safe_filename.lower().endswith(".wav"):
            raise ValueError("Only .wav files can be uploaded")
        destination = f"{MANAGED_SOUND_ROOT}/{safe_filename}"
        await hass.async_add_executor_job(
            selected_client.upload_sound, destination, content
        )
        await hass.config_entries.async_reload(selected_entry_id)

    async def delete_sound(call: ServiceCall) -> None:
        selected_entry_id, selected_client = await _get_target(call)
        await hass.async_add_executor_job(
            selected_client.delete_sound, call.data["path"]
        )
        await hass.config_entries.async_reload(selected_entry_id)

    async def refresh_sounds(call: ServiceCall) -> None:
        selected_entry_id, _ = await _get_target(call)
        await hass.config_entries.async_reload(selected_entry_id)

    if not hass.services.has_service(DOMAIN, SERVICE_PLAY_URL):
        hass.services.async_register(DOMAIN, SERVICE_PLAY_URL, play_url)
        hass.services.async_register(DOMAIN, SERVICE_PLAY_SOUND, play_sound)
        hass.services.async_register(DOMAIN, SERVICE_RUN_COMMAND, run_command)
        hass.services.async_register(DOMAIN, SERVICE_UPLOAD_SOUND, upload_sound)
        hass.services.async_register(DOMAIN, SERVICE_DELETE_SOUND, delete_sound)
        hass.services.async_register(DOMAIN, SERVICE_REFRESH_SOUNDS, refresh_sounds)

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

    hass.data[DOMAIN][DATA_COORDINATORS].pop(entry.entry_id, None)
    radio_player = hass.data[DOMAIN][DATA_RADIO_PLAYERS].pop(
        entry.entry_id,
        None,
    )
    if radio_player:
        await radio_player.async_shutdown()

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
    hass.data[DOMAIN][DATA_SELECTED_SOUND].pop(
        entry.entry_id,
        None,
    )
    hass.data[DOMAIN][DATA_SOUND_MAP].pop(
        entry.entry_id,
        None,
    )
    hass.data[DOMAIN][DATA_PLAYBACK_VOLUME].pop(
        entry.entry_id,
        None,
    )
    return True
