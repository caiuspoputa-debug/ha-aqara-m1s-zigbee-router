# Aqara M1S Gen 1 — 0.10.0 STABLE ULTIMATE KIT

[**Română**](README_RO.md) | [English](README.md)

**Kit hub:** `0.10.0 Stable Ultimate`  
**Data documentației:** 2026-09-19  
**Revizia README:** `R2 — Master Documentation`  
**Integrare Home Assistant inclusă:** `aqara_m1s_zigbee_router 0.21.7`  
**Model țintă:** Aqara M1S Gen 1 `lumi.gateway.aeu01`

> Acesta este README-ul master pentru un **hub nou, stock**. Pentru o instalare nouă folosește acest kit ca pachet unic. Kiturile `0.5.7`, `0.8` și `0.9` rămân surse istorice/de recuperare și nu trebuie amestecate în fluxul normal 0.10.0.

## 1. Ce este 0.10.0 Stable Ultimate

Scopul acestui kit este să putem lua un M1S Gen 1 stock și să avem într-o singură arhivă toate componentele necesare pentru traseul:

```text
hub stock
→ verificare PC + kit
→ Telnet temporar
→ pregătire Linux completă
→ Wi-Fi Recovery instalat
→ preflight strict
→ backup JN5189 A/B
→ flash Router
→ Zigbee2MQTT
→ Home Assistant
→ reboot final
→ verificare completă
→ test Wi-Fi Recovery
→ opțional IP static sigur
```

**Flash-ul JN5189 nu este automatizat în installerul de pregătire.** Acesta rămâne separat intenționat. Kitul nu permite ERASE/WRITE până când nu există două backupuri complete și identice ale flashului stock.

### Starea reală de validare

`Stable Ultimate` înseamnă că pachetul a fost consolidat, verificat structural și are porți de siguranță. Nu înseamnă că această combinație exactă `0.10.0` a fost deja rulată cap-coadă pe un M1S stock nou.

Primul hub nou pe care îl facem cu acest kit va fi validarea hardware finală. Dacă apare o problemă înainte de flash, fluxul este construit să se oprească fără să scrie JN5189.

Revizia R2 adaugă informațiile operaționale utile din README-ul proiectului GitHub, dar le verifică față de snapshotul real `0.21.7` înainte de includere. Istoricul vechi `0.20.x / hub v0.8` nu este folosit ca instrucțiune curentă.

---

# 2. Ce este nou față de kiturile vechi

## 2.1 Baza este v0.9, nu v0.5.7

Core-ul Linux pornește din `Aqara_M1S_WORKING_v0.9_SAFE_STATIC_IP_2026-09-18`, care conține deja tot ce era important din v0.8:

- `STRICT10` pentru click-uri până la `ten_click`;
- `hold_start`, `hold_repeat`, `hold_release`;
- Factory Reset Guard persistent și reversibil;
- citirea butonului fizic prin GPIO7;
- publisher MQTT pentru buton;
- `service_trim` pentru `homekitserver` și `mijia_automation`;
- scripturile ISP/boot pentru JN5189;
- topic MQTT stabil pentru buton;
- managerul pentru DHCP/IP static.

## 2.2 Corecțiile de rețea din 0.21.4/0.21.5 sunt deja în kit

Managerul v0.9 avea două probleme identificate ulterior din integrarea Home Assistant:

- calculul IPv4 putea înlocui ultimul octet cerut cu octetul gateway-ului;
- BusyBox-ul hubului nu are `rmdir`, iar lock-ul putea rămâne blocat.

În 0.10.0, `network_manager.sh` este deja varianta corectată:

```text
MD5: 186d81b3f459c43463d25103cda835ac
```

Curățarea lock-ului folosește `rm -r`, disponibil pe hub.

## 2.3 Wi-Fi Recovery din Complete Kit 0.5.7 a revenit, dar integrat corect

Kiturile WORKING noi nu mai transportau efectiv modulul complet Wi-Fi Recovery. 0.10.0 îl readuce din Complete Kit v0.5.7 UPDATED și îl leagă de managerul de rețea actual.

Important:

- arhiva nu conține SSID sau parola Wi-Fi;
- installerul le citește local de pe hub în momentul instalării;
- parola nu este afișată de verificatoare;
- AP recovery automat este **dezactivat implicit**;
- întâi se face testul de simulare;
- la schimbarea Wi-Fi, hook-ul scoate mai întâi IP-ul static pentru a evita blocarea pe vechea rețea.

## 2.4 Installer unic de pregătire

În loc să transferăm manual multe pachete, pentru un hub nou folosim:

```text
installers/m1s_ultimate_hub_prep_v0.10.0.tgz
```

Acesta instalează:

- core-ul 0.10.0;
- Wi-Fi Recovery;
- hook-ul DHCP/static-IP;
- diagnosticele;
- verificatorul pre-flash;
- verificatorul post-reboot.

**Nu flashează JN5189.**

## 2.5 Backup + flash au hard safety gate

Backupul citește flashul stock complet de două ori:

```text
646656 bytes A
646656 bytes B
SHA256(A) == SHA256(B)
```

Numai atunci creează markerul:

```text
BACKUP_PAIR_OK_<HUB_IP>.txt
```

Scriptul de flash refuză ERASE/WRITE dacă:

- markerul lipsește;
- markerul este pentru alt IP;
- lipsește unul dintre backupuri;
- dimensiunea backupului s-a schimbat;
- hashul unuia dintre backupuri s-a schimbat;
- firmware-ul Router nu are dimensiunea/hashul așteptat.

## 2.6 Integrarea Home Assistant este acum 0.21.7

Kitul include pentru reproducibilitate/offline:

```text
home_assistant/ha-aqara-m1s-zigbee-router-v0.21.7-SNAPSHOT.zip
```

Principalele noutăți de rețea din seria 0.21.x:

- **0.21.7:** ultimul octet al IP-ului static se introduce direct într-un câmp numeric; interval `2–254`;
- **0.21.5:** lock-ul de rețea este curățat compatibil cu BusyBox prin `rm -r`;
- **0.21.4:** corecție pentru calculul ultimului octet IPv4;
- **0.21.3:** recuperare sigură a unui lock abandonat și formular IP simplificat;
- **0.21.2:** pagina separă clar DHCP de IP static;
- **0.21.0:** identitatea dispozitivului este bazată pe MAC-ul Wi-Fi, candidatul IP este temporar, Home Assistant verifică același MAC înainte de confirmare, iar un candidat neconfirmat expiră automat după 120 s.

La schimbarea Wi-Fi, modul static este eliminat înainte de testarea noului SSID. Topic-ul MQTT al butonului rămâne stabil chiar dacă IP-ul se schimbă.

Dacă HACS are deja integrarea actualizată, nu reinstala snapshotul pentru fiecare hub. Snapshotul este o copie de siguranță/reproducibilitate.

---

# 3. Structura kitului 0.10.0

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

Pentru instalarea normală pe un hub nou, pachetul principal transferat este **installerul unic** din `installers/`. `hub_bundle/` și installerul Wi-Fi separat sunt păstrate și ca piese independente pentru diagnostic/recovery.

---

# 4. Reguli de siguranță — nu sări peste ele

1. Modelul trebuie să fie exact `lumi.gateway.aeu01`.
2. Rulează `Verify-Kit.ps1` înainte să transferi ceva.
3. Rulează `Check-Prerequisites.ps1` înainte de intervenție.
4. Nu flashea fără `ULTIMATE_PREFLASH_OK`.
5. Nu flashea fără `BACKUP_PAIR_OK`.
6. Nu scrie niciodată EFUSE, ROM, Config, PSECT sau pFLASH.
7. Nu face full-chip erase.
8. La prima conversie se șterge numai zona aplicației `0x0..0x33200`.
9. Nu repeta ERASE/WRITE doar pentru că un readback opțional a pierdut handshake-ul.
10. Nu da reboot între ERASE și WRITE.
11. Nu publica acest ZIP: configurația MQTT este personală/locală și poate conține credentialele brokerului.
12. Tokenul MiIO, backupurile JN5189 și credentialele Wi-Fi nu se publică.

Dacă un pas raportează `FAIL`, `ERROR`, `MISMATCH` sau nu afișează markerul așteptat, **STOP la acel pas**.

---

# 5. Regula de prompt

În acest README:

- `PS C:\...>` = **PowerShell pe Windows**;
- `#` = **shell Telnet pe hub**.

Nu lipi comenzi `/data/...` în PowerShell și nu lipi comenzi Windows în Telnet.

---

# 6. Pregătirea PC-ului și verificarea kitului

Din rădăcina kitului, în PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\Verify-Kit.ps1
.\scripts\windows\Check-Prerequisites.ps1
```

Rezultatul corect:

```text
KIT_SHA256_OK
PREREQUISITES_OK
```

`Check-Prerequisites.ps1` verifică:

- Python;
- `python-miio`;
- SPSDK `dk6prog`;
- existența clientului Telnet Windows și afișează warning dacă lipsește.

Dacă launcherul implicit `C:\Windows\py.exe` nu există:

```powershell
.\scripts\windows\Check-Prerequisites.ps1 -Python py
```

sau indică executabilul Python real.

### Instalare software dacă lipsește

```powershell
python -m pip install python-miio
python -m pip install "spsdk[dk6]"
python -m spsdk.apps.dk6prog --help
```

---

# 7. Pregătirea hubului stock

Înainte de modificări:

- adaugă hubul în Xiaomi Home;
- folosește Wi-Fi 2.4 GHz;
- rezervă adresa curentă în DHCP;
- obține tokenul MiIO și păstrează-l separat;
- verifică faptul că hubul funcționează normal stock.

Pentru fiecare hub păstrează o fișă separată:

```text
Nume hub:
Model:
MAC Wi-Fi:
IP inițial:
Firmware stock:
Data backupului JN5189:
SHA256 backup A:
SHA256 backup B:
SHA256 firmware Router:
Nume dispozitiv Zigbee2MQTT:
Nume intrare Home Assistant:
```

Nu pune tokenul MiIO în această fișă dacă documentul va fi distribuit.

---

# 8. Activează Telnet temporar

Din PowerShell:

```powershell
.\scripts\windows\Enable-TemporaryTelnet.ps1 -HubIp HUB_IP
```

Scriptul cere tokenul MiIO ascuns, verifică întâi dispozitivul și apoi trimite cererea de Telnet.

Markerii așteptați:

```text
MIIO_TOKEN_OK
TELNET_REQUEST_SENT HUB_IP
```

Conectare:

```powershell
telnet HUB_IP
```

Login documentat:

```text
user: admin
password: gol
```

Dacă nu apare shell-ul hubului, nu continua cu comenzile marcate `#`.

---

# 9. Transferă installerul unic 0.10.0

## Pe hub

```sh
rm -f /tmp/m1s_ultimate_hub_prep_v0.10.0.tgz
nc -l -p 12345 > /tmp/m1s_ultimate_hub_prep_v0.10.0.tgz
```

Comanda rămâne în așteptare.

## Pe Windows

```powershell
.\scripts\windows\Send-FileToM1S.ps1 `
  -HubIp HUB_IP `
  -Path .\installers\m1s_ultimate_hub_prep_v0.10.0.tgz `
  -Port 12345
```

## Înapoi pe hub

```sh
md5sum /tmp/m1s_ultimate_hub_prep_v0.10.0.tgz
```

MD5-ul exact al installerului unic din această revizie:

```text
6eff82e0acd07d7d5f7bef752d556577
```

Dacă diferă, șterge fișierul și retransmite. Nu instala un fișier cu hash diferit.

---

# 10. Rulează pregătirea completă a hubului

Pe hub:

```sh
rm -rf /tmp/m1s_ultimate_prep
mkdir -p /tmp/m1s_ultimate_prep
tar -xzf /tmp/m1s_ultimate_hub_prep_v0.10.0.tgz -C /tmp/m1s_ultimate_prep
/bin/sh -n /tmp/m1s_ultimate_prep/install.sh
/bin/sh /tmp/m1s_ultimate_prep/install.sh
```

Installerul face cinci etape:

```text
0/5 VALIDATE PAYLOAD
1/5 CORE v0.10.0
2/5 WI-FI RECOVERY v0.10.0
3/5 INSTALL DIAGNOSTICS
4/5 STRICT PREFLIGHT
5/5 READY
```

El verifică modelul, hashurile interne și sintaxa shell, apoi instalează core-ul, recovery-ul și verificatoarele.

Markerii finali obligatorii:

```text
ULTIMATE_PREFLASH_OK
ULTIMATE_HUB_PREPARED_V0_10_0
```

**În acest moment JN5189 nu a fost încă scris.**

Poți repeta poarta înainte de ISP:

```sh
/data/scripts/ultimate_preflash_check.sh
```

Trebuie să se termine exact cu:

```text
ULTIMATE_PREFLASH_OK
```

Preflight-ul verifică, fără să afișeze credentialele:

- modelul;
- toate scripturile critice;
- sintaxa shell;
- MD5-ul managerului de rețea;
- hook-ul Wi-Fi/DHCP;
- existența credentialelor Wi-Fi capturate local;
- configurația MQTT;
- procesele Wi-Fi Recovery;
- starea STA/AP stock;
- faptul că `/dev/ttyS1` este liber;
- Factory Reset Guard activ;
- service trim activ.

---

# 11. Intră JN5189 în ISP

Pe hub:

```sh
/data/scripts/jn5189_enter_isp_1888.sh
```

Nu porni backupul dacă scriptul raportează eroare.

Din Windows, pentru verificare avansată:

```powershell
python -m spsdk.apps.dk6prog `
  -b PYSERIAL `
  -d "socket://HUB_IP:1888" `
  -n info
```

Așteptat:

```text
Detected DEVICE: JN5189
FLASH Memory ID 0
Length 0x9DE00
Sector 0x200
```

Oprește procedura dacă dispozitivul sau geometria memoriei diferă.

---

# 12. Backup dublu obligatoriu

În PowerShell, din rădăcina kitului:

```powershell
.\scripts\windows\JN5189-Backup-PAIR-VERIFY.ps1 -HubIp HUB_IP
```

Dacă trebuie indicat Python explicit:

```powershell
.\scripts\windows\JN5189-Backup-PAIR-VERIFY.ps1 `
  -HubIp HUB_IP `
  -Python "C:\Path\To\python.exe"
```

Scriptul face:

```text
read A → 646656 bytes
pauză 2 s
read B → 646656 bytes
SHA256 A
SHA256 B
comparare
```

Final obligatoriu:

```text
BACKUP_PAIR_OK SHA256=...
BACKUP_GATE=...\backups\BACKUP_PAIR_OK_HUB_IP.txt
```

Dacă apare:

```text
BACKUP_HASH_MISMATCH
```

**STOP. Nu flashea.**

Păstrează backupurile în minimum două locații. Ele pot conține date specifice dispozitivului și nu trebuie publicate.

---

# 13. Identitatea firmware-ului Router

Firmware-ul permis de acest kit este:

```text
Fișier: firmware/jn5189_router_rgb_lux_rejoin_test.bin
Dimensiune: 209296 bytes
SHA256: a1a1f302be9e3ab95fd6a3b8f4ac260e1f397fec275fb3e3caf8418cd75e7a2f
Memory ID: 0 / FLASH
Erase pentru prima conversie: 0x0..0x33200
```

Numele fișierului nu este suficient. Dimensiunea și SHA256 sunt identitatea firmware-ului.

---

# 14. Flash JN5189 — numai după backup valid

În PowerShell:

```powershell
.\scripts\windows\JN5189-Flash-WRITE.ps1 -HubIp HUB_IP
```

Scriptul verifică din nou markerul și ambele backupuri înainte de ERASE.

Markerii intermediari corecți:

```text
BACKUP_GATE_OK SHA256=...
FIRMWARE_OK bytes=209296 SHA256=...
```

Apoi execută:

```text
ERASE numai 0x0..0x33200
WRITE 209296 bytes la 0x0
```

Finalul corect:

```text
FLASH_WRITE_OK bytes=209296 SHA256=A1A1F302BE9E3AB95FD6A3B8F4AC260E1F397FEC275FB3E3CAF8418CD75E7A2F
```

### Important după WRITE

Nu face readback imediat în fluxul normal. SPSDK poate pierde handshake-ul după scriere deși firmware-ul a fost scris și bootează corect. Readbackul rămâne un instrument separat de diagnostic.

Nu repeta ERASE/WRITE doar din cauza unui timeout la readback.

---

# 15. Închide ISP și bootează Routerul

Pe hub:

```sh
/data/scripts/jn5189_close_isp_1888.sh
/data/scripts/jn5189_boot_router.sh
```

În Zigbee2MQTT activează **Permit join** și așteaptă apariția dispozitivului Lumi/NXP `BDB-Router` cu rol Router.

Dacă nu apare:

- verifică Permit join;
- verifică GPIO33=`1` și GPIO18=`0`;
- verifică să nu ruleze `mzigbee_agent`;
- verifică să nu existe `cat /dev/ttyS1` permanent;
- pulsează din nou cu `jn5189_boot_router.sh`;
- nu repeta flash-ul fără o cauză demonstrată.

---

# 16. Adaugă hubul în Home Assistant

Versiunea inclusă în kit:

```text
0.21.7
```

Dacă repo-ul HACS este deja instalat și actualizat, adaugi doar noul hub.

Repo:

```text
caiuspoputa-debug/ha-aqara-m1s-zigbee-router
```

Snapshot offline:

```text
home_assistant/ha-aqara-m1s-zigbee-router-v0.21.7-SNAPSHOT.zip
```

Configurarea folosește Telnet local. Identitatea dispozitivului este stabilă după MAC-ul Wi-Fi, astfel încât schimbarea ulterioară a IP-ului să nu creeze un dispozitiv nou.

Adaugă integrarea înainte de rebootul final, apoi verifică entitățile după stabilizare.

---

# 17. Reboot final și verificare automată

Pe hub:

```sh
sync
reboot
```

După ce revine online, reconectează-te prin Telnet și rulează:

```sh
/data/scripts/verify_hub_ultimate.sh
```

Scriptul așteaptă serviciile lente și verifică:

- modelul;
- managerul de rețea;
- Telnet și syslog;
- Wi-Fi Recovery manager + portal;
- GPIO button watcher;
- bridge-ul legacy;
- `mha_master -b`;
- `mzigbee_agent`;
- GPIO33/GPIO18;
- portul ISP 1888 închis;
- `post_init.sh` executat;
- Factory Reset Guard;
- service trim;
- SSID/parolă recovery prezente fără a le afișa;
- hook-ul Wi-Fi/static-IP.

Finalul dorit:

```text
ULTIMATE_POSTBOOT_OK
```

`service_trim` are intenționat o întârziere de aproximativ 120 s. Dacă numai acel status nu este încă disponibil, repetă verificarea după stabilizarea completă.

Verifică și practic:

- Router online în Zigbee2MQTT;
- ring light;
- lux;
- media player individual;
- grup media;
- buton fizic;
- `click` / multi-click;
- `hold_start`, `hold_repeat`, `hold_release`.

---

# 18. Testează Wi-Fi Recovery înainte să-l activezi

Recovery-ul automat AP este intenționat dezactivat după instalare.

Simulare sigură:

```sh
touch /data/m1s_wifi/test_noip
sleep 20
tail -n 30 /tmp/m1s_wifi_manager.log
rm -f /data/m1s_wifi/test_noip
```

În log trebuie să apară faptul că recovery-ul **ar** porni AP, dar rețeaua nu trebuie modificată pentru că lipsește `actions_enabled`.

Numai după ce simularea este corectă:

```sh
touch /data/m1s_wifi/actions_enabled
chmod 600 /data/m1s_wifi/actions_enabled
sync
```

Dezactivare:

```sh
rm -f /data/m1s_wifi/actions_enabled
```

Portalul, atunci când AP-ul recovery este activ, folosește portul `8080`, de obicei la una dintre adresele:

```text
http://192.168.49.1:8080/
http://192.168.1.1:8080/
```

Nu expune portul 8080 în Internet.

---

# 19. IP static — fă-l ultimul, după ce hubul este stabil

Nu seta IP static înainte de:

- flash reușit;
- Router online;
- Home Assistant funcțional;
- reboot final;
- `ULTIMATE_POSTBOOT_OK`;
- test Wi-Fi Recovery.

În Home Assistant:

```text
Aqara M1S Zigbee Router
→ Configure
→ Adresă de rețea / Network address
→ IP static
```

În 0.21.7 introduci **doar ultimul octet** într-un câmp numeric (`2–254`). Prefixul vine din IP-ul actual.

Fluxul sigur:

1. Home Assistant cere adresa candidat;
2. hubul o expune temporar;
3. Home Assistant verifică faptul că răspunde același MAC Wi-Fi;
4. numai după confirmare adresa este păstrată și intrarea existentă este actualizată;
5. un candidat neconfirmat expiră automat după 120 s.

La schimbarea rețelei Wi-Fi, modul static este eliminat înainte de testarea noului SSID.

---

# 20. Factory Reset Guard și butonul fizic

Calea validată este:

```text
post_init.sh
→ factory_reset_guard_boot.sh
→ overlay temporar peste /dev/input
→ /dev/input/event0 dummy pentru firmware-ul Aqara
→ stack stock pornește fără butonul fizic real
→ gpio_button_watch.sh citește GPIO7
→ m1s_mqtt_publish.sh
→ MQTT
→ Home Assistant Physical Button
```

Payloadurile suportate includ:

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

Test manual al publisherului:

```sh
/data/m1s_button/m1s_mqtt_publish.sh click
echo "rc=$?"
```

Cu guardul activ, o apăsare fizică trebuie să ajungă prin GPIO7/MQTT și nu trebuie să creeze un nou click stock `basis.button`.

Calea `button_watch.sh` pe loguri rămâne pentru compatibilitate/diagnostic, dar nu este metoda principală de protecție la reset.

---

# 21. Service trim

După boot sunt oprite controlat:

```text
homekitserver
mijia_automation
```

Rămân active componentele necesare:

```text
mha_basis
mha_master
telnetd
Wi-Fi
audio
JN5189 Router
```

Nu opri brutal `mha_basis` sau `mha_master` pentru protecția butonului. Factory Reset Guard este mecanismul corect.

---


# 22. Home Assistant 0.21.7 — entități și disponibilitate

Această secțiune este verificată față de snapshotul `0.21.7` inclus în kit, nu preluată doar din documentația istorică.

Pentru fiecare hub sunt create, după caz:

- **Hub Connectivity** — senzor binar de conectivitate; rămâne el însuși disponibil pentru a putea indica `Disconnected`;
- **Ring Light** — lumină RGB locală;
- **Media Player** — playerul individual al hubului;
- **Sound Playback Volume** — volum `1–100%` pentru sunetele WAV locale;
- **Fine Volume Trim** — corecție fină individuală `-2.00% … +1.00%`, pas `0.01%`;
- **Include in M1S Media Group** — include/exclude hubul din grupul comun;
- **Physical Button** — evenimente MQTT pentru butonul fizic;
- **Illuminance** — lux, cu atribute `adc_raw` și `millivolts`;
- **Hub Temperature**;
- **WiFi IP**;
- **HomeKit Process**;
- **MQTT Process**;
- **Telnet Process**;
- **JN5189 Router**;
- **Refresh Sound List**;
- câte un buton pentru fiecare WAV administrat din `/data/musics/music-ch`.

Global există o singură entitate:

```text
M1S Media Group
```

Evenimente acceptate de **Physical Button**:

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

### Disponibilitate

Integrarea `0.21.7` verifică accesibilitatea Telnet aproximativ la fiecare `5 s`, independent de citirea luxului. Luxul este actualizat separat, aproximativ la `15 s`, astfel încât o problemă UART/lux să nu țină hubul artificial offline.

Când hubul dispare:

- controalele care depind de hub devin indisponibile;
- **Hub Connectivity** rămâne citibil și arată deconectarea;
- numele intrării/dispozitivului poate primi sufixul `🔴 Indisponibil`.

La revenire, integrarea detectează din nou hubul și, după aproximativ `10 s`, stinge best-effort inelul roșu stock de boot. Ultima culoare și luminozitate alese sunt păstrate pentru următoarea aprindere manuală, dar revenirea online nu reaprinde automat o stare ON veche.

---

# 23. Audio și media — valorile reale din 0.21.7

Parametrii de mai jos sunt verificați direct în snapshotul `0.21.7` inclus în acest kit.

## Player individual

```text
Port hub:               12346
PCM:                    S32_LE
Canale:                 mono
Rată:                   32000 Hz
Chunk/perioadă:         35 ms
HA jitter buffer:       4.0 s
Prebuffer inițial:      2.5 s
Rebuffer resume:        2.0 s
Remote prefill:         1.4 s
```

Driverul ALSA al M1S raportează o perioadă de `1120` cadre la `32 kHz`, adică `35 ms`; transportul este aliniat la aceeași perioadă.

Sliderul nativ al playerului folosește pași de `0.1%`. **Fine Volume Trim** este separat și adaugă o corecție fină de `-2.00 … +1.00` puncte procentuale.

## Grup media

```text
Port hub:               12347
PCM:                    S32_LE mono 32000 Hz
Chunk:                  35 ms
Jitter buffer comun:    4.0 s
Prebuffer inițial:      2.5 s
Rebuffer resume:        2.0 s
Remote prefill:         1.4 s
Primul receiver:        max. 3.0 s
Fereastră cohortă:      0.30 s
```

Grupul folosește o singură cronologie PCM comună. În buildul `0.21.7`:

- **adaptive sync este dezactivat**;
- resincronizarea periodică automată este dezactivată;
- un membru revenit poate folosi istoric PCM + catch-up, fără restart global obligatoriu;
- serviciul manual `resync_media_group` are cooldown de `20 s`;
- `reset_media_group` face reset dur numai pentru transportul grupului.

Pentru diagnostic, nu presupune că orice decalaj se rezolvă prin restart repetat. Verifică mai întâi receiverul hubului afectat, rețeaua și procesele `nc`/`aplay`.

---

# 24. WAV / ZIP — administrare și transfer

Directorul gestionat de integrare:

```text
/data/musics/music-ch
```

Porturile folosite:

```text
12347  sursă WAV locală
12348  sink PCM pentru WAV local
12349  upload WAV din Home Assistant
1889   download manual temporar către Windows
```

Limitele confirmate în codul `0.21.7`:

```text
WAV individual:         maximum 20 MiB
ZIP:                    maximum 64 fișiere WAV
Conținut WAV total ZIP: maximum 100 MiB
Arhivă ZIP:             maximum 100 MiB
```

În **Configure** poți încărca un WAV sau un ZIP. ZIP-ul este deschis în Home Assistant, nu pe hub. Fișierele administrate ajung numai în `/data/musics/music-ch`.

Transferul principal folosește TCP pe `12349`, apoi verifică dimensiunea și MD5 înainte de înlocuirea destinației. Există fallback prin BusyBox `base64` dacă transportul TCP eșuează. După upload sau ștergere reușită, integrarea reîncarcă intrarea pentru a actualiza lista de sunete.

Conversie recomandată:

```sh
ffmpeg -y -i input.mp3 -ac 1 -ar 32000 -c:a pcm_s32le output.wav
```

### Descărcarea unui WAV existent

Pe hub:

```sh
find /data/musics -type f -name '*.wav'
nc -l -p 1889 < /cale/catre/sunet.wav
```

Pe Windows, din kit:

```powershell
.\scripts\windows\Receive-FileFromM1S.ps1 `
  -HubIp HUB_IP `
  -OutputPath "$env:USERPROFILE\Downloads\sunet.wav" `
  -Port 1889
```

Portul `1889` este temporar și nu trebuie expus în Internet.

---

# 25. Rețea din Home Assistant — DHCP, IP static și schimbare Wi-Fi

## DHCP / IP static

În `0.21.7`, pagina **Configure → Network address** citește starea managerului de rețea de pe hub și permite:

```text
Automat (DHCP)
IP static
```

Pentru IP static:

- este suportată rețeaua `/24` (`255.255.255.0`);
- introduci numai ultimul octet, `2–254`;
- managerul refuză gateway-ul și o adresă detectată ca fiind deja folosită;
- adresa este pusă mai întâi ca **alias/candidat temporar**;
- Home Assistant se conectează la candidat și verifică **același MAC Wi-Fi**;
- numai după verificare candidatul este confirmat;
- integrarea verifică apoi că noul IP este efectiv activ;
- un candidat neconfirmat expiră automat conform managerului de pe hub.

Identitatea config-entry-ului este `mac:<wifi_mac>`, astfel încât schimbarea IP-ului nu trebuie să creeze un hub nou în Home Assistant.

## Schimbarea Wi-Fi

Meniul **Configure → Change Wi-Fi network** este disponibil numai dacă modulul Wi-Fi Recovery este instalat.

Fluxul Ultimate:

1. integrarea cere managerului `wifi-prepare`, care trece persistent pe DHCP înainte de schimbarea rețelei;
2. SSID-ul și parola sunt transferate prin sesiunea Telnet existentă;
3. pe hub sunt staged în fișiere cu permisiuni `0600`;
4. `wifi_apply_candidate.sh` testează rețeaua nouă;
5. noua configurație devine `safe/` numai după obținerea unui IPv4 proaspăt;
6. la eșec rămâne disponibil mecanismul Recovery/AP;
7. wrapperul Ultimate elimină lock-ul HA cu `rm -r`, compatibil cu BusyBox-ul real al hubului.

Parola Wi-Fi nu este salvată în config entry/options Home Assistant și nu este afișată de verificatoarele kitului.

**Telnet este însă plaintext.** Folosește aceste funcții numai într-un LAN de încredere și nu expune portul `23` în Internet.

Dacă noua rețea folosește alt subnet, Home Assistant poate pierde temporar hubul până când noua adresă este cunoscută/configurată.

---

# 26. Protocoalele locale JN5189 — diagnostic și recovery

Aceste cadre sunt folosite de integrarea actuală.

## RGB — `A5`

```text
A5 RED GREEN BLUE CHECKSUM
CHECKSUM = A5 XOR RED XOR GREEN XOR BLUE
```

Test OFF direct pe hub:

```sh
printf '\245\000\000\000\245' > /dev/ttyS1
```

Nu lăsa un `cat /dev/ttyS1` manual activ după teste.

## Lux — `A6`

Cerere:

```text
A6 00 00 00 A6
```

Răspuns valid:

```text
A6 RAW_H RAW_L MV_H MV_L LUX_H LUX_L CHECKSUM
```

Checksumul este XOR-ul primilor șapte bytes. Integrarea expune:

- lux;
- ADC raw;
- millivolts.

## Rejoin Zigbee — `A7`

Cerere:

```text
A7 52 4A 4E F1
```

Confirmare:

```text
A7 4F 4B 00 A3
```

Pentru mutarea Routerului pe alt coordinator:

1. activează **Permit join** pe coordinatorul destinație;
2. Home Assistant → Aqara M1S Zigbee Router → **Configure**;
3. alege **Join a different Zigbee coordinator / Conectare la alt coordonator Zigbee**;
4. confirmă.

Operația este destinată contextului Zigbee din JN5189; nu este un factory reset Linux și nu șterge Wi-Fi-ul sau sunetele de pe hub.

---

# 27. Servicii Home Assistant și securitate

Domeniu:

```text
aqara_m1s_zigbee_router
```

Serviciile existente în snapshotul `0.21.7`:

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

Roluri:

- `play_url` — descarcă/redă o sursă WAV prin hub;
- `play_sound` — redă un WAV deja existent pe filesystem;
- `run_command` — execută shell pe hub prin Telnet;
- `upload_sound` / `delete_sound` / `refresh_sounds` — administrare WAV;
- `reset_media_group` — recovery dur al transportului comun;
- `resync_media_group` — realiniere manuală a grupului;
- `update_media_metadata` — actualizează titlu/artist/canal pentru fluxul activ fără a reporni audio.

### Atenție la `run_command`

`run_command` înseamnă practic **acces administrativ shell la hub**. Nu îl expune utilizatorilor neautorizați și nu construi automatizări care trimit în el text nevalidat provenit din input extern.

---

# 28. Fișiere persistente și procese așteptate

## Fișiere importante pe hub

Boot / Router / protecție:

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

Buton / MQTT:

```text
/data/m1s_button/m1s_mqtt_publish.sh
/data/m1s_button/m1s_button.conf
/data/m1s_button/mqtt_username
/data/m1s_button/mqtt_password
/data/m1s_button/button_watch.sh
```

Rețea:

```text
/data/m1s_network/network_manager.sh
/data/m1s_network/wifi_apply_candidate_wrapper.sh
/data/m1s_wifi/
/data/m1s_wifi/safe/ssid
/data/m1s_wifi/safe/pass
/data/m1s_wifi/actions_enabled
```

Sunete:

```text
/data/musics/music-ch/
```

Nu publica backupurile JN5189, tokenul MiIO, credentialele MQTT sau fișierele `safe/ssid` / `safe/pass`.

## Procese/stări după boot stabil

În configurația Ultimate:

- `telnetd` — prezent;
- `mha_basis` și `mha_master` — păstrate;
- `gpio_button_watch.sh` — prezent când guardul este activ;
- `homekitserver` — oprit de `service_trim`;
- `mijia_automation` — oprit de `service_trim`;
- `mzigbee_agent` — nu trebuie să dețină UART-ul JN5189;
- `wifi_manager.sh` și portalul — prezente dacă Wi-Fi Recovery este instalat;
- fără listener ISP `1888` rămas după flash;
- fără `cat /dev/ttyS1` manual permanent.

Verificatorul principal rămâne:

```sh
/data/scripts/verify_hub_ultimate.sh
```

și trebuie să ajungă la:

```text
ULTIMATE_POSTBOOT_OK
```

---

# 29. Disciplina de update

## Integrarea Home Assistant

1. fă backup Home Assistant;
2. notează versiunea curentă;
3. actualizează prin HACS sau manual;
4. repornește Home Assistant;
5. verifică manifestul și logurile;
6. testează întâi **un singur hub**;
7. abia apoi lasă noua versiune pe toate huburile.

Snapshotul `0.21.7` din Ultimate este punctul reproductibil al acestui kit. Dacă pe GitHub/HACS există o versiune mai nouă, nu presupune automat că documentația R2 descrie toate modificările ei.

## Firmware JN5189

Pentru un hub stock nou se folosește exact fluxul Ultimate cu backup A/B înainte de prima scriere.

Pentru un Router deja funcțional:

- păstrează backupul stock al acelui hub;
- salvează imaginea Router curentă dacă ai nevoie de rollback exact;
- verifică hashul noii imagini;
- eliberează UART-ul;
- intră în ISP;
- urmează instrucțiunile specifice buildului nou.

Nu presupune că procedura de update a unui Router existent este identică cu prima conversie stock. Nu executa `erase` doar pentru că un fișier nou are alt nume.

---

# 30. Limitări și lucruri de ținut minte

1. **Portul 12347 este comun** pentru receiverul grupului media și sursa WAV locală. Nu porni un WAV local pe un hub cât timp același hub deține receiverul de grup pe `12347`.
2. `Stable Ultimate` descrie un build consolidat și verificat structural, dar combinația exactă 0.10.0 trebuie încă validată cap-coadă pe primul hub stock nou.
3. Wi-Fi Recovery automat rămâne dezactivat până când testul de simulare trece și creezi intenționat `actions_enabled`.
4. Backupul JN5189 este specific hubului. Nu restaura backupul altui M1S.
5. Snapshotul HA inclus este `0.21.7`; versiuni ulterioare pot schimba comportamentul și trebuie auditate înainte de a actualiza documentația master.
6. Telnet și porturile locale ale proiectului trebuie să rămână exclusiv în LAN.
7. Fișierele istorice `mqtt_client.py` și `select.py` există în snapshot, dar `select` nu este în lista platformelor încărcate; nu le considera parte a fluxului operațional curent doar pentru că există în repository.

---

# 31. Porturi importante

| Port | Rol |
|---:|---|
| 23 | Telnet local |
| 1886 | tunel UART creat de integrare |
| 1888 | listener temporar ISP/SPSDK |
| 1889 | transfer temporar de fișier de pe hub |
| 8080 | portal Wi-Fi Recovery |
| 12345 | transfer manual temporar către hub |
| 12346 | media player individual |
| 12347 | grup media și sursă WAV locală; conflict istoric cunoscut |
| 12348 | PCM pentru WAV local |
| 12349 | upload WAV |

Nu publica aceste porturi în Internet.

---

# 32. Hashuri de referință pentru această revizie

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

Pentru integritatea întregului kit folosește `SHA256SUMS.txt` și `Verify-Kit.ps1`, nu doar aceste valori.

---

# 33. Checklist final — hub gata

Nu considera hubul terminat până când toate punctele relevante sunt bifate:

### Kit și PC

- [ ] `KIT_SHA256_OK`
- [ ] `PREREQUISITES_OK`
- [ ] model `lumi.gateway.aeu01`
- [ ] DHCP reservation inițial
- [ ] token MiIO verificat
- [ ] Telnet funcțional

### Pregătire hub

- [ ] MD5 installer unic corect
- [ ] `ULTIMATE_PREFLASH_OK`
- [ ] `ULTIMATE_HUB_PREPARED_V0_10_0`
- [ ] Wi-Fi Recovery a capturat local SSID/parolă
- [ ] `actions_enabled` încă absent înainte de testul recovery

### Backup JN5189

- [ ] backup A = 646656 bytes
- [ ] backup B = 646656 bytes
- [ ] SHA256 A = SHA256 B
- [ ] `BACKUP_PAIR_OK`
- [ ] backupurile salvate și în altă locație

### Flash

- [ ] `BACKUP_GATE_OK`
- [ ] `FIRMWARE_OK`
- [ ] `FLASH_WRITE_OK`
- [ ] port 1888 închis după flash
- [ ] GPIO33=`1`
- [ ] GPIO18=`0`
- [ ] `BDB-Router` online în Zigbee2MQTT

### Home Assistant și boot

- [ ] integrare 0.21.7 sau mai nouă compatibilă
- [ ] hubul apare o singură dată și este identificat prin MAC
- [ ] reboot final făcut
- [ ] `ULTIMATE_POSTBOOT_OK`
- [ ] Factory Reset Guard activ
- [ ] GPIO watcher activ
- [ ] `service_trim` activ
- [ ] Telnet revine după reboot
- [ ] JN5189 Router revine după power cycle

### Funcții

- [ ] RGB/ring light
- [ ] lux
- [ ] radio/media individual
- [ ] media group
- [ ] click și multi-click
- [ ] HOLD start/repeat/release
- [ ] publisher MQTT manual
- [ ] test Wi-Fi Recovery în simulare
- [ ] recovery automat activat numai dacă îl dorești
- [ ] IP static setat numai după toate testele de mai sus

---

# 34. Recovery și revenire

## 34.1 SPSDK timeout

Verifică:

```sh
ps w | grep '[c]at /dev/ttyS1'
ps w | grep '[m]zigbee_agent'
netstat -lnt | grep 1888
```

Dacă listenerul trebuie rearmat:

```sh
/data/scripts/jn5189_close_isp_1888.sh
/data/scripts/jn5189_enter_isp_1888.sh
```

Continuă de la ultimul pas sigur. Nu repeta automat ERASE/WRITE dacă `FLASH_WRITE_OK` a fost deja obținut.

Un timeout la un readback opțional după WRITE nu demonstrează singur că scrierea a eșuat. Verifică mai întâi dacă Routerul bootează și apare în Zigbee2MQTT.

## 34.2 Restaurarea JN5189 stock

Folosește **numai backupul A/B al aceluiași hub**.

Ordinea de principiu:

1. oprește/dezactivează temporar integrarea HA dacă ține UART-ul;
2. intră în ISP;
3. verifică din nou identificarea `JN5189` și geometria FLASH;
4. folosește backupul complet validat al hubului respectiv;
5. după restaurare fă readback pe aceeași lungime și compară SHA256;
6. închide ISP;
7. pornește JN5189 normal.

Restaurarea flashului JN5189 nu anulează automat modificările Linux din `/data`. Pentru revenire completă la comportamentul stock trebuie tratat separat și bootul Linux.

Nu restaura niciodată backupul unui alt hub.

## 34.3 Revenire temporară la boot Linux stock

Pentru diagnostic, nu șterge imediat `post_init.sh`. Redenumește-l:

```sh
mv /data/scripts/post_init.sh /data/scripts/post_init.sh.disabled
sync
reboot
```

Aceasta oprește hook-ul Ultimate la boot. Un JN5189 care încă rulează firmware Router nu devine stock doar prin această operație; evită concurența inutilă a `mzigbee_agent` cu firmware-ul Router.

Păstrează backupul fișierului și documentează exact ce ai dezactivat.

## 34.4 Wi-Fi intră imediat în AP după boot

Verifică mai întâi stările stock:

```sh
/data/scripts/aqara_wifi_boot_state.sh check
```

Dacă este necesar:

```sh
/data/scripts/aqara_wifi_boot_state.sh fix
/data/scripts/aqara_wifi_boot_state.sh check
```

Acesta este alt caz decât recovery-ul AP declanșat după lipsă îndelungată de IPv4.

Pentru starea modulului Recovery:

```sh
ps w | grep '[w]ifi_manager.sh'
ps w | grep '[m]1s_wifi_portal_safe.sh'
tail -n 120 /tmp/m1s_wifi_manager.log
ls -l /data/m1s_wifi/actions_enabled
wc -c /data/m1s_wifi/safe/ssid /data/m1s_wifi/safe/pass
```

Nu afișa `safe/pass` în loguri sau capturi.

Revenire manuală la copia Wi-Fi sigură:

```sh
rm -f /data/m1s_wifi/ap_hold
/data/m1s_wifi/restore_sta.sh
```

## 34.5 Probleme buton

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

Interpretare:

- publisher manual nu ajunge în HA → broker/topic/credentiale MQTT;
- publisher manual ajunge, butonul fizic nu → GPIO7/watcher;
- apare din nou `basis.button click` → guardul/overlay-ul nu este activ cum trebuie;
- watcherul lipsește după boot → verifică `factory_reset_guard_boot.conf`, `gpio_button_watch.conf` și `post_init.sh`.

## 34.6 Probleme audio

Verifică exact traseul implicat:

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

Nu omorî generic toate procesele `nc` sau `aplay`; poți întrerupe alte funcții valide ale hubului.

Dacă problema este doar grupul, încearcă mai întâi serviciile dedicate `resync_media_group` sau `reset_media_group`, nu reboot complet al Home Assistant.

---

# 35. Ce NU folosim pentru următorul hub

Pentru un hub stock nou **nu mai combinăm manual**:

```text
Aqara_M1S_Complete_Kit_v0.5.7...
Aqara_M1S_WORKING_v0.8...
Aqara_M1S_WORKING_v0.9...
```

Ele rămân arhivă și surse ale componentelor validate. Fluxul nou pornește din:

```text
Aqara_M1S_0.10.0_STABLE_ULTIMATE_KIT
```

Nu înlocui fișiere din 0.10.0 cu variante vechi doar pentru că au același nume.

---

# 36. Notă personal/local

Acest kit este construit pentru instalația locală existentă. Configurația MQTT a butonului provine din kitul local validat și poate conține credentiale ale brokerului.

**Nu publica ZIP-ul Ultimate în forma aceasta.** Pentru GitHub/public trebuie creată separat o ediție sanitizată.

Kitul nu include:

- token MiIO;
- SSID-ul Wi-Fi;
- parola Wi-Fi în payloadul distribuit.

Credentialele Wi-Fi de recovery sunt capturate direct pe hub în timpul instalării.

---

# 37. Regula de aur pentru următorul hub

Urmează exact această ordine:

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
→ reboot final
→ ULTIMATE_POSTBOOT_OK
→ teste funcționale
→ simulare Wi-Fi Recovery
→ opțional actions_enabled
→ opțional IP static
```

**Nu trece la etapa următoare până când markerul etapei curente nu este corect.**

Pentru auditul tehnic al buildului vezi `docs/VALIDATION_REPORT.md`.
