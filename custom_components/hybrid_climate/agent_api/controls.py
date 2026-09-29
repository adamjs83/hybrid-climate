"""Purpose: Resolve entry-owned climate and number controls and read their values.

Key dependencies: Entity registry, dashboard control discovery, number definitions.
Used by: Agent API effective configuration view.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ..const import CONF_NUMBER_VALUES, CONF_UI_CONFIG, DOMAIN
from ..dashboard_api import _number_controls
from ..models import ZoneConfig
from ..number_definitions import PI_NUMBERS, SETPOINT_NUMBERS
from .const import SOURCE_DEFAULT, SOURCE_NUMBER_ENTITY

_LOGGER = logging.getLogger(__name__)
_INVALID_STATES = frozenset({"unknown", "unavailable"})


def zone_controls(
    hass: HomeAssistant, entry: ConfigEntry, zone_id: str, zone: ZoneConfig,
) -> dict[str, Any]:
    """Return only registered controls owned by the selected config entry."""
    registry = er.async_get(hass)

    def owned(entity_id: str | None) -> str | None:
        """Return a registry ID only when this entry owns it."""
        record = registry.async_get(entity_id) if entity_id else None
        return entity_id if record and record.config_entry_id == entry.entry_id else None

    climate = owned(registry.async_get_entity_id(
        "climate", DOMAIN, f"{DOMAIN}_{entry.entry_id}_{zone_id}"))
    numbers = _number_controls(registry, zone_id, zone)
    setpoints: dict[str, dict[str, str]] = {}
    for mode, directions in numbers["setpoints"].items():
        found = {direction: entity_id for direction, entity_id in directions.items()
                 if owned(entity_id)}
        if found:
            setpoints[mode] = found
    pi = {key: entity_id for key, entity_id in numbers["pi"].items()
          if owned(entity_id)}
    return {"climate": climate, "setpoints": setpoints, "pi": pi}


def entity_values(
    hass: HomeAssistant, entry: ConfigEntry, zone_id: str,
    controls: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe owned numbers from live state or fresh persisted values."""
    fresh = hass.config_entries.async_get_entry(entry.entry_id) or entry
    stored = fresh.options.get(CONF_UI_CONFIG, {}).get(CONF_NUMBER_VALUES, {}).get(zone_id, {})
    result: dict[str, Any] = {}
    # Resolve each catalog entry through the already ownership-filtered control map.
    for description in (*SETPOINT_NUMBERS, *PI_NUMBERS):
        if description.param_type == "pi":
            entity_id = controls["pi"].get(description.pi_param)
        else:
            direction = "cool" if description.is_cooling else "heat"
            entity_id = controls["setpoints"].get(description.setpoint_mode, {}).get(direction)
        if entity_id is None:
            continue
        state = hass.states.get(entity_id)
        value: float | None = None
        source = SOURCE_DEFAULT
        if state is not None and state.state not in _INVALID_STATES:
            try:
                numeric = float(state.state)
                if math.isfinite(numeric):
                    value, source = numeric, SOURCE_NUMBER_ENTITY
                else:
                    _LOGGER.warning("Nonfinite numeric state for owned control %s", entity_id)
            except (TypeError, ValueError):
                _LOGGER.warning("Invalid numeric state for owned control %s", entity_id)
        if value is None and description.key in stored:
            value, source = stored[description.key], SOURCE_NUMBER_ENTITY
        result[description.key] = {"entity_id": entity_id, "value": value, "source": source}
    return result
