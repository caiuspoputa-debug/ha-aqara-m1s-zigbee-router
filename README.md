# Aqara M1S Zigbee Router

Home Assistant custom integration for Aqara M1S Gen 1 hubs converted to an
NXP JN5189 BDB Zigbee Router.

Version: **0.1.0 (test release)**

## Requirements

- Aqara M1S Gen 1 (`lumi.gateway.aeu01`)
- JN5189 router firmware with RGB UART protocol enabled
- Telnet enabled on the Linux side of the hub
- `/dev/ttyS1` free from the original `mzigbee_agent`
- GPIO33=`1`, GPIO18=`0`

For compatible stock firmware, the validated temporary Telnet button sequence
is `5-2-2-2-2-2-2`. This belongs to the hub preparation procedure and is not
executed by the Home Assistant integration.

## Features

- RGB ring light through the validated five-byte UART protocol
- brightness scaling from Home Assistant
- radio streaming
- local WAV sound buttons and sound selector
- playback volume helper
- Linux, Wi-Fi, process and JN5189 status sensors
- shared 15-second online/offline monitoring
- WAV upload, deletion and list refresh actions

When the hub is offline, the light, radio, volume and sensors become
unavailable. Sound buttons intentionally remain visible.

## Installation

Copy `custom_components/aqara_m1s_zigbee_router` to Home Assistant's
`/config/custom_components/`, restart Home Assistant, then add the integration
from Settings > Devices & services.

The integration domain is `aqara_m1s_zigbee_router`; it can coexist with
`aqara_m1s_local`.

## RGB protocol

The integration writes this frame to `/dev/ttyS1`:

```text
A5 RED GREEN BLUE CHECKSUM
CHECKSUM = A5 XOR RED XOR GREEN XOR BLUE
```

## Sound management

The integration provides these Home Assistant actions:

- `aqara_m1s_zigbee_router.upload_sound`
- `aqara_m1s_zigbee_router.delete_sound`
- `aqara_m1s_zigbee_router.refresh_sounds`

Only `.wav` files below `/data/musics` are accepted. After uploading or
deleting a file, run `refresh_sounds` to recreate the selector and sound
buttons.

Uploads are validated before transfer. The accepted format is uncompressed PCM,
mono, 32000 Hz, signed 32-bit little-endian. The validated hub BusyBox contains
the `base64` decoder used for binary transfer.

Sound playback keeps the v0.5.9 FFmpeg pipeline because it provides fine volume
control and avoids the Aqara LED side effects of the historical `basis_cli`
route. Radio keeps the v0.5.9 PID-based cleanup and never runs `killall nc`, so
other `nc` users on the hub are not interrupted.
