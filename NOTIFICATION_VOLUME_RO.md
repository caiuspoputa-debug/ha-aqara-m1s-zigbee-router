# Volumul temporar al alertelor — 0.37.18 TEST

## Cauza si corectie

Numarul `*_sound_playback_volume` este aliasul volumului media. O automatizare
care seteaza acest numar la 50% inainte de `button.press` ridica radioul inca
activ. Restaurarea dupa efectul luminos poate lasa si muzica reluata la 50%.
Nu se poate deduce sigur dintr-o schimbare obisnuita de volum ca urmeaza un WAV.

`play_sound` și WAV-urile prioritare prin `play_url` primesc sunetul și volumul
temporar în aceeași cerere. `volume_percent` este opțional: fără el se folosește
sliderul individual curent al hubului, înainte de mute; dacă sliderul este 0%,
sunetul rămâne silențios. Volumul temporar nu modifică sliderul salvat.

În 0.37.18, alertele prioritare ocolesc implicit mute media individual și de grup,
fără să comute starea mute a playerelor. `respect_mute: true` păstrează pentru
cererea respectivă comportamentul anterior față de mute individual. Mute de grup
rămâne numai pentru muzica de grup. Butoanele de sunet folosesc politica implicită
și sliderul individual curent. Detalii: [SOUND_MUTE_POLICY_RO.md](SOUND_MUTE_POLICY_RO.md).

Ordinea aplicării:

1. Rezerva prioritatea si detaseaza/opreste doar media hubului respectiv.
2. Confirma `/proc/asound/card0/pcm0p/sub0/status` inchis inainte de gain.
   Daca receiverul propriu ramane activ, curata si verifica o singura data.
   Lipsa confirmarii sau BUSY persistent opreste cererea, fara volum ridicat.
3. Aplica pe hub volumul temporar si cere o singura redare WAV locala.
4. La final/Stop/eroare/anulare, elimină override-ul și confirmă volumul media
   curent, inclusiv mute curent, înainte de reluare. Lipsa confirmării nu permite
   reluare cu volumul temporar al alertei.
5. Reia playerul individual sau elibereaza hubul pentru reintrare in grup.
   Pornirea receiverului confirma din nou volumul normal inainte de ALSA.

Volumul principal și mute nu sunt restaurate dintr-o captură veche. Schimbările
manuale din timpul soneriei se păstrează pentru media reluată. Mute media nu
anulează o alertă care ocolește mute; pentru anulare se folosește Stop.
Cererile media de gain în așteptare nu suprascriu volumul temporar. Mute de grup
se reaplică la pregătirea receiverului grupului. Nu se salvează comutări mute
artificiale pentru a face alerta audibilă. La înlocuire, tokenul noii cereri
deține sunetul: curățarea cererii vechi nu îl oprește și nu aplică gain media
peste el, inclusiv pe traseele de eroare/anulare.
Nu se modifică sunetele originale, firmware-ul sau datele Zigbee.

## Apel API minimal

Exemplul de mai jos este un apel de serviciu pentru verificarea integrării,
nu o automatizare inclusă. Înlocuiește adresa și calea cu valorile reale ale
hubului. Pentru un sunet existent poți citi calea din atributul `file_path` al
butonului corespunzător. Apelurile fără `volume_percent` folosesc sliderul
individual brut.

Pauzele dintre apeluri WAV separate nu devin automat o sesiune audio comună:
media poate reveni între ele dacă nu este pe mute și intenția permite reluarea.

```yaml
action: aqara_m1s_zigbee_router.play_sound
data:
  host: 192.168.1.50
  path: "/data/musics/music-ch/alerta.wav"
  volume_percent: 50
```

## Volum fin eliminat

Ramane numai volumul principal, cu aceleasi ID-uri si precizie 0.01%.
Entitatea `*_radio_fine_trim` este eliminata din registrul HA la actualizare;
offsetul ei nu mai este aplicat. Referințele externe la ea din carduri sau
automatizări indică o entitate retrasă. Nu se schimbă regulile de pas ale
cardurilor existente.

## Instalarea integrării și compatibilitate

Fă backup componentei, înlocuiește
`/config/custom_components/aqara_m1s_zigbee_router`, repornește Home Assistant
și verifică versiunea `0.37.18` și încărcarea fără erori. Nu este necesară
repetarea asocierii huburilor sau dispozitivelor Zigbee.

Integrarea și automatizările sunt livrate strict separat; pachetul integrării
nu conține și nu instalează fișiere de automatizare. Comenzile explicite de
mute/unmute media ale unui client existent schimbă în continuare playerul;
noua politică a alertei nu le suprimă. La fel, `number.set_value` pe aliasul
volumului schimbă volumul media comun.

## Verificare

`VALIDATION.txt` identifică rularea automată finală a acestui pachet. Rezultatele
0.37.16/0.37.17 sunt istorice, nu testare a politicii noi. Supravegherea
Coordinator/Zigbee2MQTT din 0.37.17 este păstrată fără modificări. Nu s-a instalat
pachetul, nu s-a repornit HA și nu s-a efectuat verificare acustică live în
această sesiune.
