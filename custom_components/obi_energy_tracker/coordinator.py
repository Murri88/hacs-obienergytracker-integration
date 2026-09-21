"""Data update coordinator for Obi EnergyTracker."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ObiEnergyTrackerAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)
DAYS_OF_HISTORY = 7


class ObiEnergyTrackerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data update coordinator for Obi EnergyTracker.

    A single bridge can have multiple sensors (devices) connected to it, so
    this coordinator discovers the bridge's devices on every update and
    fetches meter/hourly data for each of them.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: ObiEnergyTrackerAPI,
        config_entry: Any,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            config_entry=config_entry,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API.

        Retrieves, for every device connected to the account's bridge:
        - Meter reading (Zählerstand)
        - Hourly energy data for the past 7 days
        """
        try:
            bridge_info = await self.api.async_get_bridge_devices()
            if not bridge_info:
                raise UpdateFailed("Failed to discover bridge and devices")

            bridge_id = bridge_info["bridge_id"]
            end_date = datetime.now()

            devices: dict[str, dict[str, Any]] = {}
            for device in bridge_info["devices"]:
                device_id = device["device_id"]

                meter = await self.api.async_get_meter_data(bridge_id, device_id)
                hourly_data = await self.api.async_get_hourly_data(
                    bridge_id,
                    device_id,
                    start_date=end_date,
                    num_days=DAYS_OF_HISTORY,
                )

                devices[device_id] = {
                    "device_name": device["device_name"],
                    "meter": meter,
                    "hourly": hourly_data,
                }

            _LOGGER.info(
                "Successfully fetched data for bridge %s: %d device(s)",
                bridge_id,
                len(devices),
            )
        except OSError as err:
            _LOGGER.error("Failed to update data: %s", err)
            raise UpdateFailed(f"Failed to update data: {err}") from err

        return {
            "bridge_id": bridge_id,
            "devices": devices,
        }
