"""Climate platform for Hybrid Climate integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HybridClimateCoordinator
from .master import async_setup_master_entity
from .zone import async_setup_zone_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hybrid Climate entities from a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data is None:
        _LOGGER.error(
            "Failed to set up climate entities: entry data not found for %s",
            entry.entry_id,
        )
        return
    coordinator: HybridClimateCoordinator = data["coordinator"]

    # Create master entity
    await async_setup_master_entity(hass, coordinator, entry, async_add_entities)

    # Create zone entities
    await async_setup_zone_entities(hass, coordinator, entry, async_add_entities)

    _LOGGER.info(
        "Created %d climate entities (1 master + %d zones)",
        1 + len(coordinator.config.zones),
        len(coordinator.config.zones),
    )
