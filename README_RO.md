# Aqara M1S Zigbee Coordinator + Router v0.33.0

Integrare locală Home Assistant pentru huburi Aqara M1S Gen 1 identice hardware, configurate ca Router Zigbee sau Coordinator Zigbee-on-Host. Domeniul intern rămâne `aqara_m1s_zigbee_router`, astfel încât instalările existente se actualizează fără recrearea entităților.

## Comportament în funcție de rol

- Router: în Configure apare **Conectare la alt coordonator Zigbee**; RGB și lux folosesc protocolul UART Router.
- Coordinator: nu există switch, setare sau serviciu Home Assistant pentru oprirea coordinatorului. La actualizare, vechea entitate cu ID unic `*_coordinator_radio` este eliminată automat din registru.
- Coordinator: **Ring Light** este o entitate Light RGB, iar **Illuminance** este un senzor în lux. Comenzile folosesc exclusiv helperul sideband `/data/m1s_coordinator/coordinator_io.sh`, fără a prelua portul Spinel folosit de Zigbee2MQTT.
- Rolul confirmat este memorat în intrarea Home Assistant și nu depinde de adresa IP.
- Canalul și rețeaua Zigbee rămân administrate de Zigbee2MQTT, cu `serial.adapter: zoh` și `tcp://HUB_IP:1886`.

## Validarea Coordinator din 30.09.2026

Pe huburile identice `.220` și `.222` au fost verificate firmware-ul Coordinator EXP4.4, relay-ul 0.4.1, handshake-ul Spinel `Protocol version: 4.3`, markerul `M1S_IO_V2`, proprietatea sideband 59, traficul cu dispozitive Zigbee asociate și funcționarea Zigbee2MQTT în timpul comenzilor RGB/lux. Au fost verificate și persistența după reboot pentru Telnet, Wi-Fi și runtime-ul Coordinator, plus protecția față de comenzile butonului din fabrică.

Firmware validat SHA-256: `C102149FA5A88A69535AE6E204A3F60BACB6FBB970571567D506DC8CD7844C57`.

Relay validat SHA-256: `B8FFD40CAC73048EF2868A33EE61410C4019D5CD55B673A6BB4FE64591391408`.

RGB/lux pentru Coordinator necesită acest runtime compatibil și un `coordinator_io.sh` funcțional. Integrarea nu modifică firmware-ul și nu face flash. Citirea lux este valoarea furnizată de firmware; calibrarea fotometrică absolută rămâne dependentă de senzor și montaj.

## MQTT comun

În Configure, **MQTT comun - toate huburile** salvează o singură configurație și o aplică huburilor Router și Coordinator. Huburile offline se sincronizează la revenire. Parola goală păstrează valoarea salvată; la prima configurare este obligatorie. Senzorul **MQTT configuration** arată starea aplicării pe fiecare hub.

## Administrarea sunetelor

- Uploadul rămâne în `/data/musics/music-ch`.
- Ștergerea listează toate fișierele `.wav` din `/data/musics`; nimic nu este selectat implicit.
- Confirmarea este obligatorie, iar înainte de ștergere se creează un backup în `/data/m1s_sound_backups`.
- Instalarea, pornirea și migrarea nu șterg automat sunete.

Detalii de release: [RELEASE_0.33.0.md](RELEASE_0.33.0.md).
