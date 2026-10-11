# Recuperarea automata a listei de sunete - 0.37.8 TEST

## Ce era gresit

Daca hubul nu raspundea la incarcarea integrarii, platforma de butoane folosea
lista de rezerva. Ascultatorul care ar fi refacut lista la reconectare apartinea
unui buton de refresh care nu mai era creat. Hubul putea deveni Conectat, dar
butoanele sunetelor ramaneau lipsa sau indisponibile pana la reincarcarea intrarii.

## Cum functioneaza acum

- Se foloseste aceeasi verificare interna care alimenteaza Hub Connectivity,
  fara referinte la ID-urile senzorilor, fara helper sau agent MQTT nou.
- Cand routerul revine online, integrarea citeste automat fisierele WAV.
- Hubul returneaza un marker de finalizare a scanarii. Nu este un fisier
  persistent si nu modifica scripturile de boot sau firmware-ul.
- Daca scanarea esueaza sau raspunsul este incomplet, lista existenta ramane
  pastrata. O actualizare ulterioara a conectivitatii declanseaza o noua incercare.
- Numai o scanare confirmata poate inlocui lista sau elimina un buton lipsa.
- Se pastreaza ID-urile unice, iar reincarcarea integrarii anuleaza sarcinile
  si ascultatorii vechi. Nu apare un buton suplimentar de Refresh.
- Pornirea HA nu asteapta ca toate routerele sa fie pornite.

Conectat este declansatorul verificarii, nu dovada ca fisierele exista sau ca
difuzorul reda. Markerul confirma citirea listei, nu starea retelei Zigbee.

## Instalare

Actualizeaza integrarea prin metoda folosita deja si reporneste HA o singura
data pentru incarcarea noului cod. Nu sterge si nu adauga din nou huburile.
Corectia nu necesita un kit sau o modificare pe routere.

## Limite si verificari

Pe 11 octombrie 2026 au fost verificate doar in citire cele sase routere:
.221-.225 au 28 sunete scene si 34 sunete personalizate; .226 are 18 scene si
29 personalizate. Fisierele sistem din music-us raman excluse intentionat.
Existenta fisierelor nu echivaleaza cu verificarea integritatii audio.

Corectia nu restaureaza cele 15 fisiere care lipsesc de pe .226 fata de .225
si nu repara problema anterioara de stocare UBIFS. Nu modifica redarea radio,
sincronizarea, volumul, MQTT, Wi-Fi/IP sau profilul Only Coordinator.

Scenariile de pornire offline, reconectare, eroare de scanare, evenimente
simultane si descarcare a integrarii sunt testate local cu substitute HA.
Noua citire a listei a fost verificata pe routerele reale, fara scrieri,
redare de sunete, reporniri sau instalarea integrarii in HA.
