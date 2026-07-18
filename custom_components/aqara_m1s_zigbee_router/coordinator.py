from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed


class AqaraM1SRouterCoordinator(DataUpdateCoordinator[bool]):
    """Shared online/offline state for every live hub entity."""

    def __init__(self, hass: HomeAssistant, client) -> None:
        self.client = client
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"Aqara M1S Router {client.host}",
            update_interval=timedelta(seconds=15),
        )

    async def _async_update_data(self) -> bool:
        online = await self.hass.async_add_executor_job(self.client.check_online)
        if not online:
            raise UpdateFailed("Hub is offline")
        return True
