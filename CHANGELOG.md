# Changelog

## 0.4.0

- keeps every existing per-hub Media Player and fine-volume entity
- adds one dynamic `M1S Media Group` media player
- adds one per-hub `Include in M1S Media Group` switch
- joining an active group starts the current source automatically
- removing a hub stops only that hub
- unavailable selected hubs are skipped while available hubs continue
- adds shared 0-4% fine volume in 0.1% steps
- adds Home Assistant device triggers for click, double, triple, quadruple, five-click and hold


## 0.1.0

- New integration domain: `aqara_m1s_zigbee_router`.
- Direct JN5189 RGB UART control using `A5 R G B checksum`.
- Shared 15-second hub availability coordinator.
- Light, radio, volume and sensors become unavailable when the hub is offline.
- Sound buttons intentionally remain visible while offline.
- v0.5.9 radio pipeline retained, including PID-scoped forced cleanup.
- v0.5.9 FFmpeg sound pipeline retained for fine volume and no LED side effect.
- Multi-hub action routing corrected by hub IP.
- WAV upload, deletion and sound-list refresh actions added.
- WAV upload validates PCM, mono, 32000 Hz and signed 32-bit samples.
- Upload paths are restricted to `/data/musics` and files to 20 MiB.
- Stock-firmware Telnet preparation sequence documented as `5-2-2-2-2-2-2`.
- Local Home Assistant brand icon included in 256 px and 512 px variants.
