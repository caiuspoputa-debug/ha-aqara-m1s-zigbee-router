**Current package: v0.20.1 + hub kit v0.8**

[Romana](README_RO.md) | **English**

# Aqara M1S Gen 1 - stock hub to Zigbee Router + Home Assistant integration

Documentation version: **2026-09-03 - v0.20.1 + hub kit v0.8**  
Home Assistant integration version: **0.20.1**  
Target model: **Aqara M1S Gen 1 `lumi.gateway.aeu01`**

This README is the current English operational guide for the packaged kit. The Romanian file `README_RO.md` is the long detailed reference; this file keeps the same current facts and the practical stock-hub flow.

## YouTube / YouTube Music companion

The optional **M1S YouTube Cast Receiver 1.0.1** add-on owns YouTube/YTM playback logic. It receives DIAL/Lounge Cast control, manages track EOF, queue progression, Next, Seek and Pause/Resume, and exposes the result to Home Assistant as **one continuous audio stream for the whole Cast session**.

The Aqara integration does not own per-track YT/YTM logic. A track change must not become a new HA STOP/PLAY cycle, a new prebuffer operation, a duration timer, or a queue decision in this integration. The integration only transports PCM/TCP and synchronizes M1S receivers.

## Current v0.20.1 audio behavior

- Runtime baseline is v0.20.0; v0.20.1 changes only the adaptive-sync enable flag for group-stability testing.
- Group source changes already use clean ordering: remote GROUP STOP before old FFmpeg/TCP teardown.
- v0.20.1 keeps the same clean ordering to an individual player on source replacement: remote port-12346 STOP before old FFmpeg/TCP teardown, then the new receiver/stream starts.
- PCM transport periods are **35 ms**.
- Individual and group HA jitter buffer: **4.0 s**.
- Initial source prebuffer: **2.5 s**.
- Rebuffer resume threshold after a real underrun: **2.0 s**.
- Hub-side remote prefill: **1.4 s**.
- Group startup waits up to **3.0 s** for the first receiver, then gives other ready receivers a **0.30 s** cohort grace window. There is no YT/YTM-specific fixed startup sleep.
- Periodic receiver resync is disabled. In v0.20.1, **adaptive sync is also disabled**, so no per-member micro-resampling/rate correction is applied.
- A returning group member uses history prefill + live catch-up instead of forcing a global source restart.

## Current scope

The project configuration keeps stock Linux, Wi-Fi and audio, while converting the NXP JN5189 into a Zigbee Router and exposing local controls through Home Assistant.

Current validated additions:

- persistent LAN-only Telnet;
- JN5189 BDB Zigbee Router firmware;
- RGB ring and illuminance read through the local UART protocol;
- individual media player and shared media group in Home Assistant;
- local WAV playback and upload management;
- persistent reversible Factory Reset Guard;
- physical button isolated from the stock reset path and read through GPIO7;
- MQTT button payloads up to `ten_click`, plus `hold_start`, `hold_repeat`, `hold_release`;
- controlled post-boot stop for `homekitserver` and `mijia_automation`;
- optional Wi-Fi recovery module when the package includes it.

Advanced operation: keep two verified stock JN5189 backups. Never write EFUSE, ROM, Config, PSECT or pFLASH. Never perform a full-chip erase.

## Package contents

Current kit archive:

```text
Aqara_M1S_WORKING_v0.8_STRICT10_HOLD_EVENTS_LOCAL_2026-09-02_README_RESEARCH_OK.zip
```

Main files:

```text
README.md
README_RO.md
README_FAST_RO.md
CHANGELOG_FIXES.txt
SHA256SUMS.txt
firmware/jn5189_router_rgb_lux_rejoin_test.bin
hub_bundle/m1s_hub_bundle_LOCAL.tgz
scripts/windows/Enable-Telnet.ps1
scripts/windows/Send-FileToM1S.ps1
scripts/windows/JN5189-Backup-PAIR-VERIFY.ps1
scripts/windows/JN5189-Flash-WRITE.ps1
```

Only `hub_bundle/m1s_hub_bundle_LOCAL.tgz` is copied to the hub. The Home Assistant integration is installed separately through HACS or by copying `custom_components/aqara_m1s_zigbee_router`.

## Prompt rule

- `PS C:\...>` means **PowerShell on Windows**.
- `#` means **Telnet shell on the hub**.

Do not paste `/data/...` commands into PowerShell. Do not paste Windows/Python commands into Telnet.

## Firmware identity

```text
File: firmware/jn5189_router_rgb_lux_rejoin_test.bin
Size: 209296 bytes
SHA256: A1A1F302BE9E3AB95FD6A3B8F4AC260E1F397FEC275FB3E3CAF8418CD75E7A2F
Rounded app erase size for first stock conversion: 0x33200
Memory ID: 0 / FLASH
```

File name is not identity. Size and SHA256 are the checks.

## Fast stock-hub flow

Use this order when converting a new stock hub. Do not reorder backup and flash.

```text
1. Add stock hub to Xiaomi Home.
2. Reserve the hub IP in DHCP.
3. Extract and verify the MiIO token.
4. Enable Telnet.
5. Login through Telnet as admin with an empty password.
6. Transfer and install the hub bundle.
7. Enter JN5189 ISP once.
8. Run the paired A/B stock backup.
9. Flash the Router firmware.
10. Close ISP and boot the Router.
11. Enable Zigbee2MQTT Permit Join and wait for the Router.
12. Add the hub to the Home Assistant integration.
13. Reboot the hub.
14. Wait at least 120 seconds.
15. Validate service trim, Factory Reset Guard, GPIO7/MQTT, media player and group.
```

## 1. Enable Telnet

For compatible stock firmware, the documented physical sequence is:

```text
5-2-2-2-2-2-2
```

The kit also includes a MiIO-based PowerShell helper. This is a PC command, not a Telnet command:

```powershell
.\scripts\windows\Enable-Telnet.ps1 -HubIp HUB_IP
```

Then connect:

```powershell
telnet HUB_IP
```

Login:

```text
user: admin
password: empty
```

If Telnet is not active yet, there is no `#` prompt and hub-side commands cannot be run.

## 2. Transfer and install the hub bundle

On the hub:

```sh
rm -f /tmp/m1s_hub_bundle_LOCAL.tgz
nc -l -p 12345 > /tmp/m1s_hub_bundle_LOCAL.tgz
```

In PowerShell, from the kit root:

```powershell
.\scripts\windows\Send-FileToM1S.ps1 -HubIp HUB_IP -Path .\hub_bundle\m1s_hub_bundle_LOCAL.tgz -Port 12345
```

Back on the hub:

```sh
rm -rf /tmp/m1s_bundle
mkdir -p /tmp/m1s_bundle
cd /tmp/m1s_bundle
tar -xzf /tmp/m1s_hub_bundle_LOCAL.tgz
chmod 700 install.sh
./install.sh
```

Expected:

```text
M1S_BUNDLE_V0_8_INSTALLED
Factory Reset Guard este inclus si configurabil in /data/scripts/factory_reset_guard_boot.conf.
```

## 3. Enter JN5189 ISP

On the hub:

```sh
/data/scripts/jn5189_enter_isp_1888.sh
```

Expected:

```text
ISP_LISTENER_OK port=1888 ...
GPIO33=0 GPIO18=0
```

Do not rerun `enter_isp` while a PowerShell SPSDK command is active.

If the one-shot listener must be armed again:

```sh
/data/scripts/jn5189_close_isp_1888.sh
/data/scripts/jn5189_enter_isp_1888.sh
```

## 4. Back up the stock JN5189 firmware

In PowerShell:

```powershell
.\scripts\windows\JN5189-Backup-PAIR-VERIFY.ps1 -HubIp HUB_IP
```

Expected:

```text
BACKUP_PAIR_OK SHA256=...
```

Each backup must be exactly `646656` bytes. The two hashes must match. If they differ, stop.

If the script cannot find Python automatically, pass the executable path explicitly:

```powershell
.\scripts\windows\JN5189-Backup-PAIR-VERIFY.ps1 -HubIp HUB_IP -Python "C:\Path\To\python.exe"
```

## 5. Flash the Router firmware

For a stock first conversion, use the validated write script:

```powershell
.\scripts\windows\JN5189-Flash-WRITE.ps1 -HubIp HUB_IP -FirmwarePath .\firmware\jn5189_router_rgb_lux_rejoin_test.bin
```

Expected:

```text
FLASH_WRITE_OK bytes=209296 SHA256=A1A1F302BE9E3AB95FD6A3B8F4AC260E1F397FEC275FB3E3CAF8418CD75E7A2F
```

The fast v0.8 flow does not do immediate readback after write. SPSDK 3.10 can lose the handshake even when the firmware was written and the Router boots correctly. Full readback remains an advanced separate verification step.

## 6. Close ISP and boot the Router

On the hub:

```sh
/data/scripts/jn5189_close_isp_1888.sh
/data/scripts/jn5189_boot_router.sh
```

Expected:

```text
ISP_LISTENER_CLOSED port=1888
ROUTER_BOOT_SENT GPIO33=1 GPIO18=0
```

Enable Permit Join in Zigbee2MQTT and wait for `BDB-Router` to appear online.

## 7. Add the hub in Home Assistant

Install the integration with manifest `0.20.1`.

HACS:

```text
HACS -> Integrations -> Custom repositories
Repository: https://github.com/caiuspoputa-debug/ha-aqara-m1s-zigbee-router
Category: Integration
```

Manual:

```text
custom_components/aqara_m1s_zigbee_router
-> /config/custom_components/aqara_m1s_zigbee_router
```

Add the hub:

```text
Settings -> Devices & services -> Add integration -> Aqara M1S Zigbee Router
Host: HUB_IP
Port: 23
Username: admin
Password: empty
```

Add the Home Assistant integration before the final hub reboot, so media and button validation can be done immediately after boot.

## 8. Final reboot and validation

On the hub:

```sh
sync
reboot
```

After it comes back, wait at least 120 seconds.

Validate:

```sh
cat /tmp/post_init.log
cat /tmp/factory_reset_guard_boot.status
cat /tmp/gpio_button_watch.status
cat /tmp/service_trim.status
mount | grep /dev/input
ps w | grep '[g]pio_button_watch.sh'
ps w | grep '[t]elnetd'
ps w | grep '[m]zigbee_agent'
```

Expected:

- Telnet is available.
- `mzigbee_agent` does not own `/dev/ttyS1`.
- Router is online in Zigbee2MQTT.
- `service_trim` reports `homekitserver=stopped` and `mijia_automation=stopped`.
- Factory Reset Guard reports `mode=input_dir_overlay` and `one_shot=0`.
- GPIO button watcher reports GPIO7 and `run_seconds=0`.
- Media player works locally.
- Media group works when at least two hubs are selected.

## Factory Reset Guard and GPIO button

Stock path before the guard:

```text
physical button -> /dev/input/event0 -> mha_basis / mha_master -> basis.button -> stock click/reset logic
```

Current validated path:

```text
post_init.sh
-> factory_reset_guard_boot.sh
-> temporary overlay over /dev/input
-> dummy /dev/input/event0 char 1,3 for Aqara firmware
-> mha_basis starts without the real physical button
-> gpio_button_watch.sh reads GPIO7
-> m1s_mqtt_publish.sh publishes MQTT
-> Home Assistant receives Physical Button
```

MQTT topic:

```text
m1s/<last_IP_octet>/button/action
```

Payloads accepted by the integration:

```text
click
double_click
triple_click
quadruple_click
five_click
six_click
seven_click
eight_click
nine_click
ten_click
hold
hold_start
hold_repeat
hold_release
```

Manual publisher test:

```sh
/data/m1s_button/m1s_mqtt_publish.sh click
echo "rc=$?"
```

Physical button validation:

```sh
tail -n 80 /tmp/gpio_button_watch.log
grep -n 'basis.button' /var/log/messages | tail -n 20
```

With the guard active, a physical press should publish through GPIO7/MQTT and should not create a new stock `basis.button click`.

## Service trim

The current bundle stops these after boot:

```text
homekitserver
mijia_automation
```

It deliberately keeps:

```text
mha_basis
mha_master
telnetd
Wi-Fi
audio
JN5189 Router
```

Do not kill `mha_basis` or `mha_master` as a reset-guard strategy. The reset guard is the `/dev/input` overlay plus GPIO7 watcher.

## Media source-switch rule

For both group and individual playback, an explicit source replacement must silence the exact hub-side receiver **before** detaching the old HA FFmpeg/TCP transport. This prevents already-buffered ALSA PCM from the previous source from draining after the switch.

This rule applies to a real source change (for example Radio -> YT/YTM or YT/YTM -> Radio). It does **not** apply to a normal track change inside the continuous YT/YTM Cast session.

## Important ports

| Port | Role |
|---:|---|
| 23 | Telnet |
| 1886 | UART tunnel created by the integration |
| 1888 | temporary SPSDK ISP listener |
| 1889 | temporary file receive from hub |
| 8080 | optional Wi-Fi recovery portal |
| 12345 | temporary manual transfer to hub |
| 12346 | individual media player |
| 12347 | media group and local WAV source, known conflict |
| 12348 | local WAV PCM sink |
| 12349 | WAV upload |

Do not expose these ports to the Internet.

## Known limitation

The media group receiver and the local WAV source both use port `12347`. Do not start a local WAV on a hub while that same hub is holding the group receiver port. This still needs explicit arbitration or port separation in a later code revision.

## Recovery notes

If SPSDK times out:

- verify that no `cat /dev/ttyS1` is left behind;
- verify that port `1888` is armed;
- re-enter ISP using `/data/scripts/jn5189_enter_isp_1888.sh`;
- continue from the last safe step;
- do not repeat erase/write only because an optional readback timed out after a successful `FLASH_WRITE_OK`.

Factory Reset Guard rollback:

```sh
cp /data/scripts/factory_reset_guard_boot.conf /data/scripts/factory_reset_guard_boot.conf.before_disable
sed -i 's/^ENABLE_FACTORY_RESET_BOOT_GUARD=.*/ENABLE_FACTORY_RESET_BOOT_GUARD=0/' /data/scripts/factory_reset_guard_boot.conf
sync
reboot
```

Rollback reactivates the stock `/dev/input/event0` button path and can bring back stock reset behavior.

## Final acceptance checklist

- stock model is `lumi.gateway.aeu01`;
- IP is reserved in DHCP;
- Telnet works as `admin` with empty password;
- hub bundle installed successfully;
- two stock backups are identical;
- Router firmware size and SHA256 match;
- flash completed with `FLASH_WRITE_OK`;
- port `1888` is closed after flashing;
- Router joins Zigbee2MQTT;
- Home Assistant integration manifest is `0.20.1`;
- final reboot completed;
- 120 seconds passed after boot;
- `service_trim` stopped HomeKit and Mijia automation;
- Factory Reset Guard is active and persistent;
- GPIO7 publishes the physical button to MQTT;
- a button press reaches Home Assistant;
- no new stock `basis.button click` appears with the guard active;
- media player and group are tested.

When all items pass, the hub is ready.
