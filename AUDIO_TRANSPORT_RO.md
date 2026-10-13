# Audio TCP - 0.37.12 TEST

Grupul si player-ele individuale au acum o tinta medie de 300 ms intre blocurile
TCP, fata de 490 ms in 0.37.11. Ceasul PCM ramane la 35 ms: blocurile contin
8 sau 9 perioade, adica 35.840 sau 40.320 octeti la 280 sau 315 ms.
Ciclul este 9, 9, 8, 9, 8, 9, 8 perioade: 7 trimiteri in 2,1 secunde.
Limitele sunt calculate din secventa PCM comuna, fara un al doilea cronometru
si fara eroare de rotunjire cumulativa. Aceeasi cantitate de sunet este
trimisa intr-o secunda. TCP si Wi-Fi pot fragmenta un bloc in mai multe pachete;
nu controlam direct pachetele radio sau traficul celorlalte servicii.

Ceasul audio ramane la 35 ms. Formatul S32_LE, 32 kHz, mono, volumul, rampa de
volum, comenzile ALSA si preumplerea de 1,4 secunde sunt cele din 0.37.11.
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
ascultarea sincronizarii intre camere. Diagnostic: tcp_batch_ms=300,
tcp_batch_min_ms=280, tcp_batch_max_ms=315 si tcp_batch_bytes=40320 (maxim)
pentru grup; single_tcp_batch_ms=300 si aceleasi limite pentru individuale.
tcp_batch_periods si single_tcp_batch_periods arata maximul de 9 perioade.
Testele software confirma ordinea octetilor si ciclul de viata, nu acustica.

Instalarea necesita repornirea Home Assistant pentru incarcarea modulelor
Python noi. Nu se schimba firmware-ul huburilor, IP-urile sau reteaua Zigbee.
Pentru revenire se restaureaza copia integrarii 0.37.11 si se reporneste HA.
