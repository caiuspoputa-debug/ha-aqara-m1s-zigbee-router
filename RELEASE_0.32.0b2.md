# 0.32.0b2 - Coordinator RGB/lux experiment

- Adds a strict JSON client for the relay's local Unix socket helper over the existing Telnet connection.
- Coordinator RGB/lux never uses the Router's A5/A6 UART transport, including on failure.
- Discovers light/lux entities after a validated firmware response. Re-probes every 15 seconds via the independent optional-feature task.
- Marks coordinator peripherals unavailable on transport failure/offline and does not publish invalid lux as zero.
- Keeps Router RGB transport and shared MQTT configuration behavior.
- Requires relay 0.4.0-exp2 and RCP marker M1S_IO_V2. Earlier exp1 firmware is NOT sufficient.

Validation: 9 new isolated client tests; 7 existing MQTT regression tests; Python compilation.
No full Home Assistant runtime test or on-device test has been performed.
