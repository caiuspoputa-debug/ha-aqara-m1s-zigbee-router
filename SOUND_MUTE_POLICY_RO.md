# Alerte prioritare și mute media — 0.37.18 TEST

În această versiune, mute pentru muzică nu mai împiedică implicit o alertă
prioritară. Regula se aplică central WAV-urilor stocate, butoanelor de sunet,
serviciului `play_sound` și WAV-urilor prioritare pornite prin `play_url`.
Nu trebuie adăugat unmute în fiecare automatizare.

## Regula de volum

- `volume_percent` prezent: volumul temporar al alertei, fără modificarea
  sliderului media salvat.
- `volume_percent` absent: valoarea curentă a sliderului individual al hubului,
  înainte de aplicarea mute; nu valoarea efectivă zero produsă de mute.
- Un slider individual la **0%** rămâne zero când parametrul lipsește.
  Ocolirea mute nu inventează un volum de rezervă.
- Mute individual și mute de grup își păstrează starea în Home Assistant.
  Override-ul aparține sunetului curent, nu preferințelor media persistente.

Exemplu pentru un WAV deja stocat:

```yaml
action: aqara_m1s_zigbee_router.play_sound
data:
  host: 192.168.1.50
  path: "/data/musics/music-ch/alerta.wav"
  volume_percent: 50
```

Același contract se aplică unui WAV accesibil prin URL:

```yaml
action: aqara_m1s_zigbee_router.play_url
data:
  host: 192.168.1.50
  url: "http://ADRESA_LAN_HA:PORT/local/alerta.wav"
  volume_percent: 50
```

Înlocuiește URL-ul cu o adresă accesibilă de pe hub. Pentru WAV-ul stocat
folosește calea reală, de exemplu atributul `file_path` al butonului existent.

## Optarea pentru comportamentul anterior

`respect_mute` este `false` implicit. Adaugă `respect_mute: true` în apelul
`play_sound` sau `play_url` dacă acel sunet trebuie să respecte mute individual
al hubului. Acesta este comportamentul anterior pentru mute individual.
Mute de grup rămâne, ca înainte, un control pentru muzica de grup; parametrul
nu transformă mute de grup într-un întrerupător global pentru alerte.

```yaml
action: aqara_m1s_zigbee_router.play_sound
data:
  host: 192.168.1.50
  path: "/data/musics/music-ch/alerta.wav"
  volume_percent: 35
  respect_mute: true
```

| Situație | Comportament |
| --- | --- |
| Hub individual pe mute, politică implicită | Alerta folosește volumul temporar sau sliderul individual brut. |
| Hub individual pe mute, `respect_mute: true` | Alerta respectă mute individual. |
| Numai grupul pe mute | Mute de grup rămâne aplicat muzicii de grup; nu oprește alerta. |
| Slider 0%, fără `volume_percent` | Alerta este silențioasă. |
| Mute/volum schimbat manual în timpul alertei | Alegerea curentă este păstrată pentru media de după alertă. |

Mute media schimbat manual în timpul unei alerte cu politica implicită nu
anulează ocolirea mute pentru alerta respectivă. Oprește sunetul prin mecanismul
normal Stop dacă vrei să îl anulezi; nu folosi mute media drept Stop pentru alertă.

## Predare și restaurare

Integrarea revendică prioritatea numai pe hubul țintă, oprește/detașează media
și confirmă eliberarea ALSA înainte de aplicarea volumului alertei. Dacă eliberarea
sau aplicarea volumului nu poate fi confirmată, sunetul nu primește o pornire
necontrolată la volum ridicat.

La final, Stop, eroare sau anulare, override-ul este retras și se restabilește
**volumul media curent înainte de reluare/reintrare în grup**. Acesta include mute
curent și, pentru receiverul de grup, setările curente de grup. Nu se restaurează
o captură veche care ar anula alegerea făcută manual între timp. Dacă restaurarea
nu este confirmată, media nu trebuie reluată cu volumul temporar al alertei.

La înlocuirea unui sunet, tokenul noii cereri deține sunetul și override-ul său.
O cerere veche, anulată sau întârziată, nu poate opri sunetul nou și nu poate
restaura volumul media peste alerta nouă. Verificările de intenție curentă
continuă să decidă dacă muzica se reia; Stop făcut de utilizator nu este anulat.

Apelurile separate rămân separate: radioul poate reveni între două WAV-uri
programate cu pauză, dacă media nu este pe mute și intenția permite reluarea.
Această schimbare elimină necesitatea comutărilor mute din YAML și scurtele
fragmente de radio produse de acele comutări; nu introduce o sesiune comună
pentru un șir întreg de alerte.

## Instalarea integrării și compatibilitate

Instalarea integrării înseamnă backupul componentei existente, înlocuirea
folderului `/config/custom_components/aqara_m1s_zigbee_router`, restartul
Home Assistant și verificarea versiunii `0.37.18` și încărcării fără erori.
Nu se repetă asocierea huburilor sau dispozitivelor Zigbee. Apelurile API de mai
sus sunt exemple minimale de testare; înlocuiește adresa și calea cu valori reale.

Integrarea și automatizările sunt livrate strict separat. Pachetul integrării
nu conține și nu instalează automatizări. Comenzile explicite de mute/unmute
media executate de un client existent modifică în continuare starea playerului;
noua politică nu le anulează. `number.set_value` pe
`*_sound_playback_volume` schimbă volumul media comun, nu doar volumul alertei.

Supravegherea Coordinator/Zigbee2MQTT din 0.37.17 este păstrată fără modificări.
Pachetul nu a fost instalat și nu a fost verificat audio live în această sesiune.
Rezultatele automate finale sunt identificate în `VALIDATION.txt`; probele pe
huburile reale rămân necesare.
