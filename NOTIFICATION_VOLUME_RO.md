# Sonerie fara salt de volum - 0.37.16 TEST

## Cauza si corectie

Numarul `*_sound_playback_volume` este aliasul volumului media. O automatizare
care seteaza acest numar la 50% inainte de `button.press` ridica radioul inca
activ. Restaurarea dupa efectul luminos poate lasa si muzica reluata la 50%.
Nu se poate deduce sigur dintr-o schimbare obisnuita de volum ca urmeaza un WAV.

Noul serviciu primeste soneria si volumul temporar intr-o singura cerere:

1. Rezerva prioritatea si detaseaza/opreste doar media hubului respectiv.
2. Confirma `/proc/asound/card0/pcm0p/sub0/status` inchis inainte de gain.
   Daca receiverul propriu ramane activ, curata si verifica o singura data.
   Lipsa confirmarii sau BUSY persistent opreste cererea, fara volum ridicat.
3. Aplica pe hub volumul temporar si cere o singura redare WAV locala.
4. La final/Stop/eroare, elimina override-ul si confirma volumul normal curent.
5. Reia playerul individual sau elibereaza hubul pentru reintrare in grup.
   Pornirea receiverului confirma din nou volumul normal inainte de ALSA.

Volumul principal nu este modificat sau restaurat dintr-o captura veche.
Schimbarile lui in timpul soneriei se pastreaza pentru reluare. Cererile media
de gain in asteptare nu suprascriu volumul temporar. Mute al hubului ramane activ.
Mute de grup se reaplica la pregatirea receiverului grupului, ca si anterior.
Nu se modifica sunetele originale, firmware-ul, Zigbee sau helper-ele audio.

## Automatizare

Necesita integrarea 0.37.16. Inlocuieste automatizarile existente cu variantele
din `automations/`, nu crea duplicate cu acelasi trigger MQTT:

- `Sonerie_Living_Cedare_Inainte_Volum_03716.yaml`: single, hub .226, WAV la 50%.
- `Sonerie_Dormitor_Cedare_Inainte_Volum_03716.yaml`: patru double consecutive,
  hub .222, WAV la 10% noaptea sau 50% ziua. Secventa incompleta nu atinge volumul.

Ambele pastreaza culorile rosu-albastru, timpii, restaurarea luminii si mode single.
Calea WAV vine din atributul `file_path` al butonului existent, nu este ghicita.
Nu mai sunt necesare actiuni `number.set_value` pentru sonerie sau restaurare.
Apelurile obisnuite de buton/serviciu fara override pastreaza volumul comun.

```yaml
action: aqara_m1s_zigbee_router.play_sound
data:
  host: 192.168.0.226
  path: "{{ state_attr('button.living_mp_hub_zigbee_router_192_168_0_226_play_ch_sonerie_2x', 'file_path') }}"
  volume_percent: 50
```

## Volum fin eliminat

Ramane numai volumul principal, cu aceleasi ID-uri si precizie 0.01%.
Entitatea `*_radio_fine_trim` este eliminata din registrul HA la actualizare;
offsetul ei nu mai este aplicat. Referintele la ea din carduri/automatizari
trebuie eliminate acolo. Nu se schimba regulile de pas ale cardurilor existente.

## Verificare

Testele locale acopera ordinea gain/handover/resume, ALSA ocupat, cereri gain
in asteptare, mute, inlocuire WAV, anulare, erori si migrarile. Bufferul comun,
ceasul 35 ms, transportul 105 ms si comenzile receiverelor sunt comparate cu
0.37.15. Arhiva nu a fost instalata pe HA si nu a fost verificata acustic live.
