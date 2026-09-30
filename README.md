# Aqara M1S Zigbee Coordinator + Router v0.34.1 TEST

Test release built on the `0.34.0` recovery base. Confirmed sound, media-player, volume, physical-button, shared-MQTT, Wi-Fi and diagnostic modules remain unchanged.

## Coordinator safety

- Home Assistant cannot stop the Coordinator.
- The switch, options form and internal OFF command are removed.
- The legacy `*_coordinator_radio` registry entity is removed automatically.
- Rejoin remains Router-only.
- Coordinator Ring Light uses the validated `M1S_IO_V2` helper only when Home Assistant sends a light command.
- Coordinator Illuminance uses the same helper once every 60 seconds (`lux-start`, one-second conversion, `lux-get`).
- Sideband commands use fresh Telnet sessions and never use the Router UART path or Coordinator port 1886.
- A sideband failure makes only Ring Light and Illuminance unavailable; hub, audio, MQTT and Zigbee2MQTT availability remain independent.
- Zigbee2MQTT continues independently through `zoh` at `tcp://HUB_IP:1886`.

Router RGB and Illuminance remain unchanged on their existing UART A5/A6 path. This release was validated without connecting to or changing a live hub and must be treated as TEST until hardware confirmation.
