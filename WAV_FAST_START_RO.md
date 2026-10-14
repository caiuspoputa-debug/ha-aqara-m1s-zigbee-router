# WAV unic si pornire rapida - 0.37.15 TEST

## Cauza redarii triple

Inspectia numai-citire pe hubul de test .224 a confirmat ca cele trei fisiere
audio instalate aveau hashurile arhivei 0.37.14. Executabilul nativ Aplay,
citit si verificat prin SHA256, contine un contor implicit de trei redari
si un `sleep(2)` intre ele. Optiunea ascunsa `-x` modifica acest contor.
Scriptul 0.37.14 nu o transmitea; probele locale mai vechi foloseau `-x 1`.

Scriptul nou cere `aplay -D m1s_media -x 1`, inclusiv pentru WAV prin URL.
Nu se modifica WAV-ul, formatul, volumul sau comenzile receiverelor radio/grup.
Executabilul Aqara nu este modificat sau inclus in arhiva.

## Traseul rapid

Rezervarea prioritatii si invalidarea unei porniri vechi se fac in continuare.
Decizia de hub liber este luata dupa obtinerea lockului playerului individual.
Un lock deja ocupat, FFmpeg, writer sau watcher activ pastreaza oprirea remote.
O pregatire de grup in curs este considerata o predare activa, nu hub liber.

Fara transport activ, nu se mai trimite Stop individual si nu se mai asteapta
pauza fixa de 250 ms. Scriptul hubului verifica totusi ca ALSA este liber
inainte sa porneasca WAV-ul. Daca raspunde explicit BUSY, inainte de orice
redare, HA poate curata doar receiverul sau radio si incerca o singura data
din nou. Daca ramane ocupat, raporteaza eroare si elibereaza prioritatea.
Un timeout sau o confirmare pierduta nu determina repetarea pornirii WAV.

Conexiunea privata Telnet pentru audio ramane deschisa intre gain/start/status.
Comenzile sunt serializate si nu pot amesteca raspunsurile. La eroare se inchide
numai aceasta conexiune, fara replay; urmatoarea comanda incearca o conexiune
noua. La descarcarea integrarii conexiunea este deconectata, fara oprirea UART.

## Volum si sincronizare

Volumul comun este confirmat pe hub inainte de fiecare WAV, chiar pe calea
rapida. Daca verificarea volumului esueaza, WAV-ul nu este pornit. Nu se sare
peste gain pe baza unei valori memorate, care ar putea fi veche dupa reboot.
Sliderul, trimul, mute si rezolutia ALSA raman cele din 0.37.14.

Ceasul comun, istoria PCM, blocurile de 105 ms, bufferele, prefill-ul si Stop-ul
media raman neschimbate. Prioritatea si verificarea intentiei la reluare sunt
pastrate. Schimbarile sunt numai in pregatirea si comanda WAV, nu in playout.

## Verificare

TEST_REPORT.json, TEST_LOG.txt si VALIDATION.txt contin rezultatele automate.
Logul de acceptare separa asteptarea lockului, oprirea WAV anterior,
predarea prioritatii, confirmarea volumului si pornirea pe hub. Timpul pana
la acceptare nu masoara momentul acustic din difuzor.

Nu s-a instalat acest build pe HA si nu s-au pornit probe audio live in timpul
constructiei. Viteza efectiva si o singura redare trebuie ascultate dupa
instalare, pe un hub idle si apoi cu muzica activa. Prima pregatire a unui
hub sau prima reconectare poate ramane mai lenta. Nu exista garantie de timp.

Motorul ramane in /data/m1s_audio_03714; integrarea actualizeaza automat
sound.sh dupa hash. Nu este necesara o instalare manuala separata pe hub.
Instalarea componentei necesita restart HA. Pentru revenire se restaureaza
componenta 0.37.14 si se reporneste HA; acea versiune poate reintroduce repetarea.
