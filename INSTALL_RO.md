# Instalare integrare Aqara M1S 0.37.24

1. Păstrează o copie a directorului integrării instalate.
2. Înlocuiește numai `/config/custom_components/aqara_m1s_zigbee_router` cu
   directorul cu același nume din arhivă.
3. Repornește Home Assistant și verifică versiunea **0.37.24**.
4. Dacă folosești supravegherea, deschide opțiunile coordonatorului și verifică
   dacă **Pauză** este debifată pentru funcționare automată. Pauza deja salvată
   nu este ștearsă la actualizare.
5. Când Zigbee2MQTT Ready este activ, confirmă un eveniment Zigbee nou.
   Testul de revenire controlată și explicația opțiunii Pauză sunt în
   [COORDINATOR_GUARD_RO.md](COORDINATOR_GUARD_RO.md).

Nu se reinstalează suplimentul Zigbee2MQTT sau firmware-ul și nu se refac
împerecherile. Pentru revenire, restaurează copia directorului și repornește
Home Assistant. Dacă dorești să elimini supravegherea înaintea revenirii,
dezactiveaz-o din opțiunile integrării ca să restaureze politica Supervisor.

Testele locale sunt documentate în VALIDATION.txt și TEST_REPORT.json.
