"""Purpose: Cooling regulation and coil dry-out settings of the device options form.

Key dependencies: Home Assistant selectors, const.py, config_parsers.resolve_cool_regulation.
Used by: options_flow/devices.py (device_edit form, load and save of device config).
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ..config_parsers import resolve_cool_regulation
from ..const import (
    CONF_COOL_COMPENSATION_MAX,
    CONF_COOL_COMPENSATION_SENSOR,
    CONF_COOL_DRY_OUT,
    CONF_COOL_DRY_OUT_MINUTES,
    CONF_COOL_OVERDRIVE,
    CONF_COOL_REGULATION,
    CONF_COOL_REGULATION_MIN_PERIOD,
    CONF_COOL_REGULATION_THRESHOLD,
    COOL_COMPENSATION_MAX_STEP,
    COOL_COMPENSATION_SENSOR_DOMAIN,
    COOL_DRY_OUT_MINUTES_STEP,
    COOL_REGULATION_COMPENSATION,
    COOL_REGULATION_MIN_PERIOD_STEP,
    COOL_REGULATION_OFF,
    COOL_REGULATION_OVERDRIVE,
    COOL_REGULATION_PI,
    COOL_REGULATION_THRESHOLD_STEP,
    DEFAULT_COOL_COMPENSATION_MAX,
    DEFAULT_COOL_DRY_OUT,
    DEFAULT_COOL_DRY_OUT_MINUTES,
    DEFAULT_COOL_OVERDRIVE,
    DEFAULT_COOL_REGULATION_MIN_PERIOD,
    DEFAULT_COOL_REGULATION_THRESHOLD,
    MAX_COOL_COMPENSATION_MAX,
    MAX_COOL_DRY_OUT_MINUTES,
    MAX_COOL_REGULATION_MIN_PERIOD,
    MAX_COOL_REGULATION_THRESHOLD,
    MIN_COOL_COMPENSATION_MAX,
    MIN_COOL_DRY_OUT_MINUTES,
    MIN_COOL_REGULATION_MIN_PERIOD,
    MIN_COOL_REGULATION_THRESHOLD,
)

# Stored defaults. None (mode) and "" (sensor) are dropped by the converter, so
# an unset mode keeps the load-time migration and a blank sensor means "use the
# unit's own current_temperature".
COOLING_DEFAULTS: dict[str, Any] = {
    CONF_COOL_REGULATION: None,
    CONF_COOL_COMPENSATION_MAX: DEFAULT_COOL_COMPENSATION_MAX,
    CONF_COOL_COMPENSATION_SENSOR: "",
    CONF_COOL_REGULATION_THRESHOLD: DEFAULT_COOL_REGULATION_THRESHOLD,
    CONF_COOL_REGULATION_MIN_PERIOD: DEFAULT_COOL_REGULATION_MIN_PERIOD,
    CONF_COOL_DRY_OUT: DEFAULT_COOL_DRY_OUT,
    CONF_COOL_DRY_OUT_MINUTES: DEFAULT_COOL_DRY_OUT_MINUTES,
}

MODE_OPTIONS = [
    {"value": COOL_REGULATION_OFF, "label": "Off (send the zone target)"},
    {"value": COOL_REGULATION_OVERDRIVE, "label": "Fixed overdrive"},
    {"value": COOL_REGULATION_COMPENSATION, "label": "Compensate the unit's own sensor"},
    {"value": COOL_REGULATION_PI, "label": "Cooling PI (next release)"},
]


def merge_cooling_settings(overrides: dict[str, Any]) -> dict[str, Any]:
    """Return the stored cooling settings: defaults updated with known overrides."""
    unknown = set(overrides) - set(COOLING_DEFAULTS)
    if unknown:
        raise TypeError(f"unknown cooling settings: {sorted(unknown)}")
    return {**COOLING_DEFAULTS, **overrides}


def cooling_settings_from_yaml(device_conf: dict[str, Any]) -> dict[str, Any]:
    """Map a YAML device's cooling settings to the form's stored shape."""
    return {key: device_conf.get(key, default) for key, default in COOLING_DEFAULTS.items()}


def cooling_settings_from_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Extract and coerce the submitted cooling settings from the device form."""
    return {
        CONF_COOL_REGULATION: user_input.get(CONF_COOL_REGULATION),
        CONF_COOL_COMPENSATION_MAX: float(
            user_input.get(CONF_COOL_COMPENSATION_MAX, DEFAULT_COOL_COMPENSATION_MAX)),
        CONF_COOL_COMPENSATION_SENSOR: user_input.get(CONF_COOL_COMPENSATION_SENSOR) or "",
        CONF_COOL_REGULATION_THRESHOLD: float(
            user_input.get(CONF_COOL_REGULATION_THRESHOLD, DEFAULT_COOL_REGULATION_THRESHOLD)),
        CONF_COOL_REGULATION_MIN_PERIOD: int(
            user_input.get(CONF_COOL_REGULATION_MIN_PERIOD, DEFAULT_COOL_REGULATION_MIN_PERIOD)),
        CONF_COOL_DRY_OUT: bool(user_input.get(CONF_COOL_DRY_OUT, DEFAULT_COOL_DRY_OUT)),
        CONF_COOL_DRY_OUT_MINUTES: int(
            user_input.get(CONF_COOL_DRY_OUT_MINUTES, DEFAULT_COOL_DRY_OUT_MINUTES)),
    }


def _number_box(minimum: float, maximum: float, step: float, unit: str) -> NumberSelector:
    """Build a boxed number selector."""
    return NumberSelector(NumberSelectorConfig(
        min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=NumberSelectorMode.BOX,
    ))


def cooling_form_fields(current: dict[str, Any]) -> dict[Any, Any]:
    """Build the cooling regulation and coil dry-out fields of the device form."""
    # Show the effective mode: a device without a stored mode follows the
    # load-time migration (overdrive when cool_overdrive > 0, otherwise off).
    mode = resolve_cool_regulation(
        current.get(CONF_COOL_REGULATION), current.get(CONF_COOL_OVERDRIVE, DEFAULT_COOL_OVERDRIVE))
    # suggested_value (not default) so a cleared sensor stays cleared and "" is
    # never validated as an entity ID.
    sensor = current.get(CONF_COOL_COMPENSATION_SENSOR) or None

    def stored(key: str) -> Any:
        """Return the stored value of a key or its default."""
        return current.get(key, COOLING_DEFAULTS[key])

    return {
        vol.Required(CONF_COOL_REGULATION, default=mode): SelectSelector(SelectSelectorConfig(
            options=MODE_OPTIONS, mode=SelectSelectorMode.DROPDOWN,
        )),
        vol.Required(CONF_COOL_COMPENSATION_MAX, default=stored(CONF_COOL_COMPENSATION_MAX)): _number_box(
            MIN_COOL_COMPENSATION_MAX, MAX_COOL_COMPENSATION_MAX, COOL_COMPENSATION_MAX_STEP, "°F"),
        vol.Optional(CONF_COOL_COMPENSATION_SENSOR, description={"suggested_value": sensor}): EntitySelector(
            EntitySelectorConfig(domain=COOL_COMPENSATION_SENSOR_DOMAIN)),
        vol.Required(CONF_COOL_REGULATION_THRESHOLD, default=stored(CONF_COOL_REGULATION_THRESHOLD)): _number_box(
            MIN_COOL_REGULATION_THRESHOLD, MAX_COOL_REGULATION_THRESHOLD, COOL_REGULATION_THRESHOLD_STEP, "°F"),
        vol.Required(CONF_COOL_REGULATION_MIN_PERIOD, default=stored(CONF_COOL_REGULATION_MIN_PERIOD)): _number_box(
            MIN_COOL_REGULATION_MIN_PERIOD, MAX_COOL_REGULATION_MIN_PERIOD, COOL_REGULATION_MIN_PERIOD_STEP, "min"),
        vol.Required(CONF_COOL_DRY_OUT, default=stored(CONF_COOL_DRY_OUT)): BooleanSelector(),
        vol.Required(CONF_COOL_DRY_OUT_MINUTES, default=stored(CONF_COOL_DRY_OUT_MINUTES)): _number_box(
            MIN_COOL_DRY_OUT_MINUTES, MAX_COOL_DRY_OUT_MINUTES, COOL_DRY_OUT_MINUTES_STEP, "min"),
    }
