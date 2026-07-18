# Aqara M1S Zigbee Router

**Română** | [English](README.md)

Integrare custom Home Assistant pentru un hub Aqara M1S Gen 1 convertit în
NXP JN5189 BDB Zigbee Router, cu inel RGB, iluminare, audio și diagnosticare
locală a hubului.

Versiune curentă: **0.2.0 (test release)**

> Proiectul este destinat modelului Aqara M1S Gen 1 `lumi.gateway.aeu01`.
> Scrierea JN5189 este o operație avansată. Păstrează un backup verificat și nu
> scrie niciodată EFUSE, ROM, Config sau PSECT.

## Configurație validată

- Hub: Aqara M1S Gen 1 (`lumi.gateway.aeu01`)
- Firmware stock folosit la pregătire: `3.1.3_0009`
- Linux: MIPS, kernel 3.10.90, BusyBox 1.22.1
- SoC Zigbee: NXP JN5189
- Rol Zigbee după conversie: BDB Router
- UART Zigbee: `/dev/ttyS1`, 115200 8N1
- Reset JN5189: GPIO18, activ la `1`
- Selectare ISP JN5189: GPIO33, ISP=`0`, boot normal=`1`
- Director de sunete administrat: `/data/musics/music-ch`
- Domeniul integrării: `aqara_m1s_zigbee_router`

## Funcții

- funcționare NXP BDB Zigbee Router cu Zigbee2MQTT
- inel RGB cu reglarea culorii și luminozității
- iluminare citită direct din JN5189, fără MQTT
- navigarea media nativă Home Assistant și redarea URL-urilor directe
- redare radio prin FFmpeg din Home Assistant
- butoane pentru sunetele WAV locale Aqara
- upload din browser și ștergere protejată pentru WAV-uri personalizate
- controlul volumului de redare
- temperatura hubului din proprietatea validată `persist.sys.temperature`
- diagnostic pentru IP Wi-Fi, procese și starea JN5189
- monitorizare comună online/offline la 15 secunde
- stingerea automată a inelului roșu de boot după reconectarea Wi-Fi

Când hubul este offline, lumina, media playerul, volumul și senzorii live devin
indisponibili. Butoanele sunetelor rămân intenționat vizibile. Uploadul și
ștergerea actualizează numai catalogul de sunete; nu reîncarcă integrarea și nu
resetează celelalte entități.

## Firmware-ul final RGB + lux

Imaginea finală folosește **PIO19/ADC5** pentru senzorul de lumină ambientală:

```text
Fișier: jn5189_router_rgb_lux_pio19.bin
Dimensiune: 209312 bytes (0x331A0)
Lungime erase parțial: 0x33200
Memorie: ID 0 / FLASH
SHA256: 33FB799E4B5E9C3B33E9B8E1B40089DBD04FA2DCDD7BF5D681E41F152BD8D611
```

Aceasta este singura imagine de flash care trebuie publicată împreună cu
proiectul. Build-ul final a fost validat fizic la aproximativ `54 lx` cu
senzorul luminat și `2 lx` cu senzorul acoperit.

## Instalare completă pornind de la un hub stock

### 1. Adăugarea hubului în Xiaomi Home

1. Resetează hubul sau pune-l în modul de asociere.
2. Apasă de două ori butonul hubului pentru trecerea din modul Aqara în modul
   Xiaomi/Mi Home.
3. Adaugă hubul în Xiaomi Home/Mi Home pe o rețea Wi-Fi de 2,4 GHz.
4. Folosește regiunea corectă a contului Xiaomi.
5. Rezervă adresa IP a hubului în configurația DHCP a routerului.

Apăsarea dublă schimbă ecosistemul aplicației; nu este secvența Telnet
documentată mai jos.

### 2. Extragerea tokenului MiIO

1. Instalează **Xiaomi Gateway 3** de la AlexxIT din HACS.
2. Repornește Home Assistant dacă este cerut.
3. Adaugă integrarea Xiaomi Gateway 3.
4. Autentifică-te cu același cont și aceeași regiune folosite în Xiaomi Home.
5. Găsește modelul `lumi.gateway.aeu01` și copiază tokenul MiIO.

Un token MiIO valid are exact 32 de caractere hexazecimale. Tratează-l ca pe o
parolă și nu îl publica.

Verificare în Windows PowerShell:

```powershell
python -m pip install python-miio
python -m miio.cli device --ip HUB_IP --token MIIO_TOKEN info
```

### 3. Activarea temporară Telnet

Secvența fizică temporară validată este:

```text
5-2-2-2-2-2-2
```

Dacă firmware-ul stock compatibil o acceptă, conectează-te cu:

```powershell
telnet HUB_IP
```

Încearcă utilizatorul `admin` cu parola goală; dacă este necesar, încearcă
`root` cu parola goală.

Alternativa prin MiIO este:

```powershell
python -m miio.cli device --ip HUB_IP --token MIIO_TOKEN raw_command set_ip_info '{"ssid":"\"\"","pswd":"123123 ; passwd -d admin ; passwd -d root ; telnetd"}'
```

Telnet nu este criptat și trebuie păstrat numai în LAN. Metoda fizică sau MiIO
poate fi temporară.

#### Telnet persistent și pornirea Routerului

Următorul `post_init.sh` este destinat unui hub Router pregătit de la zero. Dacă
hubul este deja convertit și scriptul său actual de boot funcționează, fă backup
și nu îl suprascrie inutil.

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

# Necesar pentru serviciile Linux, Wi-Fi, HomeKit si audio originale.
fw_manager.sh -r &

(
    wait_for_wifi
    sleep 5
    fw_manager.sh -t -k &
    echo "$(date) Telnet start requested." >> "$LOG_FILE"

    # Lasa serviciile stock sa porneasca, apoi elibereaza UART-ul JN5189.
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

Rezultatul așteptat este `syntax=0`. Nu da reboot dacă rezultatul este diferit.
După reboot, așteaptă Wi-Fi și verifică:

```sh
cat /tmp/post_init.log
ps | grep '[t]elnetd'
ps | grep '[m]zigbee_agent'
cat /sys/class/gpio/gpio33/value
cat /sys/class/gpio/gpio18/value
```

Telnet trebuie să ruleze, `mzigbee_agent` nu trebuie să ocupe UART-ul, iar
valorile GPIO trebuie să fie `1`, apoi `0`. Scriptul nu creează vechiul tunel
MQTT; v0.2.0 citește lux direct din JN5189 și nu necesită MQTT.

### 4. Backup pentru flash-ul original JN5189

Instalează SPSDK în Windows:

```powershell
python --version
python -m pip install "spsdk[dk6]"
python -m spsdk.apps.dk6prog --help
```

Transportul prin rețea folosește backendul `PYSERIAL` și URL-ul pyserial
`socket://HUB_IP:1886`. Unele versiuni SPSDK pot necesita ca driverul PYSERIAL
să deschidă dispozitivul cu `serial.serial_for_url(...)`.

Înainte de preluarea `/dev/ttyS1`, oprește procesul care îl ocupă și împiedică
monitorul să-l repornească. Identifică mai întâi PID-urile exacte:

```sh
ps | grep '[a]pp_monitor'
ps | grep '[m]zigbee_agent'
```

Pentru sesiunea temporară de programare:

```sh
kill -STOP PID_APP_MONITOR
kill PID_MZIGBEE_AGENT
```

Înlocuiește valorile numai cu PID-urile afișate de comenzile precedente.

Înainte de **fiecare** comandă SPSDK, recreează tunelul UART și resetează
JN5189 în ISP:

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

Verifică legătura din PowerShell:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1886" -n info
```

Rezultatul trebuie să includă:

```text
Detected DEVICE: JN5189
FLASH: base 0x0, length 0x9DE00, sector 0x200
```

Recreează tunelul și resetul ISP, apoi citește flash-ul original:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1886" -n read -o "jn5189_original_flash.bin" 0x0 646656 0
Get-FileHash ".\jn5189_original_flash.bin" -Algorithm SHA256
```

Păstrează acest backup în două locuri sigure.

### 5. Verificarea și scrierea imaginii finale

Verifică mai întâi imaginea descărcată:

```powershell
Get-FileHash ".\jn5189_router_rgb_lux_pio19.bin" -Algorithm SHA256
```

Trebuie să corespundă hash-ului SHA256 complet din secțiunea firmware.

Nu folosi erase complet pentru o actualizare normală. Recreează tunelul și
resetul ISP, apoi șterge numai zona imaginii:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1886" -n erase 0x0 0x33200 0
```

Recreează iar tunelul și resetul ISP, apoi scrie imaginea:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1886" -n write 0x0 ".\jn5189_router_rgb_lux_pio19.bin"
```

Nu combina erase și write. Recreează încă o dată tunelul și resetul ISP, apoi
citește înapoi exact 209312 bytes:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://HUB_IP:1886" -n read -o ".\jn5189_router_rgb_lux_pio19_verify.bin" 0x0 209312 0
Get-FileHash ".\jn5189_router_rgb_lux_pio19.bin", ".\jn5189_router_rgb_lux_pio19_verify.bin" -Algorithm SHA256
```

Ambele hash-uri trebuie să fie identice. Nu porni o imagine care nu trece
verificarea.

### 6. Ieșirea din ISP și pornirea Routerului

Rulează pe hub:

```sh
echo 1 > /sys/class/gpio/gpio33/value
echo 1 > /sys/class/gpio/gpio18/value
sleep 1
echo 0 > /sys/class/gpio/gpio18/value
sleep 10

cat /sys/class/gpio/gpio33/value
cat /sys/class/gpio/gpio18/value
```

Valorile normale sunt:

```text
1
0
```

Modul Router cere ca `/dev/ttyS1` să rămână liber de procesul original
`mzigbee_agent`. După fiecare reboot verifică:

```sh
ps | grep '[m]zigbee_agent'
ps | grep '[a]pp_monitor'
```

Niciun proces nu trebuie să ocupe `/dev/ttyS1` în timp ce integrarea folosește
protocoalele RGB și lux ale JN5189. Această cerință Router este diferită de o
configurație stock în care `mzigbee_agent` rămâne pornit.

Dacă a fost șters accidental întregul flash, activează **Permit join (All)**
în Zigbee2MQTT, păstrează GPIO33=`1`, pulsează GPIO18 `1 -> 0` și așteaptă
30–60 de secunde pentru reasocierea dispozitivului `BDB-Router`.

### 7. Verificarea Zigbee, RGB și lux

Dispozitivul trebuie să apară în Zigbee2MQTT ca Lumi/NXP `BDB-Router`, cu rol
Router.

Protocol RGB:

```text
A5 RED GREEN BLUE CHECKSUM
CHECKSUM = A5 XOR RED XOR GREEN XOR BLUE
```

Test manual OFF:

```sh
printf '\245\000\000\000\245' > /dev/ttyS1
```

Cerere și răspuns lux:

```text
Cerere:  A6 00 00 00 A6
Răspuns: A6 RAW_H RAW_L MV_H MV_L LUX_H LUX_L CHECKSUM
```

Checksum-ul răspunsului este XOR-ul primilor șapte bytes. Integrarea îl
validează și publică `LUX_H * 256 + LUX_L` în lux. Nu lăsa un proces blocant
`cat /dev/ttyS1` pornit după testele manuale; integrarea creează și administrează
singură tunelul TCP/UART pe portul `1886`.

## Instalarea în Home Assistant

### HACS

1. Deschide **HACS > Integrations**.
2. Deschide meniul și alege **Custom repositories**.
3. Adaugă:
   `https://github.com/caiuspoputa-debug/ha-aqara-m1s-zigbee-router`
4. Selectează categoria **Integration**.
5. Descarcă ultima versiune.
6. Repornește complet Home Assistant.
7. Deschide **Setări > Dispozitive și servicii > Adaugă integrare**.
8. Caută **Aqara M1S Zigbee Router**.
9. Introdu IP-ul hubului și datele Telnet.

HACS instalează direct conținutul repository-ului; `hacs.json` nu cere o
arhivă ZIP atașată separat release-ului.

### Instalare manuală

Copiază:

```text
custom_components/aqara_m1s_zigbee_router
```

în:

```text
/config/custom_components/aqara_m1s_zigbee_router
```

Repornește Home Assistant și adaugă integrarea. Domeniul este diferit de
`aqara_m1s_local`, deci cele două integrări pot coexista, dar nu trebuie să
concureze pentru același UART sau aceleași resurse audio ale hubului.

## Entități în v0.2.0

- `Ring Light`: inel RGB cu luminozitate
- `Radio`: difuzor/media player general Home Assistant
- `Sound Playback Volume`: volumul redării sunetelor locale
- `Illuminance`: lux direct din JN5189, cu atribute ADC raw și millivolts
- `Hub Temperature`: numai din `persist.sys.temperature`
- `WiFi IP`
- diagnostic pentru procesele HomeKit, MQTT și Telnet
- starea `JN5189 Router`
- câte un buton de redare pentru fiecare WAV din catalogul suportat

Entitățile vechi sunt eliminate intenționat: `Volume Property`,
`Uptime Seconds`, `Sound`, `Delete Selected Sound` și
`Play Selected Sound`.

## Media player nativ și radio

Versiunea 0.2.0 publică entitatea ca difuzor cu `PLAY_MEDIA` și `BROWSE_MEDIA`.
Poate naviga sursele audio Home Assistant compatibile, inclusiv Local Media,
și poate reda URL-uri radio HTTP/HTTPS directe.

Exemplu:

```yaml
action: media_player.play_media
target:
  entity_id: media_player.aqara_m1s_zigbee_router_radio
data:
  media_content_id: "https://example.org/live.aac"
  media_content_type: music
```

Home Assistant rezolvă identificatorii `media-source://`, iar FFmpeg convertește
intrarea în PCM mono, 32000 Hz, semnat pe 32 biți. Hubul primește fluxul pe
portul TCP `12346` și îl redă cu `aplay`. Curățarea folosește PID-urile proprii
și nu execută niciodată `killall nc`, deoarece hubul poate folosi și alte
procese `nc`.

Integrarea separată **Radio Favorites** poate selecta această entitate ca
destinație și oferă un catalog reutilizabil de posturi.

## Administrarea sunetelor

Deschide:

**Setări > Dispozitive și servicii > Aqara M1S Zigbee Router > Configure**

Sesiunea de administrare oferă:

- **Upload WAV sound**
- **Delete WAV sound**
- **Finish and close**

Fereastra rămâne deschisă după fiecare upload sau ștergere, pentru administrarea
mai multor fișiere în aceeași sesiune. La final apasă **Finish and close**. Nu
mai există o entitate de ștergere pe pagina dispozitivului și nici butonul
redundant pentru redarea sunetului selectat.

Sunt administrate numai fișierele aflate direct în directorul protejat:

```text
/data/musics/music-ch
```

Celelalte directoare originale Aqara nu sunt modificate. Format acceptat:

- extensie `.wav`
- PCM necomprimat
- mono
- 32000 Hz
- signed 32-bit little-endian (`pcm_s32le`)
- maximum 20 MiB

Conversie cu FFmpeg:

```sh
ffmpeg -y -i input.mp3 -ac 1 -ar 32000 -c:a pcm_s32le output.wav
```

Uploadul folosește transfer LAN cu verificarea dimensiunii pe portul TCP
`12349`, cu BusyBox `base64` ca rezervă. Catalogul și butoanele individuale se
actualizează fără reload pentru config entry și fără resetarea entităților lux,
temperatură, RGB sau media.

Integrarea înregistrează și următoarele acțiuni pentru automatizări avansate:

```text
aqara_m1s_zigbee_router.upload_sound
aqara_m1s_zigbee_router.delete_sound
aqara_m1s_zigbee_router.refresh_sounds
```

## Temperatura și disponibilitatea

`Hub Temperature` citește exclusiv:

```sh
getprop persist.sys.temperature
```

Valoarea Linux thermal-zone cunoscută ca fiind greșită, `1 °C`, nu este
folosită. Dacă proprietatea nu poate fi interpretată sau este neverosimilă,
entitatea devine indisponibilă.

Coordinatorul verifică hubul la 15 secunde. Entitățile live devin indisponibile
cât timp hubul este offline; butoanele sunetelor rămân vizibile intenționat.
După reconectarea Wi-Fi, integrarea trimite o singură comandă RGB OFF pentru a
stinge roșul slab de boot al firmware-ului, dar păstrează în Home Assistant
ultima culoare și luminozitate pentru următoarea pornire manuală.

## Securitate și recuperare

- Păstrează Telnet și porturile `1886`, `12346` și `12349` numai în LAN.
- Nu le expune prin port forwarding.
- Nu publica tokenul MiIO sau datele Telnet.
- Păstrează backupul flash original JN5189 și hash-ul său SHA256.
- Nu scrie niciodată EFUSE, ROM, Config sau PSECT.
- Pentru recuperare, intră în ISP cu GPIO33=`0`, verifică `info`, scrie
  backupul original validat în Memory ID 0, citește-l înapoi, compară SHA256,
  apoi pornește cu GPIO33=`1` și GPIO18=`0`.

## Actualizare de la v0.1.9

1. Actualizează fișierele repository-ului și manifestul la `0.2.0`.
2. Creează/publică tagul `v0.2.0`.
3. Actualizează integrarea prin HACS.
4. Repornește complet Home Assistant.
5. Deschide entitatea `Radio`; browserul media nativ trebuie să fie disponibil.

Nu este necesară rescrierea firmware-ului JN5189 dacă firmware-ul final
PIO19 RGB+lux este deja instalat. Modificarea v0.2.0 extinde numai interfața
media player din Home Assistant.
