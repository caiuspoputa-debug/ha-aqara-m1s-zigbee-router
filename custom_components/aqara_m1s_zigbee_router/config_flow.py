from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    FileSelector,
    FileSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from .const import (
    CONF_BUTTON_TOPIC_ID,
    CONF_DEVICE_MAC,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DATA_CLIENTS,
    DOMAIN,
    MANAGED_SOUND_ROOT,
)
from .client import AqaraM1SClient
from .device import entry_title_with_host
from .sound_upload import destination_for_filename, read_uploaded_sounds

_LOGGER = logging.getLogger(__name__)
SOUND_RELOAD_DELAY_SECONDS = 1.0


class AqaraM1SZigbeeRouterConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    VERSION = 1

    def __init__(self) -> None:
        self._pending_user: dict | None = None
        self._initial_network: dict[str, str] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return AqaraM1SZigbeeRouterOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input=None,
    ):
        errors = {}

        if user_input is not None:
            client = AqaraM1SClient(
                host=user_input[CONF_HOST],
                port=user_input.get(CONF_PORT, DEFAULT_PORT),
                username=user_input.get(CONF_USERNAME, DEFAULT_USERNAME),
                password=user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD),
            )
            try:
                network = await self.hass.async_add_executor_job(
                    client.network_status
                )
            except (OSError, RuntimeError, TimeoutError):
                errors["base"] = "network_manager_unavailable"
            else:
                self._pending_user = dict(user_input)
                self._initial_network = network
                await self.async_set_unique_id(f"mac:{network['wifi_mac']}")
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: user_input[CONF_HOST]}
                )
                return await self.async_step_network_setup()
            finally:
                await self.hass.async_add_executor_job(client.disconnect)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(
                    CONF_PORT,
                    default=DEFAULT_PORT,
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

    async def async_step_network_setup(self, user_input=None):
        """Choose DHCP or safely test a static /24 address during setup."""
        if self._pending_user is None or self._initial_network is None:
            return await self.async_step_user()
        errors = {}
        current_ip = self._initial_network.get("current_ip", self._pending_user[CONF_HOST])
        current_octet = int(current_ip.rsplit(".", 1)[-1])
        if user_input is not None:
            data = dict(self._pending_user)
            network = self._initial_network
            if user_input["mode"] == "static":
                client = AqaraM1SClient(
                    host=data[CONF_HOST],
                    port=data.get(CONF_PORT, DEFAULT_PORT),
                    username=data.get(CONF_USERNAME, DEFAULT_USERNAME),
                    password=data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
                )
                try:
                    new_host, network = await self.hass.async_add_executor_job(
                        client.set_static_ipv4, user_input["last_octet"]
                    )
                except ValueError:
                    errors["base"] = "network_invalid_octet"
                except (OSError, RuntimeError, TimeoutError):
                    errors["base"] = "network_change_failed"
                else:
                    data[CONF_HOST] = new_host
                finally:
                    await self.hass.async_add_executor_job(client.disconnect)
            if not errors:
                data[CONF_DEVICE_MAC] = network["wifi_mac"]
                data[CONF_BUTTON_TOPIC_ID] = network.get("button_topic_id", "")
                return self.async_create_entry(
                    title=entry_title_with_host(
                        data.get("name", "Aqara M1S Zigbee Router"),
                        data[CONF_HOST],
                    ),
                    data=data,
                )
        return self.async_show_form(
            step_id="network_setup",
            data_schema=vol.Schema(
                {
                    vol.Required("mode", default="dhcp"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": "dhcp", "label": "Automat (DHCP)"},
                                {"value": "static", "label": "IP static"},
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required("last_octet", default=current_octet): vol.All(
                        vol.Coerce(int), vol.Range(min=2, max=254)
                    ),
                }
            ),
            description_placeholders={"current_ip": current_ip},
            errors=errors,
        )


class AqaraM1SZigbeeRouterOptionsFlow(
    config_entries.OptionsFlowWithConfigEntry
):
    """Native file manager available from the integration Configure button."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__(config_entry)
        self._upload_task: asyncio.Task[None] | None = None
        self._upload_error = False
        self._network_task: asyncio.Task | None = None
        self._network_error = False

    @property
    def _client(self):
        return self.hass.data[DOMAIN][DATA_CLIENTS][self.config_entry.entry_id]

    async def async_step_init(self, user_input=None):
        menu_options = ["network_address", "change_wifi", "upload_sound"]
        try:
            sounds = await self.hass.async_add_executor_job(
                self._client.list_sounds
            )
        except (OSError, RuntimeError):
            sounds = []
        if any(
            path.startswith(f"{MANAGED_SOUND_ROOT}/")
            for path in sounds
        ):
            menu_options.append("delete_sound")
        menu_options.extend(["rejoin_zigbee", "finish"])
        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
        )

    async def _async_apply_network(self, mode: str, last_octet: int) -> None:
        data = dict(self.config_entry.data)
        if mode == "static":
            new_host, status = await self.hass.async_add_executor_job(
                self._client.set_static_ipv4, last_octet
            )
            data[CONF_HOST] = new_host
        else:
            status = await self.hass.async_add_executor_job(self._client.network_status)
            await self.hass.async_add_executor_job(self._client.return_to_dhcp)
        data[CONF_DEVICE_MAC] = status["wifi_mac"]
        data[CONF_BUTTON_TOPIC_ID] = status.get("button_topic_id", "")
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data=data,
            title=entry_title_with_host(
                data.get("name", self.config_entry.title), data[CONF_HOST]
            ),
            unique_id=f"mac:{status['wifi_mac']}",
        )

    async def async_step_network_address(self, user_input=None):
        """Show status and safely change the hub IPv4 mode."""
        errors = {}
        if self._network_task is not None:
            if not self._network_task.done():
                return self.async_show_progress(
                    step_id="network_address",
                    progress_action="changing_network",
                    progress_task=self._network_task,
                )
            try:
                await self._network_task
            except Exception as err:
                _LOGGER.exception("Safe IPv4 change failed: %s", err)
                self._network_error = True
                next_step_id = "network_address"
            else:
                next_step_id = "network_finish"
            finally:
                self._network_task = None
            return self.async_show_progress_done(next_step_id=next_step_id)

        if self._network_error:
            errors["base"] = "network_change_failed"
            self._network_error = False
        try:
            status = await self.hass.async_add_executor_job(self._client.network_status)
        except (OSError, RuntimeError, TimeoutError):
            errors["base"] = "network_manager_unavailable"
            status = {
                "mode": "unknown",
                "current_ip": str(self.config_entry.data.get(CONF_HOST, "")),
                "netmask": "-",
                "gateway": "-",
                "wifi_mac": "-",
            }

        current_ip = status.get("current_ip", str(self.config_entry.data.get(CONF_HOST, "")))
        try:
            current_octet = int(current_ip.rsplit(".", 1)[-1])
        except ValueError:
            current_octet = 100

        if user_input is not None and "network_manager_unavailable" not in errors.values():
            if not user_input.get("confirm", False):
                errors["base"] = "network_confirmation_required"
            else:
                self._network_task = self.hass.async_create_task(
                    self._async_apply_network(
                        user_input["mode"], user_input["last_octet"]
                    ),
                    f"{DOMAIN} safe IPv4 change",
                )
                return self.async_show_progress(
                    step_id="network_address",
                    progress_action="changing_network",
                    progress_task=self._network_task,
                )

        return self.async_show_form(
            step_id="network_address",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "mode",
                        default=(status.get("mode") if status.get("mode") in ("dhcp", "static") else "dhcp"),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": "dhcp", "label": "Automat (DHCP)"},
                                {"value": "static", "label": "IP static"},
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required("last_octet", default=current_octet): vol.All(
                        vol.Coerce(int), vol.Range(min=2, max=254)
                    ),
                    vol.Required("confirm", default=False): BooleanSelector(),
                }
            ),
            description_placeholders={
                "current_ip": status.get("current_ip", "-"),
                "mode": status.get("mode", "-"),
                "netmask": status.get("netmask", "-"),
                "gateway": status.get("gateway", "-"),
                "wifi_mac": status.get("wifi_mac", "-"),
            },
            errors=errors,
        )

    async def async_step_network_finish(self, user_input=None):
        """Close the progress dialog before loading the confirmed address."""
        entry_id = self.config_entry.entry_id
        self.hass.async_create_task(
            self._async_reload_after_flow_close(entry_id),
            f"{DOMAIN} reload after IPv4 change",
        )
        return self.async_create_entry(title="", data={})


    async def async_step_change_wifi(self, user_input=None):
        """Safely test and apply a different Wi-Fi network on the hub."""
        errors = {}
        if user_input is not None:
            if not user_input.get("confirm", False):
                errors["base"] = "wifi_confirmation_required"
            else:
                try:
                    await self.hass.async_add_executor_job(
                        self._client.start_wifi_change,
                        user_input["ssid"],
                        user_input["wifi_password"],
                    )
                except ValueError:
                    errors["base"] = "wifi_invalid"
                except (OSError, RuntimeError, TimeoutError):
                    errors["base"] = "wifi_change_failed"
                else:
                    return self.async_abort(reason="wifi_change_started")

        return self.async_show_form(
            step_id="change_wifi",
            data_schema=vol.Schema(
                {
                    vol.Required("ssid"): TextSelector(
                        TextSelectorConfig(autocomplete="ssid")
                    ),
                    vol.Required("wifi_password"): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD,
                            autocomplete="new-password",
                        )
                    ),
                    vol.Required("confirm", default=False): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def _async_reload_after_flow_close(self, entry_id: str) -> None:
        """Reload only after the frontend has received the close response."""
        await asyncio.sleep(SOUND_RELOAD_DELAY_SECONDS)
        try:
            await self.hass.config_entries.async_reload(entry_id)
        except Exception:
            _LOGGER.exception(
                "Aqara M1S automatic reload failed after sound management"
            )

    async def async_step_upload_finish(self, user_input=None):
        """Close confirmed upload and reload immediately afterward."""
        entry_id = self.config_entry.entry_id

        async def _reload_after_close() -> None:
            await asyncio.sleep(0)
            try:
                await self.hass.config_entries.async_reload(entry_id)
            except Exception:
                _LOGGER.exception(
                    "Aqara M1S automatic reload failed after WAV upload"
                )

        self.hass.async_create_task(
            _reload_after_close(),
            f"{DOMAIN} reload after WAV upload",
        )
        return self.async_create_entry(title="", data={})

    async def async_step_finish(self, user_input=None):
        """Close sound management now and reload the config entry afterward."""
        entry_id = self.config_entry.entry_id
        self.hass.async_create_task(
            self._async_reload_after_flow_close(entry_id),
            f"{DOMAIN} reload after sound management",
        )
        return self.async_create_entry(title="", data={})

    async def _async_upload_sounds(
        self,
        uploads: list[tuple[str, bytes]],
    ) -> None:
        """Upload validated WAV files and report HA-side batch progress."""
        total_size = sum(len(content) for _, content in uploads) or 1
        uploaded_size = 0
        self.async_update_progress(0.0)

        for filename, content in uploads:
            destination = destination_for_filename(filename)
            await self.hass.async_add_executor_job(
                self._client.upload_sound,
                destination,
                content,
            )
            uploaded_size += len(content)
            self.async_update_progress(min(uploaded_size / total_size, 1.0))

    async def async_step_upload_sound(self, user_input=None):
        errors = {}

        if self._upload_task is not None:
            if not self._upload_task.done():
                return self.async_show_progress(
                    step_id="upload_sound",
                    progress_action="uploading_sounds",
                    progress_task=self._upload_task,
                )

            try:
                await self._upload_task
            except Exception as err:
                _LOGGER.exception("WAV upload failed: %s", err)
                self._upload_error = True
                next_step_id = "upload_sound"
            else:
                next_step_id = "upload_finish"
            finally:
                self._upload_task = None

            return self.async_show_progress_done(next_step_id=next_step_id)

        if self._upload_error:
            errors["base"] = "upload_failed"
            self._upload_error = False

        if user_input is not None:
            try:
                uploads = await self.hass.async_add_executor_job(
                    read_uploaded_sounds,
                    self.hass,
                    user_input["source"],
                )
            except (OSError, ValueError, RuntimeError) as err:
                _LOGGER.exception("WAV upload failed: %s", err)
                errors["base"] = "upload_failed"
            else:
                self._upload_task = self.hass.async_create_task(
                    self._async_upload_sounds(uploads),
                    f"{DOMAIN} WAV upload",
                )
                return self.async_show_progress(
                    step_id="upload_sound",
                    progress_action="uploading_sounds",
                    progress_task=self._upload_task,
                )

        return self.async_show_form(
            step_id="upload_sound",
            data_schema=vol.Schema(
                {
                    vol.Required("source"): FileSelector(
                        FileSelectorConfig(
                            accept=(
                                ".wav,.zip,audio/wav,audio/x-wav,"
                                "application/zip,application/x-zip-compressed"
                            )
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_delete_sound(self, user_input=None):
        errors = {}
        if user_input is not None:
            selected_paths = user_input.get("path", [])
            if not selected_paths:
                errors["base"] = "no_files_selected"
            else:
                if isinstance(selected_paths, str):
                    selected_paths = [selected_paths]
                try:
                    for path in selected_paths:
                        await self.hass.async_add_executor_job(
                            self._client.delete_sound,
                            path,
                        )
                except (OSError, ValueError, RuntimeError):
                    errors["base"] = "delete_failed"
                else:
                    return await self.async_step_finish()

        try:
            sounds = await self.hass.async_add_executor_job(
                self._client.list_sounds
            )
        except (OSError, RuntimeError):
            sounds = []
        managed_sounds = sorted(
            path
            for path in sounds
            if path.startswith(f"{MANAGED_SOUND_ROOT}/")
        )
        if not managed_sounds:
            return await self.async_step_init()

        return self.async_show_form(
            step_id="delete_sound",
            data_schema=vol.Schema(
                {
                    vol.Optional("path", default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=managed_sounds,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_rejoin_zigbee(self, user_input=None):
        """Move the JN5189 router to a different Zigbee coordinator."""
        errors = {}
        if user_input is not None:
            if not user_input.get("confirm", False):
                errors["base"] = "rejoin_confirmation_required"
            else:
                try:
                    await self.hass.async_add_executor_job(
                        self._client.rejoin_zigbee_network
                    )
                except (OSError, RuntimeError):
                    errors["base"] = "rejoin_failed"
                else:
                    return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="rejoin_zigbee",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm", default=False): BooleanSelector(),
                }
            ),
            errors=errors,
        )
