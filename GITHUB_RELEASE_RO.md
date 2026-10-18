# 0.37.19 TEST — compatibilitate cu registrul dispozitivelor Home Assistant

Corectează folosirea API-urilor depreciate raportată pe Home Assistant 2026.10.2.

- Cele patru căutări după identificator folosesc API-ul
  `async_get_device_by_identifier(identifier, entry.entry_id)` pe HA nou.
  Compatibilitatea pentru HA vechi caută numai în intrarea proprietară.
- Rezolvarea proprietarului pentru trigger-ele dispozitivului folosește
  helperul actual al domeniului, fără citirea `DeviceEntry.config_entries`
  pe HA nou. Fallback-ul este rezervat versiunilor fără API-ul nou.
- Identificatorii, ID-urile unice și migrarea identității existente sunt păstrate.
- Runtime-ul audio rămâne identic octet cu octet cu 0.37.18; supravegherea
  Coordinator/Zigbee2MQTT rămâne neschimbată din 0.37.17.

Detaliile API și sursele oficiale pentru termenele distincte de retragere sunt
în [DEVICE_REGISTRY_COMPAT_RO.md](DEVICE_REGISTRY_COMPAT_RO.md).

Integrarea și automatizările sunt livrate strict separat. Acest pachet de
integrare nu conține și nu instalează fișiere de automatizare.

## Instalare

Fă backup componentei existente. Înlocuiește componenta în
`/config/custom_components/aqara_m1s_zigbee_router` și repornește Home Assistant.
Nu copia întregul pachet în interiorul componentei și nu crea un folder dublu.
Nu trebuie șterse intrările existente sau repetată asocierea Zigbee.
Verifică dacă manifestul componentei instalate indică `0.37.19` și dacă
integrarea se încarcă fără erori. Verifică mesajele noi de registru după restart,
conform `DEVICE_REGISTRY_COMPAT_RO.md`. Instrucțiuni complete: `INSTALL_RO.md`.

## Statut

Pachet complet de integrare, nu imagine de firmware. Nicio instalare HA,
repornire HA sau probă audio live nu a fost făcută pentru acest build.
`VALIDATION.txt` identifică rezultatele automate finale; validarea pe huburile
reale rămâne de făcut. Păstrează marcajul pre-release **TEST**.

Acesta este text pentru o publicare ulterioară. Nu s-a creat sau publicat un
release GitHub. Pentru publicare, conținutul pachetului merge în rădăcina
repository-ului `ha-aqara-m1s-zigbee-router`, cu manifestul 0.37.19.
