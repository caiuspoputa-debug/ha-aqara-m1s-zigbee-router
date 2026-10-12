# Stop grup - 0.37.11 TEST

Problema reprodusa: un proces cu stdout plin poate ramane blocat in wait(),
chiar dupa terminate(), daca datele iesirii nu sunt citite. Vechea ordine de
oprire astepta procesul dupa ce producatorul PCM putea deja sa fie inchis.

Corectia:

- Invalideaza redarea si opreste cititorii initiali, inclusiv producatorul PCM.
- Citeste si elimina stdout si stderr in timpul inchiderii FFmpeg.
- Nu trimite aceste date catre huburi si nu aplica volum asupra lor.
- Pastreaza limitele de timp si kill pentru un proces realmente blocat.
- Curata procesul si cititorii inclusiv daca operatia Stop este anulata.

Verificare: blocajul a fost reprodus cu o conducta reala plina; acelasi test
trece dupa corectie. Sunt testate si Stop complet, proprietarii anteriori ai
citirii, kill si anularea opririi. Raportul si rezultatul suitei sunt incluse.
Testarea este locala, nu o validare live a Home Assistant sau a sincronizarii.

Modulul player-elor individuale este identic cu cel din 0.37.9. Trimiterea
la 490 ms, ceasul comun, bufferul comun, preumplerea, ALSA si volumul grupului
nu sunt schimbate. Aceasta versiune nu este o corectie a decalajului acustic.

Nu a fost instalata pe server si nu a fost facut un restart pentru acest kit.
Instalarea ulterioara necesita restart Home Assistant pentru incarcarea codului.
