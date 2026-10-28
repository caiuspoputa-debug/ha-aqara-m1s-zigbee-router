# Instalare integrare Aqara M1S 0.37.21

Aceasta arhiva contine integrarea HA, documentatia si testele sale.

1. Pastreaza o copie a componentei 0.37.20 instalate.
2. Copiaza folderul custom_components/aqara_m1s_zigbee_router din arhiva peste
   /config/custom_components/aqara_m1s_zigbee_router din Home Assistant.
3. Repornește Home Assistant si verifica versiunea 0.37.21 a integrarii.
4. Lasa o piesa sa se termine natural pe un hub si verifica finalul si trecerea
   la urmatoarea, apoi selecteaza o alta piesa de pe telefon.

Daca actualizezi prin repository-ul tau GitHub/HACS, continutul arhivei este
pentru radacina repository-ului integrarii. Dupa actualizare, reporneste HA si
verifica versiunea integrarii. Nu publica acest continut in repository-ul
add-on-ului YouTube; sunt doua componente diferite.

Add-on-ul 1.0.30 contine corectia selectiei manuale. Pentru instalarea lui,
publica sursele add-on-ului si reconstruieste/actualizeaza imaginea.
Corectia taierii confirmate de logul HA este in integrarea 0.37.21.

Bufferele, prebufferul, prefilling-ul initial si sincronizarea grupului sunt
pastrate. Se schimba doar tratarea lipsei temporare de date pentru fluxul Cast
continuu: acelasi receiver ramane deschis si finalul nu este golit prin STOP.
Nu se reinstaleaza firmware si nu se refac asocierile Zigbee.

Pentru revenire, restaureaza componenta 0.37.20 si reporneste Home Assistant.
Rezultatele locale curente sunt in TEST_REPORT.json, TEST_LOG.txt si VALIDATION.txt.
Testele locale nu reprezinta o verificare audio pe huburile reale.
