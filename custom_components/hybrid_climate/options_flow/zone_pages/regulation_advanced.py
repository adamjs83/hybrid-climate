"""Purpose: The collapsed `advanced_heating` and `advanced_cooling` sections of the zone Regulation page: the
heating PI block's five advanced values and the zone cooling PI block's three, so a UI-created zone can change
them (they were YAML-only). Defaults, form fields, submit parsing and the save writers live here.

Key dependencies: const.py and cool_pi_const.py (keys, defaults, bounds), page_const.py (units).
Used by: zone_pages/regulation.py (RegulationPageMixin).
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, NumberSelectorMode

from ...const import (
    CONF_ACCUMULATED_ERROR_THRESHOLD,
    CONF_INTEGRAL_DECAY_HALFLIFE,
    CONF_INTEGRAL_RESET_FACTOR,
    CONF_INTEGRAL_RESET_THRESHOLD,
    CONF_REGULATION,
    CONF_REGULATION_TYPE,
    CONF_STABILIZATION_THRESHOLD,
    DEFAULT_ACCUMULATED_ERROR_THRESHOLD,
    DEFAULT_INTEGRAL_DECAY_HALFLIFE,
    DEFAULT_INTEGRAL_RESET_FACTOR,
    DEFAULT_INTEGRAL_RESET_THRESHOLD,
    DEFAULT_STABILIZATION_THRESHOLD,
    MAX_ACCUMULATED_ERROR_THRESHOLD,
    MAX_INTEGRAL_DECAY_HALFLIFE,
    MAX_INTEGRAL_RESET_FACTOR,
    MAX_INTEGRAL_RESET_THRESHOLD,
    MAX_STABILIZATION_THRESHOLD,
    MIN_ACCUMULATED_ERROR_THRESHOLD,
    MIN_INTEGRAL_DECAY_HALFLIFE,
    MIN_INTEGRAL_RESET_FACTOR,
    MIN_INTEGRAL_RESET_THRESHOLD,
    MIN_STABILIZATION_THRESHOLD,
    REGULATION_PI,
    STEP_ACCUMULATED_ERROR_THRESHOLD,
    STEP_INTEGRAL_DECAY_HALFLIFE,
    STEP_INTEGRAL_RESET_FACTOR,
    STEP_INTEGRAL_RESET_THRESHOLD,
    STEP_STABILIZATION_THRESHOLD,
)
from ...cool_pi_const import (
    CONF_ZONE_COOL_REGULATION,
    DEFAULT_COOL_PI_ERROR_CAP,
    DEFAULT_COOL_PI_HALFLIFE,
    DEFAULT_COOL_PI_STABILIZATION,
    MAX_COOL_PI_ERROR_CAP,
    MAX_COOL_PI_HALFLIFE,
    MAX_COOL_PI_STABILIZATION,
    MIN_COOL_PI_ERROR_CAP,
    MIN_COOL_PI_HALFLIFE,
    MIN_COOL_PI_STABILIZATION,
    STEP_COOL_PI_ERROR_CAP,
    STEP_COOL_PI_HALFLIFE,
    STEP_COOL_PI_STABILIZATION,
)
from ..page_const import MINUTES_UNIT, TEMPERATURE_UNIT

# key -> (default, min, max, step, unit or None); order is the form order.
HEATING_ADVANCED: dict[str, tuple[float, float, float, float, str | None]] = {
    CONF_STABILIZATION_THRESHOLD: (
        DEFAULT_STABILIZATION_THRESHOLD, MIN_STABILIZATION_THRESHOLD, MAX_STABILIZATION_THRESHOLD,
        STEP_STABILIZATION_THRESHOLD, TEMPERATURE_UNIT),
    CONF_ACCUMULATED_ERROR_THRESHOLD: (
        DEFAULT_ACCUMULATED_ERROR_THRESHOLD, MIN_ACCUMULATED_ERROR_THRESHOLD, MAX_ACCUMULATED_ERROR_THRESHOLD,
        STEP_ACCUMULATED_ERROR_THRESHOLD, None),
    CONF_INTEGRAL_RESET_THRESHOLD: (
        DEFAULT_INTEGRAL_RESET_THRESHOLD, MIN_INTEGRAL_RESET_THRESHOLD, MAX_INTEGRAL_RESET_THRESHOLD,
        STEP_INTEGRAL_RESET_THRESHOLD, TEMPERATURE_UNIT),
    CONF_INTEGRAL_RESET_FACTOR: (
        DEFAULT_INTEGRAL_RESET_FACTOR, MIN_INTEGRAL_RESET_FACTOR, MAX_INTEGRAL_RESET_FACTOR,
        STEP_INTEGRAL_RESET_FACTOR, None),
    CONF_INTEGRAL_DECAY_HALFLIFE: (
        DEFAULT_INTEGRAL_DECAY_HALFLIFE, MIN_INTEGRAL_DECAY_HALFLIFE, MAX_INTEGRAL_DECAY_HALFLIFE,
        STEP_INTEGRAL_DECAY_HALFLIFE, MINUTES_UNIT),
}

COOLING_ADVANCED: dict[str, tuple[float, float, float, float, str | None]] = {
    CONF_STABILIZATION_THRESHOLD: (
        DEFAULT_COOL_PI_STABILIZATION, MIN_COOL_PI_STABILIZATION, MAX_COOL_PI_STABILIZATION,
        STEP_COOL_PI_STABILIZATION, TEMPERATURE_UNIT),
    CONF_ACCUMULATED_ERROR_THRESHOLD: (
        DEFAULT_COOL_PI_ERROR_CAP, MIN_COOL_PI_ERROR_CAP, MAX_COOL_PI_ERROR_CAP, STEP_COOL_PI_ERROR_CAP, None),
    CONF_INTEGRAL_DECAY_HALFLIFE: (
        DEFAULT_COOL_PI_HALFLIFE, MIN_COOL_PI_HALFLIFE, MAX_COOL_PI_HALFLIFE, STEP_COOL_PI_HALFLIFE, MINUTES_UNIT),
}


def _defaults(table: dict[str, tuple[float, float, float, float, str | None]],
              block: dict[str, Any] | None) -> dict[str, float]:
    """Return each key's stored value (as float) or its constant default."""
    stored = block if isinstance(block, dict) else {}
    return {key: float(stored.get(key, spec[0])) for key, spec in table.items()}


def _fields(table: dict[str, tuple[float, float, float, float, str | None]],
            defaults: dict[str, float]) -> dict[Any, Any]:
    """Build the BOX number fields of one advanced section."""
    fields: dict[Any, Any] = {}
    for key, (_default, low, high, step, unit) in table.items():
        config: dict[str, Any] = {"min": low, "max": high, "step": step, "mode": NumberSelectorMode.BOX}
        if unit is not None:
            config["unit_of_measurement"] = unit
        fields[vol.Required(key, default=defaults[key])] = NumberSelector(NumberSelectorConfig(**config))
    return fields


def advanced_heating_defaults(pi_config: dict[str, Any] | None) -> dict[str, float]:
    """Return the five heating advanced values from the stored PI block, constants otherwise."""
    return _defaults(HEATING_ADVANCED, pi_config)


def advanced_cooling_defaults(cool_block: dict[str, Any] | None) -> dict[str, float]:
    """Return the three cooling advanced values from the zone's cool_regulation block, constants otherwise."""
    return _defaults(COOLING_ADVANCED, cool_block)


def advanced_heating_fields(defaults: dict[str, float]) -> dict[Any, Any]:
    """Return the advanced_heating section's fields."""
    return _fields(HEATING_ADVANCED, defaults)


def advanced_cooling_fields(defaults: dict[str, float]) -> dict[Any, Any]:
    """Return the advanced_cooling section's fields."""
    return _fields(COOLING_ADVANCED, defaults)


def advanced_values(user_input_section: dict[str, Any] | None, defaults: dict[str, float]) -> dict[str, float]:
    """Return a submitted section's values as floats; a missing key falls back to its default."""
    submitted = user_input_section or {}
    return {key: float(submitted.get(key, default)) for key, default in defaults.items()}


def apply_advanced_heating(zone: dict[str, Any], values: dict[str, float], defaults: dict[str, float]) -> None:
    """Write the five keys into a stored PI block; no-op when unchanged or when the zone has no PI block."""
    if values == defaults:
        return
    block = zone.get(CONF_REGULATION)
    # Direct stores no regulation block, so there is nothing to hold these values.
    if isinstance(block, dict) and block.get(CONF_REGULATION_TYPE) == REGULATION_PI:
        block.update(values)


def apply_advanced_cooling(zone: dict[str, Any], values: dict[str, float], defaults: dict[str, float]) -> None:
    """Merge the three values into the zone's cool_regulation block; no-op when unchanged."""
    if values == defaults:
        return
    existing = zone.get(CONF_ZONE_COOL_REGULATION)
    zone[CONF_ZONE_COOL_REGULATION] = {**(existing if isinstance(existing, dict) else {}), **values}
