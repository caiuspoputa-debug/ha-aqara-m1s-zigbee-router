# Aqara M1S Gen 1 — 0.10.0 STABLE ULTIMATE KIT

[**Română**](README_RO.md) | [English](README.md)

**Kit hub:** `0.10.0 Stable Ultimate`  
**Data documentației:** 2026-09-19  
**Revizia README:** `R3 — Self-Contained Master Manual`  
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

Revizia R3 este scrisă ca **manual autonom**: un utilizator care nu cunoaște proiectul trebuie să poată porni de la un M1S stock și să ajungă la hubul final fără să consulte conversațiile noastre sau README-uri vechi. Informațiile dependente de versiune sunt verificate față de snapshotul real `0.21.7` și față de fișierele incluse în kit.


### Reper tehnic cunoscut al proiectului

Configurația pe care a fost construit proiectul are următoarele repere confirmate istoric:

```text
Model:                  lumi.gateway.aeu01
Firmware stock reper:   3.1.3_0009
Linux:                  MIPS, kernel 3.10.90
BusyBox:                1.22.1
JN5189 UART:             /dev/ttyS1
UART:                    115200 8N1
GPIO18:                  reset JN5189, activ la 1
GPIO33:                  ISP=0, boot normal=1
FLASH JN5189:            Memory ID 0, 0x9DE00 bytes, sector 0x200
```

`3.1.3_0009` este **reperul stock cunoscut**, nu o afirmație că orice alt firmware este incompatibil. Dacă un hub nou are alt firmware, nu presupune automat că procedura este identică: verifică modelul, Telnetul, UART-ul și geometria JN5189 înainte de orice scriere. Modelul și geometria FLASH sunt condiții de oprire dacă diferă.

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

### Oprește procedura imediat dacă

- modelul nu este exact `lumi.gateway.aeu01`;
- IP-ul nu este rezervat sau rețeaua este instabilă;
- tokenul MiIO nu este verificat;
- Telnet nu funcționează stabil;
- SPSDK nu detectează `JN5189` sau geometria FLASH diferă;
- există un `cat /dev/ttyS1` manual sau `mzigbee_agent` deține UART-ul înainte de ISP;
- unul dintre backupuri nu are exact `646656` bytes;
- SHA256 A și B diferă;
- firmware-ul nu are exact `209296` bytes și SHA256-ul documentat;
- scriptul de flash nu afișează markerii așteptați;
- ești între ERASE și WRITE: în acel interval **nu folosi rebootul ca test**.


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

Dacă lipsește clientul Telnet Windows, activează **Telnet Client** din *Optional Features / Windows Features*. Alternativ, dintr-un PowerShell/CMD deschis ca Administrator:

```powershell
dism /online /Enable-Feature /FeatureName:TelnetClient
```

---

# 7. Pregătirea hubului stock și tokenul MiIO

Această etapă este descrisă de la zero. Nu continua până când hubul stock este stabil în rețea și tokenul MiIO este verificat.

## 7.1 Adaugă hubul în Xiaomi Home

1. Dacă este necesar, resetează hubul sau pune-l în modul de asociere.
2. Pentru trecerea în modul Xiaomi/Mi Home, secvența folosită/documentată în proiect este **dublu-click** pe buton.
3. Adaugă hubul în Xiaomi Home pe Wi-Fi **2.4 GHz**.
4. Folosește regiunea corectă a contului Xiaomi.
5. Confirmă în aplicație că hubul este online și funcționează stock.
6. În router identifică MAC-ul Wi-Fi al hubului și creează o **rezervare DHCP**.
7. Repornește normal hubul și confirmă că primește aceeași adresă IP.

**Dublu-click-ul pentru ecosistem nu este secvența de activare Telnet.**

## 7.2 Obține tokenul MiIO

Metoda folosită în proiect este integrarea HACS **Xiaomi Gateway 3 / XiaomiGateway3 de AlexxIT**, prin partea sa Cloud. Ea poate afișa tokenurile dispozitivelor din contul Mi Home chiar dacă acel dispozitiv nu este controlat direct de integrare.

Pași:

1. Home Assistant → **HACS → Integrations**.
2. Caută **Xiaomi Gateway 3** / `AlexxIT/XiaomiGateway3` și instaleaz-o.
3. Repornește Home Assistant dacă este cerut.
4. Configurează partea **Cloud** cu același cont Xiaomi și aceeași regiune folosite în Xiaomi Home.
5. În lista dispozitivelor contului găsește modelul `lumi.gateway.aeu01`.
6. Copiază tokenul MiIO și păstrează-l ca pe o parolă.

Tokenul are în mod normal **32 caractere hexazecimale**.

Nu pune tokenul în README, capturi, GitHub sau arhive distribuite.

### Dacă nu folosești HACS

Ai nevoie tot de tokenul MiIO înainte de metoda software de activare Telnet. Poți folosi o altă metodă de extragere a tokenului compatibilă cu contul/regiunea ta, dar **nu continua până când tokenul nu este verificat cu comanda de mai jos**.

## 7.3 Verifică tokenul înainte de activarea Telnet

În PowerShell pe PC:

```powershell
python -m miio.cli device --ip HUB_IP --token MIIO_TOKEN info
```

Trebuie să primești informațiile dispozitivului. Dacă primești timeout, token invalid sau date de la alt dispozitiv, **STOP**.

## 7.4 Fișa privată a hubului

Pentru fiecare hub păstrează separat:

```text
Nume hub:
Model:
MAC Wi-Fi:
IP rezervat:
Firmware stock:
Token MiIO: păstrat separat, NU în fișa publică
Data backupului JN5189:
SHA256 backup A:
SHA256 backup B:
SHA256 firmware Router:
Nume dispozitiv Zigbee2MQTT:
Nume intrare Home Assistant:
```

---

# 8. Activează Telnet temporar — PAS CRITIC

**Fără Telnet nu poți instala kitul. Nu trece la secțiunea 9 până când `telnet HUB_IP` nu deschide shell-ul hubului.**

## 8.1 Metoda fizică documentată

Pentru firmware stock compatibil, secvența fizică documentată în proiect este:

```text
5-2-2-2-2-2-2
```

Aceasta este **secvența pentru activarea Telnet**. Este diferită de dublu-click-ul pentru modul Xiaomi/Mi Home.

README-ul păstrează secvența exact cum a fost documentată în proiect și **nu inventează timpi între grupurile de apăsări**. Dacă firmware-ul tău nu deschide Telnet prin această metodă, folosește metoda MiIO de mai jos.

## 8.2 Metoda recomandată din kit — PowerShell + MiIO

Din rădăcina kitului, pe Windows:

```powershell
.\scripts\windows\Enable-TemporaryTelnet.ps1 -HubIp HUB_IP
```

Scriptul:

1. cere tokenul MiIO mascat;
2. verifică tokenul prin `Device.info()`;
3. numai după verificare trimite comanda de activare Telnet.

Markerii corecți:

```text
MIIO_TOKEN_OK
TELNET_REQUEST_SENT HUB_IP
```

Dacă Python nu este `C:\Windows\py.exe`, indică executabilul real:

```powershell
.\scripts\windows\Enable-TemporaryTelnet.ps1 `
  -HubIp HUB_IP `
  -Python "C:\Path\To\python.exe"
```

## 8.3 Fallback manual MiIO

Dacă trebuie diagnosticat helperul PowerShell, comanda MiIO folosită istoric este:

```powershell
python -m miio.cli device --ip HUB_IP --token MIIO_TOKEN raw_command set_ip_info '{"ssid":"\\"\\"","pswd":"123123 ; passwd -d admin ; passwd -d root ; telnetd"}'
```

Această comandă este pentru **PowerShell/PC**, nu pentru shell-ul hubului. Ruleaz-o numai în LAN și nu salva tokenul real în documente publice.


Comanda validată face explicit trei lucruri pe partea de acces administrativ:

```text
passwd -d admin
passwd -d root
telnetd
```

De aceea autentificarea documentată este cu parolă goală pentru `admin` și, ca alternativă, `root`. Consideră acest lucru **acces administrativ complet și necriptat**. Nu expune portul `23` în Internet și nu folosi această stare pe o rețea în care nu ai încredere.

## 8.4 Conectează-te prin Telnet

Pe PC:

```powershell
telnet HUB_IP
```

Login validat în proiect:

```text
user: admin
password: gol
```

Pe unele stări stock poate funcționa și:

```text
user: root
password: gol
```

După autentificare trebuie să vezi shell-ul Linux al hubului. **Abia din acest moment** rulezi comenzile `/data/...`, `ps`, `ifconfig`, `md5sum`, `tar` etc.

Dacă nu apare shell-ul, **STOP**.

## 8.5 Verificarea inițială după primul login

Pe hub:

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

Modelul trebuie să fie exact:

```text
lumi.gateway.aeu01
```

Confirmă și că `wlan0` are IP-ul rezervat. Dacă modelul este altul sau rețeaua este instabilă, **STOP**.

---

# 9. Transferă installerul unic 0.10.0

Transferul folosește un listener BusyBox `nc` pe portul `12345`. Este normal ca terminalul Telnet să pară „blocat” după comanda `nc -l`: hubul așteaptă ca PC-ul să trimită fișierul. Nu închide acea fereastră înainte de trimitere.

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

## 10.1 Dacă preflight-ul nu trece — verificări manuale

Nu ocoli `ULTIMATE_PREFLASH_OK`. Folosește verificările de mai jos doar pentru a afla **de ce** a eșuat.

Starea stock care decide STA/AP:

```sh
/data/scripts/aqara_wifi_boot_state.sh check
```

Un rezultat sănătos trebuie să ajungă la:

```text
cloud_provisioned=true
hap_provisioned=true
hap_keepalive=true
user_paired=true
BOOT_WIFI_SELECTION=STA_EXPECTED
```

Dacă helperul raportează `AP_RISK`, corecția documentată este:

```sh
/data/scripts/aqara_wifi_boot_state.sh fix
/data/scripts/aqara_wifi_boot_state.sh check
```

Verifică apoi boot hook-ul:

```sh
/bin/sh -n /data/scripts/post_init.sh
grep -n 'factory_reset_guard\|service_trim\|fw_manager\|mzigbee_agent\|gpio33' /data/scripts/post_init.sh
```

### Avertisment critic `fw_manager`

Bootul normal al serviciilor stock folosește:

```text
fw_manager.sh -r
```

Opțiunea:

```text
fw_manager.sh -f -r
```

intră pe calea de **factory reset** și nu trebuie introdusă în `post_init.sh`. Ultimate folosește intenționat numai bootul normal `-r`; Factory Reset Guard izolează butonul înainte de pornirea stackului stock.

Dacă vrei să confirmi proprietățile fără helper:

```sh
getprop persist.app.cloud_provisioned
getprop persist.app.hap_provisioned
getprop persist.app.hap_keepalive
getprop persist.app.user_paired
```

După orice corecție, rulează din nou:

```sh
/data/scripts/ultimate_preflash_check.sh
```

și nu continua până când apare exact `ULTIMATE_PREFLASH_OK`.

---

# 11. Intră JN5189 în ISP

Pe hub:

```sh
/data/scripts/jn5189_enter_isp_1888.sh
```

Rezultatul așteptat trebuie să includă:

```text
ISP_LISTENER_OK port=1888 ...
GPIO33=0 GPIO18=0
```

Nu porni backupul dacă scriptul raportează eroare. Nu rula din nou `jn5189_enter_isp_1888.sh` cât timp o comandă SPSDK este activă.

Dacă ai consumat/închis listenerul înainte de `dk6prog`, rearmează-l:

```sh
/data/scripts/jn5189_close_isp_1888.sh
/data/scripts/jn5189_enter_isp_1888.sh
```

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


Dacă `info` nu detectează JN5189, verifică înainte să repeți comanda:

```sh
ps w | grep '[c]at /dev/ttyS1'
ps w | grep '[m]zigbee_agent'
ps w | grep '[a]pp_monitor'
netstat -lnt | grep 1888
```

Pentru un `cat /dev/ttyS1` care reapare și trebuie identificat:

```sh
for p in $(ps w | grep '[c]at /dev/ttyS1' | awk '{print $1}'); do
  echo "CAT=$p"
  grep PPid /proc/$p/status
done
```

Nu opri generic toate procesele `nc`; unele sunt folosite legitim de audio sau de tunelurile temporare ale integrării.

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


Verificare manuală pe Windows:

```powershell
Get-Item .\firmware\jn5189_router_rgb_lux_rejoin_test.bin
Get-FileHash .\firmware\jn5189_router_rgb_lux_rejoin_test.bin -Algorithm SHA256
```

Dacă dimensiunea sau hashul diferă, **STOP** chiar dacă numele fișierului este identic.

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


### 14.1 Referință SPSDK manuală — numai pentru diagnostic avansat

Fluxul normal folosește scriptul `JN5189-Flash-WRITE.ps1`, deoarece acesta impune poarta de backup. Comenzile de mai jos **ocolesc acea protecție** și sunt documentate numai pentru recovery/diagnostic atunci când știi exact starea hubului.

```powershell
# Identificare
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n info

# ERASE NUMAI la prima conversie stock / recovery justificat
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n erase 0x0 0x33200 0

# WRITE imagine Router validată
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n write 0x0 ".\firmware\jn5189_router_rgb_lux_rejoin_test.bin" 0

# Readback exact al imaginii Router
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1888" -n read -o ".\readback.bin" 0x0 209296 0
```

În SPSDK 3.10, `erase` folosește argumentele poziționale de mai sus. Nu face full-chip erase și nu scrie alte Memory ID-uri.

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

# 16. Instalează integrarea și adaugă hubul în Home Assistant

Versiunea reproductibilă inclusă în kit:

```text
Aqara M1S Zigbee Router 0.21.7
```

Repository:

```text
https://github.com/caiuspoputa-debug/ha-aqara-m1s-zigbee-router
```

Snapshot offline:

```text
home_assistant/ha-aqara-m1s-zigbee-router-v0.21.7-SNAPSHOT.zip
```

## 16.1 Dacă ai HACS

1. Home Assistant → **HACS → Integrations**.
2. Deschide meniul **Custom repositories**.
3. Adaugă:
   ```text
   https://github.com/caiuspoputa-debug/ha-aqara-m1s-zigbee-router
   ```
4. Category: **Integration**.
5. Instalează **Aqara M1S Zigbee Router**.
6. Repornește complet Home Assistant.
7. Verifică `custom_components/aqara_m1s_zigbee_router/manifest.json`. Pentru snapshotul acestui kit versiunea este `0.21.7`.

Dacă HACS are deja o versiune compatibilă instalată, nu reinstala integrarea pentru fiecare hub nou.

## 16.2 Dacă NU ai HACS — instalare manuală/offline

1. Deschide `home_assistant/ha-aqara-m1s-zigbee-router-v0.21.7-SNAPSHOT.zip`.
2. Extrage directorul:
   ```text
   custom_components/aqara_m1s_zigbee_router
   ```
3. Copiază-l în Home Assistant la:
   ```text
   /config/custom_components/aqara_m1s_zigbee_router
   ```
4. Repornește complet Home Assistant.

La final trebuie să existe:

```text
/config/custom_components/aqara_m1s_zigbee_router/manifest.json
```

și versiunea să fie `0.21.7` pentru snapshotul inclus.

## 16.3 Adaugă noul hub

În Home Assistant:

```text
Settings / Setări
→ Devices & services / Dispozitive și servicii
→ Add integration / Adaugă integrare
→ Aqara M1S Zigbee Router
```

Completează:

```text
Host:      HUB_IP
Port:      23
Username:  admin
Password:  gol
Name:      un nume unic pentru hub
```

Dacă pe hub ai confirmat manual alt user/parolă Telnet, folosește exact credentialele testate.

Integrarea folosește Telnet local. Identitatea config-entry-ului este stabilizată după MAC-ul Wi-Fi (`mac:<wifi_mac>`), astfel încât schimbarea controlată ulterioară a IP-ului să actualizeze aceeași intrare.

**Adaugă integrarea înainte de rebootul final**, apoi continuă cu secțiunea 17.

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

Dacă verificatorul automat nu trece, aceste comenzi sunt sigure pentru diagnostic:

```sh
cat /tmp/post_init.log
cat /tmp/factory_reset_guard_boot.status
cat /tmp/gpio_button_watch.status
cat /tmp/service_trim.status
mount | grep /dev/input
ps w | grep '[g]pio_button_watch.sh'
ps w | grep '[t]elnetd'
ps w | grep '[m]zigbee_agent'
cat /sys/class/gpio/gpio33/value
cat /sys/class/gpio/gpio18/value
netstat -lnt | grep 1888
```

După boot stabil:
- GPIO33 trebuie să fie `1`;
- GPIO18 trebuie să fie `0`;
- portul `1888` nu trebuie să mai asculte;
- `mzigbee_agent` nu trebuie să dețină UART-ul;
- `post_init.log` trebuie să existe;
- guardul și watcherul trebuie să raporteze starea activă.

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

### Topic MQTT și timpii butonului

Publisherul real din acest kit publică pe:

```text
m1s/<BUTTON_TOPIC_ID>/button/action
```

La prima inițializare, dacă `BUTTON_TOPIC_ID` este gol, managerul de rețea îl fixează la **ultimul octet al IP-ului curent** și îl salvează în:

```text
/data/m1s_network/network.conf
```

Acest ID rămâne stabil la schimbarea ulterioară a IP-ului static, astfel încât topicul butonului să nu se schimbe doar pentru că adresa IPv4 s-a schimbat. Dacă ID-ul nu este încă salvat, publisherul are fallback la ultimul octet al IP-ului curent.

Valorile de bază ale watcherului din kit sunt:

```text
GPIO_BUTTON=7
ACTIVE_VALUE=1
POLL_INTERVAL_TENTHS=1      # 0.1 s
DOUBLE_WINDOW_TENTHS=8      # 0.8 s
HOLD_TENTHS=12              # 1.2 s până la hold
HOLD_REPEAT_TENTHS=5        # 0.5 s între repeat-uri
```

Fișierul persistent `gpio_button_watch.conf` este păstrat conservator cu `ENABLE_GPIO_BUTTON_WATCH=0` și `DRY_RUN=1`. La boot, **Factory Reset Guard pornește watcherul în mod live** printr-o copie temporară a setărilor (`ENABLE=1`, `DRY_RUN=0`, runtime nelimitat), apoi restaurează fișierul de configurare. De aceea nu interpreta valorile inactive din fișier ca dovadă că watcherul nu rulează.

Test manual al publisherului:

```sh
/data/m1s_button/m1s_mqtt_publish.sh click
echo "rc=$?"
```

Cu guardul activ, o apăsare fizică trebuie să ajungă prin GPIO7/MQTT și nu trebuie să creeze un nou click stock `basis.button`.

Calea `button_watch.sh` pe loguri rămâne pentru compatibilitate/diagnostic, dar nu este metoda principală de protecție la reset.

### Rollback Factory Reset Guard

Dacă trebuie să reactivezi temporar calea stock a butonului pentru diagnostic:

```sh
cp /data/scripts/factory_reset_guard_boot.conf /data/scripts/factory_reset_guard_boot.conf.before_disable
sed -i 's/^ENABLE_FACTORY_RESET_BOOT_GUARD=.*/ENABLE_FACTORY_RESET_BOOT_GUARD=0/' /data/scripts/factory_reset_guard_boot.conf
sync
reboot
```

Asta poate readuce comportamentul stock de reset al butonului. Păstrează copia `.before_disable` pentru revenire.

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


## 21.1 Ce face `post_init.sh` la fiecare boot

Ordinea este importantă pentru diagnostic:

1. pornește `syslogd` dacă lipsește;
2. verifică stările Aqara de provisioning STA/AP;
3. pornește Factory Reset Guard, care izolează `/dev/input` înainte de stackul stock;
4. pornește serviciile stock prin **`fw_manager.sh -r`**;
5. pornește `service_trim`;
6. așteaptă asocierea Wi-Fi;
7. reaplică IP-ul static confirmat, dacă există, fără să modifice `fw_manager.sh`;
8. solicită Telnet persistent prin `fw_manager.sh -t -k`;
9. pornește Wi-Fi Recovery/portal dacă sunt instalate;
10. ține oprit stackul Zigbee stock (`app_monitor.sh` / `mzigbee_agent`) care ar ocupa JN5189;
11. repornește `mha_master -b` pentru compatibilitatea evenimentelor legacy;
12. elimină cititoare vechi `cat /dev/ttyS1`, setează UART-ul la `115200 raw`;
13. bootează JN5189 normal: GPIO33=`1`, pulse reset GPIO18 `1 → 0`;
14. pornește bridge-ul legacy al butonului dacă este configurat;
15. trimite RGB OFF după stabilizare.

**Nu modifica această ordine fără motiv demonstrat.** În special, nu înlocui `fw_manager.sh -r` cu `fw_manager.sh -f -r`.

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
| 1884 | referință/client MQTT legacy; nu este folosit de fluxul curent |
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

### Acces inițial

- [ ] hub stock adăugat în Xiaomi Home pe 2.4 GHz
- [ ] DHCP reservation creată
- [ ] token MiIO obținut și verificat cu `device info`
- [ ] metoda Telnet cunoscută: `5-2-2-2-2-2-2` sau MiIO helper
- [ ] `telnet HUB_IP` deschide shell-ul hubului
- [ ] modelul verificat este `lumi.gateway.aeu01`

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

## 34.0 Transfer manual generic de fișier

Dacă trebuie să trimiți manual un script individual din kit pentru diagnostic, metoda folosită de proiect este:

Pe hub:

```sh
rm -f /tmp/NUME_FISIER
nc -l -p 12345 > /tmp/NUME_FISIER
```

În Windows:

```powershell
.\scripts\windows\Send-FileToM1S.ps1 `
  -HubIp HUB_IP `
  -Path .\CALEA_DIN_KIT\NUME_FISIER `
  -Port 12345
```

Apoi pe hub:

```sh
ls -l /tmp/NUME_FISIER
/bin/sh -n /tmp/NUME_FISIER
echo "syntax=$?"
busybox sha256sum /tmp/NUME_FISIER 2>/dev/null || true
```

Pentru un script shell, `syntax=0` este obligatoriu înainte de execuție. Nu folosi această metodă pentru a substitui fișiere vechi peste 0.10.0 „doar ca test”.


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


### Testul README-ului

Dacă revii la proiect peste luni sau dacă altcineva citește documentația de pe GitHub, nu trebuie să știe nimic din conversațiile anterioare. Din acest README trebuie să poată afla:

- ce model este acceptat;
- ce software trebuie instalat pe PC;
- cum se adaugă hubul stock în Xiaomi Home;
- cum se obține și verifică tokenul MiIO;
- **secvența fizică Telnet `5-2-2-2-2-2-2`**;
- metoda MiIO care activează Telnet și golește parolele `admin`/`root`;
- cum se face login;
- cum se transferă fișiere;
- cum se pregătește Linux-ul fără a scrie JN5189;
- ce înseamnă `ULTIMATE_PREFLASH_OK`;
- cum se intră în ISP;
- cum se verifică JN5189;
- cum se fac și se validează cele două backupuri;
- ce firmware și hash sunt permise;
- cum se face flash numai după backup;
- cum se bootează Routerul și se adaugă în Zigbee2MQTT;
- cum se instalează integrarea Home Assistant de la zero;
- cum se validează rebootul final;
- cum funcționează butonul, MQTT, audio, WAV, Wi-Fi Recovery și IP-ul static;
- cum se diagnostichează și cum se revine spre stock.

Dacă una dintre aceste informații lipsește într-o revizie viitoare, README-ul nu trebuie considerat master.

Pentru auditul tehnic al buildului vezi `docs/VALIDATION_REPORT.md`.
