# Publicare 0.37.14 TEST

Aceasta este integrarea Aqara M1S, nu App-ul Zigbee2MQTT ZoH.
Repository-ul din manifest:
[ha-aqara-m1s-zigbee-router](https://github.com/caiuspoputa-debug/ha-aqara-m1s-zigbee-router).

1. Continutul arhivei GITHUB trebuie pus in radacina repository-ului:
   `hacs.json`, `README.md` si `custom_components/`, fara folder suplimentar.
2. Commit-ul trebuie sa includa toate fisierele componentei, inclusiv
   `local_audio.py` si intregul folder `hub_audio/`, cu executabilul `volume_ctl`.
3. Creeaza tag-ul si release-ul `v0.37.14` din acel commit. Manifestul trebuie
   sa aiba `version: 0.37.14`. Este o versiune TEST; recomanda un pre-release.
4. Ataseaza arhiva si SHA256 la release. Nu doar ZIP-ul: codul si manifestul
   trebuie sa existe impreuna in commit-ul tag-ului citit de HACS.

## Descriere release

WAV-urile memorate se redau direct pe hub, fara transfer audio prin HA.
WAV, radio/media individual si receiverul de grup folosesc acelasi volum
software ALSA local. FFmpeg ramane pentru decodarea media, nu pentru volum.
Vechiul numar pentru volumul WAV devine alias al sliderului media, cu ID
pastrat. Automatizarile sale vor schimba acum si radioul. Fine trim ramane.

Se pastreaza prioritatile, intentia de reluare, Stop, istoria PCM comuna,
ceasul de 35 ms, blocurile de 105 ms si bufferele existente. Fisierele helper
sunt instalate automat numai pe Routere, cu verificare de spatiu si SHA256;
nu se modifica firmware-ul, Zigbee sau WAV-urile originale. Necesita restart HA.

Rezultatele testelor locale sunt in TEST_REPORT.json si VALIDATION.txt.
Pachetul final nu a fost instalat live. Sincronizarea auzita de grup,
predarea completa WAV -> muzica, conversia WAV si latenta reala raman de
verificat. Nu este o garantie de eliminare a zgomotului sau intreruperilor.

Instructiunile detaliate si revenirea la 0.37.13 sunt in LOCAL_AUDIO_RO.md.
