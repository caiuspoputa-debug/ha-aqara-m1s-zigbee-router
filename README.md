# Aqara M1S Zigbee Router

[Română](README_RO.md) | **English**

Home Assistant custom integration for an Aqara M1S Gen 1 hub converted to an
NXP JN5189 BDB Zigbee Router, with local RGB ring, illuminance, audio and hub
diagnostics.

Current version: **0.2.0 (test release)**

> This project is for the Aqara M1S Gen 1 model `lumi.gateway.aeu01`. Flashing
> the JN5189 is an advanced operation. Keep a verified backup and never write
> EFUSE, ROM, Config or PSECT.

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

When the hub is offline, the light, media player, volume and live sensors become
unavailable. Sound buttons intentionally remain visible. Upload and deletion
refresh only the sound catalogue; they do not reload the integration or reset
the other entities.

## Final RGB + lux firmware

The final image uses **PIO19/ADC5** for the ambient-light sensor:

```text
File: jn5189_router_rgb_lux_pio19.bin
Size: 209312 bytes (0x331A0)
Partial erase length: 0x33200
Memory: ID 0 / FLASH
SHA256: 33FB799E4B5E9C3B33E9B8E1B40089DBD04FA2DCDD7BF5D681E41F152BD8D611
```

This is the only flash image that should be published with the project. The
final build was physically validated at approximately `54 lx` with the sensor
illuminated and `2 lx` when covered.

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

### 4. Back up the original JN5189 flash

Install SPSDK on Windows:

```powershell
python --version
python -m pip install "spsdk[dk6]"
python -m spsdk.apps.dk6prog --help
```

The network transport uses the `PYSERIAL` backend and a pyserial
`socket://HUB_IP:1886` URL. Some SPSDK versions may require their PYSERIAL
driver to open the device with `serial.serial_for_url(...)`.

Before taking over `/dev/ttyS1`, stop the process that owns it and prevent its
monitor from restarting it. Determine the exact PIDs first:

```sh
ps | grep '[a]pp_monitor'
ps | grep '[m]zigbee_agent'
```

For a temporary programming session:

```sh
kill -STOP PID_APP_MONITOR
kill PID_MZIGBEE_AGENT
```

Replace the placeholders only with PIDs displayed by the preceding commands.

Before **every** SPSDK command, recreate the UART tunnel and reset the JN5189
into ISP:

```sh
for p in $(ps | grep '[c]at /dev/ttyS1' | awk '{print $1}'); do kill "$p"; done
for p in $(ps | grep '[n]c -l -p 1886' | awk '{print $1}'); do kill "$p"; done

rm -f /tmp/jn_uart_fifo
mkfifo /tmp/jn_uart_fifo
stty 115200 cs8 -parenb -cstopb -ixon -ixoff -icanon -echo min 1 time 0 < /dev/ttyS1
cat /dev/ttyS1 > /tmp/jn_uart_fifo &
nc -l -p 1886 < /tmp/jn_uart_fifo > /dev/ttyS1 &

echo 0 > /sys/class/gpio/gpio33/value
echo 1 > /sys/class/gpio/gpio18/value
sleep 1
echo 0 > /sys/class/gpio/gpio18/value
sleep 1

netstat -lnt | grep 1886
```

Check communication from PowerShell:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1886" -n info
```

Expected device information includes:

```text
Detected DEVICE: JN5189
FLASH: base 0x0, length 0x9DE00, sector 0x200
```

Recreate the tunnel and ISP reset, then read the original flash:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1886" -n read -o "jn5189_original_flash.bin" 0x0 646656 0
Get-FileHash ".\jn5189_original_flash.bin" -Algorithm SHA256
```

Keep this backup in two safe locations.

### 5. Verify and flash the final image

Verify the downloaded image first:

```powershell
Get-FileHash ".\jn5189_router_rgb_lux_pio19.bin" -Algorithm SHA256
```

It must match the full SHA256 shown in the firmware section.

Do not use full-chip erase for a normal update. Recreate the tunnel and ISP
reset, then erase only the image area:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1886" -n erase 0x0 0x33200 0
```

Recreate the tunnel and ISP reset again, then write:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1886" -n write 0x0 ".\jn5189_router_rgb_lux_pio19.bin"
```

Do not combine erase and write. Recreate the tunnel and ISP reset one more
time, then read back exactly 209312 bytes:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1886" -n read -o ".\jn5189_router_rgb_lux_pio19_verify.bin" 0x0 209312 0
Get-FileHash ".\jn5189_router_rgb_lux_pio19.bin", ".\jn5189_router_rgb_lux_pio19_verify.bin" -Algorithm SHA256
```

Both hashes must be identical. Do not boot an image that fails verification.

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

## Entities in v0.2.0

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

The management session provides:

- **Upload WAV sound**
- **Delete WAV sound**
- **Finish and close**

The window remains open after each upload or deletion so several files can be
managed in one session. Press **Finish and close** when done. There is no
delete entity on the device page and there is no redundant selected-sound play
button.

Only files directly inside this protected directory are managed:

```text
/data/musics/music-ch
```

Other original Aqara sound directories are not modified. Accepted uploads:

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

Upload uses a verified-size LAN transfer on TCP port `12349`, with BusyBox
`base64` as fallback. The catalogue and its individual sound buttons update
without reloading the config entry or resetting lux, temperature, RGB or media
entities.

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
After Wi-Fi reconnects, the integration sends RGB OFF once to extinguish the
firmware's weak red boot indication while preserving the last selected Home
Assistant color and brightness for the next manual turn-on.

## Security and recovery

- Keep Telnet and ports `1886`, `12346` and `12349` inside a trusted LAN.
- Never expose them through router port forwarding.
- Never publish the MiIO token or Telnet credentials.
- Keep the original JN5189 flash backup and its SHA256.
- Never write EFUSE, ROM, Config or PSECT.
- For recovery, enter ISP with GPIO33=`0`, verify `info`, write the validated
  original backup to Memory ID 0, read it back, compare SHA256, then boot with
  GPIO33=`1` and GPIO18=`0`.

## Upgrade from v0.1.9

1. Update the repository files and manifest to `0.2.0`.
2. Create/publish tag `v0.2.0`.
3. Update through HACS.
4. Restart Home Assistant completely.
5. Open the `Radio` entity; the native media browser should now be available.

No JN5189 firmware rewrite is required when the final PIO19 RGB+lux firmware is
already installed. The v0.2.0 change only extends the Home Assistant media
player interface.
