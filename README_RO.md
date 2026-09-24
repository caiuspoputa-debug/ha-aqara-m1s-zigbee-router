# Aqara M1S Zigbee Coordinator + Router v0.30.0

Integrare locală Home Assistant pentru huburi Aqara M1S Gen 1 pregătite fie ca Router Zigbee, fie ca hub Coordinator Zigbee-on-Host LAB.

Domeniul intern rămâne `aqara_m1s_zigbee_router`, pentru ca instalările Router existente să fie actualizate fără recrearea entităților.

## Control Zigbee în funcție de rol

- Runtime Router detectat: în Configure apare **Conectare la alt coordinator Zigbee**.
- Runtime Coordinator detectat: Rejoin dispare; în Configure apare **Coordinator ON/OFF**, iar dispozitivul primește și un switch Coordinator.
- Rolul confirmat este memorat în intrarea Home Assistant, astfel încât un Coordinator rămâne protejat de comenzile RGB/lux dacă HA pornește cât hubul este temporar offline.
- Rolul nu este legat de IP: `.107` este Coordinator acum, iar toate huburile Router păstrează RGB și lux.
- Canalul și rețeaua Zigbee se aleg în Zigbee2MQTT.
- Coordinatorul folosește `serial.adapter: zoh` și `tcp://HUB_IP:1886`.

## Administrarea sunetelor

- Uploadul rămâne în `/data/musics/music-ch`, pentru compatibilitate.
- Ștergerea manuală listează toate fișierele `.wav` din `/data/musics`, inclusiv folderele cu sunete originale Aqara.
- Nimic nu este selectat implicit și este necesară confirmare explicită.
- Înainte de ștergere se creează o arhivă în `/data/m1s_sound_backups`; dacă backupul eșuează, nu se șterge nimic.
- Instalarea, pornirea și migrarea nu șterg automat niciun sunet.

## Limite Coordinator LAB

Pe Aqara M1S `.107` au fost validate scrierea și readback-ul exact, handshake-ul Spinel 4.3, formarea rețelei pe canalul 20, traficul MAC, ON/OFF și revenirea după reboot. Comenzile UART RGB/lux din Router sunt dezactivate în modul Coordinator, deoarece RCP-ul standard nu implementează acel protocol particular. Audio, radio, rețea, Telnet și butonul rămân funcții Linux.

Versiunea rămâne LAB până când asocierea unui dispozitiv Zigbee real, traficul bidirecțional și revenirea Zigbee2MQTT după restart sunt demonstrate.

Versiunea `0.30.0` pornește din integrarea `0.3.0`, bazată la rândul ei pe `0.21.13`.
