"""Sensor platform for Obi EnergyTracker."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ObiEnergyTrackerConfigEntry
from .const import DOMAIN
from .coordinator import ObiEnergyTrackerCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ObiEnergyTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry.

    The bridge can have multiple devices (sensors) connected to it, and new
    ones can appear later, so entities are added dynamically as they show up
    in coordinator data instead of being fixed at setup time.
    """
    coordinator = config_entry.runtime_data
    known_device_ids: set[str] = set()

    @callback
    def _add_new_devices() -> None:
        new_device_ids = [
            device_id
            for device_id in coordinator.data.get("devices", {})
            if device_id not in known_device_ids
        ]
        if not new_device_ids:
            return
        known_device_ids.update(new_device_ids)
        async_add_entities(
            ObiMeterReadingSensor(coordinator, device_id)
            for device_id in new_device_ids
        )

    _add_new_devices()
    config_entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))


class ObiEnergySensorBase(CoordinatorEntity[ObiEnergyTrackerCoordinator], SensorEntity):
    """Base class for Obi EnergyTracker sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ObiEnergyTrackerCoordinator, device_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        device_data = coordinator.data.get("devices", {}).get(device_id, {})
        device_name = device_data.get("device_name") or device_id
        bridge_id = coordinator.data.get("bridge_id")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": f"Obi EnergyTracker {device_name}",
            "manufacturer": "Obi",
            "via_device": (DOMAIN, bridge_id) if bridge_id else None,
        }


class ObiMeterReadingSensor(ObiEnergySensorBase):
    """Sensor for total meter reading (Zählerstand)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_translation_key = "meter_reading"
    _attr_native_unit_of_measurement = "Wh"

    def __init__(self, coordinator: ObiEnergyTrackerCoordinator, device_id: str) -> None:
        """Initialize the meter reading sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{self._device_id}_meter_reading"
        self._last_native_value: float | None = None
        self._last_native_value_set = False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates and suppress duplicate readings."""
        new_value = self.native_value

        if not self._last_native_value_set or new_value != self._last_native_value:
            self._last_native_value_set = True
            self._last_native_value = new_value
            self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the meter reading value."""
        device_data = (
            self.coordinator.data.get("devices", {}).get(self._device_id)
            if self.coordinator.data
            else None
        )
        _LOGGER.debug(
            "ObiMeterReadingSensor native_value called for %s. Data: %s",
            self._device_id,
            device_data,
        )
        if device_data and device_data.get("meter"):
            meter_data = device_data["meter"]

            # If it's a list, get the latest record
            if isinstance(meter_data, list) and len(meter_data) > 0:
                meter_data = meter_data[-1]

            if not isinstance(meter_data, dict):
                return None

            # Look for "value" (if measure is energy) or "energy" directly
            if "energy" in meter_data:
                return meter_data["energy"]
            if "value" in meter_data and meter_data.get("measure") == "energy":
                return meter_data["value"]
            # Fallback to "value" if present
            if "value" in meter_data:
                return meter_data["value"]

        return None
