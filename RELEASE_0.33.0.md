# Release 0.33.0

This release makes the Coordinator an always-on Home Assistant device and adds validated RGB ring-light and illuminance support for the EXP4.4/relay 0.4.1 sideband runtime.

## Safety

The Coordinator ON/OFF options step, switch entity and client command are removed. Setup deletes the legacy `*_coordinator_radio` entity from the Home Assistant entity registry. The integration contains no path that invokes `coordinator_set.sh off`.

## Coordinator I/O

Version 0.33.0 incorporates the strict protocol work from the earlier local 0.32.0b2 experiment: capability discovery before entity creation, exact JSON schema and range validation, rejection of ambiguous replies, no fallback to Router UART, real RGB readback and correct unavailable states.

Ring Light and Illuminance communicate with `/data/m1s_coordinator/bin/uart_tcp_relay_mipsel --io ...`. Zigbee2MQTT retains its Spinel TCP connection on port 1886. An invalid lux conversion is unavailable, never a fabricated zero value.

## Hardware evidence from 2026-09-30

- Identical Aqara M1S hardware on `.220` and `.222`.
- Spinel protocol 4.3, marker `M1S_IO_V2` and sideband property 59.
- RGB and lux replies while Zigbee2MQTT remained operational.
- Associated Zigbee-device traffic through Zigbee2MQTT.
- Telnet, Wi-Fi and Coordinator runtime persistence after reboot.
- Factory-button commands isolated from the Coordinator runtime.

Firmware SHA-256: `C102149FA5A88A69535AE6E204A3F60BACB6FBB970571567D506DC8CD7844C57`.

Relay SHA-256: `B8FFD40CAC73048EF2868A33EE61410C4019D5CD55B673A6BB4FE64591391408`.

The integration performs no firmware writing or hub flashing.
