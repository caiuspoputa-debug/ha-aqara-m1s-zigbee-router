# Verificare dupa instalare - 12 octombrie 2026

Nota 0.37.14: raportul de mai jos este numai istoric. Noua ruta cu WAV local
si volum ALSA comun nu a fost instalata sau validata de grup prin acest build.
Citeste LOCAL_AUDIO_RO.md si TEST_REPORT.json pentru situatia actuala.

Raport istoric pentru 0.37.9. Versiunea 0.37.13 este pregatita ca arhiva GitHub;
aceste rezultate vechi nu sunt o validare a intervalului nou de 105 ms.
In verificarea din 14 octombrie a fost confirmata 0.37.12 activa la 300 ms;
0.37.13 nu a fost instalata. Testele 0.37.13 sunt locale si automate,
nu masuratori ale sincronizarii sau zgomotului pe huburile reale.

- Integrarea 0.37.9 a fost instalata peste 0.37.8, cu copie de rezerva.
- Verificarea configuratiei Home Assistant a trecut; serverul a fost repornit.
- Grupul a reluat redarea cu toti cei sase membri pregatiti.
- Atributele grupului confirma tcp_batch_ms=490, tcp_batch_bytes=62720,
  tcp_batch_periods=14. Noul cod este activ, nu doar prezent pe disc.
- In verificarea efectuata dupa aproximativ trei minute, toate cele sase
  iesiri ALSA erau RUNNING, cu delay=4480, avail=0 si avail_max=1120.
  Jurnalele aplay verificate nu contineau underrun sau error.
- Grupul raporta zero rebuffer, resync, clock rebase si watchdog restart.
- Utilizatorul a raportat ca sunetul este mult mai bun dupa modificare.

Aceste rezultate nu reprezinta o masuratoare acustica a sincronizarii intre
camere si nici o garantie pentru functionare pe termen lung. A fost pastrat
ceasul comun si algoritmul de sincronizare, nu a fost masurata faza difuzoarelor.
