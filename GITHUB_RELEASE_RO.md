# Publicare 0.37.12

Aceasta este integrarea Aqara M1S, nu App-ul Zigbee2MQTT ZoH.
Repository-ul indicat in manifest este:
https://github.com/caiuspoputa-debug/ha-aqara-m1s-zigbee-router

1. Extrage arhiva GITHUB si incarca fisierele in radacina repository-ului.
   La radacina trebuie sa fie hacs.json, README.md si custom_components/.
   Nu pune continutul intr-un folder suplimentar M1S_Integration_0.37.12.
2. Salveaza un commit care include manifest.json cu version 0.37.12,
   audio_batch.py, media_group.py si media_player.py din aceasta arhiva.
3. Creeaza tag-ul si release-ul v0.37.12 din acel commit.
4. Poti atasa si arhiva Windows la release pentru instalare manuala.

Simpla atasare a unui ZIP la un release vechi nu actualizeaza fisierele citite
de HACS. Manifestul si codul trebuie sa existe impreuna in commit-ul tag-ului.
Varianta ramane TEST. Daca release-ul este marcat pre-release, utilizatorii
HACS trebuie sa permita versiunile beta pentru a-l selecta.

Descriere release:
Audio TCP la 300 ms in medie: blocuri de 8/9 perioade (280/315 ms),
cu acelasi ceas PCM de 35 ms pentru grup si individuale. Nu se schimba
bufferele, preumplerea, comenzile ALSA sau volumul. Corectia Stop din
0.37.11 este pastrata. 155 teste automate, inclusiv verificarea octetilor,
recuperarii si calculului limitelor fara deriva cumulativa. Necesita restart
Home Assistant. Nu modifica firmware-ul huburilor sau Zigbee si nu garanteaza
eliminarea zgomotului ori sincronizarea acustica.
