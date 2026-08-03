# Changelog

## 0.5.4

- changed M1S media-group volume handling to debounce slider updates
- intermediate slider positions now only update the pending Home Assistant state
- the shared FFmpeg timeline restarts once, 0.8 seconds after the last volume call
- added group diagnostics: `volume_apply_mode`, `volume_settle_seconds`, `volume_apply_pending`, `applied_volume_level`, and `applied_is_volume_muted`
- retained the 0.2% volume scale and full-group resynchronisation behavior

## 0.5.3

- changed late/recovered group-member handling from live insertion to a full group restart
- when a selected online hub returns while the group is playing, all group receivers and the single shared FFmpeg process are restarted together
- retained removal of an offline or individually claimed hub without interrupting the remaining group
- added a 30-second retry guard after a failed receiver preparation to prevent repeated rapid full-group interruptions
- added group diagnostics: `rejoin_sync_mode`, `full_resync_count`, `last_full_resync_reason`, and `full_resync_retry_seconds`

## 0.5.2

- changed individual and group media-player volume normalization to one uniform 0.2% step across 0-100%
- changed volume up/down actions to 0.2% per press for individual and group players
- expanded the precise individual and group number sliders to 0-100% with a 0.2% step
- retained the precise number sliders because Home Assistant documents `volume_step` for volume up/down actions, not as a guarantee for every frontend slider drag

## 0.5.1

- fix Home Assistant platform forwarding by using explicit platform names
- no audio, synchronization, watchdog or entity behavior changes

## 0.5.0 - test

- Rebuilt from the clean v0.3.7 integration.
- Preserved all individual media players, fine volume and automatic recovery.
- Fixed the undefined delayed-resume watchdog failure variable.
- Added one shared-timeline media group with a single FFmpeg PCM source.
- Added 20 ms sequence framing and a 1.5 s common silent synchronization gate.
- Added late-member synchronization at a future shared sequence.
- Added per-hub skip/retry without stopping the rest of the group.
- Added strict individual-player priority and dedicated group resources on TCP 12347.
- Added per-hub group membership switches and group fine volume.
- Added physical-button event entity and six MQTT device triggers.

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
