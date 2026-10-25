# Corectie MQTT dupa schimbarea IP-ului - 0.37.20 TEST

## Problema

Agentul Router foloseste `TOPIC_ID=AUTO`, dar rezolva adresa in configuratia
runtime numai cand porneste. Dupa o schimbare de IP, reincarcarea vechii
integrari schimba abonamentele HA, nu si topicul agentului deja pornit.
Lumina si senzorii MQTT puteau astfel ramane indisponibili.

## Corectia

Sincronizarea MQTT existenta ruleaza in fundal dupa reincarcare/reconectare.
Tinta ei include acum si adresa clientului. Pentru un Router cu agentul MQTT
deja activat, integrarea trimite un helper temporar printr-o sesiune Telnet
izolata, fara sa instaleze vreun fisier permanent sau sa reporneasca hubul.

Helperul verifica rolul, activarea agentului, modul AUTO si adresa principala
curenta. Daca topicul este deja corect si serviciul ruleaza, nu reporneste nimic.
Altfel reporneste doar serviciul MQTT original al kitului. Confirma topicul
nou, serviciul si mesajele NOI de abonare/publicare. Logurile vechi nu confirma
o reparatie noua. Entitatile HA existente primesc date pe noile abonamente.

Corectia functioneaza si cand setarile comune ale brokerului nu au fost salvate
in HA: agentul continua sa foloseasca datele deja configurate pe hub.
O eroare nu marcheaza hubul fizic offline; sincronizarea reincearca dupa
60 de secunde, fara o bucla continua de restarturi.

## Ce ramane neschimbat

- Firmware Linux si JN5189; fara flash sau repornire de hub.
- Codul audio, gain-ul, mute, catalogul WAV si grupurile media.
- Brokerul si parola, in afara sincronizarii comune deja existente.
- ID-ul stabil al butonului. Acesta poate ramane intentionat diferit de IP.
- Identitatea dispozitivului, ID-urile entitatilor si corectia registrului HA.
- Coordonatoarele dedicate si supravegherea Zigbee2MQTT.

Nu se activeaza un agent dezactivat sau absent. Un topic numeric fixat manual
este respectat. Un receiver WAV activ, tunelul UART legacy sau mentenanta UART
amana reparatia pana la urmatoarea incercare. Agentii cu topic corect nu sunt
reporniti preventiv la fiecare reincarcare/poll.

## Instalare si acceptanta pe hardware

Inlocuieste componenta existenta din Home Assistant cu folderul
`custom_components/aqara_m1s_zigbee_router` si reporneste Home Assistant pentru
incarcarea codului Python nou. Nu copia integrarea Python pe hubul fizic M1S.
Nu sterge integrarea, dispozitivele sau entitatile existente.

Pentru GitHub, dezarhiveaza continutul in radacina repository-ului, exact ca
arhiva 0.37.19. Publicarea pe GitHub nu a fost executata.

Testul fizic ramas: schimba IP-ul din optiunile integrarii si asteapta
reincarcarea ei automata. Confirma ca lumina, luxul si telemetria revin fara
oprirea alimentarii. Verifica si o reincarcare cu topic deja corect, care nu
trebuie sa reporneasca agentul. Nu schimba adresa unui Coordinator pentru
testarea acestui mecanism Router.

Acest build este TEST, verificat local cu HA si huburi simulate. Nu a fost
instalat in HA si nu s-a executat o schimbare reala de IP cu acest build.
Reparatia manuala efectuata anterior pe hub nu valideaza automat codul nou.
Rezultatele exacte sunt in TEST_REPORT.json, TEST_LOG.txt si VALIDATION.txt.
