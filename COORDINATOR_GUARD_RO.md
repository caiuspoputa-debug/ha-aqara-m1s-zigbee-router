# Supraveghere coordonator și Zigbee2MQTT — 0.37.17 TEST

Pachet pregătit pentru instalare ulterioară. Nu a fost instalat pe Home Assistant
și nu a fost testat pe coordonatorul real în această sesiune.

## Comportament

Integrarea Home Assistant rămâne activă separat de Zigbee2MQTT. Pentru un hub
cu rolul **coordinator**, meniul Configure include **Supraveghere Zigbee2MQTT**,
iar o entitate nouă **Zigbee2MQTT Ready** separă conectivitatea Linux/Telnet de
starea operațională verificată a bridge-ului.

La pierderea coordonatorului, supravegherea publică starea MQTT `offline`, cere
oprirea suplimentului ales și nu îi permite pornirea până la verificarea revenirii.
Un eșec de publicare nu acordă permisiune de pornire; bucla încearcă și oprirea
suplimentului. Dacă Supervisor nu răspunde, oprirea nu poate fi garantată și
entitatea Ready rămâne oprită, cu motivul erorii.

## Ordinea recuperării

1. Confirmă prin Supervisor că suplimentul selectat este **stopped**. Starea
   `error`, un simplu răspuns la comanda stop și lipsa mesajelor radio nu sunt
   tratate drept confirmare a opririi.
2. Citește o fotografie proaspătă a coordonatorului printr-o sesiune Telnet
   separată: rol coordinator, configurare activată, GPIO33=1, GPIO18=0, exact
   un proces relay care deține `/dev/ttyS1`, fără procesul Zigbee stock și cu
   portul configurat în ascultare. Citește și identitatea bootului și a relay-ului.
3. Dacă există deja alt client conectat pe portul RCP, așteaptă; nu face probe
   și nu resetează radioul peste acel client.
4. Cu Zigbee2MQTT oprit, execută scriptul existent
   `/data/m1s_coordinator/coordinator_on.sh`. Acesta reinițializează GPIO/radio/relay;
   nu face flash, nu resetează rețeaua Zigbee și nu șterge dispozitivele.
5. Cere două fotografii proaspete ale aceluiași runtime, la cel puțin 5 secunde
   distanță. Nu este suficient un temporizator fix de la apariția Wi-Fi.
6. Deschide exclusiv portul RCP și verifică pachete Spinel cu CRC și identificator
   de tranzacție valide: protocol 4.3, firmware JN_5189/M1S_IO_V2, interfață 3,
   activarea PHY confirmată prin set/get și dezactivarea PHY confirmată. Nu schimbă
   canalul, cheile, PAN ID, tabela ZoH sau contoarele de securitate.
7. Închide complet conexiunea de probă, reverifică identitatea runtime-ului și
   absența clienților conectați, apoi cere pornirea suplimentului.
8. Ready devine **on** numai după un mesaj MQTT `online` nou, primit după acea
   pornire, și o sesiune TCP stabilită pe relay. Un mesaj `online` retained de
   la pornirea anterioară nu este acceptat ca dovadă.

MQTT IO auxiliar al hubului nu este o precondiție: în runtime-ul existent acesta
poate porni abia după primul client RCP. A-l cere înainte de pornirea Z2M ar crea
o dependență circulară. Radioul, transportul și brokerul folosit de Home Assistant
sunt verificate separat.

## Entitățile Zigbee în Home Assistant

Se folosește topicul normal `<base_topic>/bridge/state`, cu payload JSON și
retain. Entitățile descoperite normal de Zigbee2MQTT folosesc acest topic pentru
disponibilitate și devin **unavailable** când bridge-ul este offline.

Entitățile și dispozitivele nu sunt șterse din registru, pentru a păstra
automatizările și împerecherile. Pe carduri pot rămâne vizibile ca indisponibile;
aceasta este intenționat diferită de eliminarea lor din Home Assistant. Un card
personalizat care ascunde starea unavailable sau o entitate cu disponibilitatea
dezactivată explicit necesită adaptarea acelui card/configurații. Ready poate fi
folosit pentru afișare condiționată. Nu se șterg mesajele MQTT discovery.

## Instalare și activare

1. Fă backup integrării existente și configurației Zigbee2MQTT. Instalează
   directorul `custom_components/aqara_m1s_zigbee_router` din această arhivă peste
   integrarea existentă, păstrând structura. Repornește Home Assistant.
2. Supravegherea este implicit **dezactivată**: instalarea nu ghicește ce instanță
   Zigbee2MQTT trebuie controlată și nu schimbă pornirea altor suplimente.
3. În integrarea hubului coordinator: Configure → Supraveghere Zigbee2MQTT.
   Completează identificatorul exact al suplimentului Z2M de laborator, topicul
   MQTT de bază exact din configurația lui (uzual `zigbee2mqtt`) și portul RCP
   (1886 pentru acest M1S). Nu introduce aici parola MQTT sau un token Supervisor.
4. Activează supravegherea, lasă Pauza debifată și salvează. La activare se face
   o recuperare controlată, inclusiv oprirea/pornirea Z2M, chiar dacă era deja
   pornit. Nu activa în timpul operațiunilor de împerechere/mentenanță.
5. Integrarea salvează politica originală Supervisor, setează pornirea suplimentului
   pe **manual** și dezactivează **watchdog-ul Supervisor** pentru acel supliment.
   Astfel Supervisor nu îl repornește în timp ce coordonatorul este nepregătit.
   Politica este verificată din nou în buclă. Nu activa un alt mecanism extern
   care repornește sau accesează același supliment/port în paralel.
6. Verifică entitatea Ready și atributele `phase` / `reason`, apoi generează un
   eveniment real de la un buton Zigbee.

Este necesar Home Assistant cu Supervisor, MQTT configurat și runtime-ul M1S
dedicat existent. Această implementare vizează exact JN5189/M1S_IO_V2/Spinel 4.3;
nu face automat adaptări pentru alt firmware, alt UART sau alt coordonator.

## Oprire manuală, încercări și repornire Home Assistant

- Bifa **Pauza** ține Z2M oprit și blochează pornirea automată. Debifează și
  salvează pentru o nouă recuperare controlată.
- Dacă Z2M se oprește în timp ce hubul este verificat sănătos, supravegherea
  salvează o pauză, ca să nu contrazică butonul Stop al utilizatorului. Nu se poate
  deosebi sigur fiecare oprire manuală de fiecare ieșire a procesului numai din
  starea Supervisor. Verifică motivul, apoi reia din Configure.
- O cădere confirmată a hubului are prioritate asupra acestei reguli: revenirea
  lui declanșează automat recuperarea, fără intervenție manuală.
- Există maximum trei încercări per boot detectat, cu pauze progresive. Lipsa
  confirmării unei porniri după 90 de secunde duce la stop și o nouă încercare;
  după limită, starea este `fault`, fără o buclă infinită de reporniri. Un boot nou
  sau salvarea din Configure reîncepe seria de încercări.
- La repornirea/reîncărcarea integrării, configurația se încarcă din stocarea HA;
  dacă supravegherea este activată, se reface verificarea completă și se poate
  produce o repornire controlată Z2M. Nu se adoptă necondiționat un `online` vechi.
- La unload/restart HA, politica manual/watchdog oprit rămâne în vigoare.
  **Dezactivează supravegherea din Configure înainte să elimini integrarea**;
  dezactivarea restabilește și verifică politica Supervisor salvată. Nu pornește
  forțat Z2M: dacă este oprit, pornește-l manual după dezactivare.

## Timpi și limite ale dovezii

Bucla pornește o verificare la fiecare 5 secunde după încheierea celei precedente.
Detectarea unei căderi include și timeout-ul conexiunii/comenzii; nu este instantanee.
Recuperarea include reinițializarea runtime-ului, două probe pasive și proba Spinel.

Ready confirmă inițializarea host–RCP și pornirea bridge-ului, **nu garantează
recepția radio în aer a fiecărui dispozitiv**. Preflight-ul PHY nu este un test RF
cu un al doilea dispozitiv. Atributul `radio_over_air_verified` este explicit false.
Lipsa traficului de la senzori care dorm nu este folosită pentru a declanșa resetări.
Defecțiunile de antenă, interferențele sau un blocaj silențios după pornire pot cere
diagnostic suplimentar. Nu declarăm remedierea hardware validată înainte de test.

## Test de acceptanță după instalare

1. Confirmă Ready=on și evenimente reale de la un buton.
2. Lasă Home Assistant și brokerul pornite. Scoate numai coordonatorul din priză.
   Confirmă Ready=off, Z2M stopped și entitățile Zigbee unavailable.
3. Reconectează coordonatorul. Confirmă că Z2M rămâne oprit în timpul pornirii
   și pornește după preflight, fără comenzi manuale. Apasă din nou butonul.
4. Repetă întreruperea, inclusiv una scurtă, și testează restart HA cu hubul oprit.
5. Testează Pauza și Stop manual: Z2M nu trebuie repornit contra intenției tale.
6. Verifică soneria/radioul: fișierele audio nu au fost schimbate față de 0.37.16.

## Referințe folosite

- [Controlul aplicațiilor/suplimentelor prin Supervisor](https://www.home-assistant.io/integrations/hassio)
- [Wrapperul autentificat Supervisor din Home Assistant](https://github.com/home-assistant/core/blob/dev/homeassistant/components/hassio/handler.py)
- Codul Zigbee2MQTT 2.14.2, extensia Home Assistant: disponibilitatea discovery
  folosește `<base_topic>/bridge/state` în configurația standard.
- Codul runtime-ului M1S existent: `coordinator_on.sh`, `coordinator_status.sh`,
  relay-ul UART/TCP și definițiile Spinel din ZoH.
