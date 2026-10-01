# Aqara M1S Zigbee Coordinator + Router v0.35.0 TEST

Local Home Assistant integration for identical Aqara M1S Gen 1 / JN5189 hubs prepared either as Zigbee Routers or as a Zigbee-on-Host Coordinator. The runtime role is detected from the hub and stored in the Home Assistant config entry; it is never selected from the IP address.

Version `0.35.0 TEST` is built on the confirmed `0.34.2 TEST` base. On the Coordinator only, a persistent on-hub MQTT agent replaces per-command Telnet for Ring Light, illuminance, diagnostic telemetry and preparation of stored WAV playback. Routers keep their existing paths. Radio playback, the shared media group, synchronization, priority arbitration and the TCP/FFmpeg/aplay audio transport are unchanged. This is an integration package, not a firmware kit: it does not write or flash the JN5189.

## Requirements

- Home Assistant `2024.1.0` or newer.
- Local network access from Home Assistant to the hub.
- Telnet enabled on the hub; default connection is port `23`, user `admin`, blank password.
- A compatible Router setup, or Coordinator MQTT IO kit `1.1.0` with `M1S_IO_V2` sideband support.
- An MQTT broker reachable through its LAN address for physical-button events, shared MQTT configuration and Coordinator IO.
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
| Ring Light | Existing UART A5 path | MQTT command to persistent agent, then isolated `M1S_IO_V2` sideband |
| Illuminance | Existing UART A6 path, every 15 seconds | Retained MQTT state; on-hub sample every 60 seconds |
| Join another coordinator | Available with explicit confirmation | Hidden and blocked |
| Coordinator ON/OFF | Not applicable | Deliberately absent |

Router RGB, lux and rejoin behavior remains unchanged. Coordinator RGB/lux never falls back to the Router UART path.

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
- One button for every discovered Aqara WAV sound.
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

- WAV and ZIP uploads are available from **Configure** and are stored under `/data/musics/music-ch`.
- Manual deletion lists every `.wav` below `/data/musics`, including original Aqara folders.
- Nothing is selected by default.
- The confirmation control is displayed above the file list and must be enabled explicitly.
- Before deletion, a mandatory archive is created under `/data/m1s_sound_backups`; if backup fails, deletion is aborted.
- Installation, startup and migration never delete sounds automatically.
- A successful upload or deletion reloads the integration and rebuilds the sound entities.

For a stored WAV, the confirmed priority sequence is preserved exactly: current individual/group playback is suspended, the WAV runs through the existing TCP/FFmpeg/aplay path, and the remembered playback is restored after completion. MQTT replaces only the Coordinator command that prepares or stops this dedicated WAV pipeline. It does not transport radio/group audio and does not alter synchronization.

The individual Media Player and the shared M1S Media Group, volume controls, radio playback, metadata updates and the existing Aqara sound buttons are retained from the confirmed base.

## Network management

The configuration flow supports DHCP, a static IPv4 address on the current subnet and a Wi-Fi network change through the installed recovery module. Before changing Wi-Fi, the hub returns to DHCP and tests the new network. The Wi-Fi password is not stored in Home Assistant. A network change can temporarily make the hub unavailable; use its new address when it reconnects.

## Available services

The integration registers `play_url`, `play_sound`, `upload_sound`, `delete_sound`, `refresh_sounds`, `reset_media_group`, `resync_media_group` and `update_media_metadata`. It also retains the advanced `run_command` service; use it only for commands you understand because it executes a shell command on the selected hub over Telnet.

`delete_sound` requires `confirm: true` and always performs backup-before-delete validation. When more than one hub is configured, provide the target `host` for hub-specific sound services.

## Validation and TEST status

The `0.35.0` source passed:

- 10 isolated Coordinator MQTT RGB/lux, telemetry, topic and transport-safety tests.
- 1 dedicated priority test confirming `suspend -> WAV -> stop WAV -> resume`.
- 5 WAV deletion and mandatory-backup tests.
- 7 shared-MQTT persistence and recovery tests.
- Python compilation plus JSON/YAML parsing.
- Byte-for-byte comparison proving `media_player.py` (including radio playback) and `media_group.py` are unchanged from `0.34.2`.

A temporary agent was hardware-tested on Coordinator `192.168.0.220`: RGB ON/OFF, lux, retained telemetry and one established Z2M connection on port `1886` were confirmed. No firmware was written. The permanent agent must be activated only after this integration is installed and Home Assistant has restarted, so the former Telnet sideband poller and the new agent never run together.

## Rollback

If Coordinator MQTT IO does not behave correctly, disable it in `/data/m1s_coordinator/mqtt_io.conf`, stop `mqtt_io_service.sh`, restore integration `0.34.2`, and restart Home Assistant. Replacing the integration does not alter firmware, Zigbee network data or sound files.
