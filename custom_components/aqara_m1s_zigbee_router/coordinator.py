from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN


_LOGGER = logging.getLogger(__name__)
WATCHDOG_INTERVAL_SECONDS = 5.0
LUX_INTERVAL_SECONDS = 15.0
OFFLINE_NAME_SUFFIX = " (🔴 Indisponibil)"
LEGACY_OFFLINE_NAME_SUFFIX = " (Indisponibil)"


class AqaraM1SRouterCoordinator(DataUpdateCoordinator[dict]):
    """Own hub availability independently from optional hub features.

    The physical M1S may be powered off for long periods.  A dedicated
    watchdog therefore polls the hub forever and does not depend on the normal
    DataUpdateCoordinator listener timer.  Optional JN5189/lux work runs in a
    separate background task and can never hold availability recovery hostage.
    """

    def __init__(self, hass: HomeAssistant, client, config_entry=None) -> None:
        self.client = client
        self._was_online = False
        self._online_generation = 0
        self._post_online_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._lux_task: asyncio.Task | None = None
        self._last_lux_started = 0.0
        self._visual_availability_online: bool | None = None
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=config_entry,
            name=f"Aqara M1S Router {client.host}",
            # Deliberately disabled: our watchdog below is always alive, even
            # when no CoordinatorEntity listener exists yet.
            update_interval=None,
        )

    @callback
    def async_start_watchdog(self) -> None:
        """Start the permanent connectivity watchdog exactly once."""
        task = self._watchdog_task
        if task is not None and not task.done():
            return

        coro = self._async_watchdog_loop()
        name = f"Aqara M1S {self.client.host} availability watchdog"
        if self.config_entry is not None:
            self._watchdog_task = self.config_entry.async_create_background_task(
                self.hass, coro, name=name, eager_start=True
            )
        else:
            self._watchdog_task = self.hass.async_create_background_task(
                coro, name=name, eager_start=True
            )

    async def _async_watchdog_loop(self) -> None:
        """Refresh forever, including after any number of failed probes."""
        try:
            while True:
                started = self.hass.loop.time()
                await self.async_refresh()
                elapsed = self.hass.loop.time() - started
                await asyncio.sleep(max(0.25, WATCHDOG_INTERVAL_SECONDS - elapsed))
        except asyncio.CancelledError:
            raise

    async def _async_update_data(self) -> dict:
        # client.check_online() uses its own fresh TCP socket.  It does not wait
        # for the shared Telnet/UART lock and is therefore a true watchdog.
        online = await self.hass.async_add_executor_job(self.client.check_online)
        if not online:
            if self._was_online:
                _LOGGER.warning(
                    "Aqara M1S hub %s became unavailable; retrying every %.0f seconds",
                    self.client.host,
                    WATCHDOG_INTERVAL_SECONDS,
                )
            self._set_visual_availability(False)
            self._was_online = False
            raise UpdateFailed("Hub is offline")

        self._set_visual_availability(True)
        if not self._was_online:
            _LOGGER.info(
                "Aqara M1S hub %s is reachable again",
                self.client.host,
            )
            self._was_online = True
            self._online_generation += 1
            self._schedule_post_online_cleanup(self._online_generation)
            self._schedule_lux_refresh(force=True)
        else:
            self._schedule_lux_refresh(force=False)

        previous = self.data or {}
        return {
            "online": True,
            # Keep the most recent good lux sample.  Lux is deliberately not
            # awaited here because UART startup/read can take several seconds.
            "illuminance": previous.get("illuminance"),
            "online_generation": self._online_generation,
        }

    @callback
    def _schedule_lux_refresh(self, *, force: bool) -> None:
        task = self._lux_task
        if task is not None and not task.done():
            return

        now = self.hass.loop.time()
        if not force and now - self._last_lux_started < LUX_INTERVAL_SECONDS:
            return
        self._last_lux_started = now
        generation = self._online_generation
        self._lux_task = self.hass.async_create_task(
            self._async_refresh_lux(generation)
        )

    async def _async_refresh_lux(self, generation: int) -> None:
        """Refresh JN5189 lux without affecting hub availability."""
        try:
            reading = await self.hass.async_add_executor_job(
                self.client.read_illuminance
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return

        if not self._was_online or generation != self._online_generation:
            return

        data = dict(self.data or {})
        data.update(
            {
                "online": True,
                "illuminance": reading,
                "online_generation": self._online_generation,
            }
        )
        self.async_set_updated_data(data)

    def _schedule_post_online_cleanup(self, generation: int) -> None:
        task = self._post_online_task
        if task is not None and not task.done():
            task.cancel()
        self._post_online_task = self.hass.async_create_task(
            self._async_post_online_cleanup(generation)
        )

    async def _async_post_online_cleanup(self, generation: int) -> None:
        """Turn off the stock red boot ring without delaying availability."""
        try:
            await asyncio.sleep(10)
            if not self._was_online or generation != self._online_generation:
                return
            await self.hass.async_add_executor_job(self.client.set_rgb, 0, 0, 0)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Cosmetic only.  Never downgrade hub availability for this.
            return

    async def async_shutdown(self) -> None:
        for attr in ("_watchdog_task", "_lux_task", "_post_online_task"):
            task = getattr(self, attr)
            setattr(self, attr, None)
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await super().async_shutdown()

    @callback
    def _set_visual_availability(self, online: bool) -> None:
        if self.config_entry is None or self._visual_availability_online is online:
            return
        self._visual_availability_online = online

        title = self._availability_name(self.config_entry.title, online)
        if title != self.config_entry.title:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                title=title,
            )

        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, self.client.host)}
        )
        if device is None or device.name is None:
            return

        device_name = self._availability_name(device.name, online)
        if device_name != device.name:
            device_registry.async_update_device(device.id, name=device_name)

    @staticmethod
    def _availability_name(name: str, online: bool) -> str:
        base = str(name).removesuffix(OFFLINE_NAME_SUFFIX).removesuffix(
            LEGACY_OFFLINE_NAME_SUFFIX
        )
        return base if online else f"{base}{OFFLINE_NAME_SUFFIX}"
