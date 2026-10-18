# 0.37.18 TEST — alerte prioritare independente de mute media

WAV-urile prioritare, butoanele de sunet și `play_url` ocolesc implicit mute
individual/de grup fără să schimbe starea mute a playerelor. Nu mai sunt
necesare comutările unmute/remute în fiecare automatizare.

- `volume_percent` stabilește volumul temporar; fără el se folosește sliderul
  individual curent înainte de mute. Sliderul la 0% rămâne silențios.
- `respect_mute: true` păstrează comportamentul anterior față de mute individual
  pentru acel apel. Mute de grup rămâne control pentru media de grup.
- Volumul media curent este confirmat înainte de reluare/reintrare în grup,
  inclusiv după eroare sau anulare. Modificările manuale din timpul alertei
  rămân valabile după ea; nu se restaurează o stare veche de mute.
- Înlocuirea respectă tokenul proprietar: o cerere veche nu poate opri noul
  sunet sau suprascrie volumul lui în cursul curățării.
- Supravegherea Coordinator/Zigbee2MQTT din 0.37.17 este păstrată fără modificări.

Integrarea și automatizările sunt livrate strict separat. Acest pachet de
integrare nu conține și nu instalează fișiere de automatizare.
Apelurile WAV separate păstrează reluarea media normală între ele; nu este
adăugată o sesiune comună care să țină radioul suspendat pe durata tuturor pauzelor.

## Instalare

Fă backup componentei existente. Înlocuiește componenta în
`/config/custom_components/aqara_m1s_zigbee_router` și repornește Home Assistant.
Nu copia întregul pachet în interiorul componentei și nu crea un folder dublu.
Nu trebuie șterse intrările existente sau repetată asocierea Zigbee.
Verifică dacă manifestul componentei instalate indică `0.37.18` și dacă
integrarea se încarcă fără erori. API-ul și exemple minimale de apel sunt
descrise în `SOUND_MUTE_POLICY_RO.md` și `NOTIFICATION_VOLUME_RO.md`.
Comenzile explicite de mute/unmute media trimise de un client existent schimbă
în continuare playerul; politica alertei nu le suprimă.

## Statut

Pachet complet de integrare, nu imagine de firmware. Nicio instalare HA,
repornire HA sau probă audio live nu a fost făcută pentru acest build.
`VALIDATION.txt` identifică rezultatele automate finale; validarea pe huburile
reale rămâne de făcut. Păstrează marcajul pre-release **TEST**.

Acesta este text pentru o publicare ulterioară. Nu s-a creat sau publicat un
release GitHub. Pentru publicare, conținutul pachetului merge în rădăcina
repository-ului `ha-aqara-m1s-zigbee-router`, cu manifestul 0.37.18.
