# Audio TCP - 0.37.9 TEST

Grupul si player-ele individuale trimit cate 14 perioade audio intr-un singur
bloc TCP: 62.720 octeti la aproximativ 490 ms. Aceeasi cantitate de sunet este
trimisa intr-o secunda. TCP si Wi-Fi pot fragmenta un bloc in mai multe pachete;
nu controlam direct pachetele radio sau traficul celorlalte servicii.

Ceasul audio ramane la 35 ms. Formatul S32_LE, 32 kHz, mono, volumul, rampa de
volum, comenzile ALSA si preumplerea de 1,4 secunde sunt cele din 0.37.8.
Grupul pastreaza o singura istorie PCM si aceleasi limite de secventa pentru
toti membrii. Nu se adauga resampling sau cozi individuale pentru grup.

Datele ramase se trimit la finalul sursei. La Stop, schimbarea sursei si
refacerea unui receiver nu se retrimit blocurile vechi. Un membru lent ramane
izolat, fara schimbarea ceasului celorlalti.

Probele locale curate si zgomotul aparut la receptia datelor Wi-Fi sugereaza
o influenta a activitatii de retea. Ele nu separa definitiv driverul Wi-Fi,
alimentarea si cuplajul analogic. Blocurile rare au parut ceva mai linistite
in comparatia controlata, dar eliminarea zgomotului nu este garantata.

Verificare dupa instalare: aceeasi muzica, acelasi volum foarte mic, apoi
ascultarea sincronizarii intre camere. Diagnostic: tcp_batch_ms=490 si
tcp_batch_bytes=62720 pentru grup; single_tcp_batch_ms=490 pentru individuale.
Testele software confirma ordinea octetilor si ciclul de viata, nu acustica.

Instalarea necesita repornirea Home Assistant pentru incarcarea modulelor
Python noi. Nu se schimba firmware-ul huburilor, IP-urile sau reteaua Zigbee.
Pentru revenire se restaureaza copia integrarii 0.37.8 si se reporneste HA.
