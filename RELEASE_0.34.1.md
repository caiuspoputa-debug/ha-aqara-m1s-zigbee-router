# Release 0.34.1 TEST

This test release adds role-specific Coordinator Ring Light and Illuminance paths on top of the stable 0.34.0 recovery base.

- Router RGB/lux remains unchanged on UART A5/A6.
- Coordinator RGB/lux uses only `/data/m1s_coordinator/coordinator_io.sh` through an isolated Telnet client.
- The response must confirm protocol version 1 and capabilities 3 (`M1S_IO_V2`).
- RGB runs only on a Home Assistant light action.
- Coordinator lux runs once every minute with one `lux-start`, one-second wait and one `lux-get`.
- Sideband errors affect only Ring Light and Illuminance.
- The integration never accesses Coordinator port 1886 and contains no Coordinator ON/OFF control.

No live deployment or hub command was performed while building this package.
