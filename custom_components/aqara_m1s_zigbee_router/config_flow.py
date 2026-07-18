from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)

from .const import (
    CONF_MQTT_PORT,
    DEFAULT_MQTT_PORT,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DOMAIN,
)


class AqaraM1SZigbeeRouterConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    VERSION = 1

    async def async_step_user(
        self,
        user_input=None,
    ):
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(
                user_input[CONF_HOST]
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=(
                    user_input.get("name")
                    or (
                        "Aqara M1S "
                        f"{user_input[CONF_HOST]}"
                    )
                ),
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(
                    CONF_PORT,
                    default=DEFAULT_PORT,
                ): int,
                vol.Optional(
                    CONF_MQTT_PORT,
                    default=DEFAULT_MQTT_PORT,
                ): int,
                vol.Optional(
                    CONF_USERNAME,
                    default=DEFAULT_USERNAME,
                ): str,
                vol.Optional(
                    CONF_PASSWORD,
                    default=DEFAULT_PASSWORD,
                ): str,
                vol.Optional(
                    "name",
                    default="Aqara M1S Zigbee Router",
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
