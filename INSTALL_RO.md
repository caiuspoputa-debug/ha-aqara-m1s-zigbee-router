# Instalare integrare Aqara M1S 0.37.19 TEST

Această arhivă conține numai integrarea, documentația ei și testele proprii.

1. Păstrează o copie a componentei instalate.
2. Extrage arhiva într-un folder temporar. Copiază folderul
   `custom_components/aqara_m1s_zigbee_router` peste cel din
   `/config/custom_components/aqara_m1s_zigbee_router` din Home Assistant.
3. Repornește Home Assistant și verifică încărcarea versiunii 0.37.19.
4. Verifică dacă manifestul instalat indică `0.37.19` și dacă mesajele noi de
   după restart nu mai raportează apelurile depreciate de registru corectate.
   Detalii și surse oficiale: `DEVICE_REGISTRY_COMPAT_RO.md`.

Audio-ul este păstrat identic din 0.37.18. Regula este implicită pentru
WAV-uri prioritare, butoanele de sunet și
`play_url`. Pentru un apel care trebuie să respecte MUTE individual există
`respect_mute: true`. `volume_percent` este volumul temporar al sunetului;
în lipsa lui se folosește sliderul individual salvat, inclusiv valoarea 0%.

La final se reaplică volumul media curent înainte de reluare/reintrare în grup.
Modificările manuale făcute în timpul sunetului rămân valabile pentru media.
Supravegherea coordonatorului din 0.37.17 și identitățile entităților sunt păstrate.
Nu se refac asocierile huburilor sau dispozitivelor Zigbee.

Pentru revenire, restaurează componenta precedentă și repornește Home Assistant.

Rezultatele locale finale ale versiunii 0.37.19 sunt identificate în
`VALIDATION.txt`; rezultatele anterioare sunt istorice până la noua rulare.
Pachetul nu a fost instalat pe Home Assistant și nu a fost verificat audio
pe huburile reale. Detalii în README_RO.md, DEVICE_REGISTRY_COMPAT_RO.md,
SOUND_MUTE_POLICY_RO.md, TEST_REPORT.json și TEST_LOG.txt din arhivă.
