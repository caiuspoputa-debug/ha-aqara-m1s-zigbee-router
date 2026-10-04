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
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
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
)
from .client import AqaraM1SClient, NetworkChangeError, SoundStorageError
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
        """Choose the address mode before showing mode-specific controls."""
        if self._pending_user is None or self._initial_network is None:
            return await self.async_step_user()
        current_ip = self._initial_network.get("current_ip", self._pending_user[CONF_HOST])
        if user_input is not None:
            if user_input["mode"] == "static":
                return await self.async_step_network_setup_static()
            data = dict(self._pending_user)
            network = self._initial_network
            data[CONF_DEVICE_MAC] = network["wifi_mac"]
            data[CONF_BUTTON_TOPIC_ID] = network.get("button_topic_id", "")
            return self.async_create_entry(
                title=entry_title_with_host(
                    data.get("name", "Aqara M1S Zigbee Router"), data[CONF_HOST]
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
                    )
                }
            ),
            description_placeholders={"current_ip": current_ip},
        )

    async def async_step_network_setup_static(self, user_input=None):
        """Show the final IPv4 octet only after static mode was selected."""
        if self._pending_user is None or self._initial_network is None:
            return await self.async_step_user()
        errors = {}
        current_ip = self._initial_network.get("current_ip", self._pending_user[CONF_HOST])
        current_octet = int(current_ip.rsplit(".", 1)[-1])
        ip_field = f"{current_ip.rsplit('.', 1)[0]}.xxx"
        if user_input is not None:
            data = dict(self._pending_user)
            network = self._initial_network
            client = AqaraM1SClient(
                host=data[CONF_HOST],
                port=data.get(CONF_PORT, DEFAULT_PORT),
                username=data.get(CONF_USERNAME, DEFAULT_USERNAME),
                password=data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
            )
            try:
                new_host, network = await self.hass.async_add_executor_job(
                    client.set_static_ipv4, user_input[ip_field]
                )
            except ValueError:
                errors["base"] = "network_invalid_octet"
            except NetworkChangeError as err:
                errors["base"] = err.error_key
            except (OSError, RuntimeError, TimeoutError):
                errors["base"] = "network_change_failed"
            else:
                data[CONF_HOST] = new_host
                data[CONF_DEVICE_MAC] = network["wifi_mac"]
                data[CONF_BUTTON_TOPIC_ID] = network.get("button_topic_id", "")
                return self.async_create_entry(
                    title=entry_title_with_host(
                        data.get("name", "Aqara M1S Zigbee Router"), new_host
                    ),
                    data=data,
                )
            finally:
                await self.hass.async_add_executor_job(client.disconnect)
        return self.async_show_form(
            step_id="network_setup_static",
            data_schema=vol.Schema(
                {
                    vol.Required(ip_field, default=current_octet): NumberSelector(
                        NumberSelectorConfig(
                            min=2, max=254, step=1, mode=NumberSelectorMode.BOX
                        )
                    )
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
        self._upload_error: str | None = None
        self._upload_filename: str | None = None
        self._network_task: asyncio.Task | None = None
        self._network_error: str | None = None
        self._network_status_cache: dict[str, str] | None = None
        self._pending_sound_delete_paths: list[str] = []

    @property
    def _client(self):
        return self.hass.data[DOMAIN][DATA_CLIENTS][self.config_entry.entry_id]

    def _new_operation_client(self) -> AqaraM1SClient:
        """Return a short-lived client for long Configure-flow operations."""
        data = self.config_entry.data
        return AqaraM1SClient(
            host=data[CONF_HOST],
            port=data.get(CONF_PORT, DEFAULT_PORT),
            username=data.get(CONF_USERNAME, DEFAULT_USERNAME),
            password=data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
        )

    def _validate_upload_capacity_isolated(
        self,
        uploads: list[tuple[str, int]],
    ) -> dict[str, int]:
        """Preflight an upload without waiting for the runtime client's lock."""
        client = self._new_operation_client()
        try:
            return client.validate_sound_upload_capacity(uploads)
        finally:
            client.disconnect()

    def _upload_sounds_isolated(
        self,
        uploads: list[tuple[str, bytes]],
        progress,
    ) -> None:
        """Upload through a dedicated client and always close its Telnet socket."""
        client = self._new_operation_client()
        try:
            client.upload_sounds(uploads, progress)
        finally:
            client.disconnect()

    async def async_step_init(self, user_input=None):
        menu_options = ["shared_mqtt", "network_address", "change_wifi", "upload_sound"]
        try:
            zigbee_status = await self.hass.async_add_executor_job(
                self._client.coordinator_runtime_status
            )
        except (OSError, RuntimeError):
            zigbee_status = {"role": "router"}
        try:
            sounds = await self.hass.async_add_executor_job(
                self._client.list_sounds
            )
        except (OSError, RuntimeError):
            sounds = []
        if any(
            self._client.is_deletable_sound_path(path)
            for path in sounds
        ):
            menu_options.append("delete_sound")
        if zigbee_status.get("role") != "coordinator":
            menu_options.append("rejoin_zigbee")
        menu_options.append("finish")
        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
        )

    async def async_step_shared_mqtt(self, user_input=None):
        from .shared_mqtt import get_shared_mqtt

        manager = await get_shared_mqtt(self.hass)
        current = manager.settings or {}
        errors = {}
        if user_input is not None:
            values = dict(user_input)
            if not values.get("password"):
                values["password"] = current.get("password", "")
            try:
                await manager.save(values)
            except Exception:
                errors["base"] = "shared_mqtt_failed"
            else:
                return self.async_create_entry(title="", data=dict(self.config_entry.options))
        schema = vol.Schema({
            vol.Required("host", default=current.get("host", "")): str,
            vol.Required("port", default=current.get("port", 1883)): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required("username", default=current.get("username", "")): str,
            vol.Optional("password"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        })
        return self.async_show_form(step_id="shared_mqtt", data_schema=schema, errors=errors)

    async def _async_apply_network(self, mode: str, last_octet: int) -> None:
        data = dict(self.config_entry.data)
        if mode == "static":
            new_host, status = await self.hass.async_add_executor_job(
                self._client.set_static_ipv4, last_octet
            )
            data[CONF_HOST] = new_host
        else:
            status = await self.hass.async_add_executor_job(
                self._client.network_status
            )
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
                self._network_error = getattr(
                    err, "error_key", "network_change_failed"
                )
                next_step_id = "network_address"
            else:
                next_step_id = "network_finish"
            finally:
                self._network_task = None
            return self.async_show_progress_done(next_step_id=next_step_id)

        if self._network_error:
            errors["base"] = self._network_error
            self._network_error = None
        try:
            status = await self.hass.async_add_executor_job(
                self._client.network_status
            )
        except (OSError, RuntimeError, TimeoutError) as err:
            _LOGGER.exception(
                "Aqara M1S network status failed for %s: %s",
                self.config_entry.data.get(CONF_HOST),
                err,
            )
            errors["base"] = "network_manager_unavailable"
            status = {
                "mode": "unknown",
                "current_ip": str(self.config_entry.data.get(CONF_HOST, "")),
                "netmask": "-",
                "gateway": "-",
                "wifi_mac": "-",
            }

        if user_input is not None and "network_manager_unavailable" not in errors.values():
            self._network_status_cache = status
            if user_input["mode"] == "static":
                return await self.async_step_network_static()
            self._network_task = self.hass.async_create_task(
                self._async_apply_network("dhcp", 0),
                f"{DOMAIN} DHCP change",
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
                    )
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

    async def async_step_network_static(self, user_input=None):
        """Show the final-octet control only for static mode."""
        status = self._network_status_cache
        if status is None:
            try:
                status = await self.hass.async_add_executor_job(
                    self._client.network_status
                )
            except (OSError, RuntimeError, TimeoutError):
                self._network_error = "network_manager_unavailable"
                return await self.async_step_network_address()
        current_ip = status.get(
            "current_ip", str(self.config_entry.data.get(CONF_HOST, ""))
        )
        ip_field = f"{current_ip.rsplit('.', 1)[0]}.xxx"
        try:
            current_octet = int(current_ip.rsplit(".", 1)[-1])
        except ValueError:
            current_octet = 100
        errors = {}
        if user_input is not None:
            self._network_task = self.hass.async_create_task(
                self._async_apply_network("static", user_input[ip_field]),
                f"{DOMAIN} safe static IPv4 change",
            )
            return self.async_show_progress(
                step_id="network_address",
                progress_action="changing_network",
                progress_task=self._network_task,
            )
        return self.async_show_form(
            step_id="network_static",
            data_schema=vol.Schema(
                {
                    vol.Required(ip_field, default=current_octet): NumberSelector(
                        NumberSelectorConfig(
                            min=2, max=254, step=1, mode=NumberSelectorMode.BOX
                        )
                    )
                }
            ),
            description_placeholders={"current_ip": current_ip},
            errors=errors,
        )

    async def async_step_network_dhcp(self, user_input=None):
        """Apply DHCP directly without an extra confirmation checkbox."""
        if user_input is not None:
            self._network_task = self.hass.async_create_task(
                self._async_apply_network("dhcp", 0),
                f"{DOMAIN} DHCP change",
            )
            return self.async_show_progress(
                step_id="network_address",
                progress_action="changing_network",
                progress_task=self._network_task,
            )
        return self.async_show_form(
            step_id="network_dhcp",
            data_schema=vol.Schema({}),
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
        """Upload one WAV and expose determinate progress throughout the transfer."""
        self.async_update_progress(0.01)
        destinations = [
            (destination_for_filename(filename), content)
            for filename, content in uploads
        ]

        def report_progress(uploaded_size: int, total_size: int) -> None:
            ratio = min(uploaded_size / (total_size or 1), 1.0)
            progress = min(0.98, 0.02 + ratio * 0.96)
            self.hass.loop.call_soon_threadsafe(self.async_update_progress, progress)

        await self.hass.async_add_executor_job(
            self._upload_sounds_isolated,
            destinations,
            report_progress,
        )
        self.async_update_progress(1.0)

    async def async_step_upload_sound(self, user_input=None):
        errors = {}

        if self._upload_task is not None:
            if not self._upload_task.done():
                return self.async_show_progress(
                    step_id="upload_sound",
                    progress_action="uploading_sounds",
                    progress_task=self._upload_task,
                    description_placeholders={
                        "filename": self._upload_filename or "WAV",
                    },
                )

            try:
                await self._upload_task
            except SoundStorageError as err:
                _LOGGER.warning("WAV upload refused by storage reserve: %s", err)
                self._upload_error = "sound_storage_full"
                next_step_id = "upload_sound"
            except Exception as err:
                _LOGGER.exception("WAV upload failed: %s", err)
                self._upload_error = "upload_failed"
                next_step_id = "upload_sound"
            else:
                next_step_id = "upload_finish"
            finally:
                self._upload_task = None

            return self.async_show_progress_done(next_step_id=next_step_id)

        if self._upload_error:
            errors["base"] = self._upload_error
            self._upload_error = None

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
                destinations = [
                    (destination_for_filename(filename), len(content))
                    for filename, content in uploads
                ]
                try:
                    await self.hass.async_add_executor_job(
                        self._validate_upload_capacity_isolated,
                        destinations,
                    )
                except SoundStorageError as err:
                    _LOGGER.warning(
                        "WAV upload refused by storage reserve before progress: %s",
                        err,
                    )
                    errors["base"] = "sound_storage_full"
                except Exception as err:
                    _LOGGER.exception("WAV upload preflight failed: %s", err)
                    errors["base"] = "upload_failed"
                else:
                    self._upload_filename = uploads[0][0]
                    self._upload_task = self.hass.async_create_task(
                        self._async_upload_sounds(uploads),
                        f"{DOMAIN} WAV upload",
                    )
                    return self.async_show_progress(
                        step_id="upload_sound",
                        progress_action="uploading_sounds",
                        progress_task=self._upload_task,
                        description_placeholders={
                            "filename": self._upload_filename,
                        },
                    )

        return self.async_show_form(
            step_id="upload_sound",
            data_schema=vol.Schema(
                {
                    vol.Required("source"): FileSelector(
                        FileSelectorConfig(
                            accept=".wav,audio/wav,audio/x-wav,audio/vnd.wave"
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
                self._pending_sound_delete_paths = list(selected_paths)
                return await self.async_step_confirm_delete_sound()

        try:
            sounds = await self.hass.async_add_executor_job(
                self._client.list_sounds
            )
        except (OSError, RuntimeError):
            sounds = []
        managed_sounds = sorted(
            path
            for path in sounds
            if self._client.is_deletable_sound_path(path)
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
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_confirm_delete_sound(self, user_input=None):
        if not self._pending_sound_delete_paths:
            return await self.async_step_delete_sound()

        errors = {}
        if user_input is not None:
            if not user_input.get("confirm", False):
                errors["base"] = "sound_delete_confirmation_required"
            else:
                try:
                    await self.hass.async_add_executor_job(
                        self._client.delete_sounds,
                        self._pending_sound_delete_paths,
                    )
                except (OSError, ValueError, RuntimeError) as err:
                    _LOGGER.warning(
                        "WAV deletion failed for %s: %s",
                        self._client.host,
                        err,
                    )
                    errors["base"] = "delete_failed"
                else:
                    self._pending_sound_delete_paths = []
                    return await self.async_step_finish()

        return self.async_show_form(
            step_id="confirm_delete_sound",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm", default=False): BooleanSelector(),
                }
            ),
            description_placeholders={
                "count": str(len(self._pending_sound_delete_paths)),
            },
            errors=errors,
        )

    async def async_step_rejoin_zigbee(self, user_input=None):
        """Move the JN5189 router to a different Zigbee coordinator."""
        try:
            status = await self.hass.async_add_executor_job(
                self._client.coordinator_runtime_status
            )
        except (OSError, RuntimeError):
            status = {"role": "router"}
        if status.get("role") == "coordinator":
            return await self.async_step_init()
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
