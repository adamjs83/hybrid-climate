"""Number platform for Hybrid Climate tunable parameters.

Creates number entities for live adjustment of:
- Zone setpoints (default, away, sleep, vacation)
- PI controller parameters (kp, ki, k_ext, offset_max, balance_point)

Values persist across restarts via config_entry.options.

Key dependencies: number_definitions.py, number_entities.py
Used by: Home Assistant platform setup
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HybridClimateCoordinator
from .number_definitions import (  # noqa: F401 — re-exported
    SETPOINT_NUMBERS,
    PI_NUMBERS,
    HybridClimateNumberEntityDescription,
)
from .number_entities import (  # noqa: F401 — re-exported
    HybridClimateNumberEntity,
    get_stored_number_values,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities for Hybrid Climate."""
    coordinator: HybridClimateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    config = coordinator.config

    entities: list[HybridClimateNumberEntity] = []

    for zone_id, zone_config in config.zones.items():
        has_heat = bool(zone_config.heat_stages)
        has_cool = bool(zone_config.cool_stages)
        has_pi = zone_config.regulation is not None and zone_config.regulation.type == "pi"

        # Add setpoint numbers based on zone capabilities
        for description in SETPOINT_NUMBERS:
            # Skip cooling setpoints if zone doesn't have cooling
            if description.is_cooling and not has_cool:
                continue
            # Skip heating setpoints if zone doesn't have heating
            if not description.is_cooling and not has_heat:
                continue

            entities.append(
                HybridClimateNumberEntity(
                    hass=hass,
                    entry=entry,
                    coordinator=coordinator,
                    zone_id=zone_id,
                    zone_name=zone_config.name,
                    description=description,
                )
            )

        # Add PI numbers if zone uses PI regulation
        if has_pi:
            for description in PI_NUMBERS:
                entities.append(
                    HybridClimateNumberEntity(
                        hass=hass,
                        entry=entry,
                        coordinator=coordinator,
                        zone_id=zone_id,
                        zone_name=zone_config.name,
                        description=description,
                    )
                )

    _LOGGER.info("Setting up %d number entities for Hybrid Climate", len(entities))
    async_add_entities(entities)
