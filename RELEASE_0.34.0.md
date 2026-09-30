# Release 0.34.0

This recovery build starts from the locally preserved 0.32.0b2 integration, while reverting its unvalidated Coordinator RGB/lux experiment to the confirmed 0.31 behavior.

All sound, media, volume, button, shared MQTT, Wi-Fi and Router functions are retained. The only Coordinator behavior change is safety: no switch, options step or client method can stop the Coordinator, and the old switch registry entry is removed during setup.

The integration sends no Coordinator RGB/lux sideband requests. Zigbee2MQTT remains responsible for the Coordinator connection on port 1886. No firmware writing or flashing is performed.

WAV deletion retains explicit selection and confirmation, lexical path validation below `/data/musics`, mandatory backup-before-delete ordering and automatic integration reload. Both the Configure form and direct Home Assistant service now require explicit confirmation. Dedicated local regression tests cover these guarantees without contacting a hub.

The confirmation control is displayed above the WAV list, so it stays immediately visible even when the hub contains many sound files.
