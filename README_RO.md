# Aqara M1S Zigbee Coordinator + Router v0.34.1 TEST

Integrare locală Home Assistant pentru huburi identice Aqara M1S Gen 1 / JN5189 pregătite fie ca Routere Zigbee, fie drept Coordinator Zigbee-on-Host. Rolul activ este detectat din runtime-ul hubului și salvat în intrarea Home Assistant; nu este stabilit niciodată după adresa IP.

Versiunea `0.34.1 TEST` este construită peste baza `0.34.0 RECOVERY`. Modulele confirmate pentru sunete, media player, volum, buton fizic, MQTT comun, Wi-Fi și diagnostic sunt păstrate. Acesta este un pachet de integrare, nu un kit firmware: nu scrie și nu face flash pe JN5189.

## Cerințe

- Home Assistant `2024.1.0` sau mai nou.
- Acces prin rețeaua locală de la Home Assistant la hub.
- Telnet activ pe hub; conexiunea implicită folosește portul `23`, utilizatorul `admin` și parolă goală.
- Un setup Router compatibil sau runtime-ul Coordinator cu `/data/m1s_coordinator/coordinator_io.sh` și capabilitatea `M1S_IO_V2`.
- Un broker MQTT accesibil prin adresa sa LAN pentru evenimentele butonului fizic și configurarea MQTT comună.
- Zigbee2MQTT cu adaptorul `zoh` atunci când hubul este folosit drept Coordinator.

## Instalare și actualizare

1. Copiază `custom_components/aqara_m1s_zigbee_router` în Home Assistant, sub `/config/custom_components/`.
2. Repornește Home Assistant.
3. Intră în **Setări > Dispozitive și servicii > Adaugă integrare** și selectează **Aqara M1S Zigbee Coordinator + Router**.
4. Introdu adresa IPv4 a hubului, portul Telnet, utilizatorul și parola.
5. Alege DHCP sau adresă statică atunci când fluxul de configurare solicită modul de rețea.

Domeniul intern rămâne `aqara_m1s_zigbee_router`, astfel încât o instalare existentă poate fi actualizată fără recrearea entităților. MAC-ul Wi-Fi fizic este folosit drept identitate atunci când este disponibil, iar ultimul rol Zigbee confirmat este păstrat dacă Home Assistant pornește cât hubul este temporar offline.

## Comportament Router și Coordinator

| Funcție | Rol Router | Rol Coordinator |
| --- | --- | --- |
| Transport Zigbee | Runtime-ul existent JN5189 Router | Zigbee-on-Host prin `tcp://IP_HUB:1886` |
| Ring Light | Traseul UART A5 existent | Helper sideband izolat `M1S_IO_V2` |
| Illuminance | Traseul UART A6 existent, la 15 secunde | Eșantion sideband izolat la 60 de secunde |
| Conectare la alt coordinator | Disponibilă cu confirmare explicită | Ascunsă și blocată |
| Coordinator ON/OFF | Nu se aplică | Eliminat intenționat |

Comportamentul RGB, lux și rejoin al Routerului rămâne neschimbat. RGB/lux pentru Coordinator nu revine niciodată la traseul UART al Routerului.

## Protecția Coordinatorului și RGB/lux

- Home Assistant nu poate opri Coordinatorul. Nu există switch, formular de opțiuni, serviciu sau metodă internă pentru Coordinator ON/OFF.
- O entitate veche `*_coordinator_radio`, rămasă de la o versiune anterioară, este eliminată automat din registrul de entități.
- Ring Light pentru Coordinator rulează numai după o comandă de lumină trimisă din Home Assistant.
- Illuminance pentru Coordinator execută un `lux-start`, așteaptă o secundă pentru conversie, apoi execută un `lux-get` o dată la 60 de secunde.
- Fiecare operație sideband folosește un client Telnet nou și numai `/data/m1s_coordinator/coordinator_io.sh`.
- Răspunsul helperului trebuie să fie un singur obiect JSON valid, cu versiunea de protocol `1`, capabilități `3`, un triplet RGB valid și valori ADC/lux în limite.
- Traseul sideband nu se conectează la portul `1886`, nu trimite cadrele Router A5/A6 și nu execută rutina de curățare UART a Routerului.
- Un răspuns lipsă sau invalid face indisponibile numai Ring Light și Illuminance. Conectivitatea hubului, sunetele, MQTT și Zigbee2MQTT rămân independente.
- O măsurare lux invalidă nu este publicată niciodată ca valoare zero.

Zigbee2MQTT deține conexiunea Coordinatorului. O secțiune serială tipică este:

```yaml
serial:
  port: tcp://IP_HUB:1886
  adapter: zoh
```

Canalul Zigbee, PAN-ul, cheia de rețea și baza de date cu dispozitive rămân setări Zigbee2MQTT; această integrare nu le înlocuiește.

## Entități principale

- **Ring Light**, cu culoare RGB și luminozitate.
- **Illuminance**, cu atributele `adc_raw`, `millivolts` și sursa specifică rolului.
- **Media Player** pentru streamuri și redare locală.
- **M1S Media Group** și **Include in M1S Media Group** pentru redare sincronizată pe huburile selectate.
- **Sound Playback Volume**, **Fine Volume Trim** și selecția **Sound**.
- Câte un buton pentru fiecare sunet WAV Aqara detectat.
- Evenimente **Physical Button**: click, de la dublu până la zece clickuri, început HOLD, repetare și eliberare.
- **Hub Connectivity**, **Hub Temperature**, **WiFi IP**, starea proceselor HomeKit, MQTT și Telnet.
- Diagnosticul **JN5189 Router** numai pentru huburile cu rol Router.
- Starea **MQTT configuration**: `not_configured`, `pending`, `applied` sau `failed`.

## Configurare MQTT comună

Deschide **Configurează** pe oricare hub administrat și selectează **MQTT comun - toate huburile**. Setările aparțin întregii integrări și sunt aplicate tuturor huburilor Router și Coordinator, inclusiv celor adăugate ulterior. Huburile offline se sincronizează după reconectare; scrierile eșuate sunt reîncercate după 60 de secunde.

Folosește adresa LAN a aceluiași broker folosit de Home Assistant, nu `localhost` sau un nume intern al add-onului pe care huburile nu îl pot rezolva. Funcția folosește MQTT simplu în LAN, fără TLS, și nu creează utilizatori pe broker și nu modifică integrarea MQTT din Home Assistant.

Utilizatorul și parola trebuie să conțină caractere ASCII imprimabile și pot avea împreună cel mult 80 de caractere. La o editare ulterioară, parola goală păstrează parola salvată. Integrarea validează autentificarea la broker înainte de salvare, dar permisiunile ACL trebuie să permită în continuare publicarea topicurilor hubului. Identitatea topicului butonului este păstrată atunci când se schimbă IP-ul hubului.

Starea `applied` înseamnă că configurația a fost scrisă cu succes pe hub; confirmă livrarea reală printr-o apăsare a butonului fizic. Datele de autentificare sunt păstrate în stocarea integrării Home Assistant și în backupurile hubului, deci ambele trebuie tratate confidențial.

## Administrarea sunetelor și media

- Uploadul WAV și ZIP este disponibil din **Configurează**, iar fișierele sunt salvate sub `/data/musics/music-ch`.
- Ștergerea manuală listează toate fișierele `.wav` aflate sub `/data/musics`, inclusiv folderele originale Aqara.
- Niciun fișier nu este selectat implicit.
- Controlul de confirmare este afișat deasupra listei și trebuie activat explicit.
- Înainte de ștergere se creează obligatoriu o arhivă sub `/data/m1s_sound_backups`; dacă backupul eșuează, ștergerea este anulată.
- Instalarea, pornirea și migrarea nu șterg automat niciun sunet.
- După un upload sau o ștergere reușită, integrarea se reîncarcă și reconstruiește entitățile sunetelor.

Media Player individual și grupul comun M1S Media Group, controalele de volum, radioul, actualizarea metadatelor și butoanele existente pentru sunetele Aqara sunt păstrate din baza confirmată.

## Administrarea rețelei

Fluxul de configurare acceptă DHCP, adresă IPv4 statică în subnetul curent și schimbarea rețelei Wi-Fi prin modulul recovery instalat. Înainte de schimbarea Wi-Fi, hubul revine la DHCP și testează noua rețea. Parola Wi-Fi nu este salvată în Home Assistant. Schimbarea rețelei poate face temporar hubul indisponibil; folosește noua lui adresă după reconectare.

## Servicii disponibile

Integrarea înregistrează serviciile `play_url`, `play_sound`, `upload_sound`, `delete_sound`, `refresh_sounds`, `reset_media_group`, `resync_media_group` și `update_media_metadata`. Păstrează și serviciul avansat `run_command`; folosește-l numai pentru comenzi pe care le înțelegi, deoarece execută o comandă shell pe hubul selectat prin Telnet.

`delete_sound` necesită `confirm: true` și verifică întotdeauna ordinea backup înainte de ștergere. Dacă sunt configurate mai multe huburi, indică parametrul `host` pentru serviciile de sunet adresate unui hub anume.

## Validare și statut TEST

Sursa `0.34.1` a trecut:

- 8 teste izolate pentru RGB/lux Coordinator și siguranța transportului.
- 5 teste pentru ștergerea WAV și backupul obligatoriu.
- 7 teste pentru persistența și revenirea configurării MQTT comune.
- Compilarea Python și parsarea fișierelor JSON/YAML.
- Comparația byte-cu-byte a modulelor confirmate pentru sunete, media, buton și MQTT cu `0.34.0 RECOVERY`.

La construirea acestui pachet de integrare nu a fost contactat niciun hub live și nu a fost scris firmware. Înainte de promovarea din TEST, confirmă pe hardware Coordinator că Zigbee2MQTT rămâne conectat, Ring Light ON/OFF și culorile funcționează, luxul urmărește schimbările reale de lumină la intervalul de 60 de secunde, sunetele și butonul fizic continuă să funcționeze, iar sistemul revine după restartarea Home Assistant și Zigbee2MQTT.

## Revenire

Dacă entitățile sideband ale Coordinatorului nu funcționează corect, înlocuiește integrarea custom cu `0.34.0 RECOVERY` și repornește Home Assistant. Acea versiune păstrează Coordinatorul permanent protejat și lasă RGB/lux indisponibile. Înlocuirea integrării nu modifică firmware-ul, datele rețelei Zigbee sau fișierele audio.
