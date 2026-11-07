# v0.37.22 — Corecții senzori și diagnostic MQTT

- Corectează înregistrarea celor două clase de senzori diagnostic folosind EntityCategory.DIAGNOSTIC și importul necesar.
- Adaugă IP-ul hubului și traceback-ul excepției la avertismentul de sincronizare MQTT. Reîncercarea după 60 de secunde este păstrată.
- Păstrează fixul Cast din 0.37.21. Fișierele audio sunt identice cu arhiva de bază.

Validare: 343 de teste trecute, sintaxă Python și JSON verificate. Testele folosesc simulări; această arhivă nu a fost testată pe huburi reale sau într-o instanță Home Assistant.

## Upload GitHub

1. Dezarhivează pachetul și încarcă fișierele sale în rădăcina repository-ului ha-aqara-m1s-zigbee-router, păstrând structura custom_components/aqara_m1s_zigbee_router. Nu încărca doar ZIP-ul în repository.
2. Creează un release cu tag-ul v0.37.22 pe commitul care conține fișierele noi.
3. Folosește titlul și descrierea de mai sus; atașează M1S_Integration_0.37.22_SENSOR_MQTT_FIX.zip ca asset.
4. Pentru instalare manuală, salvează o copie a folderului integrării, înlocuiește-l cu cel din pachet și repornește Home Assistant.

Pachetul nu modifică aqara_m1s_local, Tuya Local sau bridge-ul de climatizare. Modificările debug ale acelor integrări trebuie păstrate separat.
