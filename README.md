# Aqara M1S Zigbee Coordinator + Router v0.30.0

Local Home Assistant integration for Aqara M1S Gen 1 hubs prepared either as a Zigbee Router or as the dedicated Zigbee-on-Host Coordinator LAB.

The internal domain remains `aqara_m1s_zigbee_router` to upgrade existing Router installations without recreating their entities.

## Role-aware Zigbee controls

- Router runtime detected: Configure shows **Join another Zigbee coordinator**.
- Coordinator runtime detected: Rejoin is removed; Configure shows **Coordinator ON/OFF** and the device gets a Coordinator switch.
- The confirmed role is stored in the Home Assistant config entry, so a Coordinator remains protected from RGB/lux UART commands if HA starts while that hub is temporarily offline.
- Role detection is not tied to an IP address: `.107` is currently the Coordinator, while every Router hub keeps RGB and lux.
- The Zigbee channel and network are configured in Zigbee2MQTT.
- Coordinator uses `serial.adapter: zoh` and `tcp://HUB_IP:1886`.

## Sound management

- Uploads still go to `/data/musics/music-ch` for backward compatibility.
- Manual deletion lists every `.wav` below `/data/musics`, including original Aqara sound folders.
- Nothing is selected by default and an explicit confirmation is required.
- Before deletion, one archive is created under `/data/m1s_sound_backups`; deletion is aborted if backup fails.
- No sound is deleted during installation, startup or migration.

## Coordinator LAB limits

Exact flash/readback, Spinel 4.3 handshake, channel 20 network formation, MAC traffic, ON/OFF and reboot recovery have been validated on Aqara M1S `.107`. Router RGB/lux UART commands are disabled in Coordinator mode because the standard RCP does not implement that private protocol. Audio, radio, network, Telnet and button functions remain Linux-side features.

The release remains LAB until a real Zigbee device join, bidirectional traffic and Zigbee2MQTT restart recovery are demonstrated.

Version `0.30.0` is based on integration `0.3.0`, which in turn is based on `0.21.13`.
