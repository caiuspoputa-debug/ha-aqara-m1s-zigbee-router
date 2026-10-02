# Aqara M1S Zigbee Coordinator + Router v0.36.2 TEST

Integrare locală Home Assistant pentru huburi identice Aqara M1S Gen 1 / JN5189 pregătite fie ca Routere Zigbee, fie drept Coordinator Zigbee-on-Host. Rolul activ este detectat din runtime-ul hubului și salvat în intrarea Home Assistant; nu este stabilit niciodată după adresa IP.

Versiunea `0.36.2 TEST` este construită peste baza `0.36.1 TEST`. Agentul MQTT persistent rămâne folosit pentru Ring Light, iluminanță și telemetria de diagnostic pe ambele roluri. Pe Router, agentul deține serializat UART-ul JN5189 și înlocuiește sesiunile Telnet A5/A6 numai după activarea explicită a upgrade-ului. Butonul fizic își păstrează topicul existent. Radioul, play/stop/pause, volumul, grupul media comun, sincronizarea și transportul audio TCP/FFmpeg/aplay sunt neschimbate. `0.36.2` rezervă `/data/musics/music-us` sunetelor de sistem pentru factory reset și schimbă ștergerea confirmată a celorlalte WAV-uri într-o operație directă, fără arhive backup. Acesta este un pachet de integrare, nu un kit firmware: nu scrie și nu face flash pe JN5189.

## Cerințe

- Home Assistant `2024.1.0` sau mai nou.
- Acces prin rețeaua locală de la Home Assistant la hub.
- Telnet activ pe hub; conexiunea implicită folosește portul `23`, utilizatorul `admin` și parolă goală.
- Un setup Router compatibil; pentru traseul rapid MQTT este necesar upgrade-ul Router MQTT IO `1.0.0`. Routerele fără upgrade păstrează automat A5/A6 prin traseul vechi.
- Kitul Coordinator MQTT complet `1.2.0` sau un runtime compatibil cu sideband `M1S_IO_V2`.
- Un broker MQTT accesibil prin adresa sa LAN pentru butonul fizic, configurarea MQTT comună și IO-ul ambelor roluri.
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
| Ring Light | MQTT persistent către A5; fallback vechi numai înainte de activarea upgrade-ului | Comandă MQTT către agentul persistent, apoi sideband izolat `M1S_IO_V2` |
| Illuminance | Stare MQTT retained; A6 serializat pe hub la 30 de secunde | Stare MQTT retained; eșantion pe hub la 60 de secunde |
| Conectare la alt coordinator | Disponibilă cu confirmare explicită | Ascunsă și blocată |
| Coordinator ON/OFF | Nu se aplică | Eliminat intenționat |

Acțiunea Routerului de conectare la alt coordinator rămâne explicită. Integrarea oprește temporar agentul, execută cadrul A7 printr-o fereastră UART limitată, apoi repornește agentul. Fereastra se închide automat după 90 de secunde dacă Home Assistant se deconectează. RGB/lux pentru Coordinator nu revine niciodată la traseul UART al Routerului.

## Protecția Routerului și traseul MQTT

- Topicurile sunt construite din IP-ul actual al hubului: de exemplu, Routerul `192.168.0.221` folosește `m1s/221/io/...`, indiferent de numele sau ID-ul istoric al entității.
- Agentul Router se abonează numai la `io/rgb/set` și `io/lux/refresh`; publică starea IO, disponibilitatea și telemetria.
- Luxul este citit la 30 de secunde. O citire A6 fără checksum valid nu devine `0 lx`, ci rămâne invalidă.
- După activare există un singur proprietar pentru `/dev/ttyS1`. Tunelul temporar TCP `1886` folosit anterior pentru A5/A6 este oprit și nu poate porni peste agent.
- Un mesaj retained cu rol `coordinator` este ignorat de un Router și invers.
- Dacă agentul este configurat dar indisponibil, numai Ring Light, luxul și diagnosticele MQTT devin indisponibile; integrarea nu încearcă automat UART-ul vechi peste agent.
- Disponibilitatea generală a Routerului continuă să folosească verificarea LAN ușoară existentă. Astfel o problemă a brokerului MQTT nu scoate automat playerul din grup și nu schimbă sincronizarea audio.
- Comenzile radio, WAV, play, stop, pause, volum și fluxul PCM nu există în agentul Router.

## Protecția Coordinatorului și RGB/lux

- Home Assistant nu poate opri Coordinatorul. Nu există switch, formular de opțiuni, serviciu sau metodă internă pentru Coordinator ON/OFF.
- O entitate veche `*_coordinator_radio`, rămasă de la o versiune anterioară, este eliminată automat din registrul de entități.
- Ring Light pentru Coordinator rulează numai după o comandă de lumină trimisă din Home Assistant.
- Agentul persistent serializează operațiile Ring Light și iluminanță prin `/tmp/m1s-coordinator-io.sock`; Home Assistant nu mai deschide comenzi Telnet sideband.
- Illuminance pentru Coordinator este măsurată pe hub o dată la 60 de secunde și publicată retained prin MQTT. Home Assistant poate cere o actualizare imediată tot prin MQTT.
- Topicurile folosesc identitatea adresei actuale a Coordinatorului (`m1s/220/...` pentru `192.168.0.220`), nu sufixul istoric păstrat în unele ID-uri vechi de entități.
- Răspunsul helperului trebuie să fie un singur obiect JSON valid, cu versiunea de protocol `1`, capabilități `3`, un triplet RGB valid și valori ADC/lux în limite.
- Traseul sideband nu se conectează la portul `1886`, nu trimite cadrele Router A5/A6 și nu execută rutina de curățare UART a Routerului.
- Un răspuns lipsă sau invalid face indisponibile numai funcțiile MQTT IO. Agentul nu poate executa Coordinator OFF și nu poate înlocui proprietarul ZOH al portului `1886`.
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
- Câte un buton pentru fiecare sunet WAV detectat care nu este sunet de sistem.
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
- Înainte de scrierea primului fișier, întregul lot WAV/ZIP este verificat în raport cu spațiul din `/data`. Fișierele destinație existente sunt calculate ca înlocuiri, iar lotul este refuzat integral dacă ar lăsa mai puțin de 8 MiB liberi. Aceeași rezervă se aplică serviciului direct `upload_sound`.
- `/data/musics/music-us` este rezervat sunetelor de sistem pentru factory reset. WAV-urile sale și fișierele din subfoldere nu sunt expuse ca butoane în Home Assistant și nu apar niciodată în lista de ștergere.
- Ștergerea manuală listează WAV-urile care nu sunt de sistem de sub `/data/musics`, inclusiv celelalte foldere originale Aqara.
- Niciun fișier nu este selectat implicit.
- După alegerea fișierelor și apăsarea butonului **Șterge**, apare un popup scurt separat, cu numărul fișierelor și controlul explicit de confirmare; acesta rămâne complet vizibil și nu se derulează împreună cu lista.
- Selecția este transmisă hubului printr-un manifest temporar împărțit în bucăți mici, astfel încât listele mari să nu depășească limita unei comenzi Telnet.
- Ștergerea confirmată este definitivă și nu creează arhivă backup. Întregul manifest este validat înainte, comanda de pe hub blochează independent `music-us`, iar succesul este acceptat numai când numărul șters corespunde selecției.
- Instalarea, pornirea și migrarea nu șterg automat niciun sunet.
- După un upload sau o ștergere reușită, integrarea se reîncarcă și reconstruiește entitățile sunetelor.

Pentru un WAV local se păstrează exact prioritatea confirmată: redarea individuală sau de grup este suspendată, WAV-ul rulează prin traseul existent TCP/FFmpeg/aplay, apoi redarea memorată este reluată. Pe Coordinator, MQTT înlocuiește numai comanda care pregătește sau oprește traseul dedicat WAV. Pe Router, tot traseul WAV rămâne pe implementarea existentă. MQTT nu transportă audio radio/grup și nu modifică sincronizarea.

Protecția existentă la lipsa datelor rămâne neschimbată. Dacă o sursă individuală nu mai livrează PCM, receiverul hubului este oprit înainte de rebuffer și este reconstruit numai după revenirea datelor PCM reale. La o întrerupere temporară a sursei de grup, PCM zero continuă pe aceeași secvență comună. Versiunea `0.36.2` nu modifică ordinea PLAY, sincronizarea grupului, bufferele, FFmpeg/aplay, volumul sau timpii de recovery.

După ce FFmpeg termină normal un WAV, integrarea păstrează traseul încă 500 ms înainte de comanda de oprire și de reluarea redării anterioare. Această rezervă era 400 ms în `0.36.0`; nu se aplică la Stop manual, eroare FFmpeg, radio sau grupul media.

Media Player individual și grupul comun M1S Media Group, controalele de volum, radioul, actualizarea metadatelor și butoanele existente pentru sunetele Aqara sunt păstrate din baza confirmată.

## Administrarea rețelei

Fluxul de configurare acceptă DHCP, adresă IPv4 statică în subnetul curent și schimbarea rețelei Wi-Fi prin modulul recovery instalat. Înainte de schimbarea Wi-Fi, hubul revine la DHCP și testează noua rețea. Parola Wi-Fi nu este salvată în Home Assistant. Schimbarea rețelei poate face temporar hubul indisponibil; folosește noua lui adresă după reconectare.

## Servicii disponibile

Integrarea înregistrează serviciile `play_url`, `play_sound`, `upload_sound`, `delete_sound`, `refresh_sounds`, `reset_media_group`, `resync_media_group` și `update_media_metadata`. Păstrează și serviciul avansat `run_command`; folosește-l numai pentru comenzi pe care le înțelegi, deoarece execută o comandă shell pe hubul selectat prin Telnet.

`delete_sound` necesită `confirm: true`, refuză orice cale de sub `/data/musics/music-us` și șterge celelalte căi WAV valide fără să creeze backup. Dacă sunt configurate mai multe huburi, indică parametrul `host` pentru serviciile de sunet adresate unui hub anume.

## Validare și statut TEST

Sursa `0.36.2` a trecut:

- 14 teste izolate pentru MQTT RGB/lux, telemetrie, roluri, topicuri, izolarea UART și rejoin Router.
- 1 test dedicat priorității, cu ordinea `suspendare -> WAV -> rezervă 500 ms -> oprire WAV -> reluare`.
- 9 teste pentru ștergerea directă WAV, protecția folderului de sistem și manifestul fragmentat.
- 5 teste pentru verificarea integrală a spațiului înainte de upload, calcularea înlocuirilor și protecția căilor de sistem.
- 7 teste pentru persistența și revenirea configurării MQTT comune.
- Compilarea Python și parsarea fișierelor JSON/YAML.
- Verificarea de sintaxă a tuturor scripturilor Router și compilarea agentului static MIPS32 cu avertismente tratate ca erori.
- Toate cele 36 de teste izolate trec. `media_player.py`, `media_group.py`, `sound_player.py` și `shared_mqtt.py` sunt neschimbate față de `0.36.1`; `0.36.2` modifică vizibilitatea catalogului, siguranța ștergerii, protecția spațiului la upload, documentația și testele aferente.

Traseul de ștergere multiplă din `0.36.1` a fost verificat hardware pe Coordinatorul `192.168.0.220` cu 12 fișiere temporare. Ștergerea directă și protecția `music-us` din `0.36.2` sunt acoperite de teste izolate și instalarea nu modifică automat niciun hub.

Agentul Coordinatorului a fost testat hardware pe `192.168.0.220`: RGB ON/OFF, lux, telemetrie retained și o singură conexiune Z2M stabilită pe portul `1886` au fost confirmate. Routerul `192.168.0.221` a fost inspectat read-only și corespunde exact bazei `0.10.0`; agentul Router nou nu a fost încă activat pe hardware. Nu s-a scris firmware și nu s-a modificat `.221`, de aceea versiunea rămâne `TEST`.

## Revenire

Dacă MQTT IO pentru Router nu funcționează corect, rulează rollbackul din kitul Router, restaurează integrarea `0.35.0` și repornește Home Assistant. Pentru Coordinator rămâne rollbackul kitului Coordinator. Înlocuirea integrării nu modifică firmware-ul, datele rețelei Zigbee sau fișierele audio.
