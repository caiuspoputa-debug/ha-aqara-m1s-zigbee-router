# v0.37.23 — Transfer Telnet confirmat pentru sincronizarea MQTT

Corectează transmiterea scriptului de verificare MQTT către hub: blocul Base64
este trimis în comenzi scurte, confirmate individual pe aceeași sesiune Telnet.
Comanda finală rulează numai după confirmarea tuturor segmentelor. Dacă apare
o eroare, sesiunea se închide și sincronizarea poate fi reluată integral la
următoarea încercare. Nu se reia un segment pe o sesiune care și-a pierdut variabilele.

Include corecțiile 0.37.22: EntityCategory.DIAGNOSTIC și importul necesar pentru
senzori, plus IP-ul hubului și traceback în avertismentele MQTT. Păstrează fixul
Cast 0.37.21. Transferul audio și scriptul de recuperare MQTT nu sunt modificate.

## Validare

- Pe hubul 192.168.0.203, o probă de citire cu vechea transmitere într-un singur
  bloc a arătat trunchiere: comanda base64 a ajuns ca bas, urmată de not found.
  Aceasta demonstrează coruperea transferului; nu reproduce exact timeout-ul
  istoric de 45 de secunde.
- Transferul nou a trimis 12 comenzi de maximum 454 de caractere și a primit
  M1S_ROUTER_TOPIC_SYNC_READY în aproximativ 10 secunde.
- Proba pe hub s-a oprit obligatoriu înaintea oricărei operații de modificare,
  restart sau creare de lock. Pachetul nu a fost instalat în Home Assistant.
- 345 de teste locale au trecut. Rezultatele sunt în TEST_REPORT.json și TEST_LOG.txt.

## Publicare și instalare

Încarcă fișierele dezarhivate în repository-ul ha-aqara-m1s-zigbee-router,
cu structura custom_components/aqara_m1s_zigbee_router păstrată. Creează release-ul
cu tag v0.37.23 pe acel commit și atașează ZIP-ul. Nu a fost publicat automat.

Pentru instalare manuală, salvează o copie a folderului integrării și înlocuiește
doar custom_components/aqara_m1s_zigbee_router, apoi repornește Home Assistant.
La rollback, restaurează copia folderului și repornește Home Assistant.
