# Release 0.33.2

This release fixes Coordinator sideband transport compatibility and request pacing.

- Ring Light and Illuminance remain visible for Coordinator hubs.
- Requests try the installed `coordinator_io.sh` interface and then relay 0.4.1 `--io` mode.
- Neither failure path can fall back to the Router A5/A6 UART protocol.
- Lux uses one `lux-start`, a one-second conversion wait and one `lux-get`, matching the hardware-validated sequence and avoiding rapid relay/Telnet requests.
- The Coordinator remains always-on and has no ON/OFF control.

All 17 isolated regression tests pass. No firmware writing or hub flashing is performed by this package.
