# 0.37.21 — Finalul piesei la trecerea automata Cast

Logul HA primit la 2026-10-28 22:27:33 confirma ca integrarea 0.37.20 a intrat
in `single rebuffer started ... action=stop_receiver` pentru playerul Cezara.
Acea cale golea lotul PCM in asteptare si oprea `nc`/`aplay` de pe hub. Sunetul
deja trimis in bufferul hubului putea fi taiat chiar daca sursa revenea imediat.

Corectia este limitata la URL-urile HTTP(S) de flux Cast continuu:
`/stream/<receiver>/<serial numeric>.wav`. Recunoasterea nu fixeaza IP-ul sau
portul si functioneaza si pentru o sesiune restaurata.

Cand coada HA ramane temporar fara PCM, integrarea:

1. Trimite lotul partial existent, folosind aceeasi functie de scriere.
2. Pastreaza conexiunea TCP si receiverul existente; nu trimite STOP.
3. Asteapta PCM real sau sfarsitul producatorului, verificand generatia si
   oprirea explicita la fiecare perioada existenta de 35 ms.
4. Reia acelasi flux in ordinea originala. Nu adauga cadre de tacere, prefill
   suplimentar, offset de pozitie sau o noua origine a ceasului.

Limita existenta de 5 secunde pentru o sursa blocata este pastrata. Erorile reale
TCP/ALSA si Stop sau schimbarea sursei pastreaza mecanismele existente.
Ceasul obisnuit si regula existenta de recuperare dupa jitter nu sunt schimbate.
Radio si alte surse urmeaza in continuare comportamentul lor anterior.

Nu sunt schimbate dimensiunile bufferelor, parametrii ALSA, prebufferul,
prefilling-ul initial, formatul PCM sau codul sincronizarii grupului.

Mesajul pentru o lipsa temporara Cast trebuie sa indice pastrarea receiverului,
nu vechiul `single rebuffer started ... action=stop_receiver`. Corectia elimina
acest mecanism confirmat de taiere; nu identifica motivul exact pentru care
datele au lipsit temporar in amonte.

Versiunea 1.0.30 a add-on-ului corecteaza separat o cerere de selectie manuala
depasita care putea publica STOPPED peste piesa noua. Cele doua versiuni se pot
folosi impreuna. Aceasta arhiva contine integrarea, nu firmware pentru hub.

Testele ruleaza codul de productie cu PCM etichetat si evenimente controlate.
Nu s-a instalat automat acest build in HA si nu s-a verificat acustic pe hub.
