# Compatibilitate registru dispozitive — 0.37.19 TEST

Versiunea 0.37.19 corectează folosirea API-urilor depreciate ale registrului
de dispozitive, raportată prin avertismente pe Home Assistant 2026.10.2.
Nu schimbă redarea audio sau supravegherea coordonatorului.

## Ce se schimbă în integrare

Cele patru căutări după identificator sunt limitate la intrarea de configurare
care deține hubul. Pe versiunile HA cu API-ul nou se folosește:

```python
device_registry.async_get_device_by_identifier(identifier, entry.entry_id)
```

Pentru HA mai vechi, fără această metodă, compatibilitatea caută identificatorul
numai printre dispozitivele intrării respective. Nu revine la căutarea globală
depreciată `async_get_device`. Această limitare se aplică atât identificatorului
vechi bazat pe IP, cât și celui stabil folosit deja de integrare.

Rezolvarea proprietarului în `device_trigger` folosește helperul de domeniu
`async_get_device_and_config_entry_for_domain` pe versiunile care îl oferă.
Accesul de compatibilitate necesar versiunilor vechi este folosit numai când
API-ul nou lipsește; HA nou nu citește proprietatea depreciată
`DeviceEntry.config_entries` pe această rută.

Identificatorii dispozitivelor, ID-urile unice ale entităților și regulile
migrării existente IP → identitate stabilă sunt păstrate. Nu se șterg și nu
se adaugă din nou intrările integrării. Nu este necesară repetarea asocierii
huburilor sau dispozitivelor Zigbee.

## De ce sunt necesare API-urile noi

Home Assistant limitează identificatorii la intrarea de configurare. Căutarea
veche poate fi ambiguă; metoda nouă primește și proprietarul. Pentru
`async_get_device`, documentația indică retragerea în Core **2027.8**.
[Anunțul oficial despre registrul cu un singur proprietar](https://contributors.home-assistant.io/blog/2026/07/21/device-registry-single-config-entry/)

Citirea `DeviceEntry.config_entries` produce avertisment pentru integrările
custom începând cu Core **2026.10**. Anunțul ulterior extinde disponibilitatea
acestei proprietăți până la **2027.10**, față de termenul inițial 2027.8.
Acest termen este distinct de cel al metodei de căutare de mai sus.
[Anunțul oficial despre proprietățile depreciate](https://contributors.home-assistant.io/blog/2026/09/15/device-entry-config-entries-deprecation/)

## Instalare și verificare

1. Păstrează o copie a componentei instalate.
2. Înlocuiește folderul
   `/config/custom_components/aqara_m1s_zigbee_router` cu componenta din pachet.
3. Repornește Home Assistant; o reîncărcare YAML nu încarcă noul cod Python.
4. Verifică versiunea `0.37.19` în manifestul instalat și încărcarea fără erori.
   Verifică mesajele produse după acest restart: ruta actualizată nu trebuie să
   mai raporteze apelurile depreciate `async_get_device` sau `config_entries`.
   Mesajele vechi rămase în istoric nu demonstrează o nouă apariție.

Integrarea și automatizările sunt livrate strict separat. Arhiva integrării
nu conține și nu instalează fișiere de automatizare.

## Ce rămâne păstrat și statutul verificării

- Fișierele runtime audio sunt identice octet cu octet cu 0.37.18: inclusiv
  politica WAV prioritar, `volume_percent`, `respect_mute` și restaurarea media.
- Supravegherea Coordinator/Zigbee2MQTT rămâne neschimbată din 0.37.17.
- Nu se scriu firmware, WAV-uri sau date Zigbee prin această corecție de API.

Rezultatele locale finale sunt identificate în `VALIDATION.txt`,
`TEST_REPORT.json` și `TEST_LOG.txt`; rezultatele copiate din versiunea anterioară
nu reprezintă testarea 0.37.19. Pachetul nu a fost instalat sau repornit pe Home
Assistant și nu a fost verificat pe huburile reale în această sesiune.

Pentru revenire, restaurează componenta precedentă din backup și repornește HA.
0.37.18 păstrează aceeași politică audio, dar conține apelurile depreciate
corectate în 0.37.19.
