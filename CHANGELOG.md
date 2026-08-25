## v0.9.9 - Quiet TCP self-heal and 2s hub buffer

- Increase the single and group hub `aplay` buffer request from 500 ms to 2000 ms while keeping the 50 ms period time.
- Keep the HA-side single-player buffer at 4.0 s, with 2.5 s prebuffer and 2.0 s rebuffer threshold.
- Lower successful single TCP self-heal teardown noise: TCP recovery writer-close issues are debug, normal rebuild attempts are info, and warnings are reserved for recovery bursts/failures.
- Preserve the existing moderate priorities: FFmpeg nice -5 and hub aplay nice -3. No sound-priority changes.
- Sound-player transport is unchanged.

## v0.9.8 - Single TCP self-heal

- Add immediate single-player TCP receiver recovery for `writer.drain()` backpressure.
- On TCP backpressure, rebuild only the hub receiver on port 12346, reconnect the HA writer, send a short silence cushion, and continue the existing FFmpeg stream.
- Reduce the single TCP drain timeout to 1.0 s so receiver recovery starts before the watchdog-sized interruption.
- Keep the v0.9.7 4.0 s HA buffer, 2.5 s prebuffer, 2.0 s rebuffer threshold, and 500 ms `aplay` request.
- Add diagnostics for TCP self-heal status and recovery event counts.
- Sound-player transport and hub sound priority are unchanged.

## v0.9.7 - Single 4s buffer and hub aplay cushion

- Increase the single-player HA-side jitter buffer to 4.0 s, with 2.5 s prebuffer and 2.0 s rebuffer resume threshold.
- Add explicit 500 ms `aplay` buffer and 50 ms period time for single and group hub receivers to reduce ALSA underruns.
- On single TCP writer failure, switch the FFmpeg stdout producer to discard/drain mode before terminate/kill so it cannot remain blocked in the PCM queue.
- Keep the v0.9.6 group drain/reap behavior.
- Sound-player transport and hub sound priority are unchanged.

## v0.9.6 - Single 2s buffer and group drain reap

- Increase the single-player HA-side jitter buffer to 2.0 s, with 1.5 s prebuffer and 1.0 s rebuffer resume threshold.
- Add single-player rebuffer mode so a depleted buffer sends controlled silence until enough PCM is available, instead of alternating broken audio and silence.
- Keep the single FFmpeg stdout producer active during watcher_exception teardown so subprocess pipes drain before reap.
- Group Stop now invalidates the timeline but lets FFmpeg stdout/stderr readers drain and discard until EOF before final reap.
- Group broadcaster no longer fans out PCM after Stop while it drains the old FFmpeg process.
- Sound-player transport and hub sound priority are unchanged.

## v0.9.5 - Single detached drain reap

- Fix intentional single-player Stop teardown after v0.9.4 by treating detached sessions as normal watcher exits.
- Producer keeps draining FFmpeg stdout after Stop and discards PCM instead of stopping reads and leaving subprocess pipes blocked.
- Stop remains non-blocking: one background escalator may terminate/kill, while the watcher remains the only code path that awaits/reaps FFmpeg.
- Detached watcher ignores playout/socket exceptions and does not enter watcher_exception recovery.
- Group and priority-sound transports are unchanged.

## v0.9.4 - Single async FFmpeg reap

- Fix repeated Stop/Play `FFmpeg terminate timeout` / `did not reap after kill` warnings.
- Stop detaches the old single-player session immediately instead of cancelling its watcher and waiting on the same subprocess.
- The original watcher remains the sole FFmpeg reaper; a background escalator may terminate/kill a stale process but never calls `process.wait()`.
- Old watcher state remains identity/generation guarded and cannot overwrite a newer Play session.
- Group and priority-sound transports are unchanged.

# v0.9.3 - SINGLE STOP/PLAY RECOVERY

- Fix single-player Stop -> Play lockups by making local transport teardown hard-bounded.
- TCP writer close now has a 0.50 s hard bound; a stuck close is aborted instead of holding the media-player lock indefinitely.
- FFmpeg watcher cancellation and terminate/kill are bounded so an old session cannot block a new Play forever.
- User Stop no longer performs synchronous Telnet receiver cleanup while holding the transport lock. Closing the single TCP stream lets hub-side nc reach EOF, and every subsequent REMOTE_START_COMMAND still begins with the exact PID/port-scoped cleanup for port 12346.
- Added explicit STOP, writer-close timeout, transport-abort and teardown diagnostics.
- Retains the v0.9.2 0.8 s jitter buffer, 0.6 s prebuffer, live volume behavior and moderate FFmpeg/aplay priorities.
- Sound transport and media-group code are unchanged byte-for-byte from v0.9.2.

# v0.9.2 - SINGLE STABLE BUFFER

- Single player: replace the ultra-small v0.9.1 path with a bounded 0.8 s HA-side PCM jitter buffer and 0.6 s prebuffer.
- Volume/mute gain is applied when PCM leaves the jitter buffer, so the cushion does not itself add volume-control lag.
- FFmpeg may refill the bounded buffer after short stalls; the consumer remains the only real-time playout clock.
- Short queue starvation is bridged with silence to keep hub-side aplay alive instead of causing an ALSA underrun; a true PCM stall beyond 5 s still triggers recovery.
- Single TCP write/socket buffering is capped to keep audible volume response under about one second.
- Preserve the proven moderate priorities only: FFmpeg nice -5 and hub aplay nice -3. No realtime scheduler, no extra priority for nc/Zigbee processes, no broad process kills.
- Sound transport and media-group code are unchanged from v0.9.1.

# v0.9.1 — single-player low-latency live volume

- Keeps v0.9.0 latest-request-wins single-player recovery and the v0.6.3 priority-sound transport.
- Adds FFmpeg real-time input pacing (`-re`) for single playback so finite media cannot run several seconds ahead into TCP/FIFO buffers.
- Bounds the single-player asyncio/TCP send buffering to a few 20 ms PCM frames.
- Paces outgoing single-player PCM on Home Assistant's monotonic clock and rebases after event-loop stalls instead of sending catch-up bursts.
- Live volume, Fine Volume Trim and mute remain software PCM gain changes and do not restart FFmpeg, TCP, `nc` or `aplay`.
- Group transport and priority sound transport are unchanged from v0.9.0.

# v0.6.0 TEST — clocked multi-room group transport

- Reworked the M1S Media Group around a single Home Assistant monotonic playout clock.
- Initial playback uses a bounded startup cohort instead of waiting for every selected hub.
- All ready hubs receive a common scheduled silence pre-roll before source audio; source samples are no longer discarded for startup synchronization.
- Late hubs join on a future common clock boundary after a short silent lead-in.
- FFmpeg pipe bursts are paced into 20 ms frames by the HA playout clock; FFmpeg `-re` is no longer the synchronization mechanism.
- A slow/offline receiver is isolated without stopping FFmpeg or healthy hubs.
- Per-member reconnect uses short stabilization plus exponential retry backoff.
- TCP/asyncio write buffering is bounded so stalled receivers are detected before seconds of audio accumulate.
- Legacy member-triggered full group resynchronisation is disabled; global restart is reserved for source/FFmpeg health failure or explicit user Play/Reset.
- Existing group hard-reset/OFF path remains scoped to port 12347 and does not touch individual 12346 or Zigbee 1886.

# v0.5.15 TEST - Fast group start / slow-member isolation

- Group Play starts as soon as the first selected hub receiver is ready instead of waiting for every hub.
- Slow or stuck hub preparation continues in background and joins on a future shared PCM sequence.
- Group start/stop Telnet commands, TCP connect, writer close and task cancellation are bounded by explicit timeouts.
- Queue overflow keeps the v0.5.14 isolation policy: only the slow member is detached; healthy hubs are not full-resynchronised.
- Periodic receiver resync remains disabled.
- Keeps the v0.5.14 group-only hard reset / OFF recovery path.

## 0.5.14 TEST

- Added `aqara_m1s_zigbee_router.reset_media_group` for group-only recovery without restarting Home Assistant.
- Group STOP now falls back to a hard transport reset if normal shutdown wedges.
- Group OFF performs an immediate hard group-only reset.
- A full resynchronisation that hangs for 35 seconds is aborted and the group is returned to idle instead of spinning indefinitely.
- Hard reset only targets group FFmpeg/tasks/queues/sockets and hub port 12347; individual audio 12346 and Zigbee UART 1886 are untouched.

# v0.5.13 TEST

- Added periodic 10-minute receiver-only drift guard for long-running M1S Media Group playback.
- The guard pauses the shared PCM broadcaster at a 20 ms boundary, rebuilds active hub `nc`/`aplay` receivers, reapplies the 1.5 s common silent lead-in, and resumes the same FFmpeg process.
- Periodic drift correction therefore preserves finite-media position instead of restarting the source from the beginning.
- Existing full-resync recovery paths remain for persistent lag, queue overflow, PCM stall and member rejoin.
- Retains v0.5.11 WAV/ZIP batch upload (up to 64 WAV files) and multi-delete.
- TEST status retained pending long-run physical observation.

# Changelog

## 0.5.11 - test

- Configure → Delete WAV now uses Home Assistant's native multi-select selector, so multiple managed WAV files can be selected and deleted in one operation
- Home Assistant's native FileSelector still returns a single uploaded file; Configure therefore keeps a single file picker but now accepts either one WAV or one ZIP batch
- a ZIP batch may contain up to 64 WAV files, with the existing 20 MiB limit per WAV and a 100 MiB total batch/archive safety limit
- ZIP processing is in-memory, ignores non-WAV entries, rejects encrypted archives and duplicate WAV basenames, and never extracts paths onto the Home Assistant filesystem
- all v0.5.10 audio synchronization, watchdog, TCP backpressure and Fine Volume Trim behavior is retained unchanged

## 0.5.10 - test

- fixed false full-group resynchronisations caused by a single 120 ms queue spike
- the 120 ms member-lag threshold must now persist continuously for 1.0 second before a full resync is requested
- lag detection is suppressed for the first 8 seconds after every group stream start/resync so normal receiver startup cannot trigger another resync
- a completely full 250 ms member queue still forces an immediate full-group resync because synchronization is already lost
- group TCP writer drain timeout increased from 1.0 s to 2.0 s to tolerate brief LAN scheduling/backpressure spikes without hiding real stalls
- group watchdog restart logs now include the last recorded failure reason
- individual media-player TCP writer drain timeout increased from 1.0 s to 2.0 s
- an individual writer timeout is now classified explicitly as `tcp_pcm_backpressure` instead of the misleading generic `hub_audio`; remote audio snapshots are still captured
- retains the v0.5.9 Fine Volume Trim behavior unchanged

## 0.5.9 - test

- added a separate **Fine Volume Trim** slider to every individual media player
- trim range is `-1.00%` to `+1.00%` in `0.01%` steps and is applied as absolute percentage points after the main 0.1%-step player volume
- example: main volume `6.0%` plus trim `+0.27%` produces `6.27%` effective PCM gain
- fine trim uses the existing interruption-free live S32_LE PCM gain path; changing it does not restart FFmpeg, TCP, `nc` or `aplay`
- main volume `0%` remains hard silence even with a positive trim; mute also remains hard silence
- the old pre-v0.5.6 absolute fine-volume entity is not reused; v0.5.9 creates a new `*_radio_fine_trim` entity to avoid semantic/state collisions
- retains all v0.5.8 group resynchronization and PCM-progress watchdog changes unchanged

## 0.5.8 - test

- group synchronization now has priority over uninterrupted playback: a recovered or lagging hub causes a controlled full-group restart instead of being allowed to continue with a permanent offset
- reduced the per-hub PCM queue ceiling from 1.0 s to 0.25 s and added a 120 ms lag threshold that requests full resynchronisation
- the broadcaster yields after every 20 ms PCM chunk so writer tasks can drain in real time even when FFmpeg stdout arrives in larger bursts
- a hub that returns online is allowed an 8-second stabilization window before it participates in the next full-group synchronization
- added a PCM-progress health watchdog: if FFmpeg remains alive but no PCM arrives for 12 seconds, the complete group is restarted automatically
- the 30-second stable-watch now clears watchdog failures only when PCM is actually flowing and at least one group receiver is active
- added diagnostics for PCM age, per-member queue depth, resync threshold and synchronization policy

## 0.5.7

- added **Change Wi-Fi network** to the integration Configure menu
- the Wi-Fi password is masked in the Home Assistant form and is not stored in config-entry data or options
- the integration stages the candidate only on the hub and delegates validation/rollback to the optional sanitized Wi-Fi recovery module
- hardened candidate validation by clearing a stale interface IPv4 before the new connection attempt, preventing an old address from being mistaken for success
- renamed the Configure menu from sound-only management to general Aqara M1S management
- added Romanian/English documentation links and documented the safe Wi-Fi change workflow

## 0.5.6

- moved every individual media player to the same interruption-free live PCM software-gain model already used by the group
- changed the native individual and group media-player volume step from 0.2% to 0.1% across 0-100%
- removed the separate individual and group fine-volume Number entities; the native media-player slider is now the only stream-volume control
- added a 40 ms software gain ramp for volume and mute changes to reduce clicks without restarting FFmpeg, TCP, `nc` or `aplay`
- gave FFmpeg a best-effort moderate CPU priority (`nice -5`) in Home Assistant and `aplay` a smaller best-effort priority (`nice -3`) on each hub
- priority changes use normal Linux niceness only; they never use realtime scheduling, terminate other processes, or fail playback when the OS refuses the requested priority


## 0.5.5

- removed all FFmpeg and receiver restarts caused by M1S media-group volume or mute changes
- moved group gain control into the existing Home Assistant PCM broadcast loop
- each new volume value is applied to the next common 20 ms S32_LE chunk while preserving the same FFmpeg process, TCP sessions, queues and synchronization timeline
- retained the 0.2% volume scale and full-group resynchronisation when a hub actually rejoins
- added diagnostics: `volume_apply_mode: live_pcm_software_gain` and `volume_stream_restart: false`

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

## 0.9.0 - Single audio latest-request-wins recovery
- Based on the known-good v0.6.3 audio-priority transport.
- Rapid single-player track changes now invalidate older queued starts; only the latest request may start port 12346.
- Priority sounds immediately invalidate queued single-audio starts before waiting for the transport lock.
- Superseded starts clean only the dedicated single receiver/FIFO and never use broad `nc` process-kill logic.
- Added generation/supersede logging and diagnostics while keeping the sound transport unchanged.
