# 0.37.6 TEST - coordonator dedicat, Routere pastrate

Aceasta este actualizarea integrarii Home Assistant, pornind exact de la
arhiva 0.37.5 trimisa. Nu este firmware si nu este App-ul Zigbee2MQTT.
Nu instaleaza si nu reaplica profilul Only Coordinator de pe hub.

## Pe coordonator raman

- Hub Connectivity: starea fizica a accesului la hub, prin verificarea Telnet.
- WiFi IP: adresa IPv4 citita din wlan0.
- MQTT Process: procesul Mosquitto LOCAL de pe hub, necesar stivei de baza.
  Nu este agentul MQTT auxiliar si nu indica starea brokerului HA.
- Telnet Process: starea serviciului de administrare.
- Zigbee Transport: `connected`, `listening` sau `stopped`, citit din netstat
  pentru portul 1886. Nu pretinde ca verifica intreaga retea Zigbee.

Cele patru diagnostice sunt citite impreuna la 30 de secunde, numai prin
comenzi Linux de citire. Disponibilitatea hubului pastreaza verificarea
existenta la 5 secunde. O eroare a diagnosticelor nu scoate hubul offline;
doar diagnosticele fara esantion valid devin indisponibile.

Nu se mai expun temperatura proprietatii stock, HomeKit sau lux: acestea
nu mai au o sursa actualizata fiabila dupa oprirea serviciilor auxiliare.

## In Configurare raman exact doua optiuni

1. Adresa IP: IP static, cu mecanismul existent de test/confirmare si DHCP
   disponibil pentru recuperare.
2. Schimbarea retelei Wi-Fi: acelasi mecanism existent de test si revenire.

Nu se schimba codul aplicarii IP-ului static sau al schimbarii Wi-Fi.
Schimbarea efectiva a IP/Wi-Fi ramane o operatie explicita, potential
intreruptiva pentru conexiunea Zigbee2MQTT. Dupa schimbarea IP-ului, adresa
seriala din configuratia Zigbee2MQTT trebuie actualizata separat.

## Ce dispare numai pentru rolul Coordinator

Media Player, apartenenta la grup, volum/trim, WAV, upload/stergere sunete,
Ring Light, lux, evenimente/declansatoare ale butonului fizic auxiliar si
configurarea MQTT comuna. Agentul MQTT auxiliar nu este abonat, pornit sau
reconfigurat de aceasta integrare. Nu se executa migrarea watcherului GPIO.

Entitatile vechi individuale ale coordonatorului sunt eliminate automat
din registrul integrarii. Entitatile altor integrari, ale Routerelor si
playerul global de grup nu sunt sterse. ID-urile diagnosticelor pastrate
raman aceleasi. Cardurile si automatizarile care refera entitatile retrase
trebuie corectate separat; nu le modificam automat.

Rolul se detecteaza din runtime, nu din IP. Ultimul rol confirmat ramane
valabil si daca hubul este offline cand porneste HA.

## Routerele

Pastreaza media individuala si de grup, sunetele, volumele, RGB/lux,
MQTT-ul comun si butonul fizic. Fisierele pentru transporturile audio si
sincronizare sunt identice octet cu octet cu cele din arhiva 0.37.5.
Coordonatorul nu mai este inregistrat ca membru al grupului.

## Instalare peste versiunea existenta

1. Fa backup Home Assistant si pastreaza arhiva 0.37.5 pentru revenire.
2. Extrage arhiva Windows. Inlocuieste numai directorul
   `custom_components/aqara_m1s_zigbee_router` din `/config/custom_components/`.
3. Cand alegi sa aplici actualizarea, reporneste HA Core pentru a incarca
   fisierele Python noi. Instalarea poate intrerupe temporar media routerelor.
   Nu trebuie restartat hubul coordonator sau App-ul Zigbee2MQTT pentru aceasta
   actualizare. Pachetul nu executa singur niciun restart.
4. Nu sterge si nu readauga intrarile integrarii existente.
5. Verifica versiunea 0.37.6, cele cinci entitati ale coordonatorului si cele
   doua optiuni din Configurare. Diagnosticele pot necesita cateva secunde
   pentru primul esantion.
6. Verifica un senzor/buton Zigbee si un Router media. Sterge din carduri
   referintele la vechiul player/lumina/sunete ale coordonatorului.

Pe `.220`, profilul Only Coordinator de pe hub este deja aplicat; nu trebuie
reinstalat pentru aceasta versiune a integrarii.

## Limite si revenire

Testele folosesc simulatoare mici ale API-urilor HA, nu un Home Assistant
complet. Citirea Linux a fost verificata separat pe hub; nu a fost instalata
integrarea in HA si nu s-a facut restart in timpul pregatirii arhivei.

Pentru revenire, restaureaza integrarea 0.37.5 si reporneste HA Core cand este
acceptabil. Pentru recuperarea personalizarilor entitatilor eliminate este
necesar backupul HA. Revenirea integrarii nu reactiveaza serviciile auxiliare
oprite de kitul hubului; acesta are propria procedura de revenire.

Serviciul administrativ global `run_command` ramane explicit disponibil.
Profilul nu este un sandbox care blocheaza orice comanda Telnet manuala.
