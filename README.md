# Aqara M1S Zigbee Coordinator + Router v0.37.20 TEST

Version **0.37.20 TEST** reconciles an enabled Router MQTT agent's AUTO topic
after its IPv4 address changes. The existing reload after a confirmed static-IP
change, a manual integration reload, and hub reconnection now check the topic.
Only a stale or stopped enabled agent is restarted; a repaired topic requires
new publication markers. The hub and Home Assistant are never rebooted.

Recovery runs in the existing background MQTT synchronization task, with
bounded retry. Disabled/missing agents, explicitly pinned topics and dedicated
Coordinators remain untouched. Audio, broker credentials, stable button IDs,
device-registry compatibility and firmware are unchanged. Active WAV receivers
and explicit UART maintenance defer recovery rather than interrupting them.
See [MQTT_IP_RECOVERY_RO.md](MQTT_IP_RECOVERY_RO.md) and `TEST_REPORT.json`.

The ZIP preserves the supplied repository-root layout, including
`custom_components/aqara_m1s_zigbee_router`. It is integration source, not M1S
firmware. Nothing has been published to GitHub or installed on Home Assistant.

## Retained device-registry compatibility from 0.37.19

Version **0.37.19 TEST** updates device-registry access for the deprecation
warnings reported on Home Assistant **2026.10.2**. Four identifier lookups now
use `async_get_device_by_identifier(identifier, entry.entry_id)` when available;
older HA versions use a lookup restricted to the same config entry. Device
trigger ownership uses the current domain helper instead of reading deprecated
`DeviceEntry.config_entries` on current HA.

Device identifiers, entity unique IDs and the existing IP-to-stable-identity
migration are unchanged. Audio runtime remains byte-identical to **0.37.18**,
and the Coordinator/Zigbee2MQTT guard remains unchanged from **0.37.17**.
See [DEVICE_REGISTRY_COMPAT_RO.md](DEVICE_REGISTRY_COMPAT_RO.md) for API details,
official deprecation references and the separate removal schedules.
This build has not been installed or restarted on Home Assistant; final local
test results are identified in `VALIDATION.txt`.

## Retained audio behavior from 0.37.18

Version **0.37.18 TEST** separates priority alerts from media mute. Stored WAVs,
sound buttons and priority `play_url` WAVs bypass individual and group media mute
by default, without changing either player's mute state. `respect_mute: true`
opts a service call into the previous individual-hub mute behavior; group mute
continues to apply only to group media.

Use optional `volume_percent` for a temporary alert volume. Without it, the alert
uses the current individual hub slider before mute is applied; a slider at 0%
still means silence. Current media gain is confirmed before resume/rejoin, so
manual volume and mute changes during the alert remain effective afterward.
No YAML unmute/remute sequence or persistent mute-state change is required.
Read [SOUND_MUTE_POLICY_RO.md](SOUND_MUTE_POLICY_RO.md) and
[NOTIFICATION_VOLUME_RO.md](NOTIFICATION_VOLUME_RO.md) for policy and migration.

The optional Coordinator/Zigbee2MQTT recovery guard is retained from **0.37.17**
without changes. See [COORDINATOR_GUARD_RO.md](COORDINATOR_GUARD_RO.md).
This TEST build has not been installed on Home Assistant or validated on hardware.

## Historical releases

Version `0.37.17 TEST` introduced optional coordinator/Zigbee2MQTT supervision:
confirmed stop on coordinator loss, isolated RCP restart and Spinel/PHY preflight,
then gated add-on start and fresh MQTT confirmation. It remains disabled until
the exact add-on and MQTT topic are selected on the dedicated Coordinator entry.
The following older release notes describe their original behavior; the 0.37.18
sound policy above takes precedence for this package.

Version `0.37.16 TEST` adds an atomic notification-volume request: media yields,
the hub confirms ALSA is closed, temporary WAV volume is applied, and normal
media volume is restored before resume/rejoin. Use `play_sound` with optional
`volume_percent`, not an early shared `number.set_value`. See
`NOTIFICATION_VOLUME_RO.md` for the service API.
The separate Fine Volume Trim entity and offset are removed. Main volume IDs,
0.01% precision, mute, 35 ms common clock and 105 ms batches are retained.

Version `0.37.15 TEST` requests one WAV playback explicitly, correcting the
hub Aplay's implicit triple playback. Idle hubs skip unnecessary receiver
stops and the fixed handover pause; active or in-flight players retain safe
preemption. The private audio Telnet channel is reused, with no automatic
replay of uncertain start commands. Local volume remains confirmed before
every WAV. See `WAV_FAST_START_RO.md`; the following audio overview is the
retained `0.37.14` base. This build was not deployed or restarted on HA.

Local Home Assistant integration for identical Aqara M1S Gen 1 / JN5189 hubs prepared either as Zigbee Routers or as a Zigbee-on-Host Coordinator. The runtime role is detected from the hub and stored in the Home Assistant config entry; it is never selected from the IP address.

Version `0.37.14 TEST` plays stored WAVs directly on each Router and applies one local ALSA software volume to WAVs, individual media and group receivers. Stored audio no longer passes through Home Assistant or FFmpeg. Radio/media still uses FFmpeg for decoding, but no longer for volume or HA-side gain processing. See `LOCAL_AUDIO_RO.md` for migration, requirements and the remaining live-test checklist.

The existing 35 ms clock, 105 ms transport batches, PCM history, prefill, buffers, Stop fix and priority policy are retained. Receiver commands now select the local ALSA volume route. This package is a prototype: the full new integration and multiroom acoustic synchronization have not been verified live. It was not installed on Home Assistant by this build. Installation requires a Home Assistant restart.

## Requirements

- Home Assistant `2024.1.0` or newer.
- Local network access from Home Assistant to the hub.
- Telnet enabled on the hub; default connection is port `23`, user `admin`, blank password.
- A compatible MIPS32 little-endian Router with `aplay`, ALSA `plug`/`softvol`, `/dev/snd/controlC0`, `base64`, `sha256sum`, and at least 8 MiB free on `/data` after audio-helper installation. Initial helper transfer can take longer; later WAV playback sends only control commands. There is no automatic unattenuated fallback if gain setup fails.
- An already converted Coordinator runtime with the existing static-IP/Wi-Fi managers; the Only Coordinator `1.0.0` profile is recommended. This integration does not install that profile or change hub services.
- An MQTT broker reachable through its LAN address for Router physical-button events, shared MQTT configuration and IO. The Coordinator's auxiliary MQTT agent is not used.
- Zigbee2MQTT with the `zoh` adapter when the hub is used as Coordinator.

## Installation and update

1. Back up the installed integration component. Extract this package
   and copy its `custom_components/aqara_m1s_zigbee_router` folder to
   `/config/custom_components/aqara_m1s_zigbee_router`, replacing the old component
   files. Do not create a second nested `custom_components` folder.
2. Restart Home Assistant to load **0.37.19**. A YAML reload alone does not load
   the new integration code.
3. Check that the installed component's `manifest.json` reports `0.37.19` and
   that Home Assistant loads the integration without errors.

Keep existing integration entries, hub identities and Zigbee pairings; no
integration removal or repeat pairing is needed. Integration and automation
deliverables are strictly separate. This integration package contains no
automation files, and installing it does not install or update automations.
Check fresh startup logs for device-registry warnings as described in
`DEVICE_REGISTRY_COMPAT_RO.md`. Optional sound API checks are described in
`SOUND_MUTE_POLICY_RO.md`.

Separate WAV calls still use the normal media resume policy between calls;
this change does not introduce a multi-alert session that holds radio playback
across delays between WAVs. Existing explicit media mute/unmute or shared-volume
commands still change the player; the alert policy does not suppress those calls.

The internal domain remains `aqara_m1s_zigbee_router`. Retained diagnostics and Router entities keep their unique IDs; former Coordinator media/IO entities are removed automatically. The physical Wi-Fi MAC is used as device identity when available, and the last confirmed Zigbee role is retained if Home Assistant starts while the hub is temporarily offline. References to retired controls in existing dashboards or automations are external configuration and are not changed by component installation.

## Router and Coordinator behavior

| Function | Router role | Coordinator role |
| --- | --- | --- |
| Zigbee transport | Existing JN5189 Router runtime | Zigbee-on-Host through `tcp://HUB_IP:1886` |
| Ring Light | Persistent MQTT to A5; legacy fallback only before upgrade activation | Not exposed |
| Illuminance | Retained MQTT state; serialized A6 sample every 30 seconds | Not exposed |
| Stored WAV | Direct local playback through the shared ALSA volume; Telnet control only | Not exposed; legacy sound services are blocked |
| Media / group membership | Existing individual and group playback | No player or group member is created |
| Join another coordinator | Available with explicit confirmation | Hidden and blocked |
| Coordinator ON/OFF | Not applicable | Deliberately absent |

The explicit Router rejoin action remains available. The integration pauses the agent, performs A7 through a bounded UART maintenance window, then restores the agent. The window closes itself after 90 seconds if Home Assistant disconnects. Coordinator RGB/lux never falls back to the Router UART path.

## Router safety and MQTT path

- Topics are built from the hub's current IP address: for example Router `192.168.0.221` uses `m1s/221/io/...`, regardless of historical entity names or IDs.
- Router agent `1.1.1` subscribes to `io/rgb/set`, `io/lux/refresh`, `sound/prepare` and `sound/stop`; it publishes IO state, availability, telemetry and WAV command status.
- Lux is sampled every 30 seconds. An A6 response without a valid checksum never becomes a false `0 lx` value.
- After activation, `/dev/ttyS1` has one owner. The former temporary TCP `1886` tunnel for A5/A6 is stopped and cannot start over the agent.
- A retained message declaring role `coordinator` is ignored by a Router, and vice versa.
- If the configured agent is unavailable, only Ring Light, illuminance and MQTT diagnostics become unavailable; the integration does not fall back to legacy UART over the agent.
- Overall Router availability keeps the existing lightweight LAN probe. An MQTT broker problem therefore does not automatically remove a player from the media group or change audio synchronization.
- The Router agent retains its IO responsibilities. This version does not use its legacy WAV receiver preparation: local WAV and gain commands use an isolated Telnet connection. Radio decoding and the group clock remain in Home Assistant.

## Dedicated Coordinator

- Only Hub Connectivity, WiFi IP, local MQTT Process, Telnet Process and Zigbee Transport are exposed.
- Diagnostic sampling is read-only and does not open a second connection to the Zigbee relay.
- Configure contains only network address (including static IP / DHCP recovery) and Wi-Fi change.
- No media/sound runtime, group membership, auxiliary MQTT subscription or shared-MQTT write is created for the Coordinator.
- No UART commands, lux requests, RGB cleanup, boot blinking or physical-button watcher migration run for this role.
- Temperature/HomeKit/lux and other former Coordinator entities are retired rather than displaying stale values.
- This integration neither stops hub services nor deletes WAV files. The separate Only Coordinator kit handles the on-hub profile.

Zigbee2MQTT owns the Coordinator connection. A typical serial section is:

```yaml
serial:
  port: tcp://HUB_IP:1886
  adapter: zoh
```

The Zigbee channel, PAN, network key and device database remain Zigbee2MQTT settings; this integration does not replace them.

## Router entities

- **Ring Light** with RGB color and brightness.
- **Illuminance**, including `adc_raw`, `millivolts` and the role-specific source as attributes.
- **Media Player** for streams and local playback.
- **M1S Media Group** and **Include in M1S Media Group** for synchronized playback across selected hubs.
- **Hub Volume** (the former Sound Playback Volume unique ID) and **Sound** selection. The number and individual media-player slider control the same volume. For temporary doorbell volume use `play_sound.volume_percent`; setting the shared number first still changes the radio. Fine Volume Trim is retired and removed on upgrade.
- One button for every discovered non-system WAV sound.
- **Physical Button** events: click, double through ten clicks, hold start, repeat and release.
- **Hub Connectivity**, **Hub Temperature**, **WiFi IP**, HomeKit, MQTT and Telnet process state.
- **JN5189 Router** diagnostic only for Router-role hubs.
- **MQTT configuration** state: `not_configured`, `pending`, `applied` or `failed`.

## Shared MQTT configuration

Open **Configure** on a Router and select **Shared MQTT - all hubs**. These settings are applied to Router-role hubs only, including routers added later. Coordinators are skipped. Offline routers synchronize after reconnect; failed writes retry after 60 seconds.

Use the LAN address of the same broker used by Home Assistant, not `localhost` or an internal add-on hostname that the hubs cannot resolve. This feature uses plain LAN MQTT without TLS and does not create broker users or modify Home Assistant's MQTT integration.

The username and password must use printable ASCII and may contain at most 80 characters combined. A blank password in a later edit keeps the stored password. The integration validates the broker login before saving, but publish ACLs still need to allow the hub topics. The button topic identity is preserved when the hub IP changes.

`applied` means that the hub configuration was written successfully; confirm actual delivery by pressing the physical button once. Credentials are stored in Home Assistant integration storage and in hub configuration backups, so both require normal private handling.

## Router sound and media management

- One WAV at a time can be uploaded from **Configure** and is stored under `/data/musics/music-ch`. ZIP archives are no longer accepted.
- Once transfer starts, the dialog displays `File 1 of 1`, the WAV filename and a percentage that advances as measured chunks are sent. It reaches 100% only after the hub-side size and MD5 checks succeed.
- Before writing, the WAV is preflighted against `/data`. An existing destination is counted as a replacement, and the upload is rejected if it would leave less than 8 MiB free. The same reserve applies to the direct `upload_sound` service.
- `/data/musics/music-us` is reserved for factory-reset system sounds. Its WAV files and any nested files are not exposed as Home Assistant sound buttons and never appear in the delete list.
- Manual deletion lists non-system `.wav` files below `/data/musics`, including the remaining original Aqara folders.
- Nothing is selected by default.
- After selecting files and pressing **Delete**, a short separate popup shows the selected count and the explicit confirmation control; it stays fully visible instead of scrolling with the file list.
- The selection is sent to the hub through a temporary manifest split into small chunks, preventing large selections from exceeding a Telnet command limit.
- Confirmed deletion is permanent and creates no backup archive. The complete manifest is validated first, the on-hub command independently blocks `music-us`, and success is accepted only when the deleted count matches the selection.
- Installation, startup and migration never delete sounds automatically.
- A successful upload or deletion reloads the integration and rebuilds the sound entities.

For a priority WAV on a Router, the arbiter suspends individual/group audio only
on that hub, confirms the audio device has been released, then starts the alert
with its temporary gain. Media mute is bypassed by default without flipping
mute state. After completion, Stop, error or cancellation, current media gain
must be restored before playback can resume, and current playback intent still
controls resume/rejoin. A newer sound owns its own token; stale cleanup cannot
stop it or restore media gain over it. The dedicated Coordinator has no WAV or
media pipeline. No per-volume WAV copies are made. Live handover remains to be
verified on the actual hubs.

If an individual source stops delivering PCM, the entity now reports `buffering`, stops its remote receiver and rebuilds it only after real PCM returns. A playout rebase records the lag, latest TCP drain duration and the most likely cause (`tcp_drain_timeout`, `tcp_drain_slow` or `ha_scheduler_or_other_await`). The orderly unload protection still stops the individual hub receiver before closing the local writer and adds no active watchdog on the hub.

The media group keeps one shared PCM history and one common playout clock. One 1.25-second TCP timeout is tolerated; confirmed faults quarantine only the affected hub. A returning hub waits silently, without historical PCM replay, for a common receiver prefill. Requests settle for three seconds and are coalesced, with at least 60 seconds between automatic barriers while healthy audio remains. The receiver-only barrier can briefly interrupt the group, but keeps FFmpeg and the source URL open. It skips excluded, offline, individual and priority-sound hubs. Failed receivers do not block the available cohort. Retry history resets after 30 seconds of admitted playback. A cached timing audit requests the same barrier only after three fresh, plausible relative ALSA queue-change samples; stale, slow and impossible samples are rejected. No per-hub resampling or blind timer-driven reset is enabled. Acoustic alignment still needs listening/hardware validation. The existing manual resync service remains available. Restored playback retains its bounded initial-cohort wait, and group Stop releases suspended individual players.

Local WAV completion is detected from the hub player exit status, polled every 500 ms. It no longer uses the old FFmpeg EOF cushion. Replacement and Stop target only the owned playback token and process identity. Explicit `play_url` WAVs download to hub RAM, not `/data`; stored WAVs require no download.

For Routers, the individual Media Player and the shared M1S Media Group, volume controls, radio playback, metadata updates and the existing Aqara sound buttons are retained from the confirmed base.

## Network management

The configuration flow supports DHCP, a static IPv4 address on the current subnet and a Wi-Fi network change through the installed recovery module. Before changing Wi-Fi, the hub returns to DHCP and tests the new network. The Wi-Fi password is not stored in Home Assistant. A network change can temporarily make the hub unavailable; use its new address when it reconnects.

## Available services

The integration registers `play_url`, `play_sound`, `upload_sound`, `delete_sound`, `refresh_sounds`, `reset_media_group`, `resync_media_group` and `update_media_metadata`. It also retains the advanced `run_command` service; use it only for commands you understand because it executes a shell command on the selected hub over Telnet.

Sound and media services reject a configured Coordinator before doing any work. Services remain globally registered for Router use; `run_command` remains an explicit administrator tool, not a restricted shell.

`play_sound` and priority-WAV `play_url` accept optional `volume_percent` and
`respect_mute` (default `false`). The former changes alert gain only, not the
shared media slider. The latter honors individual hub mute for that request;
group mute remains a group-media control. Sound buttons use the default bypass
policy and current individual hub slider. See `SOUND_MUTE_POLICY_RO.md` for
examples and the zero-volume case.

`delete_sound` requires `confirm: true`, rejects every path below `/data/musics/music-us` and deletes other valid WAV paths without creating a backup. When more than one hub is configured, provide the target `host` for hub-specific sound services.

## Validation and TEST status

See `VALIDATION.txt` for the current validation status and `TEST_REPORT.json` /
`TEST_LOG.txt` for the automated run identified there. A test report copied from
an older package is historical until a 0.37.19 run replaces it. No installation,
HA restart or live audio test has been performed for this build. The new mute
policy, restoration after manual changes, replacement/cancellation, common-clock
recovery and unchanged Coordinator guard require the matching local test run;
audible handover and synchronization still require actual hardware. Earlier
single-hub listening does not validate this final package or an overnight run.

The following is historical validation of the `0.37.5` base, not a new hardware test for this release:

- 20 isolated MQTT RGB/lux, telemetry, role, topic, UART-isolation, connectivity and Router-rejoin tests.
- 3 WAV priority and transport tests covering Coordinator MQTT, Router MQTT and Telnet fallback for a Router without the new capability.
- 9 direct WAV deletion, protected-system-folder and chunked-manifest tests.
- 8 storage, real-socket TCP transfer, monotonic progress, fallback and protected-path tests.
- 7 shared-MQTT persistence and recovery tests.
- 19 audio regression and loss-simulation tests covering group and individual volume precision, remote-before-local shutdown, scoped
  commands, buffering diagnostics, latest-request-wins, bounded restoration,
  individual-player release and single-member quarantine recovery.
- Python compilation plus JSON/YAML parsing.
- Shell syntax validation for every Router script and a static MIPS32 agent build with warnings treated as errors.
- That base passed all 66 isolated tests; its audio-transport hashes belong to
  that version's validation record, not the current 0.37.19 result.

Upload was also verified on Router `192.168.0.221`: 128044 bytes in 5.46 seconds, identical MD5, intermediate progress and confirmed removal of the temporary probe file.

The earlier `0.36.1` multi-delete path was hardware-verified on Coordinator `192.168.0.220` with 12 temporary files. The new `0.36.2` direct-delete and `music-us` protections are covered by isolated tests and do not modify a hub during installation.

The base release recorded Router agent `1.1.1` installation on `.200-.209` and `.222-.225`, with retained capability and the MQTT `prepare -> ports 12347/12348 -> stop -> cleanup` cycle checked on 14 hubs. These are historical records, not repeated installation by `0.37.6`. The former Coordinator agent is no longer used by this integration. No firmware is written by this package.

## Rollback

Restore the previous component from your backup (normally `0.37.18` for this
update) and restart Home Assistant. Check that its installed version loads
without errors. The previous 0.37.18 keeps the same sound policy but retains
the device-registry API warnings fixed here. Keep existing integration entries and Zigbee
pairings. This package changes no firmware, Zigbee data or original WAV files.
Router MQTT and Coordinator kit rollbacks remain separate procedures. If also
changing the optional supervision setup, follow `COORDINATOR_GUARD_RO.md`.
