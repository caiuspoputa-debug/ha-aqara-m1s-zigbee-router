# 0.37.17 TEST — recuperare coordonator si control Zigbee2MQTT

Arhiva completa a integrarii Aqara M1S. Nu este o imagine de firmware si nu
inlocuieste aplicatia Zigbee2MQTT. Include toate fisierele versiunii 0.37.16,
cu modulele noi de supraveghere si preflight RCP.

Configure → Supraveghere Zigbee2MQTT pe intrarea coordinator permite alegerea
suplimentului exact, a topicului MQTT si a portului RCP. La activare, pornirea
suplimentului este trecuta pe manual si watchdog-ul Supervisor este dezactivat;
dezactivarea supravegherii restabileste politica originala verificata.

La caderea coordonatorului: starea bridge MQTT devine offline si suplimentul
este oprit. La revenire: stop confirmat, reset runtime RCP, stabilizare,
proba exclusiva Spinel/PHY, inchiderea probei, start Z2M si confirmare noua.
Entitatile raman in registru si devin indisponibile, nu se sterg.

Documentatia principala este COORDINATOR_GUARD_RO.md. Codul audio nu este
modificat. Nu s-a instalat nimic si nu s-a facut test pe hardware in aceasta sesiune.

Pentru o publicare ulterioara: continutul arhivei merge in radacina repository-ului
ha-aqara-m1s-zigbee-router. Manifestul este 0.37.17; versiunea trebuie marcata
pre-release TEST pana dupa testele de acceptanta pe coordonatorul real.
Nu s-a creat si nu s-a publicat vreun release GitHub.
