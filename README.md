# Aqara M1S Zigbee Coordinator + Router v0.32.0

Local Home Assistant integration for hardware-identical Aqara M1S Gen 1 hubs configured either as a Zigbee Router or a Zigbee-on-Host Coordinator. The internal domain remains `aqara_m1s_zigbee_router`, preserving existing installations and entity identities.

## Role-aware behavior

- Router: Configure exposes **Join another Zigbee coordinator**; RGB and lux use the Router UART protocol.
- Coordinator: Home Assistant exposes no switch, option or service capable of stopping the Coordinator. On upgrade, the legacy `*_coordinator_radio` entity is removed from the entity registry.
- Coordinator: **Ring Light** is an RGB Light entity and **Illuminance** is a lux Sensor. Both use `/data/m1s_coordinator/coordinator_io.sh` sideband commands without taking over Zigbee2MQTT's Spinel connection.
- The confirmed role is persisted and is independent of the hub IP address.
- Zigbee channel and network remain managed by Zigbee2MQTT through `serial.adapter: zoh` and `tcp://HUB_IP:1886`.

## Coordinator validation on 2026-09-30

On identical `.220` and `.222` hubs, the EXP4.4 Coordinator firmware and relay 0.4.1 were validated with Spinel `Protocol version: 4.3`, marker `M1S_IO_V2`, sideband property 59, associated-device Zigbee traffic, and live RGB/lux commands while Zigbee2MQTT remained connected. Reboot persistence for Telnet, Wi-Fi and the Coordinator runtime was also checked, together with protection from the stock factory-button commands.

Validated firmware SHA-256: `C102149FA5A88A69535AE6E204A3F60BACB6FBB970571567D506DC8CD7844C57`.

Validated relay SHA-256: `B8FFD40CAC73048EF2868A33EE61410C4019D5CD55B673A6BB4FE64591391408`.

Coordinator RGB/lux requires that compatible runtime and a working `coordinator_io.sh`. This integration never writes firmware or flashes a hub. Lux is the firmware-provided measurement; absolute photometric calibration remains sensor- and installation-dependent.

## Shared MQTT and sounds

**Shared MQTT - all hubs** stores one broker configuration and applies it to Router and Coordinator hubs, including offline hubs after reconnect. Sound uploads remain under `/data/musics/music-ch`; deletion requires explicit selection, confirmation and a successful backup under `/data/m1s_sound_backups`.

See [RELEASE_0.32.0.md](RELEASE_0.32.0.md) for release details.
