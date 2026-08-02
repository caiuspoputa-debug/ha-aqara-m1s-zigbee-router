## 0.4.2 - test

- replaced media-group fan-out with one shared Home Assistant FFmpeg process
- the same mono 32 kHz S32_LE PCM chunks are broadcast to every active M1S hub
- slow or offline hubs are removed individually without stopping the remaining group
- preserved individual media players, fine volume, dynamic membership and physical-button events
- a hub enabled during playback joins the current common PCM stream

## 0.4.1 - test

- fixes media-group fan-out so a stale coordinator poll does not exclude a hub before the actual play attempt
- creates individual media-player objects before concurrent platform setup, removing setup-order races
- keeps every individual media player and fine-volume entity
- exposes the physical hub button as an Event entity while retaining device triggers
- fixes an undefined watchdog variable in remembered-media recovery

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
