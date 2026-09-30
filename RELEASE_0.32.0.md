# Release 0.32.0

This release makes the Coordinator an always-on Home Assistant device and adds RGB ring-light and illuminance support for the validated EXP4.4 sideband runtime.

## Safety change

The Coordinator ON/OFF options-flow step, switch entity and client command have been removed. During setup, the integration removes the legacy `*_coordinator_radio` entity from Home Assistant's entity registry. The integration therefore has no command path to `coordinator_set.sh off`.

## Coordinator I/O

Ring Light sends `rgb R G B` through `/data/m1s_coordinator/coordinator_io.sh`. Illuminance starts a conversion, waits one second and reads the validated JSON result through the same helper. Zigbee2MQTT retains the Spinel TCP connection on port 1886.

These entities require Coordinator EXP4.4 and relay 0.4.1 or another runtime implementing the same helper contract. Missing or invalid sideband replies make only the affected entity operation fail; hub availability and Zigbee2MQTT are not intentionally changed.

## Hardware evidence from 2026-09-30

- Identical Aqara M1S hardware on `.220` and `.222`.
- Spinel protocol 4.3 and `M1S_IO_V2` marker.
- Sideband property 59, RGB and lux responses while Zigbee2MQTT remained operational.
- Associated Zigbee device traffic observed through Zigbee2MQTT.
- Telnet, Wi-Fi and Coordinator runtime persistence checked after reboot.
- Factory-button commands isolated from the Coordinator runtime.

Firmware SHA-256: `C102149FA5A88A69535AE6E204A3F60BACB6FBB970571567D506DC8CD7844C57`.

Relay SHA-256: `B8FFD40CAC73048EF2868A33EE61410C4019D5CD55B673A6BB4FE64591391408`.

No firmware writing or hub flashing is performed by this integration package.
