from __future__ import annotations

import asyncio
import logging
from functools import partial

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
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DATA_CLIENTS,
    DOMAIN,
    MANAGED_SOUND_ROOT,
)
from .sound_upload import destination_for_filename, read_uploaded_sounds

_LOGGER = logging.getLogger(__name__)
SOUND_RELOAD_DELAY_SECONDS = 1.0


class AqaraM1SZigbeeRouterConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    VERSION = 1

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


class AqaraM1SZigbeeRouterOptionsFlow(
    config_entries.OptionsFlowWithConfigEntry
):
    """Native file manager available from the integration Configure button."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__(config_entry)
        self._upload_task: asyncio.Task[None] | None = None
        self._upload_error = False

    @property
    def _client(self):
        return self.hass.data[DOMAIN][DATA_CLIENTS][self.config_entry.entry_id]

    async def async_step_init(self, user_input=None):
        menu_options = ["change_wifi", "upload_sound"]
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

        for index, (filename, content) in enumerate(uploads, start=1):
            destination = destination_for_filename(filename)
            base_uploaded = uploaded_size
            max_reported = base_uploaded
            _LOGGER.info(
                "Uploading WAV %d/%d: %s", index, len(uploads), filename
            )

            def _report_file_progress(sent: int, file_size: int) -> None:
                nonlocal max_reported
                current = base_uploaded + min(max(sent, 0), file_size)
                # A TCP retry starts sent from zero. Never move HA's progress
                # bar backwards while retrying the same WAV.
                max_reported = max(max_reported, current)
                progress = min(max_reported / total_size, 0.999)
                self.hass.loop.call_soon_threadsafe(
                    self.async_update_progress, progress
                )

            await self.hass.async_add_executor_job(
                partial(
                    self._client.upload_sound,
                    destination,
                    content,
                    progress_callback=_report_file_progress,
                    allow_base64_fallback=False,
                )
            )
            uploaded_size += len(content)
            self.async_update_progress(min(uploaded_size / total_size, 1.0))
            _LOGGER.info(
                "Completed WAV %d/%d: %s", index, len(uploads), filename
            )

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
                next_step_id = "finish"
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
