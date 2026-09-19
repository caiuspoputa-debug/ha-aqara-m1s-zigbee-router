# Aqara M1S Gen 1 — 0.10.0 STABLE ULTIMATE KIT

[Română](README_RO.md) | **English**

**Hub kit:** `0.10.0 Stable Ultimate`  
**Documentation date:** 2026-09-19  
**README revision:** `R2 — Master Documentation`  
**Included Home Assistant integration:** `aqara_m1s_zigbee_router 0.21.7`  
**Target model:** Aqara M1S Gen 1 `lumi.gateway.aeu01`

> This is the master README for a **new stock hub**. For a new installation, use this kit as one complete package. Kits `0.5.7`, `0.8` and `0.9` are retained as historical/recovery sources and should not be mixed into the normal 0.10.0 flow.

## 1. What 0.10.0 Stable Ultimate is

The purpose of this kit is to take a stock M1S Gen 1 and keep everything required for the complete conversion in one archive:

```text
stock hub
→ PC + kit verification
→ temporary Telnet
→ complete Linux-side preparation
→ Wi-Fi Recovery installation
→ strict preflight
→ JN5189 A/B backup
→ Router flash
→ Zigbee2MQTT
→ Home Assistant
→ final reboot
→ complete verification
→ Wi-Fi Recovery simulation
→ optional safe static IP
```

**JN5189 flashing is intentionally not performed by the preparation installer.** Erase/write remains a separate step so the kit cannot flash until two complete identical stock backups exist.

### Real validation status

`Stable Ultimate` means the package has been consolidated, structurally validated and protected by safety gates. It does not claim that this exact `0.10.0` combination has already been run end-to-end on a brand-new physical stock M1S.

The first new hub installed with this kit is the final hardware validation. If a problem is detected before flashing, the flow is designed to stop without writing JN5189.

R2 adds useful operational material from the project GitHub README, but verifies version-dependent facts against the actual shipped `0.21.7` snapshot before inclusion. Historical `0.20.x / hub v0.8` text is not treated as current installation guidance.

---

# 2. What changed compared with the older kits

## 2.1 The base is v0.9, not v0.5.7

The Linux-side core is based on `Aqara_M1S_WORKING_v0.9_SAFE_STATIC_IP_2026-09-18`, which already contains the important v0.8 functionality:

- `STRICT10` click events through `ten_click`;
- `hold_start`, `hold_repeat`, `hold_release`;
- persistent reversible Factory Reset Guard;
- physical-button reading through GPIO7;
- MQTT button publisher;
- `service_trim` for `homekitserver` and `mijia_automation`;
- JN5189 ISP/boot helpers;
- stable MQTT button topic;
- DHCP/static-IP manager.

## 2.2 The 0.21.4/0.21.5 network fixes are already built into the kit

The original v0.9 manager had two issues later identified while developing the Home Assistant integration:

- IPv4 validation could replace the requested final octet with the gateway octet;
- the hub's minimal BusyBox has no `rmdir`, so the old lock could remain in place.

The 0.10.0 kit already contains the corrected `network_manager.sh`:

```text
MD5: 186d81b3f459c43463d25103cda835ac
```

Manager-owned locks are removed with the available `rm -r` command.

## 2.3 Wi-Fi Recovery from Complete Kit 0.5.7 is back, but integrated with the new network manager

Later WORKING kits no longer carried the full Wi-Fi Recovery module. 0.10.0 restores it from the validated Complete Kit v0.5.7 UPDATED and connects it to the current network manager.

Important behavior:

- the distributed archive contains no Wi-Fi SSID or password;
- the installer captures the current credentials locally on the hub;
- verification tools do not print the password;
- automatic recovery AP actions are **disabled by default**;
- the simulation test comes first;
- a Wi-Fi change clears static mode before the candidate SSID is tested.

## 2.4 One unified hub-preparation installer

For a new hub, the primary package is now:

```text
installers/m1s_ultimate_hub_prep_v0.10.0.tgz
```

It installs:

- 0.10.0 core;
- Wi-Fi Recovery;
- DHCP/static-IP safety hook;
- diagnostics;
- strict pre-flash verifier;
- post-reboot verifier.

It **does not flash JN5189**.

## 2.5 Hard safety gate between backup and flash

The backup script reads the complete stock flash twice:

```text
646656 bytes A
646656 bytes B
SHA256(A) == SHA256(B)
```

Only then does it create:

```text
BACKUP_PAIR_OK_<HUB_IP>.txt
```

The flash script refuses erase/write if:

- the marker is missing;
- the marker belongs to another IP;
- either backup file is missing;
- either backup size changed;
- either backup hash changed;
- the Router firmware does not match the expected size/hash.

## 2.6 Home Assistant integration is now 0.21.7

For offline recovery and reproducibility, the kit includes:

```text
home_assistant/ha-aqara-m1s-zigbee-router-v0.21.7-SNAPSHOT.zip
```

Key network-related changes in the 0.21.x series:

- **0.21.7:** the final static-IP octet is entered directly in a numeric field, range `2–254`;
- **0.21.5:** network-lock cleanup is compatible with the hub's BusyBox through `rm -r`;
- **0.21.4:** repairs the hub-side final-octet IPv4 calculation;
- **0.21.3:** safely recovers an abandoned IP lock and simplifies the static-IP form;
- **0.21.2:** clearly separates DHCP and static-IP controls;
- **0.21.0:** device identity is Wi-Fi-MAC based, candidate addresses are temporary, Home Assistant verifies the same MAC before committing, and an unconfirmed candidate expires after 120 seconds.

A Wi-Fi network change clears static mode before testing the new SSID. The physical-button MQTT topic remains stable when the IP changes.

If HACS already has the current integration installed, do not reinstall the snapshot for every hub. The snapshot is included as an offline/recovery copy.

---

# 3. 0.10.0 kit layout

```text
Aqara_M1S_0.10.0_STABLE_ULTIMATE_KIT/
├── README_RO.md
├── README.md
├── START_AICI_RO.md
├── CHANGELOG.md
├── BUILD_INFO.txt
├── PERSONAL_LOCAL_NOTICE.txt
├── SHA256SUMS.txt
│
├── firmware/
│   └── jn5189_router_rgb_lux_rejoin_test.bin
│
├── installers/
│   ├── m1s_ultimate_hub_prep_v0.10.0.tgz
│   └── m1s_wifi_recovery_ULTIMATE_v0.10.0.tgz
│
├── hub_bundle/
│   └── m1s_hub_bundle_ULTIMATE_v0.10.0.tgz
│
├── scripts/
│   ├── windows/
│   │   ├── Verify-Kit.ps1
│   │   ├── Check-Prerequisites.ps1
│   │   ├── Enable-TemporaryTelnet.ps1
│   │   ├── Send-FileToM1S.ps1
│   │   ├── Receive-FileFromM1S.ps1
│   │   ├── JN5189-Backup-PAIR-VERIFY.ps1
│   │   └── JN5189-Flash-WRITE.ps1
│   └── hub/
│       ├── aqara_wifi_boot_state.sh
│       ├── jn5189_preflight.sh
│       ├── ultimate_preflash_check.sh
│       └── verify_hub_ultimate.sh
│
├── home_assistant/
│   ├── ha-aqara-m1s-zigbee-router-v0.21.7-SNAPSHOT.zip
│   └── README_RO.md
│
└── docs/
    ├── VALIDATION_REPORT.md
    ├── BUILD_VALIDATION.txt
    └── research/...
```

For a normal new-hub installation, the main transferred file is the unified installer under `installers/`. The separate hub bundle and Wi-Fi Recovery package are retained as independent recovery/diagnostic components.

---

# 4. Safety rules — do not skip them

1. The model must be exactly `lumi.gateway.aeu01`.
2. Run `Verify-Kit.ps1` before transferring anything.
3. Run `Check-Prerequisites.ps1` before working on the hub.
4. Do not flash without `ULTIMATE_PREFLASH_OK`.
5. Do not flash without `BACKUP_PAIR_OK`.
6. Never write EFUSE, ROM, Config, PSECT or pFLASH.
7. Never perform a full-chip erase.
8. On the first conversion, erase only the application region `0x0..0x33200`.
9. Do not repeat erase/write only because an optional readback loses the handshake.
10. Do not reboot between ERASE and WRITE.
11. Do not publish this ZIP: the MQTT button configuration is personal/local and may contain broker credentials.
12. Do not publish MiIO tokens, JN5189 backups or Wi-Fi credentials.

If any step reports `FAIL`, `ERROR`, `MISMATCH`, or does not show the expected success marker, **STOP at that step**.

---

# 5. Prompt rule

In this README:

- `PS C:\...>` means **PowerShell on Windows**;
- `#` means **Telnet shell on the hub**.

Do not paste `/data/...` commands into PowerShell and do not paste Windows commands into Telnet.

---

# 6. Prepare the PC and verify the kit

From the kit root in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\Verify-Kit.ps1
.\scripts\windows\Check-Prerequisites.ps1
```

Expected result:

```text
KIT_SHA256_OK
PREREQUISITES_OK
```

`Check-Prerequisites.ps1` checks:

- Python;
- `python-miio`;
- SPSDK `dk6prog`;
- Windows Telnet Client and warns if it is missing.

If the default `C:\Windows\py.exe` launcher is unavailable:

```powershell
.\scripts\windows\Check-Prerequisites.ps1 -Python py
```

or provide the real Python executable.

### Install missing software

```powershell
python -m pip install python-miio
python -m pip install "spsdk[dk6]"
python -m spsdk.apps.dk6prog --help
```

---

# 7. Prepare the stock hub

Before modifying it:

- add the hub to Xiaomi Home;
- use working 2.4 GHz Wi-Fi;
- create a DHCP reservation for the current address;
- obtain the MiIO token and keep it separately;
- confirm the hub works normally in stock mode.

Keep a separate record for every hub:

```text
Hub name:
Model:
Wi-Fi MAC:
Initial IP:
Stock firmware:
JN5189 backup date:
Backup A SHA256:
Backup B SHA256:
Router firmware SHA256:
Zigbee2MQTT device name:
Home Assistant entry name:
```

Do not store the MiIO token in a document that may be shared.

---

# 8. Enable temporary Telnet

From PowerShell:

```powershell
.\scripts\windows\Enable-TemporaryTelnet.ps1 -HubIp HUB_IP
```

The script asks for the MiIO token as a hidden value, verifies the device first, and only then requests Telnet.

Expected markers:

```text
MIIO_TOKEN_OK
TELNET_REQUEST_SENT HUB_IP
```

Connect:

```powershell
telnet HUB_IP
```

Documented login:

```text
user: admin
password: empty
```

If the hub shell does not appear, do not continue with commands marked `#`.

---

# 9. Transfer the unified 0.10.0 installer

## On the hub

```sh
rm -f /tmp/m1s_ultimate_hub_prep_v0.10.0.tgz
nc -l -p 12345 > /tmp/m1s_ultimate_hub_prep_v0.10.0.tgz
```

The command waits for the sender.

## On Windows

```powershell
.\scripts\windows\Send-FileToM1S.ps1 `
  -HubIp HUB_IP `
  -Path .\installers\m1s_ultimate_hub_prep_v0.10.0.tgz `
  -Port 12345
```

## Back on the hub

```sh
md5sum /tmp/m1s_ultimate_hub_prep_v0.10.0.tgz
```

Exact MD5 for the unified installer in this revision:

```text
6eff82e0acd07d7d5f7bef752d556577
```

If it differs, delete the received file and transfer it again. Do not install a mismatched file.

---

# 10. Run complete hub preparation

On the hub:

```sh
rm -rf /tmp/m1s_ultimate_prep
mkdir -p /tmp/m1s_ultimate_prep
tar -xzf /tmp/m1s_ultimate_hub_prep_v0.10.0.tgz -C /tmp/m1s_ultimate_prep
/bin/sh -n /tmp/m1s_ultimate_prep/install.sh
/bin/sh /tmp/m1s_ultimate_prep/install.sh
```

The installer runs five stages:

```text
0/5 VALIDATE PAYLOAD
1/5 CORE v0.10.0
2/5 WI-FI RECOVERY v0.10.0
3/5 INSTALL DIAGNOSTICS
4/5 STRICT PREFLIGHT
5/5 READY
```

It validates the model, internal hashes and shell syntax, then installs the core, recovery module and verification scripts.

Required final markers:

```text
ULTIMATE_PREFLASH_OK
ULTIMATE_HUB_PREPARED_V0_10_0
```

**JN5189 has still not been written at this point.**

You can repeat the gate before entering ISP:

```sh
/data/scripts/ultimate_preflash_check.sh
```

It must end with:

```text
ULTIMATE_PREFLASH_OK
```

The preflight checks, without exposing credentials:

- model;
- critical scripts;
- shell syntax;
- network-manager MD5;
- Wi-Fi/DHCP hook;
- locally captured Wi-Fi recovery credentials;
- MQTT configuration;
- Wi-Fi Recovery processes;
- stock STA/AP state;
- free `/dev/ttyS1`;
- enabled Factory Reset Guard;
- enabled service trim.

---

# 11. Enter JN5189 ISP

On the hub:

```sh
/data/scripts/jn5189_enter_isp_1888.sh
```

Do not start the backup if the script reports an error.

For an advanced Windows-side check:

```powershell
python -m spsdk.apps.dk6prog `
  -b PYSERIAL `
  -d "socket://HUB_IP:1888" `
  -n info
```

Expected:

```text
Detected DEVICE: JN5189
FLASH Memory ID 0
Length 0x9DE00
Sector 0x200
```

Stop if the device or memory geometry differs.

---

# 12. Mandatory paired stock backup

From the kit root in PowerShell:

```powershell
.\scripts\windows\JN5189-Backup-PAIR-VERIFY.ps1 -HubIp HUB_IP
```

If Python must be provided explicitly:

```powershell
.\scripts\windows\JN5189-Backup-PAIR-VERIFY.ps1 `
  -HubIp HUB_IP `
  -Python "C:\Path\To\python.exe"
```

The script performs:

```text
read A → 646656 bytes
2 s pause
read B → 646656 bytes
SHA256 A
SHA256 B
comparison
```

Required final markers:

```text
BACKUP_PAIR_OK SHA256=...
BACKUP_GATE=...\backups\BACKUP_PAIR_OK_HUB_IP.txt
```

If you see:

```text
BACKUP_HASH_MISMATCH
```

**STOP. Do not flash.**

Keep the backups in at least two locations. They may contain device-specific data and must not be published.

---

# 13. Router firmware identity

The only Router firmware accepted by this kit is:

```text
File: firmware/jn5189_router_rgb_lux_rejoin_test.bin
Size: 209296 bytes
SHA256: a1a1f302be9e3ab95fd6a3b8f4ac260e1f397fec275fb3e3caf8418cd75e7a2f
Memory ID: 0 / FLASH
First-conversion erase region: 0x0..0x33200
```

The file name is not its identity. Size and SHA256 are the identity checks.

---

# 14. Flash JN5189 — only after a valid backup gate

In PowerShell:

```powershell
.\scripts\windows\JN5189-Flash-WRITE.ps1 -HubIp HUB_IP
```

The script revalidates the marker and both backup files before erase.

Expected intermediate markers:

```text
BACKUP_GATE_OK SHA256=...
FIRMWARE_OK bytes=209296 SHA256=...
```

Then it performs:

```text
ERASE only 0x0..0x33200
WRITE 209296 bytes at 0x0
```

Required final marker:

```text
FLASH_WRITE_OK bytes=209296 SHA256=A1A1F302BE9E3AB95FD6A3B8F4AC260E1F397FEC275FB3E3CAF8418CD75E7A2F
```

### Important after WRITE

Do not perform an immediate readback in the normal flow. SPSDK can lose the handshake after a successful write even when the Router firmware boots correctly. Readback remains a separate diagnostic tool.

Do not repeat ERASE/WRITE only because a readback timed out.

---

# 15. Close ISP and boot the Router

On the hub:

```sh
/data/scripts/jn5189_close_isp_1888.sh
/data/scripts/jn5189_boot_router.sh
```

Enable **Permit join** in Zigbee2MQTT and wait for the Lumi/NXP `BDB-Router` device to appear with Router role.

If it does not appear:

- verify Permit join;
- verify GPIO33=`1` and GPIO18=`0`;
- verify `mzigbee_agent` is not running;
- verify there is no permanent `cat /dev/ttyS1`;
- pulse the Router again with `jn5189_boot_router.sh`;
- do not repeat the flash without a demonstrated reason.

---

# 16. Add the hub to Home Assistant

Included integration version:

```text
0.21.7
```

If the HACS repository is already installed and current, just add the new hub.

Repository:

```text
caiuspoputa-debug/ha-aqara-m1s-zigbee-router
```

Offline snapshot:

```text
home_assistant/ha-aqara-m1s-zigbee-router-v0.21.7-SNAPSHOT.zip
```

Configuration uses local Telnet. Device identity is based on Wi-Fi MAC, so changing the IP later does not create a new Home Assistant device.

Add the integration before the final reboot, then validate its entities after the hub has fully stabilized.

---

# 17. Final reboot and automatic verification

On the hub:

```sh
sync
reboot
```

After the hub returns, reconnect through Telnet and run:

```sh
/data/scripts/verify_hub_ultimate.sh
```

The script waits for slower boot services and verifies:

- target model;
- network manager;
- Telnet and syslog;
- Wi-Fi Recovery manager + portal;
- GPIO button watcher;
- legacy button bridge;
- `mha_master -b`;
- `mzigbee_agent` state;
- GPIO33/GPIO18;
- closed ISP port 1888;
- executed `post_init.sh`;
- Factory Reset Guard;
- service trim;
- stored recovery SSID/password without displaying them;
- Wi-Fi/static-IP safety hook.

Desired final marker:

```text
ULTIMATE_POSTBOOT_OK
```

`service_trim` intentionally starts after roughly 120 seconds. If only its status is not ready yet, repeat the verification after full stabilization.

Also test in practice:

- Router online in Zigbee2MQTT;
- ring light;
- lux;
- individual media player;
- media group;
- physical button;
- click/multi-click;
- `hold_start`, `hold_repeat`, `hold_release`.

---

# 18. Test Wi-Fi Recovery before enabling automatic AP actions

Automatic recovery AP actions remain disabled after installation.

Safe simulation:

```sh
touch /data/m1s_wifi/test_noip
sleep 20
tail -n 30 /tmp/m1s_wifi_manager.log
rm -f /data/m1s_wifi/test_noip
```

The log should show that recovery **would** start AP, but the real network must not be changed because `actions_enabled` is absent.

Only after the simulation passes, if automatic AP recovery is desired:

```sh
touch /data/m1s_wifi/actions_enabled
chmod 600 /data/m1s_wifi/actions_enabled
sync
```

Disable later with:

```sh
rm -f /data/m1s_wifi/actions_enabled
```

When the recovery AP is active, the portal uses port `8080`, normally at one of:

```text
http://192.168.49.1:8080/
http://192.168.1.1:8080/
```

Do not expose port 8080 to the Internet.

---

# 19. Static IP — do this last, after the hub is stable

Do not set a static IP until all of these are complete:

- successful flash;
- Router online;
- Home Assistant working;
- final reboot;
- `ULTIMATE_POSTBOOT_OK`;
- Wi-Fi Recovery simulation.

In Home Assistant:

```text
Aqara M1S Zigbee Router
→ Configure
→ Network address
→ Static IP
```

In 0.21.7, enter **only the final octet** in a numeric field (`2–254`). The subnet prefix comes from the current IP.

Safe flow:

1. Home Assistant requests a candidate address;
2. the hub exposes it temporarily;
3. Home Assistant confirms the same Wi-Fi MAC answers at that address;
4. only then is the address committed and the existing config entry updated;
5. an unconfirmed candidate expires automatically after 120 seconds.

Changing Wi-Fi clears static mode before the new SSID is tested.

---

# 20. Factory Reset Guard and the physical button

Validated path:

```text
post_init.sh
→ factory_reset_guard_boot.sh
→ temporary overlay over /dev/input
→ dummy /dev/input/event0 for Aqara firmware
→ stock stack starts without the real physical button
→ gpio_button_watch.sh reads GPIO7
→ m1s_mqtt_publish.sh
→ MQTT
→ Home Assistant Physical Button
```

Supported payloads include:

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

With the guard active, a real press should arrive through GPIO7/MQTT and should not create a new stock `basis.button` click.

The log-based `button_watch.sh` path remains for compatibility/diagnostics but is not the primary reset-protection mechanism.

---

# 21. Service trim

After boot, the kit intentionally stops:

```text
homekitserver
mijia_automation
```

It deliberately keeps the required components:

```text
mha_basis
mha_master
telnetd
Wi-Fi
audio
JN5189 Router
```

Do not kill `mha_basis` or `mha_master` as a button reset-protection method. Factory Reset Guard is the correct mechanism.

---


# 22. Home Assistant 0.21.7 — entities and availability

This section is verified against the `0.21.7` snapshot shipped in this kit, not copied blindly from historical documentation.

Per hub, the integration exposes as applicable:

- **Hub Connectivity** — connectivity binary sensor; it deliberately remains readable so it can report `Disconnected`;
- **Ring Light** — local RGB light;
- **Media Player** — the individual hub player;
- **Sound Playback Volume** — `1–100%` volume for local WAV playback;
- **Fine Volume Trim** — per-player fine correction `-2.00% … +1.00%`, step `0.01%`;
- **Include in M1S Media Group** — include/exclude this hub from the shared group;
- **Physical Button** — MQTT-backed physical-button event entity;
- **Illuminance** — lux with `adc_raw` and `millivolts` attributes;
- **Hub Temperature**;
- **WiFi IP**;
- **HomeKit Process**;
- **MQTT Process**;
- **Telnet Process**;
- **JN5189 Router**;
- **Refresh Sound List**;
- one button for each managed WAV under `/data/musics/music-ch`.

Globally, there is one shared entity:

```text
M1S Media Group
```

Accepted **Physical Button** event types:

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

### Availability

Integration `0.21.7` probes Telnet reachability about every `5 s`, independently of lux/UART work. Lux refresh runs separately at about `15 s`, so an optional lux/UART failure does not hold hub availability offline.

When the hub disappears:

- hub-dependent controls become unavailable;
- **Hub Connectivity** remains readable and reports the disconnect;
- the config-entry/device name may receive the `🔴 Indisponibil` suffix.

When the hub comes back, the integration detects it again and after roughly `10 s` performs a best-effort RGB OFF to clear the stock red boot ring. The last selected color and brightness are retained for the next manual turn-on, but an old ON state is not restored automatically.

---

# 23. Audio and media — actual 0.21.7 values

The values below are verified directly in the `0.21.7` snapshot included in this kit.

## Individual player

```text
Hub port:                12346
PCM:                     S32_LE
Channels:                mono
Rate:                    32000 Hz
Chunk/period:            35 ms
HA jitter buffer:        4.0 s
Initial prebuffer:       2.5 s
Rebuffer resume:         2.0 s
Remote prefill:          1.4 s
```

The M1S ALSA driver reports `1120` frames per period at `32 kHz`, i.e. `35 ms`; transport pacing is aligned to that period.

The native player volume uses `0.1%` steps. **Fine Volume Trim** is separate and applies a `-2.00 … +1.00` percentage-point correction.

## Media group

```text
Hub port:                12347
PCM:                     S32_LE mono 32000 Hz
Chunk:                   35 ms
Shared jitter buffer:    4.0 s
Initial prebuffer:       2.5 s
Rebuffer resume:         2.0 s
Remote prefill:          1.4 s
First receiver timeout:  3.0 s
Cohort grace:            0.30 s
```

The group uses one shared PCM timeline. In build `0.21.7`:

- **adaptive sync is disabled**;
- periodic automatic receiver resync is disabled;
- a returning member can use PCM history + catch-up rather than forcing a global source restart;
- manual `resync_media_group` has a `20 s` cooldown;
- `reset_media_group` hard-resets only the shared group transport.

For troubleshooting, do not assume every timing problem should be fixed with repeated global restarts. Check the affected hub receiver, network path and `nc`/`aplay` processes first.

---

# 24. WAV / ZIP — management and transfer

Managed directory:

```text
/data/musics/music-ch
```

Ports:

```text
12347  local WAV source
12348  local WAV PCM sink
12349  WAV upload from Home Assistant
1889   temporary manual download to Windows
```

Limits confirmed in `0.21.7` code:

```text
Single WAV:              maximum 20 MiB
ZIP:                     maximum 64 WAV files
Total WAV content/ZIP:   maximum 100 MiB
ZIP archive:             maximum 100 MiB
```

From **Configure** you can upload either one WAV or a ZIP. ZIP extraction happens in Home Assistant, not on the hub. Managed files are written only to `/data/musics/music-ch`.

Primary upload uses TCP port `12349`, then verifies size and MD5 before replacing the destination. A BusyBox `base64` fallback exists if the TCP path fails. After a successful upload or deletion the integration reloads the entry so the sound list is current.

Recommended conversion:

```sh
ffmpeg -y -i input.mp3 -ac 1 -ar 32000 -c:a pcm_s32le output.wav
```

### Download an existing WAV

On the hub:

```sh
find /data/musics -type f -name '*.wav'
nc -l -p 1889 < /path/to/sound.wav
```

On Windows, from the kit:

```powershell
.\scripts\windows\Receive-FileFromM1S.ps1 `
  -HubIp HUB_IP `
  -OutputPath "$env:USERPROFILE\Downloads\sound.wav" `
  -Port 1889
```

Port `1889` is temporary and must never be exposed to the Internet.

---

# 25. Home Assistant network controls — DHCP, static IP and Wi-Fi change

## DHCP / static IPv4

In `0.21.7`, **Configure → Network address** reads the hub network manager and offers:

```text
Automatic (DHCP)
Static IP
```

For static IPv4:

- the supported subnet is `/24` (`255.255.255.0`);
- only the final octet is entered, `2–254`;
- the manager rejects the gateway and an address detected as already in use;
- the address is first exposed as a **temporary candidate alias**;
- Home Assistant connects to that candidate and verifies the **same Wi-Fi MAC**;
- only then is the candidate confirmed;
- the integration then verifies that the new address is really active;
- an unconfirmed candidate expires according to the hub-side manager.

The config-entry identity is `mac:<wifi_mac>`, so changing the IPv4 address should not create a different hub in Home Assistant.

## Change Wi-Fi network

**Configure → Change Wi-Fi network** requires the Wi-Fi Recovery module.

Ultimate flow:

1. the integration calls network-manager `wifi-prepare`, forcing persistent DHCP before the Wi-Fi change;
2. SSID and password are transferred over the existing Telnet session;
3. candidate files are staged on the hub with `0600` permissions;
4. `wifi_apply_candidate.sh` tests the new network;
5. the new credentials become the recovery `safe/` copy only after a fresh IPv4 is obtained;
6. the Recovery/AP mechanism remains available on failure;
7. the Ultimate wrapper removes the HA lock with BusyBox-compatible `rm -r`.

The Wi-Fi password is not stored in the Home Assistant config entry/options and is not printed by the kit verification scripts.

**Telnet itself is plaintext.** Use these features only on a trusted LAN and never expose port `23` to the Internet.

If the new Wi-Fi network is on a different subnet, Home Assistant can temporarily lose the hub until the new address is known/configured.

---

# 26. JN5189 local protocols — diagnostics and recovery

These frames are used by the current integration.

## RGB — `A5`

```text
A5 RED GREEN BLUE CHECKSUM
CHECKSUM = A5 XOR RED XOR GREEN XOR BLUE
```

Direct OFF test on the hub:

```sh
printf '\245\000\000\000\245' > /dev/ttyS1
```

Do not leave a manual `cat /dev/ttyS1` running after diagnostics.

## Lux — `A6`

Request:

```text
A6 00 00 00 A6
```

Valid response:

```text
A6 RAW_H RAW_L MV_H MV_L LUX_H LUX_L CHECKSUM
```

The checksum is the XOR of the first seven bytes. The integration exposes:

- lux;
- raw ADC;
- millivolts.

## Zigbee rejoin — `A7`

Request:

```text
A7 52 4A 4E F1
```

Acknowledgement:

```text
A7 4F 4B 00 A3
```

To move the Router to another coordinator:

1. enable **Permit join** on the destination coordinator;
2. Home Assistant → Aqara M1S Zigbee Router → **Configure**;
3. select **Join a different Zigbee coordinator**;
4. confirm.

This operation targets JN5189 Zigbee network context; it is not a Linux factory reset and does not erase hub Wi-Fi or stored sounds.

---

# 27. Home Assistant services and security

Domain:

```text
aqara_m1s_zigbee_router
```

Services present in the shipped `0.21.7` snapshot:

```text
play_url
play_sound
run_command
upload_sound
delete_sound
refresh_sounds
reset_media_group
resync_media_group
update_media_metadata
```

Purpose:

- `play_url` — download/play a WAV source through the hub;
- `play_sound` — play a WAV already on the hub filesystem;
- `run_command` — run a shell command on the hub over Telnet;
- `upload_sound` / `delete_sound` / `refresh_sounds` — WAV management;
- `reset_media_group` — hard recovery of the common group transport;
- `resync_media_group` — manual group realignment;
- `update_media_metadata` — update title/artist/channel for the exact active stream without restarting audio.

### `run_command` warning

`run_command` is effectively **administrative shell access to the hub**. Do not expose it to untrusted users and do not feed it unvalidated external text from automations.

---

# 28. Persistent files and expected processes

## Important files on the hub

Boot / Router / protection:

```text
/data/scripts/post_init.sh
/data/scripts/service_trim.sh
/data/scripts/service_trim.conf
/data/scripts/factory_reset_guard_boot.sh
/data/scripts/factory_reset_guard_boot.conf
/data/scripts/gpio_button_watch.sh
/data/scripts/gpio_button_watch.conf
/data/scripts/jn5189_enter_isp_1888.sh
/data/scripts/jn5189_close_isp_1888.sh
/data/scripts/jn5189_boot_router.sh
/data/scripts/ultimate_preflash_check.sh
/data/scripts/verify_hub_ultimate.sh
```

Button / MQTT:

```text
/data/m1s_button/m1s_mqtt_publish.sh
/data/m1s_button/m1s_button.conf
/data/m1s_button/mqtt_username
/data/m1s_button/mqtt_password
/data/m1s_button/button_watch.sh
```

Network:

```text
/data/m1s_network/network_manager.sh
/data/m1s_network/wifi_apply_candidate_wrapper.sh
/data/m1s_wifi/
/data/m1s_wifi/safe/ssid
/data/m1s_wifi/safe/pass
/data/m1s_wifi/actions_enabled
```

Sounds:

```text
/data/musics/music-ch/
```

Never publish JN5189 backups, the MiIO token, MQTT credentials, or `safe/ssid` / `safe/pass`.

## Expected stable-boot processes/state

In the Ultimate configuration:

- `telnetd` — present;
- `mha_basis` and `mha_master` — retained;
- `gpio_button_watch.sh` — present when the guard is enabled;
- `homekitserver` — stopped by `service_trim`;
- `mijia_automation` — stopped by `service_trim`;
- `mzigbee_agent` — must not own the JN5189 UART;
- `wifi_manager.sh` and the portal — present when Wi-Fi Recovery is installed;
- no ISP listener on `1888` after flashing;
- no permanent manual `cat /dev/ttyS1`.

The main verifier remains:

```sh
/data/scripts/verify_hub_ultimate.sh
```

and should finish with:

```text
ULTIMATE_POSTBOOT_OK
```

---

# 29. Update discipline

## Home Assistant integration

1. back up Home Assistant;
2. record the current integration version;
3. update via HACS or manually;
4. restart Home Assistant;
5. check the manifest and logs;
6. test **one hub first**;
7. only then keep the new version on all hubs.

The `0.21.7` snapshot shipped in Ultimate is this kit's reproducible baseline. If GitHub/HACS has a newer version, do not assume R2 documents every newer behavior.

## JN5189 firmware

For a new stock hub, use the exact Ultimate flow with paired stock backup before the first write.

For an already-working Router:

- keep that hub's stock backup;
- save the currently running Router image if exact rollback is desired;
- verify the new image hash;
- free the UART;
- enter ISP;
- follow the instructions specific to the new build.

Do not assume an existing-Router update is identical to first-time stock conversion. Do not run `erase` merely because a newer file has a different filename.

---

# 30. Known limitations and reminders

1. **Port 12347 is shared** by the media-group receiver and the local WAV source. Do not start a local WAV on a hub while that same hub owns the group receiver on `12347`.
2. `Stable Ultimate` means consolidated and structurally verified; the exact 0.10.0 combination still needs the first full end-to-end validation on a new stock hub.
3. Automatic Wi-Fi Recovery remains disabled until the simulation test passes and you intentionally create `actions_enabled`.
4. A JN5189 backup belongs to one physical hub. Never restore another M1S hub's backup.
5. The included HA snapshot is `0.21.7`; later releases may change behavior and should be audited before updating this master documentation.
6. Telnet and all local project ports must remain LAN-only.
7. Historical `mqtt_client.py` and `select.py` files exist in the snapshot, but `select` is not in the loaded platform list; do not treat those files as current operational features merely because they are present in the repository.

---

# 31. Important ports

| Port | Role |
|---:|---|
| 23 | local Telnet |
| 1886 | UART tunnel created by the integration |
| 1888 | temporary ISP/SPSDK listener |
| 1889 | temporary file transfer from hub |
| 8080 | Wi-Fi Recovery portal |
| 12345 | temporary manual transfer to hub |
| 12346 | individual media player |
| 12347 | media group and local WAV source; known historical conflict |
| 12348 | local WAV PCM sink |
| 12349 | WAV upload |

Do not expose these ports to the Internet.

---

# 32. Reference hashes for this revision

```text
JN5189 Router firmware
  bytes: 209296
  SHA256: a1a1f302be9e3ab95fd6a3b8f4ac260e1f397fec275fb3e3caf8418cd75e7a2f

network_manager.sh fixed
  MD5: 186d81b3f459c43463d25103cda835ac

hub_bundle/m1s_hub_bundle_ULTIMATE_v0.10.0.tgz
  MD5: 66c5a8d7e8ba2a4ceb7654f40f1682df

installers/m1s_wifi_recovery_ULTIMATE_v0.10.0.tgz
  MD5: 233963580c12980983b07b7a9bebd40d

installers/m1s_ultimate_hub_prep_v0.10.0.tgz
  MD5: 6eff82e0acd07d7d5f7bef752d556577

Home Assistant snapshot 0.21.7
  SHA256: 2acd02dc75046bae4cc68a3bfb8e69a0b7875a91ebe5d3f8e761248fb6250a14
```

Use `SHA256SUMS.txt` and `Verify-Kit.ps1` for whole-kit integrity rather than relying only on this reference block.

---

# 33. Final acceptance checklist

Do not call the hub finished until every relevant item is confirmed.

### Kit and PC

- [ ] `KIT_SHA256_OK`
- [ ] `PREREQUISITES_OK`
- [ ] model `lumi.gateway.aeu01`
- [ ] initial DHCP reservation
- [ ] verified MiIO token
- [ ] working Telnet

### Hub preparation

- [ ] unified installer MD5 matches
- [ ] `ULTIMATE_PREFLASH_OK`
- [ ] `ULTIMATE_HUB_PREPARED_V0_10_0`
- [ ] Wi-Fi Recovery captured SSID/password locally
- [ ] `actions_enabled` still absent before recovery simulation

### JN5189 backup

- [ ] backup A = 646656 bytes
- [ ] backup B = 646656 bytes
- [ ] SHA256 A = SHA256 B
- [ ] `BACKUP_PAIR_OK`
- [ ] backups stored in another location as well

### Flash

- [ ] `BACKUP_GATE_OK`
- [ ] `FIRMWARE_OK`
- [ ] `FLASH_WRITE_OK`
- [ ] port 1888 closed after flashing
- [ ] GPIO33=`1`
- [ ] GPIO18=`0`
- [ ] `BDB-Router` online in Zigbee2MQTT

### Home Assistant and boot

- [ ] integration 0.21.7 or newer compatible version
- [ ] hub appears once and is identified by MAC
- [ ] final reboot complete
- [ ] `ULTIMATE_POSTBOOT_OK`
- [ ] Factory Reset Guard active
- [ ] GPIO watcher active
- [ ] service trim active
- [ ] Telnet returns after reboot
- [ ] JN5189 Router returns after power cycle

### Functions

- [ ] RGB/ring light
- [ ] lux
- [ ] individual radio/media
- [ ] media group
- [ ] click and multi-click
- [ ] HOLD start/repeat/release
- [ ] manual MQTT publisher
- [ ] Wi-Fi Recovery simulation
- [ ] automatic recovery enabled only if desired
- [ ] static IP configured only after all previous checks

---

# 34. Recovery and rollback

## 34.1 SPSDK timeout

Check:

```sh
ps w | grep '[c]at /dev/ttyS1'
ps w | grep '[m]zigbee_agent'
netstat -lnt | grep 1888
```

If the listener must be re-armed:

```sh
/data/scripts/jn5189_close_isp_1888.sh
/data/scripts/jn5189_enter_isp_1888.sh
```

Continue from the last known-safe step. Do not automatically repeat ERASE/WRITE if `FLASH_WRITE_OK` was already obtained.

A timeout during an optional post-write readback does not by itself prove that the write failed. First check whether the Router boots and appears in Zigbee2MQTT.

## 34.2 Restore stock JN5189

Use **only the paired backup from that exact physical hub**.

Principle:

1. temporarily stop/disable the HA integration if it owns the UART;
2. enter ISP;
3. re-check `JN5189` identity and FLASH geometry;
4. use the validated complete backup from that hub;
5. after restore, read back the same length and compare SHA256;
6. close ISP;
7. boot JN5189 normally.

Restoring JN5189 FLASH does not automatically undo Linux changes under `/data`. A complete stock rollback must also treat the Linux boot hook separately.

Never restore another hub's backup.

## 34.3 Temporarily return Linux boot to stock behavior

For diagnostics, do not immediately delete `post_init.sh`. Rename it:

```sh
mv /data/scripts/post_init.sh /data/scripts/post_init.sh.disabled
sync
reboot
```

This disables the Ultimate boot hook. A JN5189 still running Router firmware does not become stock merely because the Linux hook was disabled; avoid unnecessary competition from `mzigbee_agent`.

Keep the backup and record exactly what you disabled.

## 34.4 Wi-Fi immediately enters AP after boot

Check stock provisioning state first:

```sh
/data/scripts/aqara_wifi_boot_state.sh check
```

If required:

```sh
/data/scripts/aqara_wifi_boot_state.sh fix
/data/scripts/aqara_wifi_boot_state.sh check
```

This is different from Recovery AP triggered after a prolonged lack of IPv4.

Check the Recovery module:

```sh
ps w | grep '[w]ifi_manager.sh'
ps w | grep '[m]1s_wifi_portal_safe.sh'
tail -n 120 /tmp/m1s_wifi_manager.log
ls -l /data/m1s_wifi/actions_enabled
wc -c /data/m1s_wifi/safe/ssid /data/m1s_wifi/safe/pass
```

Do not print `safe/pass` in logs or screenshots.

Manual return to the safe Wi-Fi copy:

```sh
rm -f /data/m1s_wifi/ap_hold
/data/m1s_wifi/restore_sta.sh
```

## 34.5 Button problems

```sh
cat /tmp/factory_reset_guard_boot.status
cat /tmp/gpio_button_watch.status
mount | grep /dev/input
ps w | grep '[g]pio_button_watch.sh'
tail -n 100 /tmp/gpio_button_watch.log
/data/m1s_button/m1s_mqtt_publish.sh click
echo "rc=$?"
grep -n 'basis.button' /var/log/messages | tail -n 20
```

Interpretation:

- manual publisher does not reach HA → broker/topic/MQTT credentials;
- manual publisher works but physical press does not → GPIO7/watcher;
- a new `basis.button click` appears → guard/overlay is not active as expected;
- watcher missing after boot → check `factory_reset_guard_boot.conf`, `gpio_button_watch.conf` and `post_init.sh`.

## 34.6 Audio problems

Check only the relevant path:

```sh
ps w | grep '[n]c -l -p 12346'
ps w | grep '[n]c -l -p 12347'
ps w | grep '[n]c -l -p 12348'
ps w | grep '[a]play'
netstat -lnt | grep ':12346'
netstat -lnt | grep ':12347'
netstat -lnt | grep ':12348'
netstat -lnt | grep ':12349'
```

Do not blindly kill every `nc` or `aplay` process; that can interrupt other valid hub functions.

If the problem is group-only, try the dedicated `resync_media_group` or `reset_media_group` services before rebooting Home Assistant.

---

# 35. What not to use for the next new hub

For a new stock hub, do **not** manually combine:

```text
Aqara_M1S_Complete_Kit_v0.5.7...
Aqara_M1S_WORKING_v0.8...
Aqara_M1S_WORKING_v0.9...
```

They remain archived sources of previously validated components. The current flow starts from:

```text
Aqara_M1S_0.10.0_STABLE_ULTIMATE_KIT
```

Do not replace 0.10.0 files with older files merely because their names are similar.

---

# 36. Personal/local notice

This kit is built for the existing local installation. The button MQTT configuration comes from the validated local kit and may contain broker credentials.

**Do not publish the Ultimate ZIP in this form.** A separate sanitized edition must be created for GitHub/public distribution.

The distributed payload does not contain:

- the MiIO token;
- Wi-Fi SSID;
- Wi-Fi password.

Wi-Fi Recovery credentials are captured locally on the hub during installation.

---

# 37. Golden rule for the next hub

Follow this exact order:

```text
Verify-Kit
→ Check-Prerequisites
→ Xiaomi Home + DHCP reservation + token
→ Telnet
→ Ultimate hub prep
→ ULTIMATE_PREFLASH_OK
→ ISP
→ backup A/B
→ BACKUP_PAIR_OK
→ flash
→ FLASH_WRITE_OK
→ close ISP
→ Permit Join
→ boot Router
→ Zigbee2MQTT online
→ add Home Assistant
→ final reboot
→ ULTIMATE_POSTBOOT_OK
→ functional tests
→ Wi-Fi Recovery simulation
→ optional actions_enabled
→ optional static IP
```

**Do not move to the next stage until the current stage has produced its expected success marker.**

For build-level technical validation, see `docs/VALIDATION_REPORT.md`.
