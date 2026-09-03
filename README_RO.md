**Pachet curent: v0.20.0 + kit hub v0.8**

[**Română**](README_RO.md) | [English](README.md)

## Add-on companion pentru YouTube / YouTube Music Cast

Integrarea poate fi folosită împreună cu add-on-ul opțional **M1S YouTube Cast Receiver 1.0.1**:

- Repository: https://github.com/caiuspoputa-debug/m1s-youtube-cast-receiver
- Add-on-ul primește controlul YouTube / YouTube Music prin DIAL/Lounge și este **playerul YT/YTM**: el gestionează piesele, coada, EOF-ul de piesă, Next, Seek și Pause/Resume.
- Pentru Home Assistant și integrarea Aqara, o sesiune YT/YTM este **un singur flux audio continuu**. Schimbarea melodiei nu înseamnă STOP/PLAY sau o sursă nouă în integrare.
- Poate folosi ca țintă grupul `media_player.m1s_media_group` sau un media player Aqara M1S individual.
- Integrarea Aqara rămâne responsabilă numai de transportul audio PCM/TCP, buffering-ul transportului și sincronizarea huburilor.
- În integrare **nu se adaugă logică per-track YT/YTM**: fără detectare EOF de melodie, fără Next, fără timere de durată și fără restart/prebuffer la fiecare melodie.

# Aqara M1S Gen 1 — conversie completă în Zigbee Router + integrare Home Assistant

Versiune documentație: **2026-09-03 — v0.20.0 + kit hub v0.8**  
Integrare Home Assistant inclusă: **0.20.0**  
Model țintă: **Aqara M1S Gen 1 `lumi.gateway.aeu01`**

Acesta este ghidul principal pentru refacerea unui hub stock în configurația folosită de proiect:

- Linux, Wi-Fi și audio stock păstrate;
- Telnet persistent numai în LAN;
- NXP JN5189 convertit în **BDB Zigbee Router**;
- inel RGB și iluminare citite direct prin UART;
- media player individual și grup media în Home Assistant;
- sunete WAV locale administrabile;
- Factory Reset Guard persistent și reversibil, pentru izolarea comenzilor stock de reset;
- buton fizic citit din GPIO7 și publicat prin MQTT pe topicul existent;
- oprire controlată după boot pentru `homekitserver` și `mijia_automation`;
- mecanism opțional de recuperare Wi-Fi, fără SSID sau parole incluse în pachet.

Revizia integrării din 2026-09-03 păstrează kitul hub v0.8 validat și aduce la zi comportamentul Home Assistant/audio: instalare rapidă din bundle, service trim, Factory Reset Guard prin overlay peste `/dev/input`, watcher GPIO7 și evenimente de buton extinse până la `ten_click` plus `hold_start`, `hold_repeat`, `hold_release`.

> **Operație avansată.** Conversia scrie memoria FLASH a JN5189. Nu continua fără două backupuri identice și verificate. Nu scrie niciodată EFUSE, ROM, Config, PSECT sau pFLASH și nu executa erase complet al cipului.

---

## Modificări curente v0.20.0 / kit hub v0.8

- manifestul integrării este `0.20.0`; baza runtime rămâne `0.10.32`, fără importarea experimentelor YT/YTM din versiunile ulterioare;
- source-switch-ul de grup păstrează regula curată din `0.10.32`: **GROUP STOP pe huburi înainte de teardown-ul FFmpeg/TCP al sursei vechi**;
- source-switch-ul playerului individual folosește acum aceeași ordine: **REMOTE STOP pe receiverul 12346 înainte de teardown-ul FFmpeg/TCP**, apoi pornește transportul nou;
- dacă pre-STOP-ul individual reușește, startul nou nu mai repetă inutil același STOP; dacă pre-STOP-ul eșuează, comanda standard de start păstrează cleanup-ul scoped ca fallback;
- grupul și playerul individual folosesc perioade PCM de **35 ms**, jitter buffer de **4,0 s**, prebuffer inițial de **2,5 s**, prag de reluare după underrun de **2,0 s** și remote prefill de **1,4 s**;
- grupul nu are o pauză YT/YTM fixă: la start așteaptă primul receiver disponibil maximum **3,0 s**, acordă celorlalți o fereastră de cohortă de **0,30 s**, apoi pornește fluxul și face prefill-ul comun;
- resincronizarea periodică a receiverelor este **dezactivată**; corecția curentă de drift este continuă, per hub, prin micro-resampling adaptiv de maximum **±0,8%**, fără restartarea fluxului;
- un hub care revine online se stabilizează scurt și intră prin **history prefill + live catch-up**, fără restart global al sursei;
- add-on-ul M1S YouTube Cast Receiver `1.0.1` livrează YT/YTM ca flux continuu; integrarea nu interpretează schimbarea piesei și nu face buffering per-track;
- evenimentele de buton `click` ... `ten_click`, `hold`, `hold_start`, `hold_repeat`, `hold_release`, Factory Reset Guard, service trim, Wi-Fi, RGB/lux, WAV și restul funcțiilor rămân neschimbate.

> Secțiunile `v0.5.x TEST` de mai jos sunt **istoric de dezvoltare**. Ele explică experimente vechi și nu descriu politica audio curentă din v0.20.0.

---

## Modificări v0.5.13 TEST — resincronizare periodică

- redarea de grup de lungă durată are acum o resincronizare preventivă a receiverelor la fiecare 10 minute
- mecanismul oprește broadcasterul PCM la limita unui cadru de 20 ms, repornește pe toate huburile active doar lanțul `nc`/`aplay`, aplică din nou lead-in-ul comun de 1,5 secunde și apoi continuă fluxul
- FFmpeg nu este repornit de această resincronizare periodică; pentru fișiere finite redarea nu sare la început, deoarece sursa este ținută pe loc prin back-pressure cât timp receiverele sunt reconstruite
- restarturile complete de siguranță pentru lag persistent, coadă plină, blocaj PCM și revenirea unui hub rămân neschimbate
- batch management-ul de sunete din v0.5.11 rămâne inclus: un WAV sau un ZIP cu până la 64 WAV-uri, plus ștergere multiplă
- aceasta este o versiune TEST deoarece decalajul intermitent trebuie urmărit în timp pe huburile fizice


## Modificări v0.5.13 TEST — administrare sunete în lot

- Configure → Ștergere WAV permite selectarea și ștergerea mai multor fișiere administrate într-o singură operație
- selectorul nativ de fișier Home Assistant primește un singur upload; de aceea Configure acceptă acum fie un WAV, fie un ZIP cu mai multe WAV-uri
- un ZIP poate conține maximum 64 WAV-uri, cu limita existentă de 20 MiB per WAV și maximum 100 MiB total
- ZIP-ul este procesat în memorie; intrările non-WAV sunt ignorate, iar arhivele criptate și numele WAV duplicate sunt refuzate
- toate modificările audio v0.5.10, inclusiv watchdog, diagnosticul `tcp_pcm_backpressure` și Fine Volume Trim, rămân neschimbate

## Modificări v0.5.10 TEST — eliminarea resync-urilor false și diagnostic audio mai precis

- pragul de aproximativ 120 ms al cozii unui hub nu mai provoacă resync la un singur vârf; trebuie să rămână depășit continuu timp de 1,0 secundă
- după fiecare pornire/resync al grupului există 8 secunde de grație în care detecția de lag este suspendată, astfel încât faza normală de pornire a receiverelor să nu declanșeze alt restart
- dacă o coadă ajunge complet plină la 250 ms, sincronizarea este deja compromisă și se face în continuare resync complet imediat
- timeoutul `writer.drain()` pentru PCM/TCP crește de la 1,0 s la 2,0 s atât pentru grup, cât și pentru playerul individual
- timeoutul individual este raportat acum explicit ca `tcp_pcm_backpressure`, nu generic `hub_audio`; snapshotul de diagnostic al hubului se păstrează
- watchdog-ul pe progres PCM, resync-ul complet la revenirea unui hub și Fine Volume Trim din v0.5.9 rămân active

Această versiune rămâne **TEST** până verificăm pe huburile reale: redare de câteva ore, oprire/pornire a unui membru și absența resync-urilor repetate fără motiv.

## Modificări v0.5.9 TEST — reglaj fin individual

- fiecare media player individual primește un al doilea slider **Fine Volume Trim**
- volumul principal rămâne 0–100% cu pas de 0,1%; trim-ul este -1,00% … +1,00% cu pas de 0,01 puncte procentuale
- exemplu: volum principal 6,0% + trim +0,27% = gain PCM efectiv 6,27%
- trim-ul se aplică live pe PCM S32_LE prin aceeași rampă anti-click de 40 ms, fără restart FFmpeg, TCP, `nc` sau `aplay`
- volum principal 0% rămâne tăcere completă chiar dacă trim-ul este pozitiv; mute rămâne de asemenea tăcere completă
- logica de sincronizare și watchdog introdusă în v0.5.8 rămâne neschimbată

## Modificări v0.5.8 TEST — sincronizare și redare de lungă durată

- sincronizarea are prioritate față de continuitate: dacă un hub revine sau acumulează latență, grupul este întrerupt scurt și repornit complet
- un hub revenit online primește 8 secunde pentru stabilizare înainte de resynchronizare
- coada PCM per hub este limitată la 250 ms; la aproximativ 120 ms de coadă se cere resync complet, în loc să fie acceptată redarea întârziată
- broadcasterul cedează event loop-ul după fiecare chunk PCM de 20 ms, astfel încât writer-ele huburilor să poată goli cozile în timp real
- un watchdog nou urmărește progresul PCM, nu doar existența procesului FFmpeg; dacă nu apare PCM timp de 12 secunde, întregul grup este repornit
- starea „stabil” este acceptată numai când PCM-ul curge efectiv și există cel puțin un receiver activ

Această versiune este intenționat **TEST** până la validarea pe huburi reale a scenariilor: oprire/pornire hub în timpul redării și redare continuă de mai multe ore.

---

## 1. Ce este „curent” și ce este doar istoric

Folosește pentru o instalare nouă numai următoarele componente:

| Componentă | Versiune/fișier curent | Rol |
|---|---|---|
| Integrare Home Assistant | `custom_components/aqara_m1s_zigbee_router`, manifest `0.20.0` | control local, senzori, audio, grup, diagnostic, buton extins și schimbare Wi-Fi sigură |
| Kit hub validat | `Aqara_M1S_WORKING_v0.8_STRICT10_HOLD_EVENTS_LOCAL_2026-09-02_README_RESEARCH_OK.zip` | pachet practic pentru transformarea unui hub stock în varianta locală curentă |
| Bundle hub | `hub_bundle/m1s_hub_bundle_LOCAL.tgz` | instalează pe hub bootul persistent, guardul, service trim, GPIO watcher, MQTT publisher și scripturile JN5189 |
| Firmware JN5189 | `jn5189_router_rgb_lux_rejoin_test.bin` | Zigbee Router, RGB, lux PIO19/ADC5, comandă rejoin A7 |
| Boot persistent | `/data/scripts/post_init.sh` din bundle | Telnet, syslogd, Factory Reset Guard, service trim, UART liber, boot Router |
| Factory Reset Guard | `/data/scripts/factory_reset_guard_boot.sh` + `.conf` | izolează `/dev/input/event0` față de firmware-ul stock și previne calea de reset prin buton |
| Buton GPIO nou | `/data/scripts/gpio_button_watch.sh` + `/data/m1s_button/m1s_mqtt_publish.sh` | citește GPIO7 și publică în MQTT pe topicul existent |
| Service trim | `/data/scripts/service_trim.sh` + `.conf` | oprește după boot `homekitserver` și `mijia_automation` |
| Diagnostic boot Wi-Fi stock | `scripts/hub/aqara_wifi_boot_state.sh` | verifică și, la cerere, corectează stările Aqara care aleg STA sau AP |
| Programare JN5189 | `/data/scripts/jn5189_*.sh` și `scripts/windows/JN5189-*.ps1` | ISP, backup A/B, flash, închidere ISP și boot Router |
| Recuperare Wi-Fi | `installers/m1s_wifi_recovery_SANITIZED.tgz`, dacă există în kitul folosit | opțional/istoric; pornește AP după lipsă IP |
| Buton fizic MQTT legacy | `installers/m1s_button_bridge_SANITIZED.tgz`, dacă există în kitul folosit | istoric/opțional; citește `basis.button` din loguri și nu protejează de reset |

Folderele și README-urile versiunilor 0.1.x–0.5.5 au fost folosite pentru reconstruirea istoricului, dar nu trebuie amestecate cu procedura curentă. Vezi [auditul complet](docs/AUDIT_README_SI_SCRIPTURI.md) și [raportul de validare](docs/VALIDATION_REPORT.md).

### Hash firmware curent

```text
Fișier: jn5189_router_rgb_lux_rejoin_test.bin
Dimensiune: 209296 bytes (0x33190)
SHA256: a1a1f302be9e3ab95fd6a3b8f4ac260e1f397fec275fb3e3caf8418cd75e7a2f
Zona aplicației rotunjită la sector: 0x33200
Memory ID: 0 / FLASH
```

Verificare în PowerShell:

```powershell
Get-Item .\jn5189_router_rgb_lux_rejoin_test.bin
Get-FileHash .\jn5189_router_rgb_lux_rejoin_test.bin -Algorithm SHA256
```

Oprește procedura dacă dimensiunea sau SHA256 diferă. Buildul istoric `jn5189_router_rgb_lux_no_switch.bin` nu a demonstrat eliminarea serverului On/Off și **nu se folosește** la o conversie nouă. Numele unui binar nu este dovadă de identitate; folosește numai fișierul și hashul de mai sus.

După extragerea întregului kit, verifică toate fișierele din PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\Verify-Kit.ps1
```

Rezultatul corect se termină cu `KIT_SHA256_OK`. Lista `SHA256SUMS.txt` nu se include pe ea însăși în calcul.

---

## 2. Starea de validare

Separă clar ce provine din configurația fizic folosită și ce a fost standardizat în acest kit:

### Confirmat în istoricul proiectului

- modelul `lumi.gateway.aeu01` și firmware stock de pregătire `3.1.3_0009`;
- Linux MIPS, kernel 3.10.90, BusyBox 1.22.1;
- JN5189 pe `/dev/ttyS1`, 115200 8N1;
- GPIO18 reset, activ la `1`;
- GPIO33: ISP=`0`, boot normal=`1`;
- programare prin SPSDK și `socket://HUB_IP:1888`;
- backup FLASH Memory ID 0 de 646656 bytes (`0x9DE00`);
- firmware-ul curent scris cu succes și revenirea Routerului în Zigbee2MQTT;
- bootul persistent de bază, RGB, lux, audio și integrarea Home Assistant.

### Standardizat în această revizie

- README master reorganizat pentru o instalare de la zero;
- scripturi separate pentru preflight, ISP, boot, verificare și PowerShell;
- backup A/B obligatoriu înainte de prima conversie;
- flash prin scriptul simplu `JN5189-Flash-WRITE.ps1`, fără readback imediat în fluxul rapid validat;
- readback SHA256 disponibil pentru verificare avansată, dar un timeout de readback după `write` nu justifică repetarea automată a `erase/write` dacă Routerul bootează și intră în Zigbee2MQTT;
- script separat pentru diagnosticul și corectarea stărilor stock care aleg STA/AP, fără citirea SSID-ului sau parolei;
- installer Wi-Fi fără credențiale incluse, care preia datele existente numai local de pe hub;
- pachet separat pentru bridge-ul butonului fizic, fără broker/username/parolă incluse;
- Factory Reset Guard persistent prin `input_dir_overlay`;
- watcher GPIO7 cu `click` până la `ten_click` și `hold_start`/`hold_repeat`/`hold_release`;
- service trim pentru `homekitserver` și `mijia_automation`;
- inventar de porturi, pași de acceptare și proceduri de recuperare.

Scripturile nou standardizate au fost verificate static și ca arhive, dar recuperarea Wi-Fi și bridge-ul butonului trebuie reverificate fizic pe un hub de test înainte de copierea pe toate huburile.

---

## 3. Cerințe

### Hardware

- Aqara M1S Gen 1, model exact `lumi.gateway.aeu01`;
- rețea Wi-Fi 2,4 GHz;
- router cu rezervare DHCP;
- coordinator Zigbee2MQTT cu Permit join disponibil;
- PC Windows în aceeași rețea;
- Home Assistant cu acces la HACS sau la `/config/custom_components`.

### Software pe Windows

- PowerShell 5.1 sau PowerShell 7;
- Python 3;
- `python-miio` pentru verificarea tokenului;
- SPSDK cu aplicația `dk6prog`;
- client Telnet Windows sau PuTTY.

Instalare:

```powershell
python --version
python -m pip install python-miio
python -m pip install "spsdk[dk6]"
python -m spsdk.apps.dk6prog --help
```

Dacă scripturile Windows nu găsesc automat Python, folosește parametrul `-Python` cu calea exactă către executabilul Python instalat.

### Reguli de rețea

1. Rezervă un IP fix prin DHCP înainte de conversie.
2. Nu expune prin port forwarding Telnet sau porturile proiectului.
3. PC-ul, Home Assistant și hubul trebuie să fie în LAN-ul de încredere.
4. Ultimul octet al IP-ului este folosit de topicul butonului: `m1s/<octet>/button/action`; schimbarea IP-ului rupe asocierea până la actualizarea integrării.

---

## 4. Structura kitului

```text
Aqara_M1S_WORKING_v0.8_STRICT10_HOLD_EVENTS_LOCAL_2026-09-02_README_RESEARCH_OK.zip
├── README_FAST_RO.md
├── CHANGELOG_FIXES.txt
├── SHA256SUMS.txt
├── docs/
│   └── research/
│       ├── AQARA_M1S_192_168_0_100_RESEARCH_READ_ONLY_2026-08-28.md
│       └── AQARA_M1S_192_168_0_100_RESEARCH_RAW_2026-08-28.txt
├── firmware/
│   └── jn5189_router_rgb_lux_rejoin_test.bin
├── hub_bundle/
│   └── m1s_hub_bundle_LOCAL.tgz
└── scripts/
    └── windows/
        ├── Enable-Telnet.ps1
        ├── Send-FileToM1S.ps1
        ├── JN5189-Backup-PAIR-VERIFY.ps1
        └── JN5189-Flash-WRITE.ps1
```

Bundle-ul `m1s_hub_bundle_LOCAL.tgz` conține fișierele care ajung efectiv pe hub:

```text
install.sh
data/scripts/post_init.sh
data/scripts/service_trim.sh
data/scripts/service_trim.conf
data/scripts/factory_reset_guard_boot.sh
data/scripts/factory_reset_guard_boot.conf
data/scripts/gpio_button_watch.sh
data/scripts/gpio_button_watch.conf
data/scripts/jn5189_enter_isp_1888.sh
data/scripts/jn5189_close_isp_1888.sh
data/scripts/jn5189_boot_router.sh
data/m1s_button/button_watch.sh
data/m1s_button/m1s_mqtt_publish.sh
data/m1s_button/m1s_button.conf
```

Nu copia pe hub întregul repository Home Assistant. Pe hub ajunge numai `hub_bundle/m1s_hub_bundle_LOCAL.tgz`, iar integrarea se instalează separat în Home Assistant prin HACS sau prin copierea directorului `custom_components/aqara_m1s_zigbee_router`.

Fișierele din `docs/research` sunt arhivă tehnică, nu pași de instalare. Ele păstrează investigația read-only făcută pe hubul `192.168.0.100`, inclusiv observațiile certe, ipotezele și motivul deciziilor `service_trim`, Factory Reset Guard și GPIO7.

---

## 4A. Flux rapid validat pentru un hub stock nou

Aceasta este ordinea scurtă folosită când nu facem cercetare, ci scriem un hub nou deja cunoscut:

```text
1. Xiaomi Home: adaugă hubul stock și obține tokenul MiIO.
2. Router: rezervă IP-ul hubului în DHCP.
3. Hub: activează Telnet prin secvența fizică documentată sau prin scriptul MiIO al kitului.
4. PowerShell: conectează-te cu `telnet HUB_IP`.
5. Telnet: login `admin`, parolă goală.
6. Telnet + PowerShell: transferă `hub_bundle/m1s_hub_bundle_LOCAL.tgz`.
7. Telnet: extrage bundle-ul și rulează `./install.sh`.
8. Telnet: intră o singură dată în ISP cu `/data/scripts/jn5189_enter_isp_1888.sh`.
9. PowerShell: rulează `JN5189-Backup-PAIR-VERIFY.ps1`.
10. PowerShell: rulează `JN5189-Flash-WRITE.ps1`.
11. Telnet: închide ISP și pornește Routerul cu scripturile din `/data/scripts`.
12. Zigbee2MQTT: activează Permit join și așteaptă Routerul online.
13. Home Assistant: adaugă hubul în integrarea Aqara M1S Zigbee Router.
14. Telnet: `sync`, apoi `reboot`.
15. După minimum 120 secunde: verifică service trim, Factory Reset Guard, GPIO7/MQTT, playerul și grupul.
```

La un hub stock nou, nu schimba ordinea backup/flash. Backupul A/B vine înainte de prima scriere firmware. Readbackul după flash este opțional și separat; criteriul practic de succes al fluxului rapid este `FLASH_WRITE_OK`, portul `1888` închis, Router online în Zigbee2MQTT și validarea după reboot.

---

# PARTEA I — Pregătirea hubului stock

## Regula de prompt

În acest ghid apar două tipuri de comenzi:

- `PS C:\...>` înseamnă **PowerShell pe Windows**;
- `#` înseamnă **Telnet pe hub**.

Nu lipi comenzile `/data/...` în PowerShell și nu lipi comenzile `python`, `C:\...` sau `.\scripts\windows\...` în Telnet. Când o comandă Telnet pornește un listener `nc`, ea poate rămâne blocată până când Windows trimite fișierul sau până când SPSDK se conectează.

## 5. Etapa 0 — Fișa hubului și punctele de oprire

Înainte de orice comandă, notează separat pentru fiecare hub:

```text
Nume hub:
Model:
IP rezervat:
MAC Wi-Fi:
Firmware stock:
Token MiIO salvat în manager de parole:
Data backupului JN5189:
SHA256 backup 1:
SHA256 backup 2:
SHA256 firmware scris:
Rezultat readback:
Numele dispozitivului în Zigbee2MQTT:
Numele intrării Home Assistant:
```

### Oprește procedura dacă

- modelul nu este `lumi.gateway.aeu01`;
- IP-ul nu este rezervat;
- Telnet cade sau rețeaua este instabilă;
- SPSDK nu detectează `JN5189`;
- backupul nu are exact 646656 bytes;
- cele două backupuri stock au SHA256 diferit;
- firmware-ul nu are dimensiunea și SHA256 documentate;
- readbackul după scriere diferă de firmware, dacă ai ales să faci readback;
- flashul raportează altă dimensiune decât 209296 bytes sau alt SHA256 decât cel documentat;
- există încă un proces real `cat /dev/ttyS1` sau `mzigbee_agent` înainte de ISP.

Nu folosi reboot ca „test” între erase și write.

---

## 6. Etapa 1 — Adăugare în Xiaomi Home

1. Resetează hubul sau pune-l în modul de asociere.
2. Apasă de două ori butonul pentru trecerea din modul Aqara în Xiaomi/Mi Home.
3. Adaugă-l în Xiaomi Home pe Wi-Fi 2,4 GHz.
4. Folosește regiunea corectă a contului.
5. Confirmă că hubul este online și funcțional stock.
6. Creează rezervarea DHCP și verifică IP-ul după un restart normal.

Apăsarea dublă pentru ecosistem nu este secvența de activare Telnet.

---

## 7. Etapa 2 — Obținerea și verificarea tokenului MiIO

Metoda folosită în proiect:

1. Instalează **Xiaomi Gateway 3** de la AlexxIT prin HACS.
2. Autentifică integrarea cu același cont și aceeași regiune Xiaomi.
3. Găsește `lumi.gateway.aeu01` și copiază tokenul MiIO.
4. Păstrează tokenul ca parolă; nu îl introduce în README, scripturi sau arhive.

Un token valid are 32 de caractere hexazecimale.

```powershell
python -m miio.cli device --ip HUB_IP --token MIIO_TOKEN info
```

Comanda trebuie să răspundă cu informațiile dispozitivului. Nu continua cu un token neverificat.

---

## 8. Etapa 3 — Telnet temporar

Secvența fizică documentată pentru firmware stock compatibil:

```text
5-2-2-2-2-2-2
```

Dacă hubul încă nu acceptă Telnet, nu există prompt `#` și nu se pot rula comenzi pe hub. În punctul acesta se folosește fie secvența fizică de mai sus, fie scriptul MiIO din PowerShell, în funcție de metoda disponibilă pentru hubul respectiv.

Conectare:

```powershell
telnet HUB_IP
```

În configurația documentată s-a folosit `admin` cu parolă goală; alternativ `root` cu parolă goală.

Metoda MiIO folosită istoric pentru activarea temporară Telnet este:

```powershell
python -m miio.cli device --ip HUB_IP --token MIIO_TOKEN raw_command set_ip_info '{"ssid":"\"\"","pswd":"123123 ; passwd -d admin ; passwd -d root ; telnetd"}'
```

Această comandă modifică temporar accesul administrativ. Ruleaz-o numai în LAN și nu o salva împreună cu tokenul real.

Important: metoda MiIO este comandă PowerShell/PC către hub, nu comandă Telnet. Comenzile marcate cu `#` în acest README încep abia după ce conectarea Telnet afișează shell-ul hubului.

### Verificare inițială pe hub

```sh
uname -a
busybox | head -n 1
getprop ro.product.model
ifconfig wlan0
ps w | grep '[m]zigbee_agent'
ps w | grep '[a]pp_monitor'
ps w | grep '[m]ha_master'
ls -l /dev/ttyS1
```

Rezultatul trebuie să corespundă modelului și arhitecturii documentate.

---

## 9. Transfer de fișiere între Windows și hub

Metoda simplă folosește un listener BusyBox `nc` pentru o singură conexiune. Portul exemplu este `12345` și trebuie să rămână numai în LAN.

### Hub — primește un fișier

```sh
rm -f /tmp/post_init.sh
nc -l -p 12345 > /tmp/post_init.sh
```

Comanda rămâne blocată până când Windows trimite fișierul.

### Windows — trimite fișierul

Din rădăcina kitului:

```powershell
.\scripts\windows\Send-FileToM1S.ps1 `
  -HubIp HUB_IP `
  -Path .\scripts\hub\post_init.sh `
  -Port 12345
```

### Hub — validează ce a primit

```sh
ls -l /tmp/post_init.sh
/bin/sh -n /tmp/post_init.sh
echo "syntax=$?"
busybox sha256sum /tmp/post_init.sh 2>/dev/null || true
```

Așteaptă `syntax=0`. Repetă aceeași metodă pentru celelalte scripturi sau pachete, schimbând numele destinației.

## 9A. Etapa 3A — Verificarea alegerii stock STA/AP

Această verificare este **separată** de modulul opțional de recuperare Wi-Fi. Firmware-ul Aqara decide la boot dacă pornește în STA sau AP din următoarele trei proprietăți:

```text
persist.app.cloud_provisioned
persist.app.hap_provisioned
persist.app.hap_keepalive
```

Dacă toate trei sunt `false` sau goale, `fw_manager.sh -r` poate porni intenționat `wifi_start.sh AP`, chiar dacă SSID-ul și parola sunt încă salvate. `persist.app.user_paired=true` și existența backupului local Wi-Fi nu schimbă această decizie.

Transferă scriptul fără secrete:

Pe hub:

```sh
rm -f /tmp/aqara_wifi_boot_state.sh
nc -l -p 12345 > /tmp/aqara_wifi_boot_state.sh
```

În Windows:

```powershell
.\scripts\windows\Send-FileToM1S.ps1 `
  -HubIp HUB_IP `
  -Path .\scripts\hub\aqara_wifi_boot_state.sh `
  -Port 12345
```

Pe hub:

```sh
chmod 700 /tmp/aqara_wifi_boot_state.sh
/bin/sh -n /tmp/aqara_wifi_boot_state.sh
/tmp/aqara_wifi_boot_state.sh check
echo "rc=$?"
```

Rezultate:

- `BOOT_WIFI_SELECTION=STA_EXPECTED` — cel puțin una dintre cele trei stări este `true`;
- `BOOT_WIFI_SELECTION=AP_RISK` și `rc=1` — toate trei sunt inactive; corectează înainte de primul reboot.

Corecție validată:

```sh
/tmp/aqara_wifi_boot_state.sh fix
/tmp/aqara_wifi_boot_state.sh check
```

Rezultatul final trebuie să conțină:

```text
cloud_provisioned=true
hap_provisioned=true
hap_keepalive=true
user_paired=true
BOOT_WIFI_SELECTION=STA_EXPECTED
```

Scriptul nu citește și nu afișează SSID-ul, parola Wi-Fi sau tokenul MiIO. Echivalentul manual este `setprop ... true` pentru cele patru proprietăți urmat de `sync`.

> **Critic:** `fw_manager.sh -r` înseamnă pornire normală a serviciilor. `fw_manager.sh -f -r` declanșează calea de factory reset și nu trebuie pus în `post_init.sh`.

---

# PARTEA II — Boot persistent și backupul original

## 10. Etapa 4 — Instalarea bundle-ului hub și a `post_init.sh`

Înainte de instalare, etapa 9A trebuie să arate `STA_EXPECTED`. `post_init.sh` doar înregistrează un avertisment dacă stările devin din nou inactive; nu le modifică automat la fiecare boot.

În fluxul curent nu se copiază manual doar `post_init.sh`. Se transferă și se instalează bundle-ul:

```text
hub_bundle/m1s_hub_bundle_LOCAL.tgz
```

Pe hub, pregătește listenerul:

```sh
rm -f /tmp/m1s_hub_bundle_LOCAL.tgz
nc -l -p 12345 > /tmp/m1s_hub_bundle_LOCAL.tgz
```

În PowerShell, din rădăcina kitului:

```powershell
.\scripts\windows\Send-FileToM1S.ps1 -HubIp HUB_IP -Path .\hub_bundle\m1s_hub_bundle_LOCAL.tgz -Port 12345
```

Pe hub:

```sh
rm -rf /tmp/m1s_bundle
mkdir -p /tmp/m1s_bundle
cd /tmp/m1s_bundle
tar -xzf /tmp/m1s_hub_bundle_LOCAL.tgz
chmod 700 install.sh
./install.sh
```

Rezultat așteptat:

```text
M1S_BUNDLE_V0_8_INSTALLED
Factory Reset Guard este inclus si configurabil in /data/scripts/factory_reset_guard_boot.conf.
Verifica setarile, apoi reboot controlat.
```

Installerul validează sintaxa scripturilor, pune proprietățile Aqara în starea STA, creează backupuri locale cu timestamp pentru fișierele înlocuite și copiază scripturile în `/data/scripts` și `/data/m1s_button`.

`post_init.sh` curent face următoarele la fiecare boot Linux:

1. pornește `syslogd`, necesar pentru unele diagnostice vechi;
2. dacă Factory Reset Guard este activ, izolează `/dev/input` înainte de `fw_manager.sh -r`;
3. pornește serviciile stock prin `fw_manager.sh -r` — pornire normală, fără opțiunea `-f`;
4. pornește `service_trim.sh`, dacă este instalat;
5. așteaptă Wi-Fi;
6. solicită Telnet persistent prin `fw_manager.sh -t -k`;
7. pornește opțional managerul Wi-Fi și portalul, dacă au fost instalate;
8. ține oprit stackul Zigbee stock care ar ocupa JN5189;
9. repornește `mha_master -b` pentru compatibilitate cu diagnosticele `basis.button`;
10. oprește orice `cat /dev/ttyS1` rămas;
11. configurează UART-ul la 115200;
12. pornește JN5189 normal, GPIO33=`1`, reset GPIO18 `1 -> 0`;
13. pornește bridge-ul legacy pe loguri numai dacă există și este configurat;
14. stinge inelul după 10 secunde.

În configurația v0.8 validată, Factory Reset Guard pornește separat watcherul GPIO7 și publică butonul prin MQTT. Bridge-ul legacy `button_watch.sh` poate rămâne prezent pentru compatibilitate, dar nu este sursa principală când guardul este activ.

După instalare, verifică:

```sh
ls -l /data/scripts/post_init.sh
/bin/sh -n /data/scripts/post_init.sh
grep -n 'factory_reset_guard\|service_trim\|gpio_button_watch\|fw_manager\|mzigbee_agent\|gpio33' /data/scripts/post_init.sh
```

Nu da reboot dacă verificarea de sintaxă nu se termină cu `0`.

<!-- Istoric: varianta veche copia individual `post_init.sh` și `install_post_init.sh`. Pentru kitul v0.8, fluxul principal este bundle-ul de mai sus. -->

<!--
1. pornește serviciile stock prin `fw_manager.sh -r` — pornire normală, fără opțiunea `-f`;
2. așteaptă Wi-Fi;
3. solicită Telnet persistent prin `fw_manager.sh -t -k`;
4. pornește opțional managerul Wi-Fi și portalul, dacă au fost instalate;
5. suspendă `app_monitor`, pentru a nu reporni agentul Zigbee stock;
6. oprește `mzigbee_agent` și orice `cat /dev/ttyS1` rămas;
7. configurează UART-ul la 115200;
8. pornește JN5189 normal, GPIO33=`1`, reset GPIO18 `1 -> 0`;
9. pornește opțional bridge-ul butonului, dacă este configurat;
10. stinge inelul după 10 secunde.

După transferul fișierelor `post_init.sh` și `install_post_init.sh` în `/tmp`:

```sh
chmod 700 /tmp/install_post_init.sh
/bin/sh -n /tmp/install_post_init.sh
/tmp/install_post_init.sh /tmp/post_init.sh
```

Verifică:

```sh
ls -l /data/scripts/post_init.sh
/bin/sh -n /data/scripts/post_init.sh
grep -n 'fw_manager\|mzigbee_agent\|gpio33\|button_watch' /data/scripts/post_init.sh
```
-->

Nu reporni încă hubul. Mai întâi efectuează backupul JN5189.

> În huburile proiectului, `/data/scripts/post_init.sh` este hookul persistent folosit la boot. După primul reboot verifică obligatoriu `/tmp/post_init.log`; existența fișierului în `/data` nu este suficientă pentru a demonstra că a fost executat.

---

## 11. Etapa 5 — Eliberarea UART-ului înainte de ISP

Dacă hubul a fost deja adăugat în integrarea Home Assistant, dezactivează temporar intrarea sau oprește Home Assistant. Integrarea poate recrea automat tunelul UART și un proces `cat /dev/ttyS1`.

În kitul v0.8, instalarea bundle-ului pune deja scripturile JN5189 în `/data/scripts`. Verificarea minimă înainte de ISP este:

```sh
ps w | grep '[c]at /dev/ttyS1'
ps w | grep '[m]zigbee_agent'
ps w | grep '[a]pp_monitor'
netstat -lnt | grep 1888
```

Starea corectă înainte de ISP:

- niciun `cat /dev/ttyS1` real;
- `mzigbee_agent` poate fi oprit;
- `app_monitor` poate fi suspendat în starea `T`;
- portul 1888 liber;
- numai sesiunea Telnet folosită pentru intervenție.

Pentru identificarea părintelui unui proces care reapare:

```sh
for p in $(ps w | grep '[c]at /dev/ttyS1' | awk '{print $1}'); do
  echo "CAT=$p"
  grep PPid /proc/$p/status
 done
```

Nu folosi opriri generale pentru procesele `nc`; hubul poate avea tuneluri audio sau UART legitime.

---

## 12. Etapa 6 — Intrarea JN5189 în ISP

Rulează o singură dată scriptul instalat de bundle:

```sh
/bin/sh -n /data/scripts/jn5189_enter_isp_1888.sh
/data/scripts/jn5189_enter_isp_1888.sh
```

Rezultatul așteptat:

```text
ISP_LISTENER_OK port=1888 ...
GPIO33=0 GPIO18=0
```

Verificare suplimentară:

```sh
netstat -lnt | grep 1888
ps w | grep '[n]c -l -p 1888'
```

Scriptul folosește o buclă care recreează listenerul după fiecare conexiune SPSDK. Așteaptă aproximativ două secunde între comenzile SPSDK. Nu testa portul `1888` cu un client care consumă conexiunea exact înainte de `dk6prog`; dacă ai consumat listenerul, rearmarea se face cu:

```sh
/data/scripts/jn5189_close_isp_1888.sh
/data/scripts/jn5189_enter_isp_1888.sh
```

### Verificare din Windows

```powershell
python -m spsdk.apps.dk6prog `
  -b PYSERIAL `
  -d "socket://HUB_IP:1888" `
  -n info
```

Trebuie să apară:

```text
Detected DEVICE: JN5189
FLASH  Memory ID 0  Base 0x0  Length 0x9DE00  Sector 0x200
```

Oprește-te dacă dispozitivul sau geometria memoriei diferă.

---

## 13. Etapa 7 — Două backupuri stock identice

Din PowerShell, rulează scriptul pereche. El face secvența `read A -> read B -> SHA256 compare` într-o singură comandă:

```powershell
.\scripts\windows\JN5189-Backup-PAIR-VERIFY.ps1 -HubIp HUB_IP
```

Dacă `C:\Windows\py.exe` nu există pe calculator, indică explicit Pythonul instalat:

```powershell
.\scripts\windows\JN5189-Backup-PAIR-VERIFY.ps1 -HubIp HUB_IP -Python "C:\Users\Dell\AppData\Local\Programs\Python\Python311\python.exe"
```

Fiecare fișier trebuie să aibă:

```text
646656 bytes
```

La final trebuie să apară:

```text
BACKUP_PAIR_OK SHA256=...
```

Condiția de continuare este:

- ambele au 646656 bytes;
- SHA256 este identic;
- fișierele sunt copiate în minimum două locații fizice diferite;
- numele conține IP-ul/identitatea hubului; backupurile huburilor nu se amestecă.

Backupul poate conține date specifice dispozitivului. Nu îl publica.

---

# PARTEA III — Scrierea firmware-ului Router

## 14. Etapa 8 — Alegerea între update și prima conversie

### Hub deja Router, actualizare de firmware

Pentru un Router existent pe care vrei doar să îl actualizezi fără pierderea contextului Zigbee, nu folosi scriptul rapid `JN5189-Flash-WRITE.ps1`, deoarece acesta șterge zona aplicației înainte de write. Folosește comenzile SPSDK directe din secțiunea de depanare, fără `erase`, numai dacă știi sigur ce imagine înlocuiești.

### Hub stock, prima conversie

Pentru un hub stock sau pentru un hub pe care îl rescrii controlat cu imaginea Router validată, folosește scriptul rapid. El șterge numai zona aplicației `0x0–0x33200`, apoi scrie imaginea. Nu șterge întregul cip.

### Verificare simulată PowerShell

```powershell
.\scripts\windows\JN5189-Flash-WRITE.ps1 `
  -HubIp HUB_IP `
  -FirmwarePath .\firmware\jn5189_router_rgb_lux_rejoin_test.bin
```

O simulare completă nu există în scriptul rapid; verificarea de siguranță este hashul local al firmware-ului și faptul că `dk6prog info` a detectat `JN5189` înainte de flash.

---

## 15. Etapa 9 — Flash și validare

### Prima conversie stock

```powershell
.\scripts\windows\JN5189-Flash-WRITE.ps1 `
  -HubIp HUB_IP `
  -FirmwarePath .\firmware\jn5189_router_rgb_lux_rejoin_test.bin
```

Dacă `C:\Windows\py.exe` nu există pe calculator, indică explicit Pythonul instalat:

```powershell
.\scripts\windows\JN5189-Flash-WRITE.ps1 `
  -HubIp HUB_IP `
  -FirmwarePath .\firmware\jn5189_router_rgb_lux_rejoin_test.bin `
  -Python "C:\Users\Dell\AppData\Local\Programs\Python\Python311\python.exe"
```

Scriptul:

1. verifică dimensiunea și SHA256 ale firmware-ului;
2. șterge numai `0x33200` bytes din Memory ID 0;
3. scrie 209296 bytes la adresa `0x0`;
4. se oprește cu eroare dacă `erase` sau `write` eșuează.

Confirmarea finală trebuie să fie:

```text
FLASH_WRITE_OK bytes=209296 SHA256=A1A1F302BE9E3AB95FD6A3B8F4AC260E1F397FEC275FB3E3CAF8418CD75E7A2F
```

În fluxul rapid v0.8 nu se face readback imediat după `write`, deoarece SPSDK 3.10 poate pierde handshake-ul deși firmware-ul a fost scris și Routerul bootează corect. Nu repeta automat `erase/write` doar pentru un timeout de readback. Dacă vrei verificare suplimentară, rearmează ISP după boot/recovery și fă readback separat pe exact 209296 bytes.

### Comenzi SPSDK echivalente, pentru depanare

```powershell
# Info
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n info

# Erase numai la prima conversie/recuperare
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n erase 0x0 0x33200 0

# Write
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n write 0x0 ".\jn5189_router_rgb_lux_rejoin_test.bin" 0

# Readback exact
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n read -o ".\readback.bin" 0x0 209296 0
```

În SPSDK 3.10.0, `erase` folosește argumente poziționale; forma `--memory-id` nu este acceptată.

---

## 16. Etapa 10 — Închiderea ISP și bootul Routerului

După `FLASH_WRITE_OK`, închide listenerul ISP și pornește JN5189 în modul normal:

```sh
/data/scripts/jn5189_close_isp_1888.sh
netstat -lnt | grep 1888
```

Ultima comandă nu trebuie să afișeze nimic.

În Zigbee2MQTT activează **Permit join (All)**, apoi:

```sh
/data/scripts/jn5189_boot_router.sh
```

Rezultatul așteptat:

```text
ROUTER_BOOT_SENT GPIO33=1 GPIO18=0
```

Așteaptă 30–60 de secunde. În Zigbee2MQTT trebuie să apară dispozitivul Lumi/NXP `BDB-Router` cu rol Router.

### Dacă nu apare

1. confirmă Permit join;
2. confirmă GPIO33=`1`, GPIO18=`0`;
3. confirmă că `mzigbee_agent` și `cat /dev/ttyS1` nu rulează;
4. repornește o singură dată Zigbee2MQTT;
5. pulsează din nou resetul prin `/data/scripts/jn5189_boot_router.sh`;
6. nu repeta erase/write fără un motiv demonstrat.

---

## 17. Etapa 11 — Primul reboot complet

După ce Routerul este online în Zigbee2MQTT și hubul a fost adăugat în integrarea Home Assistant, fă rebootul final:

```sh
sync
reboot
```

Așteaptă minimum 120 de secunde, reconectează Telnet și verifică starea:

```sh
cat /tmp/post_init.log
cat /tmp/factory_reset_guard_boot.status
cat /tmp/gpio_button_watch.status
cat /tmp/service_trim.status
mount | grep /dev/input
ps w | grep '[t]elnetd'
ps w | grep '[m]zigbee_agent'
ps w | grep '[a]pp_monitor'
ps w | grep '[g]pio_button_watch.sh'
cat /sys/class/gpio/gpio33/value
cat /sys/class/gpio/gpio18/value
```

Criterii de acceptare:

- `/tmp/post_init.log` există și conține pornirea JN5189;
- Telnet rulează;
- `mzigbee_agent` este absent sau numai zombie și nu ocupă `/dev/ttyS1`;
- GPIO33=`1`, GPIO18=`0`;
- Routerul reapare în Zigbee2MQTT după reboot;
- inelul roșu de boot se stinge după întârzierea finală;
- Wi-Fi păstrează IP-ul rezervat;
- cu guard activ, `/tmp/factory_reset_guard_boot.status` arată `phase=fw_manager_after_isolation`, `enabled=1`, `one_shot=0`, `mode=input_dir_overlay`;
- `mount | grep /dev/input` arată overlay-ul temporar peste `/dev/input`;
- `/tmp/gpio_button_watch.status` arată watcher activ, GPIO7 și `run_seconds=0`;
- `/tmp/service_trim.status` ajunge după fereastra de așteptare la `homekitserver=stopped` și `mijia_automation=stopped`.

Integrarea Home Assistant se adaugă înainte de acest reboot final, ca playerul și topicul butonului să poată fi validate imediat după revenire.

---

# PARTEA IV — Protocoalele locale

## 18. RGB, lux și rejoin

### RGB

```text
A5 RED GREEN BLUE CHECKSUM
CHECKSUM = A5 XOR RED XOR GREEN XOR BLUE
```

Test OFF:

```sh
printf '\245\000\000\000\245' > /dev/ttyS1
```

### Lux

```text
Cerere:  A6 00 00 00 A6
Răspuns: A6 RAW_H RAW_L MV_H MV_L LUX_H LUX_L CHECKSUM
```

Checksumul răspunsului este XOR-ul primilor șapte bytes. Firmware-ul curent folosește PIO19/ADC5.

### Rejoin A7

```text
Cerere:     A7 52 4A 4E F1
Confirmare: A7 4F 4B 00 A3
```

Înainte de rejoin, activează **Permit join** pe coordonatorul destinație. În Home Assistant deschide:

**Setări → Dispozitive și servicii → Aqara M1S Zigbee Router → Configurează → Conectare la alt coordonator Zigbee**

Citește avertismentul și confirmă. Acțiunea șterge numai contextul persistent al rețelei Zigbee din JN5189 și pornește Network Steering. Nu șterge Linux, Wi-Fi, RGB/lux sau sunetele. Coordonatorul vechi poate păstra o intrare rămasă; elimin-o numai după ce Routerul apare online pe coordonatorul nou.

Nu lăsa un `cat /dev/ttyS1` manual după teste; integrarea își administrează singură tunelul UART.

---

# PARTEA V — Home Assistant

## 19. Etapa 12 — Instalarea integrării v0.20.0

### HACS

1. HACS → Integrations → Custom repositories.
2. Adaugă repository-ul:
   `https://github.com/caiuspoputa-debug/ha-aqara-m1s-zigbee-router`
3. Categoria: **Integration**.
4. Pentru această procedură reproductibilă instalează pachetul/release-ul care conține manifest `0.20.0`. Dacă folosești „latest”, verifică imediat după instalare că fișierul `custom_components/aqara_m1s_zigbee_router/manifest.json` arată `0.20.0`.
5. HACS instalează direct repository-ul; nu este necesar un ZIP separat atașat release-ului.
6. Repornește complet Home Assistant.

### Manual

Copiază directorul:

```text
custom_components/aqara_m1s_zigbee_router
```

în:

```text
/config/custom_components/aqara_m1s_zigbee_router
```

Repornește Home Assistant.

### Adăugarea hubului

Setări → Dispozitive și servicii → Adaugă integrare → **Aqara M1S Zigbee Router**.

Completează:

- Host: IP-ul rezervat al hubului;
- Port: `23`;
- Username: de regulă `admin`;
- Password: parola Telnet folosită, goală în configurația documentată;
- Name: numele unic al hubului.

> Config flow-ul salvează datele de conectare la hub. Verifică Telnet manual înainte de prima adăugare. Parola Wi-Fi introdusă ulterior în Configure nu este salvată în config entry sau options.

---

## 20. Entitățile curente

Pentru fiecare hub:

- **Ring Light** — RGB și luminozitate;
- **Media Player** — redare individuală, volum/mute live, pas 0,1%;
- **Fine Volume Trim** — corecție fină individuală, separată de sliderul nativ;
- **Include in M1S Media Group** — includerea hubului în grup;
- **Physical Button** — eveniment MQTT;
- **Sound Playback Volume** — volum pentru WAV-urile locale;
- **Refresh Sound List**;
- câte un buton pentru fiecare WAV detectat;
- **Illuminance** — lux, ADC raw și millivolts;
- **Hub Temperature** — `persist.sys.temperature`;
- **WiFi IP**;
- stări pentru HomeKit Process, MQTT Process, Telnet Process și JN5189 Router.

Global, o singură entitate:

- **M1S Media Group** — cronologie PCM comună pentru huburile selectate.

Evenimentele recunoscute pentru buton sunt:

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

Sliderul nativ al playerului are pas de 0,1%. Entitatea **Fine Volume Trim** există separat pentru corecție fină pe hub.

Cu `service_trim` activ, senzorul **HomeKit Process** trebuie să ajungă la `stopped` după stabilizarea de boot. Asta este comportament intenționat în varianta curentă, nu eroare.

### Disponibilitate și revenire online

Coordonatorul verifică hubul la fiecare 15 secunde. Când hubul este offline, lumina, playerul, volumul și senzorii live devin indisponibili. Butoanele WAV rămân intenționat vizibile. La prima revenire online, integrarea așteaptă 10 secunde pentru stabilizarea Wi-Fi/Telnet/UART și trimite o singură comandă RGB OFF; ultima culoare și luminozitate selectate rămân memorate pentru următoarea aprindere manuală.

---

## 21. Audio și media

### Player individual

- port hub: `12346`;
- FFmpeg în Home Assistant → PCM `S32_LE`, mono, 32000 Hz;
- perioada/chunk-ul de transport este **35 ms**, aliniat cu `period_size=1120` raportat de ALSA la 32 kHz;
- jitter buffer HA: **4,0 s**; prebuffer inițial: **2,5 s**; rebuffer resume: **2,0 s**; remote prefill: **1,4 s**;
- gain și mute live, rampă anti-click de 40 ms;
- redarea individuală are prioritate față de grup;
- suportă `PLAY_MEDIA` și `BROWSE_MEDIA`, inclusiv surse Home Assistant `media-source://` și URL-uri HTTP/HTTPS;
- la un **STOP explicit**, receiverul/aplay de pe hub este oprit înainte ca Home Assistant să detașeze FFmpeg/TCP, astfel încât ALSA să nu mai golească audio vechi după Stop;
- la o **schimbare explicită de sursă**, v0.20.0 aplică aceeași regulă: `REMOTE STOP → teardown FFmpeg/TCP vechi → receiver nou → flux nou`;
- dacă fluxul are un defect TCP real, playerul poate reconstrui receiverul și aruncă o fereastră mică de PCM stale, fără a transforma o simplă schimbare de melodie YT/YTM într-un source-switch;
- FFmpeg solicită best-effort `nice -5`, iar `aplay` pe hub `nice -3`; sunt priorități Linux normale, nu realtime.

Integrarea separată **Radio Favorites** și add-on-ul **M1S YouTube Cast Receiver** pot folosi același player ca țintă. Pentru integrare, ambele sunt surse audio; logica YouTube/YTM rămâne în add-on.

### Grup media

- port hub: `12347`;
- o singură cronologie FFmpeg și un singur clock PCM comun pentru membrii grupului;
- perioadă/chunk PCM: **35 ms**;
- jitter buffer HA: **4,0 s**;
- prebuffer inițial sursă: **2,5 s**;
- rebuffer resume după underrun real: **2,0 s**;
- remote prefill comun înainte de playout: **1,4 s**;
- la pornire se așteaptă primul receiver maximum **3,0 s**; după primul receiver gata există o fereastră de cohortă de **0,30 s** pentru ceilalți; nu există o pauză fixă specială pentru YT/YTM sau Radio;
- la schimbarea reală de sursă se execută **GROUP STOP înainte de teardown-ul FFmpeg/TCP vechi**, apoi se pregătește noul transport;
- un membru lent/defect este izolat fără restartarea membrilor sănătoși;
- un hub revenit online intră prin **history prefill + live catch-up** după o stabilizare scurtă, fără restart global al sursei;
- resincronizarea periodică este dezactivată; driftul este corectat continuu prin micro-resampling adaptiv per hub, cu limită **±0,8%**;
- adaptive sync nu accelerează întregul material audio și nu este o compensare YT/YTM; corectează numai mici diferențe de clock între huburile grupului;
- schimbarea melodiei în add-on-ul YT/YTM 1.0.1 nu este schimbare de sursă pentru integrare: același flux continuă și nu se repetă prebuffer-ul de start.

### Sunete WAV locale

- sursă hub: port `12347`;
- destinație PCM hub: port `12348`;
- upload: port `12349`;
- director administrat: `/data/musics/music-ch`;
- format: WAV PCM mono, 32000 Hz, signed 32-bit little-endian;
- limită upload: 20 MiB.

Conversie:

```sh
ffmpeg -y -i input.mp3 -ac 1 -ar 32000 -c:a pcm_s32le output.wav
```

### Administrarea sunetelor din Home Assistant

Deschide:

**Setări → Dispozitive și servicii → Aqara M1S Zigbee Router → Configurează**

Meniul curent oferă:

- **Schimbă rețeaua Wi-Fi / Change Wi-Fi network**;
- **Încărcare WAV / ZIP / Upload WAV / ZIP**;
- **Ștergere multiplă WAV / Delete multiple WAV files**, numai când există fișiere administrate;
- **Conectare la alt coordonator Zigbee / Join a different Zigbee coordinator**;
- **Finalizare și închidere / Finish and close**.

Încărcare:

1. alege un fișier WAV sau un ZIP care conține mai multe WAV-uri;
2. pentru WAV rămâne limita de 20 MiB per fișier; un ZIP poate conține maximum 64 WAV-uri și maximum 100 MiB total;
3. transferul principal folosește portul `12349`, verifică dimensiunea și MD5 înainte de înlocuirea destinației;
4. dacă transferul TCP eșuează, există fallback BusyBox `base64`, tot cu verificare;
5. fișierul ajunge numai în `/data/musics/music-ch`;
6. lista butoanelor de sunet se actualizează imediat;
7. după toate operațiile apasă **Finalizare și închidere** pentru reloadul complet și controlat al config entry-ului.

Ștergere:

1. selectează unul sau mai multe fișiere oferite de meniu;
2. confirmă o singură dată; toate fișierele selectate sunt șterse în aceeași operație;
3. apasă **Finalizare și închidere**.

Sunetele originale din directoare precum `/data/musics/music-scene` nu sunt oferite pentru ștergere. Butonul **X** al ferestrei aparține frontendului Home Assistant: închiderea cu X nu anulează uploadul/ștergerea și lista se reîmprospătează imediat, dar sare reloadul final al config entry-ului.

### Schimbarea Wi-Fi direct din integrare

Această opțiune apare numai ca interfață de comandă; mecanismul sigur rulează pe hub și necesită instalarea prealabilă a modulului Wi-Fi recovery, când acesta este inclus în kitul folosit.

1. În router, rezervă **același IP** pentru MAC-ul Wi-Fi al hubului pe noua rețea, dacă este posibil. Integrarea este configurată după IP.
2. Deschide **Setări → Dispozitive și servicii → Aqara M1S Zigbee Router → Configurează → Schimbă rețeaua Wi-Fi**.
3. Introdu noul SSID și parola; parola este afișată mascat și **nu este salvată** în datele sau opțiunile Home Assistant.
4. Bifează confirmarea și pornește schimbarea.
5. Integrarea scrie temporar candidatul numai pe hub, cu permisiuni `0600`, apoi pornește `wifi_apply_candidate.sh`.
6. Helperul șterge mai întâi un IPv4 vechi rămas pe interfață, pornește asocierea la noul SSID și consideră testul reușit numai după apariția unui **IPv4 proaspăt**.
7. Numai după succes, SSID-ul și parola devin copia `safe/` folosită la recovery. Dacă testul eșuează, rulează mecanismul de recuperare/AP existent.

Este normal ca Home Assistant să marcheze temporar hubul offline în timpul schimbării. Dacă noua rețea acordă alt IP, integrarea nu îl poate ghici automat; actualizează rezervarea DHCP astfel încât hubul să păstreze IP-ul configurat sau reconfigurează integrarea ulterior.

> Nu folosi opțiunea dacă modulul Wi-Fi recovery nu este instalat și verificat. Integrarea va refuza pornirea dacă `/data/m1s_wifi/wifi_apply_candidate.sh` lipsește.

### Descărcarea unui WAV existent de pe hub

Interfața Configure încarcă și șterge, dar nu oferă download. Folosește un listener temporar LAN-only pe `1889`.

Pe hub:

```sh
find /data/musics -type f -name '*.wav'
nc -l -p 1889 < /data/musics/music-scene/disarm.wav
```

În Windows:

```powershell
.\scripts\windows\Receive-FileFromM1S.ps1 `
  -HubIp HUB_IP `
  -OutputPath "$env:USERPROFILE\Downloads\disarm.wav" `
  -Port 1889
```

Scriptul Windows afișează calea, dimensiunea și SHA256. Listenerul `nc` este one-shot și se închide după transfer. Nu publica portul `1889` în Internet.

### Limitare cunoscută importantă rămasă

Grupul media și sursa sunetelor WAV folosesc ambele portul `12347`. Nu porni un WAV local pe un hub în timp ce receptorul de grup al acelui hub deține portul. Aceasta trebuie corectată într-o versiune ulterioară prin separarea porturilor sau prin arbitraj explicit; README-ul curent nu pretinde că acest conflict este rezolvat.

---

## 22. Servicii Home Assistant

Domeniu: `aqara_m1s_zigbee_router`

```text
play_url
play_sound
run_command
upload_sound
delete_sound
refresh_sounds
```

`run_command` execută o comandă shell prin Telnet pe hub și trebuie tratat ca acces administrativ complet. Nu îl expune utilizatorilor neautorizați și nu construi automatizări din input nevalidat.

---

# PARTEA VI — Butonul fizic prin MQTT

## 23. Etapa 13 — Factory Reset Guard și buton GPIO7

În varianta curentă, scopul principal nu este doar publicarea butonului în MQTT. Scopul este izolarea butonului fizic de calea stock care putea interpreta secvențe de apăsări ca reset.

### Calea stock, înainte de guard

```text
buton fizic → /dev/input/event0 → mha_basis / mha_master → basis.button → logica stock de click/reset
```

Bridge-ul vechi citea `basis.button` din `/var/log/messages` și publica evenimentul în MQTT. Acea metodă exporta evenimentul spre Home Assistant, dar nu decupla butonul de resetul stock.

### Calea curentă validată

```text
post_init.sh
→ factory_reset_guard_boot.sh
→ overlay temporar peste /dev/input
→ /dev/input/event0 devine dummy char 1,3 pentru firmware-ul Aqara
→ mha_basis pornește fără acces la butonul fizic real
→ gpio_button_watch.sh citește GPIO7
→ m1s_mqtt_publish.sh publică în MQTT
→ Home Assistant primește Physical Button
```

Cu guardul activ, `basis.button click` nu trebuie să mai apară în log după o apăsare reală. Mesajul de buton trebuie să ajungă prin calea nouă GPIO7/MQTT.

### Configurația guardului

Fișier:

```text
/data/scripts/factory_reset_guard_boot.conf
```

Valori curente validate:

```sh
ENABLE_FACTORY_RESET_BOOT_GUARD=1
MODE=input_dir_overlay
EVENT_NODE=/dev/input/event0
REAL_EVENT_NODE=/dev/input/event0.aqara_real
DUMMY_MAJOR=1
DUMMY_MINOR=3
GPIO_WATCH_SECONDS=0
GPIO_WATCH_PUBLISHER=/data/m1s_button/m1s_mqtt_publish.sh
WAIT_EVENT_SECONDS=20
INPUT_OVERLAY_DIR=/tmp/factory_guard_input
KEEP_EVENT1=1
EVENT1_MAJOR=13
EVENT1_MINOR=65
ONE_SHOT=0
```

`ONE_SHOT=0` înseamnă persistent. Guardul se aplică la fiecare boot. Rollback-ul se face prin setarea `ENABLE_FACTORY_RESET_BOOT_GUARD=0` și reboot.

### Configurația watcherului GPIO

Fișier:

```text
/data/scripts/gpio_button_watch.conf
```

Valori de bază:

```sh
ENABLE_GPIO_BUTTON_WATCH=0
DRY_RUN=1
GPIO_BUTTON=7
ACTIVE_VALUE=1
POLL_INTERVAL_TENTHS=1
DOUBLE_WINDOW_TENTHS=8
HOLD_TENTHS=12
HOLD_REPEAT_TENTHS=5
RUN_SECONDS=30
PUBLISHER=/data/m1s_button/m1s_mqtt_publish.sh
```

În mod normal, fișierul rămâne conservator (`ENABLE=0`, `DRY_RUN=1`). Factory Reset Guard pornește watcherul cu enable real, dry-run oprit și `RUN_SECONDS=0`, astfel încât butonul să fie publicat permanent după boot.

### Payloaduri MQTT acceptate de integrare

Topic:

```text
m1s/<ultimul_octet_IP>/button/action
```

Payloaduri:

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

Pentru automatizări Home Assistant, folosește direct aceste payloaduri. Pentru apăsare lungă, preferă `hold_start` și `hold_release`; `hold_repeat` este util pentru acțiuni continue, de exemplu volum sau dimmer.

### Verificare fără apăsarea butonului

```sh
/data/m1s_button/m1s_mqtt_publish.sh click
echo "rc=$?"
```

Așteaptă `rc=0`. Verifică în Home Assistant Developer Tools → MQTT sau Events că payloadul ajunge pe topicul exact.

### Verificare după reboot

```sh
cat /tmp/factory_reset_guard_boot.status
cat /tmp/gpio_button_watch.status
cat /tmp/service_trim.status
mount | grep /dev/input
ps w | grep '[g]pio_button_watch.sh'
tail -n 80 /tmp/gpio_button_watch.log
grep -n 'basis.button' /var/log/messages | tail -n 20
```

Rezultatul bun:

- `/tmp/factory_reset_guard_boot.status` arată guard activ, `mode=input_dir_overlay`, `one_shot=0`;
- `/tmp/gpio_button_watch.status` arată GPIO7, watcher activ și `run_seconds=0`;
- `mount | grep /dev/input` arată overlay-ul peste `/dev/input`;
- o apăsare simplă publică `click` în MQTT și ajunge în Home Assistant;
- după apăsare, nu apare un click nou `basis.button` în logul stock.

### Teste fizice recomandate

1. Testează întâi o singură apăsare scurtă.
2. Verifică MQTT și Home Assistant.
3. Testează dublu click.
4. Verifică dacă integrarea vede payloadul final corect.
5. Testează apăsare lungă numai după ce `hold_start`/`hold_release` sunt confirmate în MQTT.
6. Testul de 10 clickuri se face numai cu guard activ și confirmat după reboot.

Nu testa secvențe lungi de clickuri pe un hub stock sau pe un hub unde guardul nu este confirmat.

### Rollback guard

Pe hub:

```sh
cp /data/scripts/factory_reset_guard_boot.conf /data/scripts/factory_reset_guard_boot.conf.before_disable
sed -i 's/^ENABLE_FACTORY_RESET_BOOT_GUARD=.*/ENABLE_FACTORY_RESET_BOOT_GUARD=0/' /data/scripts/factory_reset_guard_boot.conf
sync
reboot
```

După reboot:

```sh
cat /tmp/factory_reset_guard_boot.status
mount | grep /dev/input
ps w | grep '[g]pio_button_watch.sh'
```

Cu guard dezactivat, hubul revine la calea stock pentru `/dev/input/event0`. Asta poate reactiva comportamentul original de reset pe secvențe de buton.

### Calea legacy pe loguri

Fișierele legacy pot exista în continuare:

```text
/data/m1s_button/button_watch.sh
/data/m1s_button/m1s_mqtt_publish.sh
/data/m1s_button/m1s_button.conf
/data/m1s_button/mqtt_username
/data/m1s_button/mqtt_password
```

`button_watch.sh` citește `/var/log/messages`, filtrează `mha_master` cu `on_message basis.button`, nu deschide `/dev/input/event0`, aplică o fereastră de aproximativ 1,2 secunde și publică MQTT QoS 0 pe același topic. În configurația curentă această cale este istorică/opțională, nu soluția de protecție la reset.

Nu publica fișierele `m1s_button.conf`, `mqtt_username` sau `mqtt_password`.

---

# PARTEA VII — Recuperare Wi-Fi

## 24. Etapa 14 — Installerul Wi-Fi sanitizat, opțional

Dacă pachetul există în kitul folosit, numele lui este:

```text
installers/m1s_wifi_recovery_SANITIZED.tgz
```

Acest modul nu face parte din fluxul minim v0.8 strict pentru transformarea hubului stock în Router. Când este folosit, nu conține SSID sau parolă. Fișierele `safe/ssid` și `safe/pass` din payload sunt goale, iar installerul preia valorile curente direct de pe hub înainte de înlocuire.

### Înainte de instalare

Rulează mai întâi etapa 9A. Modulul de recovery nu repară logica stock de provisioning care poate alege AP imediat după boot; el intervine numai ulterior, după lipsa IPv4 pentru pragul configurat. Dacă hubul intră în AP la aproximativ 20 de secunde de la boot, verifică proprietățile Aqara înainte de a suspecta managerul de recovery.

### Funcționare

- managerul verifică IPv4 la fiecare 10 secunde;
- după 240 secunde fără IPv4 poate porni AP;
- AP-ul este automat numai dacă există `/data/m1s_wifi/actions_enabled`;
- fără acel fișier, managerul rămâne în simulare și doar scrie în log ce ar face;
- portalul de configurare ascultă pe `8080`;
- noua rețea devine backup numai după obținerea unui IPv4;
- la eșec, hubul revine în AP și ulterior la rețeaua sigură.

### Transfer și instalare

Hub:

```sh
rm -f /tmp/m1s_wifi_recovery_SANITIZED.tgz
nc -l -p 12345 > /tmp/m1s_wifi_recovery_SANITIZED.tgz
```

Windows:

```powershell
.\scripts\windows\Send-FileToM1S.ps1 `
  -HubIp HUB_IP `
  -Path .\installers\m1s_wifi_recovery_SANITIZED.tgz
```

Hub:

```sh
rm -rf /tmp/m1s_wifi_install
mkdir -p /tmp/m1s_wifi_install
cd /tmp/m1s_wifi_install
tar -xzf /tmp/m1s_wifi_recovery_SANITIZED.tgz
/bin/sh -n install.sh
./install.sh
```

Rezultat așteptat:

```text
WIFI_RECOVERY_INSTALL_OK
```

### Verificare fără afișarea credentialelor

```sh
wc -c /data/m1s_wifi/safe/ssid /data/m1s_wifi/safe/pass
ls -l /data/m1s_wifi/safe/ssid /data/m1s_wifi/safe/pass
ps w | grep '[w]ifi_manager.sh'
ps w | grep '[m]1s_wifi_portal_safe.sh'
tail -n 80 /tmp/m1s_wifi_manager.log
```

Ambele fișiere trebuie să aibă dimensiune mai mare de zero și permisiuni restrictive. Nu folosi `cat` asupra parolei în capturi sau loguri.

### Test în modul simulare

```sh
touch /data/m1s_wifi/test_noip
sleep 20
tail -n 30 /tmp/m1s_wifi_manager.log
rm -f /data/m1s_wifi/test_noip
```

Pentru că `actions_enabled` lipsește, logul trebuie să arate că AP-ul **ar fi pornit**, fără schimbarea reală a rețelei.

### Activarea recuperării reale

Activează numai după testul de simulare și după ce ai confirmat că backupul Wi-Fi local este populat:

```sh
touch /data/m1s_wifi/actions_enabled
chmod 600 /data/m1s_wifi/actions_enabled
sync
```

Dezactivare:

```sh
rm -f /data/m1s_wifi/actions_enabled
```

În AP, portalul este accesat direct la una dintre adresele detectate de hub:

```text
http://192.168.49.1:8080/
http://192.168.1.1:8080/
```

Nu expune portul 8080 în afara LAN-ului.

---

# PARTEA VIII — Porturi, fișiere și procese

## 25. Inventar de porturi

| Port | Direcție/rol | Permanent |
|---:|---|---|
| 23 | Telnet către hub | da, numai LAN |
| 1886 | tunel UART JN5189 creat de integrare | la nevoie |
| 1888 | ISP temporar SPSDK | nu; închide după programare |
| 1889 | transfer temporar WAV/fișier de pe hub | nu |
| 8080 | portal recuperare Wi-Fi | opțional |
| 12345 | transfer manual temporar către hub | nu |
| 12346 | media player individual | în timpul redării |
| 12347 | grup media și, separat, sursa WAV locală | în timpul redării; conflict cunoscut |
| 12348 | destinație PCM pentru WAV local | în timpul redării |
| 12349 | upload WAV | temporar |
| 1884 | client/tunel MQTT legacy din cod | nefolosit de fluxul curent |

Porturile listener ale hubului nu trebuie publicate în Internet. Porturile `1888`, `1889` și `12345` sunt one-shot sau temporare: după folosire trebuie să dispară.

---

## 26. Fișiere persistente importante

### Boot și servicii pe hub

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
```

### Buton și MQTT

```text
/data/m1s_button/m1s_mqtt_publish.sh
/data/m1s_button/m1s_button.conf
/data/m1s_button/mqtt_username
/data/m1s_button/mqtt_password
/data/m1s_button/button_watch.sh
```

`button_watch.sh` este calea legacy pe loguri. În kitul curent, calea principală este `gpio_button_watch.sh` pornit prin Factory Reset Guard.

### Wi-Fi recovery opțional

```text
/data/m1s_wifi/
/data/m1s_wifi/safe/ssid
/data/m1s_wifi/safe/pass
/data/m1s_wifi/actions_enabled
```

### Sunete administrate de integrare

```text
/data/musics/music-ch/
```

Fișiere sensibile care nu se publică:

- backupurile JN5189 stock;
- tokenul MiIO;
- SSID/parola Wi-Fi;
- configurația și credentialele MQTT;
- datele Telnet când nu sunt goale.

---

## 27. Procese așteptate

După boot, după cele minimum 120 de secunde de stabilizare:

- `telnetd` — prezent;
- `app_monitor` — suspendat (`T`);
- `mzigbee_agent` — absent, zombie sau fără control pe UART;
- `mha_basis` și `mha_master` — prezente pentru stackul stock, dar cu `/dev/input/event0` izolat dacă guardul este activ;
- `gpio_button_watch.sh` — prezent când Factory Reset Guard este activ persistent;
- `homekitserver` — oprit de `service_trim`, dacă `DISABLE_HOMEKIT=1`;
- `mijia_automation` — oprit de `service_trim`, dacă `DISABLE_MIJIA_AUTOMATION=1`;
- `wifi_manager.sh` — prezent numai dacă modulul Wi-Fi recovery este instalat;
- `m1s_wifi_portal_safe.sh` — prezent numai dacă modulul Wi-Fi recovery este instalat;
- `button_watch.sh` — opțional/legacy, nu sursa principală în varianta cu guard;
- fără `cat /dev/ttyS1` permanent în afara tunelului temporar administrat de integrare;
- fără listener `nc` rămas pe `1888` după flash.

`service_trim` nu oprește `mha_basis` și nu oprește `mha_master`. Oprirea lor brută poate rupe funcții stock utile și nu este metoda recomandată pentru izolarea butonului.

---

# PARTEA IX — Verificarea finală „hub refăcut din prima”

## 28. Checklist obligatoriu

### Hardware și acces

- [ ] modelul este `lumi.gateway.aeu01`;
- [ ] IP DHCP rezervat și stabil;
- [ ] token MiIO verificat și păstrat separat;
- [ ] Telnet activ;
- [ ] login `admin` fără parolă confirmat în configurația documentată.

### Bundle hub

- [ ] `m1s_hub_bundle_LOCAL.tgz` transferat pe hub;
- [ ] `./install.sh` a afișat `M1S_BUNDLE_V0_8_INSTALLED`;
- [ ] `/bin/sh -n /data/scripts/post_init.sh` trece;
- [ ] `/data/scripts/service_trim.conf` are `ENABLE_SERVICE_TRIM=1`;
- [ ] `/data/scripts/factory_reset_guard_boot.conf` are `ENABLE_FACTORY_RESET_BOOT_GUARD=1`;
- [ ] `post_init.sh` conține `factory_reset_guard_boot`, `service_trim`, `fw_manager.sh -r`, `mzigbee_agent` și `gpio33`;
- [ ] nu există `fw_manager.sh -f -r` în `post_init.sh`.

### Backup JN5189

- [ ] SPSDK detectează JN5189 și memoria corectă;
- [ ] două backupuri stock de 646656 bytes;
- [ ] SHA256 identic între cele două backupuri;
- [ ] backupurile salvate în două locații;
- [ ] backupurile nu sunt amestecate între huburi.

### Firmware

- [ ] firmware 209296 bytes;
- [ ] SHA256 `a1a1f302...e7a2f`;
- [ ] pentru hub stock, erase limitat la `0x33200`;
- [ ] `JN5189-Flash-WRITE.ps1` a terminat cu `FLASH_WRITE_OK`;
- [ ] readback opțional făcut separat numai dacă este necesară verificare suplimentară;
- [ ] portul `1888` închis după programare;
- [ ] GPIO33=`1`, GPIO18=`0`;
- [ ] `BDB-Router` online în Zigbee2MQTT.

### Boot persistent

- [ ] `aqara_wifi_boot_state.sh check` arată `STA_EXPECTED`;
- [ ] `/tmp/post_init.log` creat după reboot;
- [ ] Telnet disponibil după reboot;
- [ ] `app_monitor` suspendat;
- [ ] `mzigbee_agent` nu ocupă UART-ul;
- [ ] inelul de boot se stinge;
- [ ] Routerul revine automat după power cycle;
- [ ] `/tmp/service_trim.status` confirmă `homekitserver=stopped` și `mijia_automation=stopped`;
- [ ] `/tmp/factory_reset_guard_boot.status` confirmă guard activ, `mode=input_dir_overlay`, `one_shot=0`;
- [ ] `/tmp/gpio_button_watch.status` confirmă GPIO7 și `run_seconds=0`.

### Home Assistant

- [ ] manifestul integrării arată `0.20.0`;
- [ ] toate entitățile live sunt disponibile;
- [ ] RGB și lux funcționează;
- [ ] media player individual pornește/oprește și își păstrează volumul;
- [ ] Fine Volume Trim este disponibil dacă pachetul curent îl include;
- [ ] grupul funcționează cu minimum două huburi selectate;
- [ ] un hub offline nu oprește permanent celelalte;
- [ ] revenirea hubului intră prin late join / history prefill fără restart global al sursei;
- [ ] upload/listare/redare WAV testate fără grup activ pe același port.

### Buton

- [ ] publisherul manual trimite `click` pe `m1s/<ultimul_octet_IP>/button/action`;
- [ ] apăsarea scurtă produce `click` în MQTT și în Home Assistant;
- [ ] dublu click produce payloadul final așteptat;
- [ ] apăsarea lungă produce `hold_start` și `hold_release`;
- [ ] `hold_repeat` apare numai dacă menții apăsarea suficient;
- [ ] secvența de până la `ten_click` este acceptată de integrare;
- [ ] cu guard activ, apăsarea fizică nu mai generează click nou `basis.button` în logul stock.

### Opționale

- [ ] installerul Wi-Fi are `safe/ssid` și `safe/pass` populate local;
- [ ] testul `test_noip` în simulare a trecut;
- [ ] `actions_enabled` creat numai după simulare;
- [ ] niciun secret nu există în arhiva distribuită.

---

# PARTEA X — Recuperare

## 29. `TimeoutError` în SPSDK

Cauzele cele mai frecvente documentate:

- integrarea Home Assistant recreează `cat /dev/ttyS1`;
- un shell Telnet vechi ține UART-ul;
- listenerul BusyBox `nc` s-a închis după o comandă;
- JN5189 nu a fost resetat în ISP;
- GPIO33 nu este `0`;
- portul `1888` este ocupat sau filtrat;
- SPSDK a pierdut handshake-ul la readback după write, deși firmware-ul poate fi deja scris.

Procedură:

1. dacă nu ești între erase și write, oprește testul și notează ultimul pas sigur;
2. dezactivează temporar integrarea Home Assistant dacă ea redeschide UART-ul;
3. verifică să nu existe `cat /dev/ttyS1`;
4. rearmează ISP cu `/data/scripts/jn5189_enter_isp_1888.sh`;
5. confirmă `info`;
6. continuă de la ultimul pas sigur;
7. nu repeta automat erase/write doar pentru un timeout de readback dacă Routerul bootează și intră în Zigbee2MQTT.

Restartul fizic este acceptabil numai ca recovery când hubul nu mai răspunde sau când nu ești între erase și write.

---

## 30. Restaurarea firmware-ului stock JN5189

Folosește numai backupul exact al aceluiași hub.

1. intră în ISP;
2. rulează `info`;
3. șterge numai zona necesară, conform dimensiunii imaginii de restaurat;
4. scrie backupul original în Memory ID 0 la `0x0`;
5. citește-l înapoi pe aceeași lungime;
6. compară SHA256 cu backupul original;
7. închide listenerul;
8. pornește JN5189 normal;
9. pentru revenire complet stock trebuie restaurat și comportamentul boot care permite `mzigbee_agent`; simpla scriere a flashului JN5189 nu anulează automat `post_init.sh`.

Nu scrie backupul unui alt hub.

---

## 31. Revenirea la boot stock Linux

Pentru diagnostic, nu șterge imediat scriptul. Redenumește-l și păstrează backupul:

```sh
mv /data/scripts/post_init.sh /data/scripts/post_init.sh.disabled
sync
reboot
```

Aceasta permite serviciilor stock să pornească normal, inclusiv agentul Zigbee original. Un JN5189 care încă are firmware Router nu devine stock doar prin dezactivarea scriptului; evită să lași `mzigbee_agent` să concureze inutil cu firmware-ul Router.

---

## 32. Probleme audio

Verifică numai procesele și PID-urile traseului implicat. Pe hub folosește comenzi compatibile BusyBox:

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

Nu folosi opriri generale pentru procesele `nc` sau `aplay`. Integrarea folosește PID files și filtre pe linia de comandă tocmai pentru a nu întrerupe alte funcții.

---

## 33. Probleme cu butonul

În varianta curentă verifică întâi calea GPIO7/guard:

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

- dacă publisherul manual nu ajunge în Home Assistant, problema este în broker, topic sau credentiale MQTT;
- dacă publisherul manual ajunge, dar apăsarea fizică nu ajunge, problema este în GPIO7 sau `gpio_button_watch.sh`;
- dacă după apăsare apare click nou `basis.button`, Factory Reset Guard nu este activ sau overlay-ul `/dev/input` nu s-a aplicat;
- dacă `gpio_button_watch.sh` lipsește după boot, verifică `factory_reset_guard_boot.conf` și `post_init.sh`.

Calea legacy se verifică numai dacă ai dezactivat intenționat guardul:

```sh
ps w | grep '[b]utton_watch.sh'
tail -n 100 /tmp/m1s_button.log
tail -f /var/log/messages | grep 'on_message basis.button'
```

Nu folosi calea legacy ca protecție la reset. Ea doar exportă în MQTT ce firmware-ul stock a citit deja.

---

## 34. Probleme cu recuperarea Wi-Fi

Separă mai întâi cele două cazuri:

1. **AP imediat după boot** — verifică `cloud_provisioned`, `hap_provisioned` și `hap_keepalive` cu `aqara_wifi_boot_state.sh check`;
2. **AP după aproximativ 240 secunde fără IPv4** — investighează managerul opțional de recovery.

```sh
ps w | grep '[w]ifi_manager.sh'
ps w | grep '[m]1s_wifi_portal_safe.sh'
tail -n 120 /tmp/m1s_wifi_manager.log
ls -l /data/m1s_wifi/actions_enabled
wc -c /data/m1s_wifi/safe/ssid /data/m1s_wifi/safe/pass
```

Nu afișa conținutul `safe/pass`. Pentru revenire manuală la STA:

```sh
rm -f /data/m1s_wifi/ap_hold
/data/m1s_wifi/restore_sta.sh
```

---

# PARTEA XI — Actualizare și disciplină de versiune

## 35. Actualizarea integrării Home Assistant

1. fă backup Home Assistant;
2. notează versiunea manifestului curent;
3. actualizează prin HACS sau copiere manuală;
4. repornește complet Home Assistant;
5. verifică logurile și entitățile eliminate/migrate;
6. testează un singur hub înaintea tuturor;
7. abia apoi actualizează restul huburilor.

Pentru pachetul curent, manifestul așteptat este `0.20.0`. După update verifică în special STOP-ul curat și source-switch-ul atât pe grup, cât și pe un player individual; evenimentele de buton trebuie să includă până la `ten_click` plus `hold_start`, `hold_repeat`, `hold_release`.

---

## 36. Actualizarea firmware-ului JN5189

Pentru un hub stock transformat prima dată:

- păstrează backupul stock A/B;
- verifică hashul firmware-ului Router;
- dezactivează temporar orice proces care ține `/dev/ttyS1`;
- intră în ISP cu `/data/scripts/jn5189_enter_isp_1888.sh`;
- folosește `JN5189-Flash-WRITE.ps1`;
- acceptă `FLASH_WRITE_OK` ca validare de scriere;
- închide ISP, activează Permit join, bootează Routerul și verifică în Zigbee2MQTT.

Pentru un Router funcțional pe care îl actualizezi:

- păstrează backupul stock;
- salvează imaginea Router curentă dacă vrei rollback exact;
- verifică hashul nou;
- dezactivează temporar integrarea HA;
- intră în ISP;
- folosește scriere directă fără erase, exceptând cazul în care noul build cere explicit altceva;
- fă readback separat numai dacă este necesar;
- testează Zigbee, RGB, lux, rejoin și buton.

Numele fișierului nu este dovadă de identitate; hashul este obligatoriu.

---

## 37. Ce nu este rezolvat doar prin documentație

Pentru introspecția ulterioară de cod rămân cel puțin următoarele puncte:

1. conflictul portului `12347` între grup și sursa WAV;
2. fișierul `mqtt_client.py` legacy, prezent dar nefolosit;
3. `select.py` legacy, prezent dar platforma nu este încărcată;
4. lipsa unei verificări reale de conectivitate în config flow;
5. securizarea suplimentară a serviciului `run_command`;
6. testarea completă pe mai multe huburi a secvențelor `hold_start`, `hold_repeat`, `hold_release`;
7. testarea fizică a installerului Wi-Fi sanitizat și a tuturor ramurilor AP/rollback;
8. verificarea comportamentului la log rotation pentru watcherul legacy, dacă mai este păstrat;
9. eliminarea sau arhivarea codului/fișierelor istorice care nu mai aparțin release-ului curent;
10. clarificarea descriptorului ZCL care menține switch-ul expus în Zigbee2MQTT; buildul experimental `no_switch` nu a demonstrat rezolvarea și nu este inclus ca firmware recomandat;
11. „device library” nu este identificat în kit ca proces separat confirmat. În varianta curentă sunt oprite clar `homekitserver` și `mijia_automation`; dacă apare un proces real numit device library, trebuie documentat separat înainte de dezactivare.

Acestea sunt documentate intenționat, nu ascunse sub afirmația „totul este final”.

---

## 38. Regula de aur pentru refacerea următorului hub

Pentru fiecare hub nou, urmează aceeași ordine fără scurtături:

```text
model/IP → token MiIO → activare Telnet → login admin fără parolă →
verificare STA/AP → transfer bundle → install.sh → ISP info →
backup A/B identic → firmware hash → flash WRITE pentru stock →
închidere ISP → Permit join → boot Router → Zigbee2MQTT online →
adăugare în Home Assistant → reboot final → așteptare minimum 120 secunde →
verificare service_trim → verificare Factory Reset Guard → verificare GPIO7/MQTT →
verificare player individual/grup → checklist final
```

Readbackul complet rămâne instrument de verificare avansată, nu pas obligatoriu în fluxul rapid validat. Nu se repetă erase/write doar fiindcă readbackul pierde handshake-ul după scriere.

Nu trece la etapa următoare până când criteriul de acceptare al etapei curente este îndeplinit.


## Anexă istorică v0.5.14 — Group recovery

Serviciul `aqara_m1s_zigbee_router.reset_media_group` resetează dur numai transportul comun al grupului media. Acțiunea OFF a grupului folosește aceeași cale de recovery; playerele individuale și bridge-ul UART Zigbee nu sunt atinse.
