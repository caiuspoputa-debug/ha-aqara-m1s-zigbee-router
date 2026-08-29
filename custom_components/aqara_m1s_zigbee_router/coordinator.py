from __future__ import annotations

import asyncio
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

HEALTH_UPDATE_INTERVAL = timedelta(seconds=30)
OFFLINE_RELOAD_RETRY_SECONDS = 30


class AqaraM1SRouterCoordinator(DataUpdateCoordinator[dict]):
    """Shared availability and JN5189 lux data for the hub entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client) -> None:
        self.entry = entry
        self.client = client
        self._was_online = False
        self._online_generation = 0
        self._reload_task: asyncio.Task | None = None
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"Aqara M1S Router {client.host}",
            update_interval=HEALTH_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict:
        online = await self.hass.async_add_executor_job(self.client.check_online)
        if not online:
            if self._was_online:
                self._schedule_reload_after_runtime_offline()
            self._was_online = False
            raise UpdateFailed("Hub is offline")

        if not self._was_online:
            self._online_generation += 1
            self.hass.async_create_background_task(
                self._async_clear_boot_light(),
                f"aqara_m1s_clear_boot_light_{self.client.host}",
            )
        self._was_online = True

        illuminance = None
        try:
            illuminance = await self.hass.async_add_executor_job(
                self.client.read_illuminance
            )
        except Exception:
            # A failed lux request must not make the otherwise healthy hub and
            # all of its entities unavailable.
            illuminance = None

        return {
            "online": True,
            "illuminance": illuminance,
            "online_generation": self._online_generation,
        }

    async def _async_clear_boot_light(self) -> None:
        # Do not let the optional UART RGB cleanup delay or fail availability.
        await asyncio.sleep(10)
        try:
            await self.hass.async_add_executor_job(
                self.client.set_rgb, 0, 0, 0
            )
        except Exception:
            pass

    def schedule_reload_until_online(self, *, initial_delay: float = 0.0) -> None:
        if self._reload_task is not None and not self._reload_task.done():
            return
        self._reload_task = self.hass.async_create_background_task(
            self._async_reload_until_online(initial_delay),
            f"aqara_m1s_reload_until_online_{self.entry.entry_id}",
        )

    def _schedule_reload_after_runtime_offline(self) -> None:
        self.schedule_reload_until_online()

    async def _async_reload_until_online(self, initial_delay: float) -> None:
        if initial_delay > 0:
            await asyncio.sleep(initial_delay)
        while True:
            try:
                if await self.hass.config_entries.async_reload(self.entry.entry_id):
                    return
            except Exception:
                pass
            await asyncio.sleep(OFFLINE_RELOAD_RETRY_SECONDS)

    async def async_shutdown(self) -> None:
        task = self._reload_task
        if (
            task is None
            or task.done()
            or task is asyncio.current_task()
        ):
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
