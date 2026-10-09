# 0.37.7 TEST - recuperarea redarii de grup

Acesta este un update al integrarii Home Assistant, nu firmware, kit Router
sau App Zigbee2MQTT. Nu modifica UART, sunetele stocate ori /data pe huburi.
Coordonatorul dedicat ramane exclus din media; IP static si Wi-Fi sunt pastrate.

## Ce se schimba

- Un hub cu defect confirmat este izolat. Restul reda in continuare.
- Hubul revenit nu mai primeste separat audio vechi ca sa ajunga cursorul HA.
  Ramane fara audio pana la o pornire comuna a receptoarelor eligibile.
- Cererile se grupeaza trei secunde. Cu receptoare sanatoase, pornirile comune
  automate sunt separate de minimum 60 de secunde. Un hub revenit poate deci
  astepta pana expira aceasta pauza. Fara niciun receptor sanatos nu se impune
  pauza de 60 de secunde pentru restabilirea audio.
- Pornirea comuna poate intrerupe scurt grupul. FFmpeg si sursa raman deschise;
  receptoarele primesc acelasi bloc PCM nou, apoi acelasi ceas comun.
- Probele ALSA deja colectate sunt auditate. Trei modificari relative de
  minimum 200 ms pot cere aceeasi aliniere, doar daca probele sunt noi,
  plauzibile, rapide si receptoarele nu recupereaza transportul.
- Nu exista resetare oarba periodica sau resampling separat pe hub.
- Retry-ul se reseteaza dupa 30 de secunde de redare admisa, nu la conectarea TCP.
- Logurile identifica IP-ul; atributul member_diagnostics_by_entry_id pastreaza
  fiecare hub distinct, chiar daca toate au acelasi nume.

## Limite importante

ALSA si cursorul TCP nu masoara sunetul auzit si nu includ toate cozile
hardware/FIFO. Valorile imposibile, absente, prea vechi sau citite lent nu sunt
folosite ca dovada. Nu putem promite sincronizare acustica perfecta cu aceste
sonde; trebuie verificata pe huburile reale. Versiunea ramane TEST.

O retea permanent instabila poate necesita alinieri repetate, cel mult una pe
minut cat timp exista receptoare sanatoase. Aceasta limita previne o bucla
rapida; nu inseamna ca o pauza pe minut ar fi acceptabila in utilizare.

Problema UBIFS/read-only a hubului .226 este separata si NU este reparata de
acest update. Acest build nu a accesat hubul sau fisierele lui.

## Instalare si verificare

1. Fa backup HA si pastreaza arhiva 0.37.6 pentru revenire.
2. Extrage ZIP-ul in Windows. Inlocuieste numai directorul integrarii
   custom_components/aqara_m1s_zigbee_router din /config/custom_components/.
   Nu sterge intrarile, helperii sau cardurile existente.
3. Reporneste HA Core cand alegi sa instalezi. Pachetul nu executa restarturi.
   Nu este necesara rescrierea firmware-ului ori restartarea huburilor/Z2M.
4. Confirma versiunea 0.37.7. Testeaza initial 2-3 Routere cu stocare sanatoasa.
   Verifica Play/Stop, volumul 0,01%, un WAV si redarea individuala.
5. Testeaza o deconectare scurta a unui singur Router. Ceilalti trebuie sa
   continue pana la alinierea comuna; receptorul revenit asteapta acea aliniere.
   Asculta daca reintra aliniat si verifica IP-urile din loguri.
6. Abia dupa probele scurte, testeaza cateva ore/noaptea. Noteaza decalajul
   auzit, pauzele si receiver_resync_count, nu doar absenta erorilor.

Daca este mai rau, restaureaza directorul 0.37.6 si reporneste HA Core.
Nu este nevoie de reimperecherea dispozitivelor Zigbee.

Testele executate si limitele lor sunt in TEST_REPORT.json si VALIDATION.txt.
