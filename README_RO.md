# Aqara M1S Zigbee Coordinator + Router v0.37.21

Corecteaza oprirea receiverului la o lipsa scurta de PCM in fluxurile continue
YouTube Cast. In 0.37.20, logul `single rebuffer started ... action=stop_receiver`
insemna ca integrarea golea lotul PCM si oprea receiverul de pe hub, inclusiv
finalul piesei care era deja in curs de redare.

Pentru fluxurile Cast continue `/stream/<receiver>/<serial>.wav`, integrarea
trimite acum si ultimul lot partial, pastreaza acelasi receiver si asteapta
datele urmatoare in limita existenta de 5 secunde. Nu insereaza audio suplimentar
si nu reporneste transportul pentru aceasta lipsa temporara de date.

Dimensiunile bufferelor, prebufferul, prefilling-ul initial, formatul PCM,
batching-ul obisnuit, ceasul de redare si sincronizarea grupului sunt pastrate.
Stop explicit si defectele reale de transport pastreaza recuperarea existenta.
Comportamentul pentru radio si alte surse ramane acelasi.

Se instaleaza integrarea **0.37.21**, apoi se reporneste Home Assistant.
Add-on-ul **1.0.30** contine separat corectia selectiei manuale a piesei.
Detalii: [CAST_CONTINUOUS_TAIL_RO.md](CAST_CONTINUOUS_TAIL_RO.md).
Testele locale nu reprezinta o verificare acustica pe huburile utilizatorului.

## Istoric 0.37.20 — MQTT Router dupa schimbarea IP-ului

Versiunea **0.37.20 TEST** corecteaza topicul MQTT ramas pe vechiul IP dupa
schimbarea adresei hubului Router. Reincarcarea automata de dupa confirmarea
IP-ului, o reincarcare manuala sau reconectarea hubului verifica acum agentul.
Daca agentul este deja activat pe `TOPIC_ID=AUTO`, dar configuratia runtime nu
corespunde adresei curente, integrarea reporneste numai agentul MQTT si cere
confirmarea unei publicari noi. Nu reporneste hubul sau Home Assistant.

Verificarea este idempotenta, ruleaza in fundal si reincearca limitat dupa o
eroare. Nu modifica brokerul, parola, identitatea stabila a butonului, audio
sau firmware-ul. Nu activeaza agenti dezactivati si nu atinge coordonatoarele
dedicate. Detalii si limite: [MQTT_IP_RECOVERY_RO.md](MQTT_IP_RECOVERY_RO.md).

Arhiva are aceeasi structura ca versiunea primita: continutul se poate pune in
radacina repository-ului GitHub; componenta Home Assistant este in
`custom_components/aqara_m1s_zigbee_router`. Nu este un kit de firmware M1S.
Nu s-a publicat nimic pe GitHub si nu s-a instalat acest build pe dispozitive.

## Compatibilitate cu registrul pastrata din 0.37.19

Versiunea **0.37.19 TEST** actualizează accesul la registrul dispozitivelor
pentru avertismentele de API depreciat raportate pe Home Assistant **2026.10.2**.
Cele patru căutări după identificator folosesc
`async_get_device_by_identifier(identifier, entry.entry_id)` când este disponibil;
pe HA vechi căutarea rămâne limitată la aceeași intrare de configurare.
Proprietarul pentru trigger-ele dispozitivului este rezolvat prin helperul
actual al domeniului, fără citirea `DeviceEntry.config_entries` pe HA nou.

Identificatorii dispozitivelor, ID-urile unice ale entităților și migrarea
existentă de la IP la identitatea stabilă sunt păstrate. Codul audio rămâne
identic octet cu octet cu **0.37.18**, iar supravegherea Coordinator/Zigbee2MQTT
rămâne neschimbată din **0.37.17**. Detalii, surse oficiale și termenele distincte:
[DEVICE_REGISTRY_COMPAT_RO.md](DEVICE_REGISTRY_COMPAT_RO.md).
Acest build nu a fost instalat și nu a repornit Home Assistant; rezultatele
locale finale sunt identificate în `VALIDATION.txt`.

## Comportament audio păstrat din 0.37.18

Versiunea **0.37.18 TEST** separă alertele prioritare de mute pentru media.
WAV-urile stocate, butoanele de sunet și WAV-urile prioritare prin `play_url`
ocolesc implicit mute individual și mute de grup, fără să schimbe starea mute
a vreunui player. `respect_mute: true` păstrează, pentru apelul respectiv,
comportamentul anterior față de mute individual al hubului; mute de grup
continuă să se aplice doar muzicii de grup.

`volume_percent` stabilește opțional volumul temporar al alertei. Dacă lipsește,
se folosește valoarea curentă a sliderului individual al hubului înainte de mute;
un slider la 0% înseamnă în continuare liniște. Volumul media curent este
confirmat înainte de reluare/reintrare în grup. Schimbările manuale de volum și
mute din timpul alertei rămân valabile după ea. Nu este necesară o secvență YAML
de unmute/remute și nu se salvează schimbări artificiale de mute.
Detalii: [SOUND_MUTE_POLICY_RO.md](SOUND_MUTE_POLICY_RO.md) și
[NOTIFICATION_VOLUME_RO.md](NOTIFICATION_VOLUME_RO.md).

Supravegherea opțională Coordinator/Zigbee2MQTT din **0.37.17** este păstrată
fără modificări; vezi [COORDINATOR_GUARD_RO.md](COORDINATOR_GUARD_RO.md).
Pachetul TEST nu a fost instalat pe Home Assistant și nu este validat pe hardware.

## Versiuni istorice

`0.37.17 TEST` a introdus supravegherea opțională Coordinator/Zigbee2MQTT:
stop confirmat la pierderea coordonatorului, reinițializare RCP și verificare
Spinel/PHY cu Z2M oprit, apoi pornire condiționată și confirmare MQTT nouă.
Rămâne dezactivată până alegi exact suplimentul și topicul MQTT pe intrarea
Coordinator. Notele mai vechi de mai jos descriu versiunile respective;
politica audio 0.37.18 de mai sus are prioritate în acest pachet.

In `0.37.16 TEST`, cererea soneriei include volumul temporar: muzica cedeaza,
hubul confirma ALSA inchis, se aplica volumul WAV-ului, iar volumul normal
revine inainte de reluarea muzicii. Foloseste `play_sound.volume_percent`,
nu `number.set_value` inainte de sonerie. API-ul serviciului este descris in
`NOTIFICATION_VOLUME_RO.md`.
Reglajul separat Fine Volume Trim este eliminat, inclusiv offsetul vechi.
ID-urile volumului principal, precizia 0.01%, mute, ceasul comun de 35 ms
si blocurile de 105 ms raman neschimbate.

In `0.37.15 TEST`, WAV-ul este cerut explicit o singura data, corectand
repetarea implicita de trei ori din Aplay-ul hubului. Huburile libere sar
peste opririle inutile si pauza fixa; cele cu player activ sau pornire in
curs pastreaza predarea sigura. Conexiunea Telnet audio este reutilizata,
fara repetarea automata a unei comenzi de pornire cu rezultat necunoscut.
Volumul local ramane confirmat inainte de fiecare WAV. Citeste
`WAV_FAST_START_RO.md`; descrierea audio de mai jos este baza 0.37.14 pastrata.
Acest build nu a instalat sau repornit HA.

Integrare locală Home Assistant pentru huburi identice Aqara M1S Gen 1 / JN5189 pregătite fie ca Routere Zigbee, fie drept Coordinator Zigbee-on-Host. Rolul activ este detectat din runtime-ul hubului și salvat în intrarea Home Assistant; nu este stabilit niciodată după adresa IP.

Versiunea `0.37.14 TEST` reda WAV-urile direct de pe Router si aplica acelasi volum ALSA local pentru WAV, radio/media individual si receiverele grupului. WAV-ul nu mai trece prin Home Assistant sau FFmpeg. Pentru radio/media, FFmpeg ramane decodorul, nu reglajul de volum. Citeste `LOCAL_AUDIO_RO.md` pentru migrare, cerinte si verificarea live ramasa.

Ceasul comun de 35 ms, blocurile de 105 ms, istoria PCM, preumplerea, bufferele, corectia Stop si regulile de prioritate sunt pastrate. Comenzile receiverelor selecteaza acum ruta ALSA cu volum local. Pachetul este un prototip: integrarea completa si sincronizarea acustica de grup nu sunt inca verificate live. Acest build nu a instalat nimic pe HA. Dupa instalare este necesara repornirea Home Assistant.

## Cerințe

- Home Assistant `2024.1.0` sau mai nou.
- Acces prin rețeaua locală de la Home Assistant la hub.
- Telnet activ pe hub; conexiunea implicită folosește portul `23`, utilizatorul `admin` și parolă goală.
- Router MIPS32 little-endian compatibil, cu `aplay`, ALSA `plug`/`softvol`, `/dev/snd/controlC0`, `base64`, `sha256sum` si cel putin 8 MiB liberi pe `/data` dupa instalarea utilitarelor audio. Transferul initial dureaza mai mult; apoi redarea WAV trimite numai comenzi. Daca reglajul local esueaza, nu se porneste automat o ruta fara atenuare.
- Un coordonator deja convertit, cu managerii existenți pentru IP static/Wi-Fi; este recomandat profilul Only Coordinator `1.0.0`. Integrarea nu instalează profilul și nu schimbă serviciile de pe hub.
- Un broker MQTT accesibil prin adresa sa LAN pentru butonul fizic, configurarea comună și IO-ul routerelor. Agentul MQTT auxiliar al coordonatorului nu este folosit.
- Zigbee2MQTT cu adaptorul `zoh` atunci când hubul este folosit drept Coordinator.

## Instalare și actualizare

1. Fă backup componentei de integrare instalate. Dezarhivează
   pachetul și copiază folderul `custom_components/aqara_m1s_zigbee_router` în
   `/config/custom_components/aqara_m1s_zigbee_router`, înlocuind fișierele vechi.
   Nu crea încă un folder `custom_components` în interiorul celui existent.
2. Repornește Home Assistant pentru încărcarea **0.37.19**. Reîncărcarea YAML
   singură nu încarcă noul cod al integrării.
3. Verifică dacă `manifest.json` al componentei instalate indică `0.37.19` și
   dacă Home Assistant încarcă integrarea fără erori.

Păstrează intrările integrării, identitatea huburilor și dispozitivele Zigbee
asociate; nu șterge integrarea și nu repeta asocierea. Integrarea și
automatizările sunt livrate strict separat. Acest pachet de integrare nu conține
fișiere de automatizare și instalarea lui nu instalează sau actualizează
automatizări. Verificarea mesajelor noi de registru este descrisă în
`DEVICE_REGISTRY_COMPAT_RO.md`; verificări audio API opționale:
`SOUND_MUTE_POLICY_RO.md`.

Apelurile WAV separate păstrează regula obișnuită de reluare media între apeluri;
versiunea nu introduce o sesiune care să țină radioul suspendat și în pauzele
dintre mai multe WAV-uri. Comenzile explicite de mute/unmute media sau de volum
comun modifică în continuare playerul; politica alertei nu suprimă aceste apeluri.

Domeniul intern rămâne `aqara_m1s_zigbee_router`. Diagnosticele păstrate și entitățile routerelor își păstrează ID-urile unice; vechile entități media/IO ale coordonatorului sunt eliminate automat. MAC-ul Wi-Fi fizic este folosit drept identitate atunci când este disponibil, iar ultimul rol Zigbee confirmat este păstrat dacă hubul este offline. Referințele la controale retrase din carduri sau automatizări sunt configurație externă și nu sunt schimbate de instalarea componentei.

## Comportament Router și Coordinator

| Funcție | Rol Router | Rol Coordinator |
| --- | --- | --- |
| Transport Zigbee | Runtime-ul existent JN5189 Router | Zigbee-on-Host prin `tcp://IP_HUB:1886` |
| Ring Light | MQTT persistent către A5; fallback vechi numai înainte de activarea upgrade-ului | Nu este expus |
| Illuminance | Stare MQTT retained; A6 serializat pe hub la 30 de secunde | Nu este expus |
| WAV stocat | Redare locala directa, cu volumul ALSA comun; numai comenzi prin Telnet | Nu este expus; serviciile WAV vechi sunt blocate |
| Media / apartenență grup | Redare individuală și de grup existentă | Nu se creează player sau membru în grup |
| Conectare la alt coordinator | Disponibilă cu confirmare explicită | Ascunsă și blocată |
| Coordinator ON/OFF | Nu se aplică | Eliminat intenționat |

Acțiunea Routerului de conectare la alt coordinator rămâne explicită. Integrarea oprește temporar agentul, execută cadrul A7 printr-o fereastră UART limitată, apoi repornește agentul. Fereastra se închide automat după 90 de secunde dacă Home Assistant se deconectează. RGB/lux pentru Coordinator nu revine niciodată la traseul UART al Routerului.

## Protecția Routerului și traseul MQTT

- Topicurile sunt construite din IP-ul actual al hubului: de exemplu, Routerul `192.168.0.221` folosește `m1s/221/io/...`, indiferent de numele sau ID-ul istoric al entității.
- Agentul Router `1.1.1` se abonează la `io/rgb/set`, `io/lux/refresh`, `sound/prepare` și `sound/stop`; publică starea IO, disponibilitatea, telemetria și rezultatul comenzilor WAV.
- Luxul este citit la 30 de secunde. O citire A6 fără checksum valid nu devine `0 lx`, ci rămâne invalidă.
- După activare există un singur proprietar pentru `/dev/ttyS1`. Tunelul temporar TCP `1886` folosit anterior pentru A5/A6 este oprit și nu poate porni peste agent.
- Un mesaj retained cu rol `coordinator` este ignorat de un Router și invers.
- Dacă agentul este configurat dar indisponibil, numai Ring Light, luxul și diagnosticele MQTT devin indisponibile; integrarea nu încearcă automat UART-ul vechi peste agent.
- Disponibilitatea generală a Routerului continuă să folosească verificarea LAN ușoară existentă. Astfel o problemă a brokerului MQTT nu scoate automat playerul din grup și nu schimbă sincronizarea audio.
- Agentul Router isi pastreaza functiile IO. Noua redare WAV nu mai foloseste pregatirea vechiului receiver MQTT: comenzile WAV si de volum folosesc Telnet izolat. Decodarea radioului si ceasul grupului raman in Home Assistant.

## Coordonator dedicat

- Rămân doar Hub Connectivity, WiFi IP, MQTT Process local, Telnet Process și Zigbee Transport.
- Diagnosticele sunt numai citire și nu deschid o a doua conexiune la relay-ul Zigbee.
- În Configurare rămân adresa IP (inclusiv IP static / recuperare DHCP) și schimbarea Wi-Fi.
- Nu se creează runtime media/sunete, membru de grup, abonare MQTT auxiliară sau scriere a MQTT-ului comun pentru coordonator.
- Nu se execută comenzi UART, citiri lux, curățare RGB, semnal la boot sau migrarea watcherului de buton fizic pentru acest rol.
- Temperatura, HomeKit, luxul și vechile comenzi ale coordonatorului sunt retrase, nu afișate cu valori vechi.
- Integrarea nu oprește servicii pe hub și nu șterge WAV-uri. Profilul de pe hub este gestionat de kitul separat Only Coordinator.

Zigbee2MQTT deține conexiunea Coordinatorului. O secțiune serială tipică este:

```yaml
serial:
  port: tcp://IP_HUB:1886
  adapter: zoh
```

Canalul Zigbee, PAN-ul, cheia de rețea și baza de date cu dispozitive rămân setări Zigbee2MQTT; această integrare nu le înlocuiește.

## Entități Router

- **Ring Light**, cu culoare RGB și luminozitate.
- **Illuminance**, cu atributele `adc_raw`, `millivolts` și sursa specifică rolului.
- **Media Player** pentru streamuri și redare locală.
- **M1S Media Group** și **Include in M1S Media Group** pentru redare sincronizată pe huburile selectate.
- **Hub Volume**, cu ID-ul unic al fostului Sound Playback Volume, si selectia **Sound**. Numarul si sliderul media individual controleaza acelasi volum. Pentru volum temporar foloseste `play_sound.volume_percent`; automatizarile care modifica numarul comun modifica si radioul. Fine Volume Trim este eliminat automat la actualizare.
- Câte un buton pentru fiecare sunet WAV detectat care nu este sunet de sistem.
- Evenimente **Physical Button**: click, de la dublu până la zece clickuri, început HOLD, repetare și eliberare.
- **Hub Connectivity**, **Hub Temperature**, **WiFi IP**, starea proceselor HomeKit, MQTT și Telnet.
- Diagnosticul **JN5189 Router** numai pentru huburile cu rol Router.
- Starea **MQTT configuration**: `not_configured`, `pending`, `applied` sau `failed`.

## Configurare MQTT comună

Deschide **Configurează** pe un Router și selectează **MQTT comun - toate huburile**. Setările sunt aplicate doar huburilor cu rol Router, inclusiv celor adăugate ulterior. Coordonatorii sunt omiși. Routerele offline se sincronizează după reconectare; scrierile eșuate sunt reîncercate după 60 de secunde.

Folosește adresa LAN a aceluiași broker folosit de Home Assistant, nu `localhost` sau un nume intern al add-onului pe care huburile nu îl pot rezolva. Funcția folosește MQTT simplu în LAN, fără TLS, și nu creează utilizatori pe broker și nu modifică integrarea MQTT din Home Assistant.

Utilizatorul și parola trebuie să conțină caractere ASCII imprimabile și pot avea împreună cel mult 80 de caractere. La o editare ulterioară, parola goală păstrează parola salvată. Integrarea validează autentificarea la broker înainte de salvare, dar permisiunile ACL trebuie să permită în continuare publicarea topicurilor hubului. Identitatea topicului butonului este păstrată atunci când se schimbă IP-ul hubului.

Starea `applied` înseamnă că configurația a fost scrisă cu succes pe hub; confirmă livrarea reală printr-o apăsare a butonului fizic. Datele de autentificare sunt păstrate în stocarea integrării Home Assistant și în backupurile hubului, deci ambele trebuie tratate confidențial.

## Administrarea sunetelor și media

- Uploadul unui singur WAV este disponibil din **Configurează**, iar fișierul este salvat sub `/data/musics/music-ch`. Arhivele ZIP nu mai sunt acceptate.
- După pornirea transferului, fereastra afișează `Fișier 1 din 1`, numele WAV-ului și un procent care avansează pe măsură ce sunt transmise blocurile. Procentul ajunge la 100% numai după verificarea dimensiunii și MD5 pe hub.
- Înainte de scriere, WAV-ul este verificat în raport cu spațiul din `/data`. Un fișier destinație existent este calculat ca înlocuire, iar uploadul este refuzat dacă ar lăsa mai puțin de 8 MiB liberi. Aceeași rezervă se aplică serviciului direct `upload_sound`.
- `/data/musics/music-us` este rezervat sunetelor de sistem pentru factory reset. WAV-urile sale și fișierele din subfoldere nu sunt expuse ca butoane în Home Assistant și nu apar niciodată în lista de ștergere.
- Ștergerea manuală listează WAV-urile care nu sunt de sistem de sub `/data/musics`, inclusiv celelalte foldere originale Aqara.
- Niciun fișier nu este selectat implicit.
- După alegerea fișierelor și apăsarea butonului **Șterge**, apare un popup scurt separat, cu numărul fișierelor și controlul explicit de confirmare; acesta rămâne complet vizibil și nu se derulează împreună cu lista.
- Selecția este transmisă hubului printr-un manifest temporar împărțit în bucăți mici, astfel încât listele mari să nu depășească limita unei comenzi Telnet.
- Ștergerea confirmată este definitivă și nu creează arhivă backup. Întregul manifest este validat înainte, comanda de pe hub blochează independent `music-us`, iar succesul este acceptat numai când numărul șters corespunde selecției.
- Instalarea, pornirea și migrarea nu șterg automat niciun sunet.
- După un upload sau o ștergere reușită, integrarea se reîncarcă și reconstruiește entitățile sunetelor.

Pentru WAV prioritar, arbitrul suspendă audio individual/de grup numai pe hubul
respectiv, confirmă eliberarea dispozitivului audio și pornește alerta cu volumul
temporar. Implicit ocolește mute pentru media fără să-i schimbe starea. La final,
Stop, eroare sau anulare, volumul media curent trebuie restabilit înainte de
reluare; intenția curentă decide dacă playerul se reia sau hubul reintră în grup.
Sunetul nou deține propriul token, iar curățarea unei cereri vechi nu îl poate
opri și nu poate aplica peste el volumul media. Coordinatorul nu participă.
Nu se creează copii WAV pentru fiecare volum. Predarea pe huburile reale rămâne
de verificat live.

Dacă o sursă individuală nu mai livrează PCM, entitatea afișează acum `buffering`, oprește receiverul remote și îl reconstruiește numai după revenirea datelor PCM reale. La un rebase sunt memorate întârzierea, durata ultimei scrieri TCP și cauza probabilă (`tcp_drain_timeout`, `tcp_drain_slow` sau `ha_scheduler_or_other_await`). Protecția la oprirea ordonată continuă să oprească receiverul individual înainte de închiderea writerului local și nu adaugă watchdog activ pe hub.

Grupul păstrează o singură istorie PCM și un singur ceas. Primul timeout TCP de 1,25 secunde este tolerat; defecțiunile confirmate izolează doar hubul afectat. Hubul revenit așteaptă fără audio vechi o pornire comună. Cererile se grupează timp de trei secunde, cu minimum 60 de secunde între alinieri cât timp există receptoare sănătoase. Pornirea comună poate produce o scurtă pauză, dar nu redeschide sursa FFmpeg. Huburile excluse, offline, folosite individual sau pentru WAV nu sunt preluate. O încercare eșuată nu blochează celelalte receptoare. Contorul încercărilor se resetează după 30 de secunde de redare admisă. Auditul folosește probe ALSA deja colectate și cere trei modificări relative plauzibile și noi; probele vechi, lente sau imposibile sunt ignorate. Nu se face resampling separat și nu se resetează grupul orbește după un cronometru. Alinierea auzită trebuie verificată pe huburile reale. Serviciul manual de resincronizare și pornirea inițială limitată în timp rămân disponibile.

Finalul WAV este detectat din iesirea playerului local, verificata la 500 ms; vechea rezerva dupa EOF FFmpeg nu mai este folosita. Stop si inlocuirea tintesc doar tokenul si procesul detinut. Un WAV cerut prin `play_url` este descarcat in RAM pe hub, nu pe `/data`; WAV-ul deja memorat nu necesita descarcare.

Pentru Routere, Media Player individual și grupul comun M1S Media Group, controalele de volum, radioul, actualizarea metadatelor și butoanele pentru sunetele Aqara sunt păstrate din baza confirmată.

## Administrarea rețelei

Fluxul de configurare acceptă DHCP, adresă IPv4 statică în subnetul curent și schimbarea rețelei Wi-Fi prin modulul recovery instalat. Înainte de schimbarea Wi-Fi, hubul revine la DHCP și testează noua rețea. Parola Wi-Fi nu este salvată în Home Assistant. Schimbarea rețelei poate face temporar hubul indisponibil; folosește noua lui adresă după reconectare.

## Servicii disponibile

Integrarea înregistrează serviciile `play_url`, `play_sound`, `upload_sound`, `delete_sound`, `refresh_sounds`, `reset_media_group`, `resync_media_group` și `update_media_metadata`. Păstrează și serviciul avansat `run_command`; folosește-l numai pentru comenzi pe care le înțelegi, deoarece execută o comandă shell pe hubul selectat prin Telnet.

Serviciile media/WAV refuză un coordonator configurat ca țintă. Serviciile sunt globale deoarece rămân necesare Routerelor; ele nu sunt comenzi expuse pe dispozitivul coordonator. `run_command` rămâne un instrument administrativ explicit, nu o izolare de securitate a hubului.

`play_sound` și `play_url` pentru WAV prioritar acceptă opțional `volume_percent`
și `respect_mute` (implicit `false`). Primul schimbă numai volumul alertei,
nu sliderul media comun. Al doilea respectă mute individual pentru cererea
respectivă; mute de grup rămâne control pentru media de grup. Butoanele de sunet
folosesc politica implicită și sliderul individual curent. Exemplele și cazul
sliderului la zero sunt în `SOUND_MUTE_POLICY_RO.md`.

`delete_sound` necesită `confirm: true`, refuză orice cale de sub `/data/musics/music-us` și șterge celelalte căi WAV valide fără să creeze backup. Dacă sunt configurate mai multe huburi, indică parametrul `host` pentru serviciile de sunet adresate unui hub anume.

## Validare și statut TEST

`VALIDATION.txt` indică starea curentă a validării și identifică rularea din
`TEST_REPORT.json` / `TEST_LOG.txt`. Un raport copiat din pachetul anterior este
istoric până la înlocuirea lui cu o rulare 0.37.19. Acest build nu a fost instalat
pe HA, nu a repornit HA și nu a fost testat audio live. Politica mute nouă,
restaurarea după modificări manuale, înlocuirea/anularea sunetelor, recuperarea
ceasului comun și supravegherea Coordinator păstrată necesită rularea locală
corespunzătoare; predarea auzită și sincronizarea necesită huburile reale.
Ascultarea anterioară pe un singur hub nu validează acest pachet final și nu
reprezintă un test real peste noapte.

### Istoric al bazei 0.37.5 (nu funcții active pe coordonatorul dedicat)

Sursa `0.37.5` a trecut:

- 20 de teste izolate pentru MQTT RGB/lux, telemetrie, roluri, topicuri, izolarea UART, conectivitate și rejoin Router.
- 3 teste dedicate priorității și transportului WAV: Coordinator MQTT, Router MQTT și fallback Telnet pentru un Router fără capabilitatea nouă.
- 9 teste pentru ștergerea directă WAV, protecția folderului de sistem și manifestul fragmentat.
- 8 teste pentru verificarea spațiului, transferul TCP real pe socket, progresul monoton, fallback și protecția căilor de sistem.
- 7 teste pentru persistența și revenirea configurării MQTT comune.
- 19 teste de regresie și simulare audio pentru precizia volumului de grup și individual, oprirea remote înainte de local, comenzile
  limitate, diagnosticul de buffering, ultima comandă prioritară, restaurarea
  limitată, eliberarea playerelor individuale și realinierea receptorilor după
  pierderea dovedită a poziției comune.
- Compilarea Python și parsarea fișierelor JSON/YAML.
- Verificarea de sintaxă a tuturor scripturilor Router și compilarea agentului static MIPS32 cu avertismente tratate ca erori.
- Baza respectivă a trecut toate cele 66 de teste izolate; hashurile ei audio
  aparțin validării acelei versiuni, nu rezultatului curent 0.37.19.

Uploadul a fost verificat și pe Routerul `192.168.0.221`: 128.044 octeți în 5,46 secunde, MD5 identic, progres intermediar și ștergerea confirmată a fișierului temporar.

Traseul de ștergere multiplă din `0.36.1` a fost verificat hardware pe Coordinatorul `192.168.0.220` cu 12 fișiere temporare. Ștergerea directă și protecția `music-us` din `0.36.2` sunt acoperite de teste izolate și instalarea nu modifică automat niciun hub.

Istoric pentru baza anterioară: agentul Router `1.1.1` fusese instalat pe `.200-.209` și `.222-.225`, iar agentul Coordinatorului fusese validat pe `.220`. Acestea nu sunt verificări ale stării actuale a tuturor huburilor. În `0.37.6`, agentul coordonatorului nu mai este folosit. Pachetul nu scrie firmware.

## Revenire

Restaurează componenta anterioară din backup (în mod obișnuit `0.37.18` pentru
această actualizare) și repornește Home Assistant. Verifică versiunea instalată
și încărcarea ei fără erori. Versiunea 0.37.18 păstrează aceeași politică audio,
dar are avertismentele de API ale registrului corectate aici. Păstrează intrările integrării și asocierile
Zigbee. Pachetul nu schimbă firmware-ul, datele Zigbee sau WAV-urile originale.
Revenirea kiturilor Router MQTT și Coordinator rămâne separată. Dacă modifici
și supravegherea opțională, urmează `COORDINATOR_GUARD_RO.md`.
