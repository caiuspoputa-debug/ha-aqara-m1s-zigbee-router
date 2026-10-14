# Audio TCP - 0.37.13 TEST

Grupul si player-ele individuale au acum blocuri TCP fixe de 105 ms,
fata de media de 300 ms in 0.37.12. Ceasul PCM ramane la 35 ms: fiecare
bloc contine 3 perioade, adica 13.440 octeti. Nu exista alternare de intervale.
Limitele sunt calculate din secventa PCM comuna, fara un al doilea cronometru
si fara eroare de rotunjire cumulativa. Aceeasi cantitate de sunet este
trimisa intr-o secunda. TCP si Wi-Fi pot fragmenta un bloc in mai multe pachete;
nu controlam direct pachetele radio sau traficul celorlalte servicii.

Ceasul audio ramane la 35 ms. Formatul S32_LE, 32 kHz, mono, volumul, rampa de
volum, comenzile ALSA si preumplerea de 1,4 secunde sunt cele din 0.37.12.
Grupul pastreaza o singura istorie PCM si aceleasi limite de secventa pentru
toti membrii. Nu se adauga resampling sau cozi individuale pentru grup.

Datele ramase se trimit la finalul sursei. La Stop, schimbarea sursei si
refacerea unui receiver nu se retrimit blocurile vechi. Un membru lent ramane
izolat, fara schimbarea ceasului celorlalti.

Probele locale curate si zgomotul aparut la receptia datelor Wi-Fi sugereaza
o influenta a activitatii de retea. Ele nu separa definitiv driverul Wi-Fi,
alimentarea si cuplajul analogic. Blocurile rare au parut ceva mai linistite
in comparatia controlata, dar eliminarea zgomotului nu este garantata.

Varianta 105 ms este o proba pentru intreruperile observate la 300 ms.
Pe hubul inspectat, ALSA avea 4480 de cadre la 32 kHz, adica 140 ms,
chiar daca receiverul solicita 2 secunde. Aceasta este valoarea activa,
nu o limita maxima hardware demonstrata. Alegerea 105 ms nu garanteaza
eliminarea timeout-urilor: rezervele TCP/FIFO si activitatea receiverului
conteaza in continuare. Mai multe trimiteri pot schimba zgomotul auzit.

Verificare dupa instalare: aceeasi muzica, acelasi volum foarte mic, apoi
ascultarea sincronizarii intre camere. Diagnostic: tcp_batch_ms=105,
tcp_batch_min_ms=105, tcp_batch_max_ms=105 si tcp_batch_bytes=13440
pentru grup; single_tcp_batch_ms=105 si aceleasi limite pentru individuale.
tcp_batch_periods si single_tcp_batch_periods sunt 3.
Testele software confirma ordinea octetilor si ciclul de viata, nu acustica.

Instalarea necesita repornirea Home Assistant pentru incarcarea modulelor
Python noi. Nu se schimba firmware-ul huburilor, IP-urile sau reteaua Zigbee.
Pentru revenire se restaureaza copia integrarii 0.37.12 si se reporneste HA.
