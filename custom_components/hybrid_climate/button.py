"""Purpose: Expose a per-zone "Restore control" button entity (spec §2.2).

Key dependencies: control_restore.async_restore, the zone device identity
shared with number_entities.py/diagnostic_sensors.py.
Used by: Home Assistant button platform setup.
"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DIAG_DEVICE_NAME_PREFIX,
    DIAG_MANUFACTURER,
    DIAG_ZONE_MODEL,
    DOMAIN,
    RESTORE_CONTROL_KEY,
)
from .control_restore import async_restore
from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


class RestoreControlButton(ButtonEntity):
    """Request a manual restore pass scoped to this zone (spec §2.2).

    EntityCategory.CONFIG, not DIAGNOSTIC: HA reserves DIAGNOSTIC for
    read-only entities, and pressing this button changes device state
    (like a device "restart" button) — see spec ruling S6.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = RESTORE_CONTROL_KEY

    def __init__(
        self, hass: HomeAssistant, coordinator: HybridClimateCoordinator, zone_id: str,
    ) -> None:
        """Keep the zone identity this button restores."""
        self.hass = hass
        self.coordinator = coordinator
        self.zone_id = zone_id
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_{RESTORE_CONTROL_KEY}"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the same zone device as the zone's other entities."""
        zone = self.coordinator.config.zones[self.zone_id]
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_{self.zone_id}")},
            name=f"{DIAG_DEVICE_NAME_PREFIX}{zone.name}",
            manufacturer=DIAG_MANUFACTURER, model=DIAG_ZONE_MODEL,
        )

    async def async_press(self) -> None:
        """Run this zone's restore pass; HA entity permissions gate the press."""
        result = await async_restore(self.coordinator, self.zone_id)
        _LOGGER.info("Restore control button for zone %s: %s", self.zone_id, result)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one restore-control button per configured zone."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data is None:
        _LOGGER.error("Failed to set up restore control buttons: entry data not found")
        return
    coordinator: HybridClimateCoordinator = data["coordinator"]
    async_add_entities(
        RestoreControlButton(hass, coordinator, zone_id) for zone_id in coordinator.config.zones
    )
