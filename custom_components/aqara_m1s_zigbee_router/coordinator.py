from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed


class AqaraM1SRouterCoordinator(DataUpdateCoordinator[dict]):
    """Shared availability and JN5189 lux data for the hub entities."""

    def __init__(self, hass: HomeAssistant, client) -> None:
        self.client = client
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"Aqara M1S Router {client.host}",
            update_interval=timedelta(seconds=15),
        )

    async def _async_update_data(self) -> dict:
        online = await self.hass.async_add_executor_job(self.client.check_online)
        if not online:
            raise UpdateFailed("Hub is offline")

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
        }
