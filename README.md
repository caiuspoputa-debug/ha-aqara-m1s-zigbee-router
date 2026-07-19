# Aqara M1S Zigbee Router

[Română](README_RO.md) | **English**

Home Assistant custom integration for an Aqara M1S Gen 1 hub converted to an
NXP JN5189 BDB Zigbee Router, with local RGB ring, illuminance, audio and hub
diagnostics.

Current version: **0.2.4 (test release)**

> This project is for the Aqara M1S Gen 1 model `lumi.gateway.aeu01`. Flashing
> the JN5189 is an advanced operation. Keep a verified backup and never write
> EFUSE, ROM, Config or PSECT.

## What changed in v0.2.4

- bilingual Configure labels, with Romanian displayed first
- immediate sound-catalogue refresh after WAV upload or deletion
- controlled full integration reload through **Finalizare și închidere / Finish and close**
- clearer documentation for upload, deletion, download and final reload behavior
- the Home Assistant **X** close control remains frontend-managed; using it skips only
  the final config-entry reload, not the immediate sound-catalogue refresh

## Validated configuration

- Hub: Aqara M1S Gen 1 (`lumi.gateway.aeu01`)
- Stock firmware used during preparation: `3.1.3_0009`
- Linux: MIPS, kernel 3.10.90, BusyBox 1.22.1
- Zigbee SoC: NXP JN5189
- Zigbee role after conversion: BDB Router
- Zigbee UART: `/dev/ttyS1`, 115200 8N1
- JN5189 reset: GPIO18, asserted at `1`
- JN5189 ISP selection: GPIO33, ISP=`0`, normal boot=`1`
- Managed sound directory: `/data/musics/music-ch`
- Integration domain: `aqara_m1s_zigbee_router`

## Features

- NXP BDB Zigbee Router operation with Zigbee2MQTT
- RGB ring light with brightness and color control
- direct illuminance readings from the JN5189, without MQTT
- native Home Assistant media browsing and direct URL playback
- radio streaming through Home Assistant FFmpeg
- local Aqara WAV playback buttons
- browser upload and protected deletion of custom WAV files
- playback-volume control
- hub temperature from the validated `persist.sys.temperature` property
- Wi-Fi IP, process and JN5189 state diagnostics
- shared 15-second online/offline monitoring
- automatic red boot-ring shutdown after the hub reconnects to Wi-Fi
- confirmed migration of the router to a different Zigbee coordinator

When the hub is offline, the light, media player, volume and live sensors become
unavailable. Sound buttons intentionally remain visible. Upload and deletion refresh the sound catalogue immediately. The full config-entry
reload is performed only through **Finalizare și închidere / Finish and close**, so
the remaining entities and device information are rebuilt in a controlled way.

## Current RGB + lux + rejoin firmware

The v0.2.1-compatible test image uses **PIO19/ADC5** for ambient light and adds
the protected UART rejoin command:

```text
File: jn5189_router_rgb_lux_rejoin_test.bin
Size: 209296 bytes (0x33190)
Sector-rounded image area: 0x33200
Memory: ID 0 / FLASH
```

This image was written successfully on 2026-07-19 with SPSDK and the router
returned online in Zigbee2MQTT without a full-chip erase. Before publishing a
binary, calculate and record its SHA256; never assume that a similarly named
build has the same hash.

## Complete installation from a stock hub

### 1. Add the hub to Xiaomi Home

1. Factory-reset or place the hub in pairing mode.
2. Double-press the hub button to switch from Aqara mode to Xiaomi/Mi Home
   mode.
3. Add it in Xiaomi Home/Mi Home using a 2.4 GHz Wi-Fi network.
4. Use the correct Xiaomi account region.
5. Reserve the hub IP address in the router DHCP configuration.

The double-press changes the application ecosystem; it is not the Telnet
sequence described below.

### 2. Extract the MiIO token

1. Install **Xiaomi Gateway 3** by AlexxIT from HACS.
2. Restart Home Assistant when requested.
3. Add the Xiaomi Gateway 3 integration.
4. Sign in with the same Xiaomi account and region used by Xiaomi Home.
5. Find model `lumi.gateway.aeu01` and copy its MiIO token.

A valid MiIO token contains exactly 32 hexadecimal characters. Treat it as a
password and never publish it.

Verify it in Windows PowerShell:

```powershell
python -m pip install python-miio
python -m miio.cli device --ip HUB_IP --token MIIO_TOKEN info
```

### 3. Enable temporary Telnet

The physically validated temporary button sequence is:

```text
5-2-2-2-2-2-2
```

If the compatible stock firmware accepts it, connect with:

```powershell
telnet HUB_IP
```

Try user `admin` with an empty password; if needed, try `root` with an empty
password.

The MiIO alternative is:

```powershell
python -m miio.cli device --ip HUB_IP --token MIIO_TOKEN raw_command set_ip_info '{"ssid":"\"\"","pswd":"123123 ; passwd -d admin ; passwd -d root ; telnetd"}'
```

Telnet is unencrypted and must remain LAN-only. The physical or MiIO method can
be temporary.

#### Persistent Telnet and Router startup

The following `post_init.sh` is for a newly prepared Router hub. If the hub is
already converted and its current boot script works, back it up and do not
overwrite it unnecessarily.

```sh
mkdir -p /data/scripts
[ -f /data/scripts/post_init.sh ] && cp /data/scripts/post_init.sh /data/scripts/post_init.sh.bak

cat > /data/scripts/post_init.sh <<'EOF'
#!/bin/sh

LOG_FILE="/tmp/post_init.log"

wait_for_wifi()
{
    i=0
    while [ "$i" -lt 120 ]; do
        if ifconfig wlan0 2>/dev/null | grep -q 'inet addr'; then
            return 0
        fi
        sleep 2
        i=$((i+2))
    done
    return 1
}

# Required for the original Linux, Wi-Fi, HomeKit and audio services.
fw_manager.sh -r &

(
    wait_for_wifi
    sleep 5
    fw_manager.sh -t -k &
    echo "$(date) Telnet start requested." >> "$LOG_FILE"

    # Let the stock services finish starting, then free the JN5189 UART.
    sleep 20
    for p in $(ps | grep '[a]pp_monitor' | awk '{print $1}'); do
        kill -STOP "$p" 2>/dev/null
    done
    for p in $(ps | grep '[m]zigbee_agent' | awk '{print $1}'); do
        kill "$p" 2>/dev/null
    done

    stty -F /dev/ttyS1 115200 raw -echo
    echo 1 > /sys/class/gpio/gpio33/value
    echo 1 > /sys/class/gpio/gpio18/value
    sleep 1
    echo 0 > /sys/class/gpio/gpio18/value
    echo "$(date) Router UART released and JN5189 started." >> "$LOG_FILE"
) &

exit 0
EOF

chmod +x /data/scripts/post_init.sh
/bin/sh -n /data/scripts/post_init.sh
echo "syntax=$?"
sync
```

The expected syntax result is `syntax=0`. Do not reboot if it is different.
After a reboot, wait for Wi-Fi and verify:

```sh
cat /tmp/post_init.log
ps | grep '[t]elnetd'
ps | grep '[m]zigbee_agent'
cat /sys/class/gpio/gpio33/value
cat /sys/class/gpio/gpio18/value
```

Telnet must be running, `mzigbee_agent` must not own the UART, and the GPIO
values must be `1` then `0`. This script intentionally does not create the old
MQTT tunnel; v0.2.0 reads lux directly from the JN5189 and does not require
MQTT.

### 4. Back up and program the JN5189

Install SPSDK on Windows:

```powershell
python --version
python -m pip install "spsdk[dk6]"
python -m spsdk.apps.dk6prog --help
```

The validated network transport is pyserial `socket://` through BusyBox `nc`.
The procedure below uses temporary TCP port `1888`. Keep it inside the trusted
LAN and close it immediately after programming.


#### 4.0 Hub already added to the Home Assistant integration

If the hub is already configured in the **Aqara M1S Zigbee Router** integration,
temporarily disable the integration or stop Home Assistant before programming the
JN5189.

The integration may automatically open Telnet sessions and start a blocking
process:

```sh
cat /dev/ttyS1
```

This process owns the UART. In this condition, the TCP connection on port `1888`
may still work and SPSDK may send the ISP frame, but the JN5189 does not reply and
the command ends with:

```text
GENERAL ERROR: TimeoutError
```

Killing only the `cat` process is not enough if the integration recreates it.
After disabling the integration or stopping Home Assistant, verify on the hub:

```sh
ps | grep ttyS1
ps | grep 1886
ps | grep 1888
ps | awk '$5=="-sh"{print $1,$5}'
```

The correct state before entering ISP is:

- no `cat /dev/ttyS1`;
- no old listener on `1886` or `1888`;
- only the Telnet session used for the intervention.

If old Telnet shells recreate `cat /dev/ttyS1`, identify the process parent:

```sh
for p in $(ps | grep 'cat /dev/ttyS1' | grep -v grep | awk '{print $1}'); do
  echo "CAT=$p"
  grep PPid /proc/$p/status
done
```

Then identify the parent shell:

```sh
tr '\0' ' ' < /proc/PARENT_PID/cmdline
echo
cat /proc/PARENT_PID/status | grep PPid
```

If it is an old Telnet shell and not the current session, stop it with:

```sh
kill -9 PARENT_PID
```

Do not use `killall nc`, because the hub may have other active `nc` tunnels.

After a physical restart, stock services may start again. Stop the watchdog and
free the UART before ISP:

```sh
for p in $(ps | grep '[a]pp_monitor' | awk '{print $1}'); do
  kill -STOP "$p" 2>/dev/null
done

for p in $(ps | grep '[m]zigbee_agent' | awk '{print $1}'); do
  kill -9 "$p" 2>/dev/null
done

for p in $(ps | grep '[c]at /dev/ttyS1' | awk '{print $1}'); do
  kill -9 "$p" 2>/dev/null
done

ps | grep app_monitor
ps | grep mzigbee
ps | grep ttyS1
```

The validated state is:

- `app_monitor.sh` in state `T`;
- `mzigbee_agent` absent or zombie only;
- no real process owning `/dev/ttyS1`.


#### 4.1 Prepare the hub and enter ISP

Run in Telnet on the hub. This block stops the stock Zigbee owner, puts
GPIO33 low for ISP, resets the JN5189 and starts a self-restarting direct
TCP-to-UART listener. It deliberately does **not** use a FIFO or `cat` process.

```sh
PORT=1888
LOOP_PID_FILE=/var/tmp/jn1888_loop.pid
LOOP_LOG=/var/tmp/jn1888_loop.log

# Stop an older programming loop recorded by this procedure.
if [ -f "$LOOP_PID_FILE" ]; then
    OLD_LOOP=$(cat "$LOOP_PID_FILE" 2>/dev/null)
    [ -n "$OLD_LOOP" ] && kill -9 "$OLD_LOOP" 2>/dev/null
    rm -f "$LOOP_PID_FILE"
fi

# Remove any leftover listener on the temporary port.
for p in $(ps w | grep "[n]c -l -p $PORT" | awk '{print $1}'); do
    kill -9 "$p" 2>/dev/null
done

# Prevent the stock watchdog from restarting mzigbee_agent.
for p in $(ps w | grep '[a]pp_monitor' | awk '{print $1}'); do
    kill -STOP "$p" 2>/dev/null
done
for p in $(ps w | grep '[m]zigbee_agent' | awk '{print $1}'); do
    kill -9 "$p" 2>/dev/null
done

stty 115200 cs8 -parenb -cstopb cread clocal -crtscts \
  -ignbrk -brkint -ignpar -parmrk -inpck -istrip \
  -ixon -ixoff -icanon -echo min 1 time 0 < /dev/ttyS1

# ISP=0 on GPIO33; reset is asserted with GPIO18=1.
echo out > /sys/class/gpio/gpio33/direction
echo out > /sys/class/gpio/gpio18/direction
echo 0 > /sys/class/gpio/gpio33/value
echo 1 > /sys/class/gpio/gpio18/value
sleep 1
echo 0 > /sys/class/gpio/gpio18/value
sleep 1

(
    while true; do
        nc -l -p "$PORT" < /dev/ttyS1 > /dev/ttyS1
        sleep 1
    done
) >"$LOOP_LOG" 2>&1 &
LOOP_PID=$!
echo "$LOOP_PID" > "$LOOP_PID_FILE"

sleep 3
netstat -lnt | grep ":$PORT"
```

The important confirmation is a `LISTEN` line for port `1888`. A single `nc`
session exits after each SPSDK connection; the loop starts the next listener.
Therefore, check `netstat` before every SPSDK command.

#### 4.2 Verify communication

PowerShell:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n info
```

Expected output includes:

```text
Detected DEVICE: JN5189
FLASH  Memory ID 0  Base 0x0  Length 0x9DE00  Sector 0x200
```

After `info`, return to Telnet and confirm the loop has recreated the listener:

```sh
netstat -lnt | grep 1888
```

#### 4.3 Back up a stock hub

Before the first conversion, read Memory ID 0 and keep the backup in two safe
locations:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n read -o ".\jn5189_original_flash.bin" 0x0 646656 0
Get-FileHash ".\jn5189_original_flash.bin" -Algorithm SHA256
```

Check `LISTEN` again before any following SPSDK command.

### 5. Write or update the firmware

Verify the exact file selected for flashing:

```powershell
Get-Item ".\jn5189_router_rgb_lux_rejoin_test.bin"
Get-FileHash ".\jn5189_router_rgb_lux_rejoin_test.bin" -Algorithm SHA256
```

For an update from an already working Router firmware, write directly at
address `0x0` **without a full erase**. This was the successful 2026-07-19
procedure and preserved the existing Zigbee association:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n write 0x0 ".\jn5189_router_rgb_lux_rejoin_test.bin"
```

Successful output for this build:

```text
Written 209296 bytes to memory ID 0 at address 0x0
```

For a first conversion or recovery where an image-area erase is genuinely
required, erase only the sector-rounded application area, never the full chip:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n erase 0x0 0x33200 0
```

Then confirm `LISTEN` again and execute the `write` command. Never write EFUSE,
ROM, Config, PSECT or pFLASH.


#### 5.2 Validated recovery after `TimeoutError`

The validated procedure for a hub that had already been flashed but no longer
responded reliably in ISP was:

1. physically power-cycle the hub;
2. temporarily disable the Home Assistant integration;
3. suspend `app_monitor.sh`;
4. stop `mzigbee_agent`;
5. remove all `cat /dev/ttyS1` processes and stale Telnet shells recreating them;
6. confirm that `/dev/ttyS1`, `1886` and `1888` are free;
7. set GPIO33=`0`;
8. pulse GPIO18 `1 -> 0`;
9. start the temporary listener:
   ```sh
   nc -l -p 1888 < /dev/ttyS1 > /dev/ttyS1 &
   ```
10. run `info` from PowerShell;
11. erase only the application area:
    ```powershell
    python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n erase 0x0 0x33200 0
    ```
12. restart the `1888` listener;
13. write the image using its full path:
    ```powershell
    python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n write 0x0 "C:\full\path\jn5189_router_rgb_lux_rejoin_test.bin" 0
    ```
14. confirm:
    ```text
    Written 209296 bytes to memory ID 0 at address 0x0
    ```
15. boot normally with GPIO33=`1` and pulse GPIO18 `1 -> 0`.

In SPSDK 3.10.0, the `erase` command uses positional arguments. The
`--memory-id` form is not accepted.

A simple BusyBox `nc -l` listener serves one connection and exits after every
SPSDK command. If the loop documented in 4.1 is not used, restart the listener
manually before every `info`, `erase` or `write`.


#### 5.1 Close the temporary programming listener

After the final SPSDK operation, run in Telnet:

```sh
if [ -f /var/tmp/jn1888_loop.pid ]; then
    LOOP_PID=$(cat /var/tmp/jn1888_loop.pid 2>/dev/null)
    [ -n "$LOOP_PID" ] && kill -9 "$LOOP_PID" 2>/dev/null
    rm -f /var/tmp/jn1888_loop.pid
fi
for p in $(ps w | grep '[n]c -l -p 1888' | awk '{print $1}'); do
    kill -9 "$p" 2>/dev/null
done
sleep 2
netstat -lnt | grep 1888
```

The final command must return no line.

### 6. Leave ISP and start the Router

Run on the hub:

```sh
echo 1 > /sys/class/gpio/gpio33/value
echo 1 > /sys/class/gpio/gpio18/value
sleep 1
echo 0 > /sys/class/gpio/gpio18/value
sleep 10

cat /sys/class/gpio/gpio33/value
cat /sys/class/gpio/gpio18/value
```

Normal values are:

```text
1
0
```

Router mode requires `/dev/ttyS1` to remain free from the original
`mzigbee_agent`. After every reboot verify:

```sh
ps | grep '[m]zigbee_agent'
ps | grep '[a]pp_monitor'
```

No process may own `/dev/ttyS1` while the integration is using the JN5189 RGB
and lux protocols. This Router requirement is different from a stock-firmware
setup that keeps `mzigbee_agent` running.

If the complete flash was erased by mistake, enable **Permit join (All)** in
Zigbee2MQTT, keep GPIO33=`1`, pulse GPIO18 `1 -> 0`, and wait 30–60 seconds for
the `BDB-Router` to join again.

### 7. Validate Zigbee, RGB and lux

The device must appear in Zigbee2MQTT as a Lumi/NXP `BDB-Router` with Router
role.

RGB protocol:

```text
A5 RED GREEN BLUE CHECKSUM
CHECKSUM = A5 XOR RED XOR GREEN XOR BLUE
```

Manual OFF test:

```sh
printf '\245\000\000\000\245' > /dev/ttyS1
```

Lux request and response:

```text
Request:  A6 00 00 00 A6
Response: A6 RAW_H RAW_L MV_H MV_L LUX_H LUX_L CHECKSUM
```

The response checksum is the XOR of the first seven bytes. The integration
validates it and publishes `LUX_H * 256 + LUX_L` in lux. Avoid leaving a
blocking `cat /dev/ttyS1` process running during manual tests; the integration
creates and manages its own TCP/UART tunnel on port `1886`.

### Rejoin protocol and button location (firmware v0.2.1 compatible build)

Before starting, enable **Permit join** on the destination coordinator.

The rejoin action is not a device-page entity. Open it here:

**Settings > Devices & services > Aqara M1S Zigbee Router > Configure > Join a different Zigbee coordinator**

Read the warning and confirm. The integration sends the command only after the
confirmation step.


The integration sends this deliberately distinctive five-byte request:

```text
Request: A7 52 4A 4E F1
ACK:     A7 4F 4B 00 A3
```

The payload `52 4A 4E` spells `RJN`. After transmitting the ACK, the JN5189
clears only its persisted Zigbee network context and restarts. Its existing BDB
startup path automatically begins Network Steering. Linux, Wi-Fi settings,
RGB/lux support and files below `/data/musics` are not erased.

The older physically validated `jn5189_router_rgb_lux_pio19.bin` does not
implement `A7`. The Configure action therefore fails safely without changing
anything until a compatible firmware build is installed.

## Home Assistant installation

### HACS

1. Open **HACS > Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Add:
   `https://github.com/caiuspoputa-debug/ha-aqara-m1s-zigbee-router`
4. Select category **Integration**.
5. Download the latest release.
6. Restart Home Assistant completely.
7. Open **Settings > Devices & services > Add integration**.
8. Search for **Aqara M1S Zigbee Router**.
9. Enter the hub IP and Telnet credentials.

HACS installs this repository directly; a separately attached release ZIP is
not required by `hacs.json`.

### Manual installation

Copy:

```text
custom_components/aqara_m1s_zigbee_router
```

to:

```text
/config/custom_components/aqara_m1s_zigbee_router
```

Then restart Home Assistant and add the integration. The domain differs from
`aqara_m1s_local`, so both integrations can coexist, although they must not
compete for the same hub UART or audio resources.

## Entities in v0.2.4

- `Ring Light`: RGB ring with brightness
- `Radio`: general Home Assistant speaker/media player
- `Sound Playback Volume`: local-sound playback volume
- `Illuminance`: direct JN5189 lux value, with ADC raw and millivolts attributes
- `Hub Temperature`: `persist.sys.temperature` only
- `WiFi IP`
- HomeKit, MQTT and Telnet process diagnostics
- `JN5189 Router` state
- one playback button for every WAV found in the supported sound catalogue

Obsolete entities are deliberately removed: `Volume Property`,
`Uptime Seconds`, `Sound`, `Delete Selected Sound` and
`Play Selected Sound`.

## Native media player and radio

Version 0.2.0 publishes the entity as a speaker with `PLAY_MEDIA` and
`BROWSE_MEDIA`. It can browse compatible Home Assistant audio sources,
including Local Media, and it can play direct HTTP/HTTPS radio URLs.

Example:

```yaml
action: media_player.play_media
target:
  entity_id: media_player.aqara_m1s_zigbee_router_radio
data:
  media_content_id: "https://example.org/live.aac"
  media_content_type: music
```

Home Assistant resolves `media-source://` identifiers and FFmpeg transcodes
the input to mono, 32000 Hz, signed 32-bit PCM. The hub receives it on TCP port
`12346` and plays it with `aplay`. Cleanup is PID-scoped and never uses
`killall nc`, because the hub may use other `nc` processes.

The separate **Radio Favorites** integration can select this entity as its
target and provides a reusable station catalogue.

## Sound management

Open:

**Settings > Devices & services > Aqara M1S Zigbee Router > Configure**

The management session uses bilingual labels, with Romanian first:

- **Încărcare sunet WAV / Upload WAV sound**
- **Ștergere sunet WAV / Delete WAV sound**
- **Conectare la alt coordonator Zigbee / Join a different Zigbee coordinator**
  (separate confirmed action)
- **Finalizare și închidere / Finish and close**

### Upload a WAV file

1. Open **Configure** and select **Încărcare sunet WAV / Upload WAV sound**.
2. Select or drag the WAV file into the upload field.
3. Wait for the success message. A successful upload is copied to:

   ```text
   /data/musics/music-ch
   ```

4. Repeat the operation for any other files needed. The management window stays
   open after every upload.
5. When all operations are complete, return to the management menu and press
   **Finalizare și închidere / Finish and close**.

The upload operation refreshes the sound catalogue immediately. For the complete
config-entry reload, press **Finalizare și închidere / Finish and close**. Version
0.2.4 then rebuilds the remaining entities and refreshes the device information.

The **X** button belongs to the Home Assistant frontend and cannot be removed by a
custom integration. Closing with **X** skips the final config-entry reload, but it
no longer leaves the sound catalogue stale after upload or deletion.

Accepted uploads:

- `.wav`
- uncompressed PCM
- mono
- 32000 Hz
- signed 32-bit little-endian (`pcm_s32le`)
- maximum 20 MiB

Convert with FFmpeg:

```sh
ffmpeg -y -i input.mp3 -ac 1 -ar 32000 -c:a pcm_s32le output.wav
```

Upload uses a verified LAN transfer on TCP port `12349`. The integration checks
the transferred size and integrity before moving the temporary file into the
protected sound directory. BusyBox `base64` is retained as a fallback.

### Delete a WAV file

1. Open **Configure** and select **Ștergere sunet WAV / Delete WAV sound**.
2. Select the custom file to remove.
3. Confirm the deletion.
4. Repeat for any additional files.
5. Press **Finalizare și închidere / Finish and close** so version 0.2.4 performs
   the complete integration reload and refreshes all related device information.

Only files directly inside the following protected directory can be managed:

```text
/data/musics/music-ch
```

Original Aqara sounds from directories such as `/data/musics/music-scene` are
not offered for deletion by the integration.

### Download an existing WAV from the hub

The Home Assistant management dialog currently uploads and deletes files; it
does not expose a browser-download button. To copy an existing WAV from the hub,
use a temporary LAN-only TCP transfer.

On the hub, first locate the file and start a one-shot listener:

```sh
find /data/musics -type f -name '*.wav'
nc -l -p 1889 < /data/musics/music-scene/disarm.wav
```

Then run this in Windows PowerShell, replacing the output name when needed:

```powershell
$client = New-Object System.Net.Sockets.TcpClient
$client.Connect("HUB_IP", 1889)
$stream = $client.GetStream()
$file = [System.IO.File]::Create("$env:USERPROFILE\Downloads\disarm.wav")
$stream.CopyTo($file)
$file.Close()
$stream.Close()
$client.Close()
Get-Item "$env:USERPROFILE\Downloads\disarm.wav"
```

The hub-side `nc` listener exits automatically after the transfer. Keep port
`1889` inside the trusted LAN and do not expose it through router forwarding.

The integration also registers these actions for advanced automation use:

```text
aqara_m1s_zigbee_router.upload_sound
aqara_m1s_zigbee_router.delete_sound
aqara_m1s_zigbee_router.refresh_sounds
```

## Temperature and availability

`Hub Temperature` reads only:

```sh
getprop persist.sys.temperature
```

The known invalid Linux thermal-zone value of `1 °C` is never used. If the
property cannot be parsed or is implausible, the entity becomes unavailable.

The coordinator checks the hub every 15 seconds. Live entities become
unavailable while the hub is offline; sound buttons remain visible by design.
After the hub first becomes reachable, the integration waits **10 seconds** and
then sends RGB OFF once. The delay allows Wi-Fi, Telnet and the JN5189 UART to
stabilize before extinguishing the weak red boot indication. The last selected
Home Assistant color and brightness remain stored for the next manual turn-on.

## Security and recovery

- Keep Telnet and ports `1886`, `12346` and `12349` inside a trusted LAN.
- Never expose them through router port forwarding.
- Never publish the MiIO token or Telnet credentials.
- Keep the original JN5189 flash backup and its SHA256.
- Never write EFUSE, ROM, Config or PSECT.
- For recovery, enter ISP with GPIO33=`0`, verify `info`, write the validated
  original backup to Memory ID 0, read it back, compare SHA256, then boot with
  GPIO33=`1` and GPIO18=`0`.

## Upgrade from v0.2.0

1. Build and physically validate the supplied JN5189 source with the `A7`
   rejoin protocol.
2. Flash only the verified compatible image and check RGB, lux and Zigbee.
3. Update the repository files and manifest to `0.2.1`.
4. Create/publish tag `v0.2.1`.
5. Update through HACS and restart Home Assistant completely.
6. Enable Permit join on the target coordinator.
7. Open the integration's **Configure** menu, choose **Join a different Zigbee
   coordinator**, read the warning and confirm.

The old coordinator may retain a stale device entry that can be removed after
the router appears on the new coordinator. The action does not erase the Linux
hub, Wi-Fi, RGB/lux support or audio files
