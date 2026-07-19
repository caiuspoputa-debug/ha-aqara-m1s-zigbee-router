# Aqara M1S Zigbee Router

**Română** | [English](README.md)

Integrare custom Home Assistant pentru un hub Aqara M1S Gen 1 convertit în
NXP JN5189 BDB Zigbee Router, cu inel RGB, iluminare, audio și diagnosticare
locală a hubului.

Versiune curentă: **0.2.4 (test release)**

> Proiectul este destinat modelului Aqara M1S Gen 1 `lumi.gateway.aeu01`.
> Scrierea JN5189 este o operație avansată. Păstrează un backup verificat și nu
> scrie niciodată EFUSE, ROM, Config sau PSECT.


## Ce s-a schimbat în v0.2.4

- etichete bilingve în meniul Configure, cu româna afișată prima
- actualizarea imediată a catalogului de sunete după încărcarea sau ștergerea unui WAV
- reîncărcarea completă și controlată a integrării prin
  **Finalizare și închidere / Finish and close**
- documentație mai clară pentru upload, ștergere, download și reîncărcarea finală
- butonul **X** aparține interfeței Home Assistant; folosirea lui sare numai peste
  reîncărcarea finală a intrării de configurare, nu și peste actualizarea imediată
  a catalogului de sunete

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
- mutarea confirmată a routerului la un alt coordonator Zigbee

Când hubul este offline, lumina, media playerul, volumul și senzorii live devin
indisponibili. Butoanele sunetelor rămân intenționat vizibile. Uploadul și
ștergerea actualizează numai catalogul de sunete; nu reîncarcă integrarea și nu
resetează celelalte entități.

## Firmware RGB + lux + rejoin curent

Imaginea de test compatibilă cu v0.2.1 folosește **PIO19/ADC5** pentru lumină
ambientală și adaugă comanda UART protejată pentru rejoin:

```text
Fișier: jn5189_router_rgb_lux_rejoin_test.bin
Dimensiune: 209296 bytes (0x33190)
Zona imaginii rotunjită la sector: 0x33200
Memorie: ID 0 / FLASH
```

Imaginea a fost scrisă cu succes la 19 iulie 2026, iar routerul a revenit online
în Zigbee2MQTT fără ștergerea completă a memoriei. Înainte de publicarea unui
fișier binar trebuie calculat și notat SHA256; două builduri cu nume asemănător
nu trebuie presupuse identice.

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

### 4. Backup și programarea JN5189

Instalează SPSDK în Windows:

```powershell
python --version
python -m pip install "spsdk[dk6]"
python -m spsdk.apps.dk6prog --help
```

Transportul validat folosește pyserial `socket://` prin BusyBox `nc`. Procedura
de mai jos folosește temporar portul TCP `1888`. Portul trebuie să rămână doar
în LAN și trebuie închis imediat după programare.

#### 4.1 Pregătirea hubului și intrarea în ISP

Rulează în Telnet pe hub. Blocul oprește procesul Zigbee stock, pune GPIO33 pe
nivelul ISP, resetează JN5189 și pornește un listener direct TCP–UART care se
repornește după fiecare conexiune. Nu folosește FIFO și nici proces `cat`.

```sh
PORT=1888
LOOP_PID_FILE=/var/tmp/jn1888_loop.pid
LOOP_LOG=/var/tmp/jn1888_loop.log

if [ -f "$LOOP_PID_FILE" ]; then
    OLD_LOOP=$(cat "$LOOP_PID_FILE" 2>/dev/null)
    [ -n "$OLD_LOOP" ] && kill -9 "$OLD_LOOP" 2>/dev/null
    rm -f "$LOOP_PID_FILE"
fi

for p in $(ps w | grep "[n]c -l -p $PORT" | awk '{print $1}'); do
    kill -9 "$p" 2>/dev/null
done

for p in $(ps w | grep '[a]pp_monitor' | awk '{print $1}'); do
    kill -STOP "$p" 2>/dev/null
done
for p in $(ps w | grep '[m]zigbee_agent' | awk '{print $1}'); do
    kill -9 "$p" 2>/dev/null
done

stty 115200 cs8 -parenb -cstopb cread clocal -crtscts \
  -ignbrk -brkint -ignpar -parmrk -inpck -istrip \
  -ixon -ixoff -icanon -echo min 1 time 0 < /dev/ttyS1

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

Confirmarea importantă este linia `LISTEN` pentru portul `1888`. O sesiune
`nc` se închide după fiecare comandă SPSDK, iar bucla pornește listenerul
următor. Verifică `netstat` înaintea fiecărei comenzi SPSDK.

#### 4.2 Verificarea comunicației

În PowerShell:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://IP_HUB:1888" -n info
```

Rezultatul trebuie să includă:

```text
Detected DEVICE: JN5189
FLASH  Memory ID 0  Base 0x0  Length 0x9DE00  Sector 0x200
```

După `info`, revino în Telnet și verifică dacă bucla a recreat listenerul:

```sh
netstat -lnt | grep 1888
```

#### 4.3 Backup pentru un hub stock

Înaintea primei conversii, citește Memory ID 0 și păstrează backupul în două
locuri sigure:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://IP_HUB:1888" -n read -o ".\jn5189_original_flash.bin" 0x0 646656 0
Get-FileHash ".\jn5189_original_flash.bin" -Algorithm SHA256
```

Verifică din nou `LISTEN` înaintea oricărei alte comenzi SPSDK.

### 5. Scrierea sau actualizarea firmware-ului

Verifică fișierul exact ales pentru flash:

```powershell
Get-Item ".\jn5189_router_rgb_lux_rejoin_test.bin"
Get-FileHash ".\jn5189_router_rgb_lux_rejoin_test.bin" -Algorithm SHA256
```

Pentru actualizarea unui firmware Router deja funcțional, scrie direct la
adresa `0x0`, **fără erase complet**. Aceasta este procedura reușită la
19 iulie 2026 și a păstrat asocierea Zigbee existentă:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://IP_HUB:1888" -n write 0x0 ".\jn5189_router_rgb_lux_rejoin_test.bin"
```

Confirmarea reușită pentru acest build este:

```text
Written 209296 bytes to memory ID 0 at address 0x0
```

La prima conversie sau la recuperare, când ștergerea zonei imaginii este cu
adevărat necesară, șterge numai zona aplicației rotunjită la sector, niciodată
întregul cip:

```powershell
python -m spsdk.apps.dk6prog -b PYSERIAL -d "socket://IP_HUB:1888" -n erase 0x0 0x33200 0
```

Confirmă din nou `LISTEN`, apoi execută `write`. Nu scrie niciodată în EFUSE,
ROM, Config, PSECT sau pFLASH.

#### 5.1 Închiderea listenerului temporar

După ultima comandă SPSDK, rulează în Telnet:

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

Ultima comandă nu trebuie să afișeze nimic.

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

### Protocolul de rejoin și locul butonului (firmware compatibil v0.2.1)

Activează mai întâi **Permit join** pe coordonatorul destinație.

Acțiunea de rejoin nu este o entitate pe pagina dispozitivului. Se găsește aici:

**Setări > Dispozitive și servicii > Aqara M1S Zigbee Router > Configure > Conectare la alt coordonator Zigbee**

Citește avertismentul și confirmă. Integrarea trimite comanda numai după pasul
de confirmare.


Integrarea trimite această cerere distinctă de cinci bytes:

```text
Cerere:    A7 52 4A 4E F1
Confirmare: A7 4F 4B 00 A3
```

Payloadul `52 4A 4E` reprezintă `RJN`. După trimiterea confirmării, JN5189
șterge numai contextul persistent al rețelei Zigbee și se repornește. Calea BDB
existentă pornește automat Network Steering la boot. Linux, setările Wi-Fi,
RGB/lux și fișierele din `/data/musics` nu sunt șterse.

Firmware-ul fizic validat anterior `jn5189_router_rgb_lux_pio19.bin` nu
implementează `A7`. Acțiunea din Configurare eșuează astfel în siguranță, fără
să modifice nimic, până la instalarea unui build de firmware compatibil.

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

## Entități în v0.2.4

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

Sesiunea de administrare folosește etichete bilingve, cu româna prima:

- **Încărcare sunet WAV / Upload WAV sound**
- **Ștergere sunet WAV / Delete WAV sound**
- **Conectare la alt coordonator Zigbee / Join a different Zigbee coordinator**
  (acțiune separată cu confirmare)
- **Finalizare și închidere / Finish and close**

### Încărcarea unui fișier WAV

1. Deschide **Configure** și selectează
   **Încărcare sunet WAV / Upload WAV sound**.
2. Selectează fișierul WAV sau trage-l în câmpul de încărcare.
3. Așteaptă mesajul de succes. Fișierul încărcat corect este copiat în:

   ```text
   /data/musics/music-ch
   ```

4. Repetă operația pentru celelalte fișiere. Fereastra de administrare rămâne
   deschisă după fiecare încărcare.
5. După terminarea tuturor operațiilor, revino în meniul de administrare și apasă
   **Finalizare și închidere / Finish and close**.

Operația de upload actualizează imediat catalogul de sunete. Pentru reîncărcarea
completă a intrării de configurare, apasă
**Finalizare și închidere / Finish and close**. Versiunea 0.2.4 reconstruiește
apoi celelalte entități și actualizează informațiile dispozitivului.

Butonul **X** aparține interfeței Home Assistant și nu poate fi eliminat de o
integrare custom. Închiderea cu **X** sare peste reîncărcarea finală a intrării
de configurare, dar nu mai lasă catalogul de sunete neactualizat după upload sau
ștergere.

Format acceptat:

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

Uploadul folosește un transfer LAN verificat pe portul TCP `12349`. Integrarea
verifică dimensiunea și integritatea fișierului transferat înainte de mutarea
fișierului temporar în directorul protejat. BusyBox `base64` rămâne disponibil
ca metodă de rezervă.

### Ștergerea unui fișier WAV

1. Deschide **Configure** și selectează
   **Ștergere sunet WAV / Delete WAV sound**.
2. Selectează fișierul personalizat care trebuie eliminat.
3. Confirmă ștergerea.
4. Repetă pentru celelalte fișiere, dacă este necesar.
5. Apasă **Finalizare și închidere / Finish and close**, pentru ca versiunea 0.2.4
   să facă reîncărcarea completă a integrării și să actualizeze toate informațiile
   asociate dispozitivului.

Pot fi administrate numai fișierele aflate direct în directorul protejat:

```text
/data/musics/music-ch
```

Sunetele Aqara originale din directoare precum `/data/musics/music-scene` nu
sunt oferite pentru ștergere de integrare.

### Descărcarea unui WAV existent de pe hub

Fereastra de administrare Home Assistant poate încărca și șterge fișiere, dar
nu oferă momentan un buton de descărcare în browser. Pentru copierea unui WAV
existent de pe hub, folosește un transfer TCP temporar, numai în rețeaua locală.

Pe hub, găsește fișierul și pornește un listener pentru o singură conexiune:

```sh
find /data/musics -type f -name '*.wav'
nc -l -p 1889 < /data/musics/music-scene/disarm.wav
```

Apoi rulează în Windows PowerShell, schimbând numele fișierului când este cazul:

```powershell
$client = New-Object System.Net.Sockets.TcpClient
$client.Connect("IP_HUB", 1889)
$stream = $client.GetStream()
$file = [System.IO.File]::Create("$env:USERPROFILE\Downloads\disarm.wav")
$stream.CopyTo($file)
$file.Close()
$stream.Close()
$client.Close()
Get-Item "$env:USERPROFILE\Downloads\disarm.wav"
```

Listenerul `nc` de pe hub se închide automat după transfer. Păstrează portul
`1889` numai în LAN și nu îl expune prin port forwarding.

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
După ce hubul devine accesibil, integrarea așteaptă **10 secunde** și trimite
o singură comandă RGB OFF. Întârzierea permite stabilizarea Wi-Fi, Telnet și
UART-ului JN5189 înainte de stingerea roșului slab de boot. Ultima culoare și
luminozitate selectate în Home Assistant rămân memorate pentru următoarea
pornire manuală.

## Securitate și recuperare

- Păstrează Telnet și porturile `1886`, `12346` și `12349` numai în LAN.
- Nu le expune prin port forwarding.
- Nu publica tokenul MiIO sau datele Telnet.
- Păstrează backupul flash original JN5189 și hash-ul său SHA256.
- Nu scrie niciodată EFUSE, ROM, Config sau PSECT.
- Pentru recuperare, intră în ISP cu GPIO33=`0`, verifică `info`, scrie
  backupul original validat în Memory ID 0, citește-l înapoi, compară SHA256,
  apoi pornește cu GPIO33=`1` și GPIO18=`0`.

## Actualizare de la v0.2.0

1. Compilează și validează fizic sursa JN5189 furnizată cu protocolul `A7`.
2. Scrie numai imaginea compatibilă verificată și testează RGB, lux și Zigbee.
3. Actualizează fișierele repository-ului și manifestul la `0.2.1`.
4. Creează/publică tagul `v0.2.1`.
5. Actualizează prin HACS și repornește complet Home Assistant.
6. Activează Permit join pe coordonatorul destinație.
7. Deschide **Configurare** la integrare, alege **Conectare la alt coordonator
   Zigbee**, citește avertizarea și confirmă.

Vechiul coordonator poate păstra o intrare învechită, care poate fi ștearsă după
apariția routerului în noul coordonator. Acțiunea nu șterge Linux, Wi-Fi,
RGB/lux sau fișierele audio.
