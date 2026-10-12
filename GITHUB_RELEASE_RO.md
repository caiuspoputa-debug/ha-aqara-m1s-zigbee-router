# Publicare 0.37.11

Aceasta este integrarea Aqara M1S, nu App-ul Zigbee2MQTT ZoH.
Repository-ul indicat in manifest este:
https://github.com/caiuspoputa-debug/ha-aqara-m1s-zigbee-router

1. Extrage arhiva GITHUB si incarca fisierele in radacina repository-ului.
   La radacina trebuie sa fie hacs.json, README.md si custom_components/.
   Nu pune continutul intr-un folder suplimentar M1S_Integration_0.37.11.
2. Salveaza un commit care include manifest.json cu version 0.37.11,
   media_group.py si media_player.py din aceasta arhiva.
3. Creeaza tag-ul si release-ul v0.37.11 din acel commit.
4. Poti atasa si arhiva Windows la release pentru instalare manuala.

Simpla atasare a unui ZIP la un release vechi nu actualizeaza fisierele citite
de HACS. Manifestul si codul trebuie sa existe impreuna in commit-ul tag-ului.
Varianta ramane TEST. Daca release-ul este marcat pre-release, utilizatorii
HACS trebuie sa permita versiunile beta pentru a-l selecta.

Descriere release:
Corectie la Stop pentru grup: elimina datele FFmpeg necitite si previne
blocarea inchiderii procesului, pastrand resetul de urgenta pentru defecte reale.
152 teste automate, inclusiv procese reale si conducte pline. Transportul audio,
ceasul comun, comenzile ALSA si volumul raman ca in 0.37.9. Necesita restart
Home Assistant dupa instalare. Nu modifica firmware-ul huburilor si nu adauga
o corectie noua a desincronizarii acustice.
