DOMAIN = "aqara_m1s_zigbee_router"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_NAME = "name"
DEFAULT_PORT = 23
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = ""

SERVICE_PLAY_URL = "play_url"
SERVICE_PLAY_SOUND = "play_sound"
SERVICE_RUN_COMMAND = "run_command"

DATA_CLIENTS = "clients"
DATA_COORDINATORS = "coordinators"
DATA_PLAYBACK_VOLUME = "playback_volume"

DATA_RADIO_PLAYERS = "radio_players"
DATA_SOUND_PLAYERS = "sound_players"

SERVICE_UPLOAD_SOUND = "upload_sound"
SERVICE_DELETE_SOUND = "delete_sound"
SERVICE_REFRESH_SOUNDS = "refresh_sounds"

SOUND_ROOT = "/data/musics"
MANAGED_SOUND_ROOT = "/data/musics/music-ch"


def sound_list_signal(entry_id: str) -> str:
    """Return the dispatcher signal for one hub's sound catalog."""
    return f"{DOMAIN}_{entry_id}_sound_list_updated"


def radio_volume_signal(entry_id: str) -> str:
    """Return dispatcher signal for radio volume changes."""
    return f"{DOMAIN}_{entry_id}_radio_volume_updated"
