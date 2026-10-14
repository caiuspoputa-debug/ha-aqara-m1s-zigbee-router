# Audio local - 0.37.14 TEST

Prototip bazat pe 0.37.13, pregatit pentru GitHub. Nu este instalat automat.

## Ce se schimba

- WAV memorat: comanda Telnet -> `aplay` -> fisierul original de pe hub.
  Nu este descarcat in HA, procesat de FFmpeg sau copiat la alte volume.
  Conversia formatului WAV ramane pe hub prin ALSA `plug`, daca este necesara.
- Radio/media: FFmpeg din HA decodeaza in continuare sursa. PCM S32_LE, mono,
  32 kHz este trimis fara atenuare in HA. ALSA `softvol` aplica volumul pe hub,
  dupa transport. Reglajul nu depinde de Mi Home sau de playerul Aqara.
- WAV, radio si receiverul de grup selecteaza acelasi control local:
  `M1S Media Volume`. Nu este un mixer hardware global si nu controleaza
  sunete pornite independent de alte aplicatii.
- Sliderul media individual si numarul fostului volum WAV sunt aliasuri.
  ID-ul unic ramane `*_sound_playback_volume`; numele devine `Hub Volume`.
  Un entity_id redenumit anterior de utilizator nu este schimbat.
  Automatizarile care setau doar volumul WAV vor schimba acum si radioul.
- La restart, volumul restaurat al media playerului este valoarea comuna.
  Vechea valoare separata WAV (de exemplu 50%) nu o suprascrie.
- Fine Volume Trim ramane -2.00..+1.00 puncte procentuale si se aplica local
  pentru ambele tipuri de sunet. Volumul principal zero ramane liniste,
  chiar cu trim pozitiv. Mute nu opreste fluxul PCM.

## Grup si prioritate

Ceasul PCM de 35 ms, blocurile de 105 ms / 13.440 octeti, istoria comuna,
prefill-ul si dimensiunile bufferelor sunt pastrate. Nu se adauga cozi
individuale de grup, alt cronometru sau resampling separat pe hub.
Selectarea rutei ALSA locale este totusi o schimbare audio reala; numai
testele software nu pot garanta sincronizarea auzita intre camere.

Volumul grupului seteaza volumul comun al huburilor selectate, dar nu al
celor folosite independent. O ajustare individuala ulterioara se pastreaza
la reintrarea acelui hub; urmatoarea schimbare a volumului de grup o inlocuieste.
Mute de grup ramane pentru redarea grupului, nu pentru WAV-ul prioritar
care detine temporar acel hub.

WAV-ul foloseste arbitrul existent de prioritate asupra audio-ului acelui hub.
La final, radioul individual revine numai daca intentia de redare este inca
activa; pentru grup, hubul asteapta reintrarea comuna existenta. Un Stop
explicit nu este anulat de finalul notificarii. Celelalte camere nu sunt
oprite direct de WAV, dar bariera existenta de reintrare poate produce
scurta pauza comuna deja documentata in versiunile precedente.

Stop-ul local verifica tokenul, PID-ul, momentul pornirii si comanda procesului.
Nu foloseste `killall`, nu opreste `mha_basis`, Zigbee, Wi-Fi sau MQTT.
Anularea unei porniri asteapta rezultatul si curata numai sesiunea detinuta.

## Componentele locale

La prima initializare a unui Router online se pregatesc `volume_ctl`,
`alsa.conf` si `sound.sh` in `/data/m1s_audio_03714`. Executabilul static
MIPS32 little-endian este livrat impreuna cu sursa C. Fisierele existente
cu SHA256 corect nu sunt rescrise. Transferul foloseste fragmente de 512
caractere base64, verificare SHA256 si inlocuire atomica. Se cer minimum
8 MiB liberi dupa fisierele temporare. Nu se modifica `/etc/asound.conf`,
firmware-ul sau WAV-urile originale. Coordinatorul nu primeste componente audio.

Prima instalare poate dura mai mult decat o apasare ulterioara. Daca hubul
este offline sau nu permite crearea controlului ALSA, se raporteaza eroare
si se incearca din nou la urmatorul Play. Nu se porneste automat redarea
fara reglaj local, deoarece PCM-ul transportat nu mai este atenuat in HA.

Controlul are 1024 trepte logaritmice, aproximativ -80 dB..0 dB. Interfata
cere pasi de 0.01%; nivelul real este cuantizat de ALSA, nu reproduce exact
fiecare procent. Zero este mute. Modificarile sunt comasate pentru 30 ms,
apoi utilitarul aplica o rampa locala de pana la aproximativ 35 ms. Nu este
o promisiune de latenta totala: Telnet, reteaua si bufferul ALSA contribuie.

Cerinte: Router MIPS32 little-endian, ALSA `plug` si `softvol`,
`/dev/snd/controlC0`, `aplay`, `base64`, `sha256sum`, `awk`, `df`, Telnet
si acces de scriere la `/data` si `/tmp`.

`play_sound` accepta WAV-uri existente sub `/data/musics`, pe un Router
configurat. `play_url` descarca un WAV in RAM pe hub; descarcarea este
oprita dupa 30 s si fisierele propriei sesiuni sunt sterse la final.
Nu se poate reda pe un IP neconfigurat, fara control local.

Documentatia ALSA:
[PCM plugins](https://www.alsa-project.org/alsa-doc/alsa-lib/pcm_plugins.html).

## Validare si probe ramase

Probele anterioare pe .224 au confirmat volume diferite pentru WAV prin
playerul Aqara si pentru radio printr-un control ALSA local, fara reporniri
intre reglajele radioului. Nu au confirmat aceasta integrare finala: ea
unifica ambele trasee prin ALSA, cu un wrapper `plug` pentru WAV.

Testele automate si hashurile sunt in TEST_REPORT.json, TEST_LOG.txt,
VALIDATION.txt si SHA256SUMS.txt. Acest build nu a facut instalare,
restart HA, test live de grup sau masurare a zgomotului.

Verificarea practica ramasa, dupa backup si instalare:

1. Pe un hub, acelasi WAV la doua niveluri mici, apoi radio cu reglaj live.
2. Radio -> WAV -> reluare, apoi Stop in timpul WAV-ului: sa nu revina radio.
3. Grup -> WAV pe un hub -> reintrare comuna; ascultarea decalajului intre camere.
4. Volum/mute in timpul redarii si o reconectare de hub.

Diagnostic: `volume_apply_mode=hub_alsa_softvol`, `local_volume_level`,
`local_volume_apply_pending`, `local_volume_error`, iar in grup nivelurile
si erorile membrilor. Acceptarea WAV in log nu masoara inceputul acustic.

Pentru revenire, restaureaza 0.37.13 si reporneste HA. Nu este necesara
resetarea hubului; vechea ruta nu foloseste configuratia versionata.
