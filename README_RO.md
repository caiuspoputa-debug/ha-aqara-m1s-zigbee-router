# Aqara M1S Zigbee Coordinator + Router v0.34.0

Versiune de recuperare construită direct din baza locală `0.32.0b2`, păstrând modulele confirmate pentru sunete, media player, volum, buton fizic, MQTT comun, Wi-Fi și diagnostic.

## Coordinator

- Coordinatorul este permanent activ din perspectiva Home Assistant.
- Nu există switch, formular sau metodă internă pentru oprirea lui.
- Vechea entitate `*_coordinator_radio` este eliminată automat din registru.
- Rejoin este disponibil numai pentru Router.
- RGB și LUX Coordinator nu sunt interogate în această versiune; nu există polling sideband și integrarea nu execută relay-ul Coordinator.
- Zigbee2MQTT continuă independent prin `zoh` la `tcp://HUB_IP:1886`.

## Funcții păstrate din 0.32

- Toate butoanele și fișierele audio Aqara.
- Media player, radio, volum și Fine Volume Trim.
- Evenimentele butonului fizic.
- MQTT comun pentru huburile existente și cele adăugate ulterior.
- Configurarea Wi-Fi și adresei de rețea.
- RGB și Illuminance pentru huburile Router.

Integrarea nu scrie firmware și nu face flash. RGB/LUX Coordinator vor fi adăugate numai după validarea separată a unei interfețe sideband care nu afectează Telnet, sunetele sau Zigbee2MQTT.
