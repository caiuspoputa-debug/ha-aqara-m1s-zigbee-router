# Release 0.33.1

This maintenance release fixes Coordinator entity discovery after the 0.33.0 field test.

- Ring Light and Illuminance are always registered for a detected Coordinator, matching their placement on Router devices.
- Until a valid sideband reply is received, the entities remain visible but unavailable instead of being omitted.
- Coordinator requests use `/data/m1s_coordinator/coordinator_io.sh`, the relay 0.4.1 helper validated on `.220` and `.222`.
- Device information now identifies a Coordinator as `M1S Gen 1 / JN5189 Coordinator`.
- The Coordinator remains always-on; no ON/OFF entity or settings action is restored.

All 16 isolated regression tests pass. No firmware writing or hub flashing is performed by this package.
