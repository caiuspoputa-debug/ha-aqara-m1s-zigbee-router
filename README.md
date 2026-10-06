# Aqara M1S Zigbee Coordinator + Router v0.37.1 TEST

Local Home Assistant integration for identical Aqara M1S Gen 1 / JN5189 hubs prepared either as Zigbee Routers or as a Zigbee-on-Host Coordinator. The runtime role is detected from the hub and stored in the Home Assistant config entry; it is never selected from the IP address.

Version `0.37.1 TEST` prevents integration reload or update from stopping the Coordinator's persistent TCP/UART relay. It retains the deterministic individual and group radio playback, dual-path connectivity and all Zigbee, MQTT IO, WAV upload/deletion and stored-sound behavior from `0.37.0`. This package does not write or flash the JN5189.

## Requirements

- Home Assistant `2024.1.0` or newer.
- Local network access from Home Assistant to the hub.
- Telnet enabled on the hub; default connection is port `23`, user `admin`, blank password.
- A compatible Router setup; fast stored-WAV commands require Router MQTT IO `1.1.1`. Routers without that capability automatically retain the established Telnet WAV path.
- Coordinator complete MQTT kit `1.2.3`, or a compatible runtime with `M1S_IO_V2` sideband support.
- An MQTT broker reachable through its LAN address for physical-button events, shared MQTT configuration and IO for both roles.
- Zigbee2MQTT with the `zoh` adapter when the hub is used as Coordinator.

## Installation and update

1. Copy `custom_components/aqara_m1s_zigbee_router` into Home Assistant under `/config/custom_components/`.
2. Restart Home Assistant.
3. Open **Settings > Devices & services > Add integration** and select **Aqara M1S Zigbee Coordinator + Router**.
4. Enter the hub IPv4 address, Telnet port, user and password.
5. Select DHCP or a static address when the setup flow asks for the network mode.

The internal domain remains `aqara_m1s_zigbee_router`, so an existing installation can be upgraded without recreating its entities. The physical Wi-Fi MAC is used as device identity when available, and the last confirmed Zigbee role is retained if Home Assistant starts while the hub is temporarily offline.

## Router and Coordinator behavior

| Function | Router role | Coordinator role |
| --- | --- | --- |
| Zigbee transport | Existing JN5189 Router runtime | Zigbee-on-Host through `tcp://HUB_IP:1886` |
| Ring Light | Persistent MQTT to A5; legacy fallback only before upgrade activation | MQTT command to persistent agent, then isolated `M1S_IO_V2` sideband |
| Illuminance | Retained MQTT state; serialized A6 sample every 30 seconds | Retained MQTT state; on-hub sample every 60 seconds |
| Stored WAV | MQTT prepare/stop with agent `1.1.1`; automatic Telnet fallback | MQTT prepare/stop |
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
- The Router agent handles only local WAV receiver preparation and stop. Radio, media play/pause, volume, mute, FFmpeg, PCM transport and group synchronization are not moved into the agent.

## Coordinator safety and RGB/lux

- Home Assistant cannot stop the Coordinator. There is no switch, options form, service or internal method for Coordinator ON/OFF.
- A stale `*_coordinator_radio` entity from an older version is removed automatically from the entity registry.
- Coordinator Ring Light runs only after a Home Assistant light command.
- The persistent Coordinator agent serializes Ring Light and illuminance operations through `/tmp/m1s-coordinator-io.sock`; Home Assistant never opens a Telnet sideband command.
- Coordinator Illuminance is sampled on the hub every 60 seconds and is published as retained MQTT state. Home Assistant may request an immediate refresh over MQTT.
- Topics follow the Coordinator's current address identity (`m1s/220/...` for `192.168.0.220`), never the historical suffix retained in old entity IDs.
- The helper response must be one valid JSON object with protocol version `1`, capabilities `3`, a valid RGB triplet and bounded ADC/lux values.
- The sideband path does not connect to port `1886`, does not send Router A5/A6 frames and does not invoke Router UART cleanup.
- An invalid or missing response makes only the MQTT IO features unavailable. It cannot issue a Coordinator OFF command or replace the ZOH owner of port `1886`.
- An invalid lux measurement is never published as zero.

Zigbee2MQTT owns the Coordinator connection. A typical serial section is:

```yaml
serial:
  port: tcp://HUB_IP:1886
  adapter: zoh
```

The Zigbee channel, PAN, network key and device database remain Zigbee2MQTT settings; this integration does not replace them.

## Main entities

- **Ring Light** with RGB color and brightness.
- **Illuminance**, including `adc_raw`, `millivolts` and the role-specific source as attributes.
- **Media Player** for streams and local playback.
- **M1S Media Group** and **Include in M1S Media Group** for synchronized playback across selected hubs.
- **Sound Playback Volume**, **Fine Volume Trim** and **Sound** selection.
- One button for every discovered non-system WAV sound.
- **Physical Button** events: click, double through ten clicks, hold start, repeat and release.
- **Hub Connectivity**, **Hub Temperature**, **WiFi IP**, HomeKit, MQTT and Telnet process state.
- **JN5189 Router** diagnostic only for Router-role hubs.
- **MQTT configuration** state: `not_configured`, `pending`, `applied` or `failed`.

## Shared MQTT configuration

Open **Configure** on any managed hub and select **Shared MQTT - all hubs**. These settings are integration-wide and are applied to every Router and Coordinator, including hubs added later. Offline hubs synchronize after reconnect; failed writes retry after 60 seconds.

Use the LAN address of the same broker used by Home Assistant, not `localhost` or an internal add-on hostname that the hubs cannot resolve. This feature uses plain LAN MQTT without TLS and does not create broker users or modify Home Assistant's MQTT integration.

The username and password must use printable ASCII and may contain at most 80 characters combined. A blank password in a later edit keeps the stored password. The integration validates the broker login before saving, but publish ACLs still need to allow the hub topics. The button topic identity is preserved when the hub IP changes.

`applied` means that the hub configuration was written successfully; confirm actual delivery by pressing the physical button once. Credentials are stored in Home Assistant integration storage and in hub configuration backups, so both require normal private handling.

## Sound and media management

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

For a stored WAV, the confirmed priority sequence is preserved exactly: current individual/group playback is suspended, the WAV runs through the existing TCP/FFmpeg/aplay path, and the remembered playback is restored after completion. On the Coordinator, MQTT replaces only the command that prepares or stops this dedicated WAV pipeline. On a Router, the complete WAV path remains on the existing implementation. MQTT does not transport radio/group audio and does not alter synchronization.

If an individual source stops delivering PCM, the entity now reports `buffering`, stops its remote receiver and rebuilds it only after real PCM returns. A playout rebase records the lag, latest TCP drain duration and the most likely cause (`tcp_drain_timeout`, `tcp_drain_slow` or `ha_scheduler_or_other_await`). The orderly unload protection still stops the individual hub receiver before closing the local writer and adds no active watchdog on the hub.

The media group keeps one shared PCM history and one common playout clock. Adaptive synchronization, per-hub resampling and periodic automatic resync remain disabled. A receiver is rebuilt independently only after three consecutive stale ALSA samples, taken five seconds apart. Restored playback waits up to 30 seconds for the complete selected cohort, then starts the available hubs and admits missing hubs through the existing late-join path. Manual Play allows a one-second initial cohort window. The newest Play/Stop request always wins, and group Stop or hard reset releases every suspended individual player.

After FFmpeg completes a WAV normally, the integration keeps the path open for 500 ms before remote stop and playback restoration. This cushion was 400 ms in `0.36.0`; it does not apply to manual Stop, FFmpeg errors, radio or media-group playback.

The individual Media Player and the shared M1S Media Group, volume controls, radio playback, metadata updates and the existing Aqara sound buttons are retained from the confirmed base.

## Network management

The configuration flow supports DHCP, a static IPv4 address on the current subnet and a Wi-Fi network change through the installed recovery module. Before changing Wi-Fi, the hub returns to DHCP and tests the new network. The Wi-Fi password is not stored in Home Assistant. A network change can temporarily make the hub unavailable; use its new address when it reconnects.

## Available services

The integration registers `play_url`, `play_sound`, `upload_sound`, `delete_sound`, `refresh_sounds`, `reset_media_group`, `resync_media_group` and `update_media_metadata`. It also retains the advanced `run_command` service; use it only for commands you understand because it executes a shell command on the selected hub over Telnet.

`delete_sound` requires `confirm: true`, rejects every path below `/data/musics/music-us` and deletes other valid WAV paths without creating a backup. When more than one hub is configured, provide the target `host` for hub-specific sound services.

## Validation and TEST status

The `0.37.1` source passed:

- 19 isolated MQTT RGB/lux, telemetry, role, topic, UART-isolation, connectivity and Router-rejoin tests.
- 3 WAV priority and transport tests covering Coordinator MQTT, Router MQTT and Telnet fallback for a Router without the new capability.
- 9 direct WAV deletion, protected-system-folder and chunked-manifest tests.
- 8 storage, real-socket TCP transfer, monotonic progress, fallback and protected-path tests.
- 7 shared-MQTT persistence and recovery tests.
- 9 audio regression tests covering remote-before-local shutdown, scoped
  commands, buffering diagnostics, latest-request-wins, bounded restoration,
  individual-player release and member-only receiver recovery.
- Python compilation plus JSON/YAML parsing.
- Shell syntax validation for every Router script and a static MIPS32 agent build with warnings treated as errors.
- All 56 isolated tests pass. The reviewed hashes of both audio transports are
  recorded in `VALIDATION.txt`.

Upload was also verified on Router `192.168.0.221`: 128044 bytes in 5.46 seconds, identical MD5, intermediate progress and confirmed removal of the temporary probe file.

The earlier `0.36.1` multi-delete path was hardware-verified on Coordinator `192.168.0.220` with 12 temporary files. The new `0.36.2` direct-delete and `music-us` protections are covered by isolated tests and do not modify a hub during installation.

Router agent `1.1.1` was installed on `.200-.209` and `.222-.225`. Retained capability and the complete MQTT `prepare -> ports 12347/12348 -> stop -> cleanup` cycle were confirmed on all 14 available hubs. `.221` remains in scope but is pending because it is unreachable. The Coordinator agent remains validated on `.220`. No firmware is written by this package.

## Rollback

If Router MQTT IO does not behave correctly, run the Router kit rollback, restore integration `0.35.0`, and restart Home Assistant. The Coordinator kit retains its own rollback. Replacing the integration does not alter firmware, Zigbee network data or sound files.
