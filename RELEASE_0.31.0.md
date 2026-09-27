# 0.31.0 - Shared MQTT configuration

Open Configure on any M1S entry, then Shared MQTT - all hubs. These are integration-wide settings, not per-hub options. Nothing changes until the form is submitted and the broker accepts the connection.

Enter the LAN address of the same broker used by Home Assistant's MQTT integration. For the test HA installation this is expected to be 192.168.0.109, but no address or credentials are preset. This release does not create broker accounts or change HA's own MQTT integration.

Password is stored once in Home Assistant's integration storage and copied to each managed hub's MQTT configuration, never to entity attributes or logs. The form does not return the saved password; a blank password retains it. HA backups and hub backups contain credentials and need normal private handling. Transport is the existing plain LAN MQTT/Telnet path, without TLS.

Authenticated accounts with printable ASCII credentials are supported. Combined username and password length is limited to 80 characters for compatibility with the existing hub publisher. Broker login validation is from HA, not from every hub, and does not prove publish ACL permissions.

Online hubs synchronize on their existing watchdog cycle. The MQTT configuration sensor reports not_configured, pending, applied or failed; offline hubs are unavailable and retry on return. Failed writes retry after 60 seconds. Newly added hubs use the same settings. No telemetry event is synthesized during setup.

Only /data/m1s_button/m1s_button.conf is replaced, with restrictive permissions and a .before_shared backup when contents differ. The publisher reads this file on every event, so no radio restart is required. Frozen button topic IDs are preserved. applied means the configuration was written, not that HA received a button event.

An integration restart rechecks configurations; a hub reconnect reapplies them if necessary. A kit reinstall can overwrite MQTT settings; reload the integration after reinstalling a kit to reapply shared settings. Configuring an older integration alone does not revert hub files: restore the hub backup or enter the prior broker in this release before downgrading.

No JN5189 firmware, RGB/lux protocol, audio behavior or GPIO polling changes are included. Both roles keep their existing entity behavior.

Validation: Python syntax, JSON parsing, isolated manager tests, Paho callback tests and actual shell replacement tests. Full Home Assistant execution and live deployment have not been performed. The archive is an integration release, not a firmware kit.

Paho API reference: https://eclipse.dev/paho/clients/python/docs/
