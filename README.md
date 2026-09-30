# Aqara M1S Zigbee Coordinator + Router v0.34.0

Recovery release built directly from the local `0.32.0b2` base. Confirmed sound, media-player, volume, physical-button, shared-MQTT, Wi-Fi and diagnostic modules are preserved.

## Coordinator safety

- Home Assistant cannot stop the Coordinator.
- The switch, options form and internal OFF command are removed.
- The legacy `*_coordinator_radio` registry entity is removed automatically.
- Rejoin remains Router-only.
- Coordinator RGB/lux is not polled in this release; no sideband or relay command is executed.
- Zigbee2MQTT continues independently through `zoh` at `tcp://HUB_IP:1886`.

Router RGB and Illuminance remain unchanged. Coordinator RGB/lux will return only after its sideband transport is validated separately without affecting Telnet, sound playback or Zigbee2MQTT.
