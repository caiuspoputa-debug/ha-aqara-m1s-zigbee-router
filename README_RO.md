# Aqara M1S Zigbee Coordinator + Router v0.34.1 TEST

Versiune de test construită peste baza de recuperare `0.34.0`. Modulele confirmate pentru sunete, media player, volum, buton fizic, MQTT comun, Wi-Fi și diagnostic au rămas neschimbate.

## Coordinator

- Coordinatorul este permanent activ din perspectiva Home Assistant.
- Nu există switch, formular sau metodă internă pentru oprirea lui.
- Vechea entitate `*_coordinator_radio` este eliminată automat din registru.
- Rejoin este disponibil numai pentru Router.
- Ring Light pentru Coordinator folosește helperul validat `M1S_IO_V2` numai la o comandă trimisă din Home Assistant.
- Illuminance pentru Coordinator folosește același helper o dată la 60 de secunde (`lux-start`, o secundă pentru conversie, `lux-get`).
- Comenzile sideband folosesc sesiuni Telnet noi și nu folosesc traseul UART al Routerului sau portul 1886 al Coordinatorului.
- O eroare sideband face indisponibile numai Ring Light și Illuminance; hubul, sunetele, MQTT și Zigbee2MQTT rămân independente.
- Zigbee2MQTT continuă independent prin `zoh` la `tcp://HUB_IP:1886`.

## Funcții păstrate din 0.32

- Toate butoanele și fișierele audio Aqara.
- Media player, radio, volum și Fine Volume Trim.
- Evenimentele butonului fizic.
- MQTT comun pentru huburile existente și cele adăugate ulterior.
- Configurarea Wi-Fi și adresei de rețea.
- RGB și Illuminance pentru huburile Router.

Traseele RGB și Illuminance ale Routerului rămân neschimbate pe UART A5/A6. Integrarea nu scrie firmware și nu face flash. Această versiune a fost verificată fără conectare la un hub live și rămâne TEST până la confirmarea hardware.
