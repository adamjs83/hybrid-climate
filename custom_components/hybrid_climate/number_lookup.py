"""Purpose: Read a zone's number entities by entity-registry unique id, with per-parameter defaults.

Key dependencies: zone_helpers.resolve_number_entity_id (registry lookup on
hybrid_climate_<zone_id>_<key>); cool_pi_const.py (cooling number keys); const.py (heating defaults).
Used by: pi_controller.py (heating PI gains); the cooling PI controller (cooling gains).
"""
from __future__ import annotations

from collections.abc import Mapping
import logging

from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_BALANCE_POINT,
    DEFAULT_K_EXT,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_OFFSET_MAX,
)
from .cool_pi_const import (
    NUMBER_KEY_COOL_PI_KI,
    NUMBER_KEY_COOL_PI_KP,
    NUMBER_KEY_COOL_PI_OFFSET_MAX,
)
from .zone_helpers import resolve_number_entity_id

_LOGGER = logging.getLogger(__name__)

# Parameter name -> number entity key (the unique-id suffix).
HEAT_PI_NUMBER_KEYS: Mapping[str, str] = {
    "kp": "pi_kp",
    "ki": "pi_ki",
    "k_ext": "pi_k_ext",
    "offset_max": "pi_offset_max",
    "balance_point": "pi_balance_point",
}
COOL_PI_NUMBER_KEYS: Mapping[str, str] = {
    "kp": NUMBER_KEY_COOL_PI_KP,
    "ki": NUMBER_KEY_COOL_PI_KI,
    "offset_max": NUMBER_KEY_COOL_PI_OFFSET_MAX,
}
HEAT_PI_DEFAULTS: Mapping[str, float] = {
    "kp": DEFAULT_KP,
    "ki": DEFAULT_KI,
    "k_ext": DEFAULT_K_EXT,
    "offset_max": DEFAULT_OFFSET_MAX,
    "balance_point": DEFAULT_BALANCE_POINT,
}


def read_zone_numbers(
    hass: HomeAssistant,
    zone_id: str,
    keys: Mapping[str, str],
    defaults: Mapping[str, float],
) -> dict[str, float]:
    """Return {param: value} from the zone's registered numbers, the default where unreadable."""
    params: dict[str, float] = {}
    for param, key in keys.items():
        # Registry resolution by unique id; entity ids are never built from patterns.
        entity_id = resolve_number_entity_id(hass, zone_id, key)
        state = hass.states.get(entity_id) if entity_id else None
        if state is not None:
            try:
                params[param] = float(state.state)
                continue
            except (ValueError, TypeError):
                _LOGGER.debug("Number %s for zone %s is not numeric (%s); using default",
                              key, zone_id, state.state)
        else:
            _LOGGER.debug("Number %s for zone %s not found; using default", key, zone_id)
        params[param] = defaults[param]
    return params
