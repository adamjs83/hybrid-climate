"""Purpose: Expose cached uncontrolled-device and outdoor fallback problems.

Key dependencies: Coordinator state and Agent API entity projections.
Used by: Home Assistant binary sensor platform.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .agent_api.entity_view import device_mode_snapshot, outdoor_source
from .const import (
    ATTR_REPORTED_MODE, DIAG_DEVICE_NAME_PREFIX, DIAG_MANUFACTURER, DIAG_MASTER_MODEL, DIAG_DEVICE_ID_PREFIX, DIAG_OUTDOOR_FALLBACK_SUFFIX,
    DIAG_UNCONTROLLED_SUFFIX, DOMAIN, TRANSLATION_OUTDOOR_FALLBACK, TRANSLATION_UNCONTROLLED,
)
from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


class DiagnosticProblemSensor(BinarySensorEntity):
    """Base for coordinator-backed problem sensors under the master device."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, coordinator: HybridClimateCoordinator) -> None:
        """Keep the loaded runtime and Home Assistant state store."""
        self.hass = hass
        self.coordinator = coordinator

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the existing master device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_master")},
            name=f"{DIAG_DEVICE_NAME_PREFIX}{self.coordinator.config.master.name}",
            manufacturer=DIAG_MANUFACTURER, model=DIAG_MASTER_MODEL,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator refreshes."""
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))

    @callback
    def _handle_coordinator_update(self) -> None:
        """Publish the current problem state."""
        self.async_write_ha_state()


class DeviceUncontrolledSensor(DiagnosticProblemSensor):
    """Report a device active without a controlling zone."""

    _attr_translation_key = TRANSLATION_UNCONTROLLED

    def __init__(self, hass: HomeAssistant, coordinator: HybridClimateCoordinator, device_id: str) -> None:
        """Set the stable device-specific identity."""
        super().__init__(hass, coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{DIAG_DEVICE_ID_PREFIX}_{device_id}_{DIAG_UNCONTROLLED_SUFFIX}"
        self._attr_translation_placeholders = {"device": device_id}
        self._refresh_snapshot()

    def _refresh_snapshot(self) -> None:
        """Cache one device projection for both state and attributes."""
        self._reported_mode, self._uncontrolled_mode = device_mode_snapshot(
            self.hass, self.coordinator, self.device_id,
        )

    async def async_added_to_hass(self) -> None:
        """Refresh the initial projection when HA adds the entity."""
        await super().async_added_to_hass()
        self._refresh_snapshot()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh the cached device projection before publishing."""
        self._refresh_snapshot()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Mirror the get_status uncontrolled flag."""
        return self._uncontrolled_mode is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show the normalized mode reported by the physical device."""
        return {ATTR_REPORTED_MODE: self._reported_mode}


class OutdoorFallbackSensor(DiagnosticProblemSensor):
    """Report selection of a non-primary outdoor source."""

    _attr_translation_key = TRANSLATION_OUTDOOR_FALLBACK
    _attr_unique_id = f"{DOMAIN}_{DIAG_OUTDOOR_FALLBACK_SUFFIX}"

    @property
    def is_on(self) -> bool:
        """Mirror the get_status fallback flag."""
        return outdoor_source(self.coordinator)[1]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one problem sensor per device and one global fallback sensor."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data is None:
        _LOGGER.error("Failed to set up binary sensors: entry data not found")
        return
    coordinator: HybridClimateCoordinator = data["coordinator"]
    entities: list[BinarySensorEntity] = [
        DeviceUncontrolledSensor(hass, coordinator, device_id)
        for device_id in coordinator.config.devices
    ]
    entities.append(OutdoorFallbackSensor(hass, coordinator))
    async_add_entities(entities)
