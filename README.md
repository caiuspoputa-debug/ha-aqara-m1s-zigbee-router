# Aqara M1S Zigbee Coordinator + Router v0.37.15 TEST

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

1. Copy `custom_components/aqara_m1s_zigbee_router` into Home Assistant under `/config/custom_components/`.
2. Restart Home Assistant.
3. Open **Settings > Devices & services > Add integration** and select **Aqara M1S Zigbee Coordinator + Router**.
4. Enter the hub IPv4 address, Telnet port, user and password.
5. Select DHCP or a static address when the setup flow asks for the network mode.

The internal domain remains `aqara_m1s_zigbee_router`. Retained diagnostics and Router entities keep their unique IDs; former Coordinator media/IO entities are removed automatically. The physical Wi-Fi MAC is used as device identity when available, and the last confirmed Zigbee role is retained if Home Assistant starts while the hub is temporarily offline. Back up HA before upgrading; old Coordinator controls referenced in dashboards/automations must be removed there too.

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
- **Hub Volume** (the former Sound Playback Volume unique ID), **Fine Volume Trim** and **Sound** selection. The number and individual media-player slider now control the same volume; old automations setting WAV volume also change radio volume. The restored media-player level is authoritative, not the former WAV value.
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

For a stored WAV on a Router, the existing priority arbiter suspends individual/group audio only on that hub, starts `aplay` on the existing file with the shared local gain, and restores playback only if current intent still permits it. The dedicated Coordinator has no WAV or media pipeline. No WAV copies are made. The prior handover rules are retained and regression-tested, but the complete new handover still needs a live check.

If an individual source stops delivering PCM, the entity now reports `buffering`, stops its remote receiver and rebuilds it only after real PCM returns. A playout rebase records the lag, latest TCP drain duration and the most likely cause (`tcp_drain_timeout`, `tcp_drain_slow` or `ha_scheduler_or_other_await`). The orderly unload protection still stops the individual hub receiver before closing the local writer and adds no active watchdog on the hub.

The media group keeps one shared PCM history and one common playout clock. One 1.25-second TCP timeout is tolerated; confirmed faults quarantine only the affected hub. A returning hub waits silently, without historical PCM replay, for a common receiver prefill. Requests settle for three seconds and are coalesced, with at least 60 seconds between automatic barriers while healthy audio remains. The receiver-only barrier can briefly interrupt the group, but keeps FFmpeg and the source URL open. It skips excluded, offline, individual and priority-sound hubs. Failed receivers do not block the available cohort. Retry history resets after 30 seconds of admitted playback. A cached timing audit requests the same barrier only after three fresh, plausible relative ALSA queue-change samples; stale, slow and impossible samples are rejected. No per-hub resampling or blind timer-driven reset is enabled. Acoustic alignment still needs listening/hardware validation. The existing manual resync service remains available. Restored playback retains its bounded initial-cohort wait, and group Stop releases suspended individual players.

Local WAV completion is detected from the hub player exit status, polled every 500 ms. It no longer uses the old FFmpeg EOF cushion. Replacement and Stop target only the owned playback token and process identity. Explicit `play_url` WAVs download to hub RAM, not `/data`; stored WAVs require no download.

For Routers, the individual Media Player and the shared M1S Media Group, volume controls, radio playback, metadata updates and the existing Aqara sound buttons are retained from the confirmed base.

## Network management

The configuration flow supports DHCP, a static IPv4 address on the current subnet and a Wi-Fi network change through the installed recovery module. Before changing Wi-Fi, the hub returns to DHCP and tests the new network. The Wi-Fi password is not stored in Home Assistant. A network change can temporarily make the hub unavailable; use its new address when it reconnects.

## Available services

The integration registers `play_url`, `play_sound`, `upload_sound`, `delete_sound`, `refresh_sounds`, `reset_media_group`, `resync_media_group` and `update_media_metadata`. It also retains the advanced `run_command` service; use it only for commands you understand because it executes a shell command on the selected hub over Telnet.

Sound and media services reject a configured Coordinator before doing any work. Services remain globally registered for Router use; `run_command` remains an explicit administrator tool, not a restricted shell.

`delete_sound` requires `confirm: true`, rejects every path below `/data/musics/music-us` and deletes other valid WAV paths without creating a backup. When more than one hub is configured, provide the target `host` for hub-specific sound services.

## Validation and TEST status

See `TEST_REPORT.json`, `TEST_LOG.txt` and `VALIDATION.txt` for this version's actual automated results. Tests cover ordered transport, common-clock recovery, priority and cancellation, volume aliases, local gain acknowledgement, space checks and Coordinator isolation. Earlier listening on one hub confirmed local volume changes, but did not validate this final package, its WAV conversion wrapper, latency, or multiroom acoustic synchronization. Simulation is not proof of an overnight hardware test.

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
- All 66 isolated tests pass. The reviewed hashes of both audio transports are
  recorded in `VALIDATION.txt`.

Upload was also verified on Router `192.168.0.221`: 128044 bytes in 5.46 seconds, identical MD5, intermediate progress and confirmed removal of the temporary probe file.

The earlier `0.36.1` multi-delete path was hardware-verified on Coordinator `192.168.0.220` with 12 temporary files. The new `0.36.2` direct-delete and `music-us` protections are covered by isolated tests and do not modify a hub during installation.

The base release recorded Router agent `1.1.1` installation on `.200-.209` and `.222-.225`, with retained capability and the MQTT `prepare -> ports 12347/12348 -> stop -> cleanup` cycle checked on 14 hubs. These are historical records, not repeated installation by `0.37.6`. The former Coordinator agent is no longer used by this integration. No firmware is written by this package.

## Rollback

For this audio prototype, restore the backed-up `0.37.13` component and restart Home Assistant. The older receiver paths do not select the versioned local ALSA configuration; unused helper files may remain under `/data/m1s_audio_03714`. This build changes no firmware, Zigbee data or original WAV files. Router MQTT and Coordinator kit rollbacks remain separate procedures.
