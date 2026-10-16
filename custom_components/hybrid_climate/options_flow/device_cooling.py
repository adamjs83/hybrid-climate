"""Purpose: A device's cooling settings: the per-device cooling regulation block the Regulation zone page shows
(mode, correction, sensor, change limits; v0.17.0 §2), the coil dry-out fields the device page keeps, their
load/coerce helpers, and the device-entry writer the Regulation page saves through.

Key dependencies: Home Assistant selectors, const.py, cool_pi_const.py (v0.17.3 unit-correction keys),
config_parsers.resolve_cool_regulation.
Used by: options_flow/devices.py (dry-out fields, load and save of device config);
options_flow/zone_pages/regulation_cooling.py (regulation fields, write_cooling_settings).
"""
from __future__ import annotations

from collections.abc import Mapping
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
    CONF_DEVICES,
    CONF_UI_VERSION,
    COOL_COMPENSATION_MAX_STEP,
    COOL_COMPENSATION_SENSOR_DOMAIN,
    COOL_DRY_OUT_MINUTES_STEP,
    COOL_OVERDRIVE_STEP,
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
    MAX_COOL_OVERDRIVE,
    MAX_COOL_REGULATION_MIN_PERIOD,
    MAX_COOL_REGULATION_THRESHOLD,
    MIN_COOL_COMPENSATION_MAX,
    MIN_COOL_DRY_OUT_MINUTES,
    MIN_COOL_OVERDRIVE,
    MIN_COOL_REGULATION_MIN_PERIOD,
    MIN_COOL_REGULATION_THRESHOLD,
)
from ..cool_pi_const import (
    CONF_COOL_MAX_TOTAL_PUSH,
    CONF_COOL_PI_COMPENSATION,
    COOL_MAX_TOTAL_PUSH_STEP,
    DEFAULT_COOL_MAX_TOTAL_PUSH,
    DEFAULT_COOL_PI_COMPENSATION,
    MAX_COOL_MAX_TOTAL_PUSH,
    MIN_COOL_MAX_TOTAL_PUSH,
)

# Stored defaults. None (mode) and "" (sensor) are dropped by the converter, so
# an unset mode keeps the load-time migration and a blank sensor means "use the
# unit's own current_temperature".
COOLING_DEFAULTS: dict[str, Any] = {
    CONF_COOL_REGULATION: None,
    CONF_COOL_COMPENSATION_MAX: DEFAULT_COOL_COMPENSATION_MAX,
    CONF_COOL_PI_COMPENSATION: DEFAULT_COOL_PI_COMPENSATION,
    CONF_COOL_MAX_TOTAL_PUSH: DEFAULT_COOL_MAX_TOTAL_PUSH,
    CONF_COOL_COMPENSATION_SENSOR: "",
    CONF_COOL_REGULATION_THRESHOLD: DEFAULT_COOL_REGULATION_THRESHOLD,
    CONF_COOL_REGULATION_MIN_PERIOD: DEFAULT_COOL_REGULATION_MIN_PERIOD,
    CONF_COOL_DRY_OUT: DEFAULT_COOL_DRY_OUT,
    CONF_COOL_DRY_OUT_MINUTES: DEFAULT_COOL_DRY_OUT_MINUTES,
}

# The page keys of one device's cooling regulation block, in form order (the Regulation page writes only these).
COOLING_REGULATION_KEYS = (
    CONF_COOL_REGULATION, CONF_COOL_OVERDRIVE, CONF_COOL_COMPENSATION_MAX, CONF_COOL_PI_COMPENSATION,
    CONF_COOL_MAX_TOTAL_PUSH, CONF_COOL_COMPENSATION_SENSOR, CONF_COOL_REGULATION_THRESHOLD,
    CONF_COOL_REGULATION_MIN_PERIOD,
)
DRY_OUT_KEYS = (CONF_COOL_DRY_OUT, CONF_COOL_DRY_OUT_MINUTES)
UI_VERSION = 1

# Cooling PI is an ordinary mode since v0.17.0 (the zone's cooling PI number entities hold its gains).
MODE_OPTIONS = [
    {"value": COOL_REGULATION_OFF, "label": "Use room target"},
    {"value": COOL_REGULATION_OVERDRIVE, "label": "Fixed cooling correction"},
    {"value": COOL_REGULATION_COMPENSATION, "label": "Correct the unit's temperature reading"},
    {"value": COOL_REGULATION_PI, "label": "Cooling PI"},
]


def merge_cooling_settings(overrides: dict[str, Any]) -> dict[str, Any]:
    """Return the stored cooling settings: defaults updated with known overrides."""
    unknown = set(overrides) - set(COOLING_DEFAULTS)
    if unknown:
        raise TypeError(f"unknown cooling settings: {sorted(unknown)}")
    return {**COOLING_DEFAULTS, **overrides}


def cooling_settings_from_yaml(device_conf: Mapping[str, Any]) -> dict[str, Any]:
    """Map a YAML device's cooling settings to the form's stored shape."""
    return {key: device_conf.get(key, default) for key, default in COOLING_DEFAULTS.items()}


def regulation_settings_from_stored(current: Mapping[str, Any]) -> dict[str, Any]:
    """Return a device's stored cooling regulation block as saved (an unset mode stays None)."""
    return {
        key: current.get(key, DEFAULT_COOL_OVERDRIVE if key == CONF_COOL_OVERDRIVE else COOLING_DEFAULTS[key])
        for key in COOLING_REGULATION_KEYS
    }


def regulation_form_values(current: Mapping[str, Any]) -> dict[str, Any]:
    """Return the block as the form shows it: the effective mode and "" for no sensor."""
    values = regulation_settings_from_stored(current)
    # A device without a stored mode follows the load-time migration (overdrive when cool_overdrive > 0).
    values[CONF_COOL_REGULATION] = resolve_cool_regulation(
        values[CONF_COOL_REGULATION], float(values[CONF_COOL_OVERDRIVE]))
    values[CONF_COOL_COMPENSATION_SENSOR] = values[CONF_COOL_COMPENSATION_SENSOR] or ""
    return values


def regulation_settings_from_input(user_input: Mapping[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    """Extract and coerce one submitted cooling regulation block; a missing field keeps its default."""
    def value(key: str) -> Any:
        """Return the submitted value of a key or the block's default."""
        return user_input.get(key, defaults[key])

    return {
        CONF_COOL_REGULATION: value(CONF_COOL_REGULATION),
        CONF_COOL_OVERDRIVE: float(value(CONF_COOL_OVERDRIVE)),
        CONF_COOL_COMPENSATION_MAX: float(value(CONF_COOL_COMPENSATION_MAX)),
        CONF_COOL_PI_COMPENSATION: bool(value(CONF_COOL_PI_COMPENSATION)),
        CONF_COOL_MAX_TOTAL_PUSH: float(value(CONF_COOL_MAX_TOTAL_PUSH)),
        # A cleared sensor is not submitted: "" means the unit's own current_temperature.
        CONF_COOL_COMPENSATION_SENSOR: user_input.get(CONF_COOL_COMPENSATION_SENSOR) or "",
        CONF_COOL_REGULATION_THRESHOLD: float(value(CONF_COOL_REGULATION_THRESHOLD)),
        CONF_COOL_REGULATION_MIN_PERIOD: int(value(CONF_COOL_REGULATION_MIN_PERIOD)),
    }


def dry_out_from_stored(current: Mapping[str, Any]) -> dict[str, Any]:
    """Return a device's stored coil dry-out settings (for a save that did not show them)."""
    return {key: current.get(key, COOLING_DEFAULTS[key]) for key in DRY_OUT_KEYS}


def dry_out_from_input(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Extract and coerce the submitted coil dry-out settings from the device form."""
    return {
        CONF_COOL_DRY_OUT: bool(user_input.get(CONF_COOL_DRY_OUT, DEFAULT_COOL_DRY_OUT)),
        CONF_COOL_DRY_OUT_MINUTES: int(user_input.get(CONF_COOL_DRY_OUT_MINUTES, DEFAULT_COOL_DRY_OUT_MINUTES)),
    }


def _number_box(minimum: float, maximum: float, step: float, unit: str) -> NumberSelector:
    """Build a boxed number selector."""
    return NumberSelector(NumberSelectorConfig(
        min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=NumberSelectorMode.BOX,
    ))


def cooling_regulation_fields(current: Mapping[str, Any]) -> dict[Any, Any]:
    """Build one device's cooling regulation block: mode, correction, unit correction, sensor, change limits."""
    values = regulation_form_values(current)
    # suggested_value (not default) so a cleared sensor stays cleared and "" is
    # never validated as an entity ID.
    sensor = values[CONF_COOL_COMPENSATION_SENSOR] or None
    return {
        vol.Required(CONF_COOL_REGULATION, default=values[CONF_COOL_REGULATION]): SelectSelector(
            SelectSelectorConfig(options=MODE_OPTIONS, mode=SelectSelectorMode.DROPDOWN)),
        vol.Required(CONF_COOL_OVERDRIVE, default=values[CONF_COOL_OVERDRIVE]):
            _number_box(MIN_COOL_OVERDRIVE, MAX_COOL_OVERDRIVE, COOL_OVERDRIVE_STEP, "°F"),
        vol.Required(CONF_COOL_COMPENSATION_MAX, default=values[CONF_COOL_COMPENSATION_MAX]): _number_box(
            MIN_COOL_COMPENSATION_MAX, MAX_COOL_COMPENSATION_MAX, COOL_COMPENSATION_MAX_STEP, "°F"),
        vol.Required(CONF_COOL_PI_COMPENSATION, default=values[CONF_COOL_PI_COMPENSATION]): BooleanSelector(),
        vol.Required(CONF_COOL_MAX_TOTAL_PUSH, default=values[CONF_COOL_MAX_TOTAL_PUSH]): _number_box(
            MIN_COOL_MAX_TOTAL_PUSH, MAX_COOL_MAX_TOTAL_PUSH, COOL_MAX_TOTAL_PUSH_STEP, "°F"),
        vol.Optional(CONF_COOL_COMPENSATION_SENSOR, description={"suggested_value": sensor}): EntitySelector(
            EntitySelectorConfig(domain=COOL_COMPENSATION_SENSOR_DOMAIN)),
        vol.Required(CONF_COOL_REGULATION_THRESHOLD, default=values[CONF_COOL_REGULATION_THRESHOLD]): _number_box(
            MIN_COOL_REGULATION_THRESHOLD, MAX_COOL_REGULATION_THRESHOLD, COOL_REGULATION_THRESHOLD_STEP, "°F"),
        vol.Required(CONF_COOL_REGULATION_MIN_PERIOD, default=values[CONF_COOL_REGULATION_MIN_PERIOD]):
            _number_box(MIN_COOL_REGULATION_MIN_PERIOD, MAX_COOL_REGULATION_MIN_PERIOD,
                        COOL_REGULATION_MIN_PERIOD_STEP, "min"),
    }


def dry_out_fields(current: Mapping[str, Any]) -> dict[Any, Any]:
    """Build the device page's coil dry-out fields (a physical property of the unit)."""
    stored = dry_out_from_stored(current)
    return {
        vol.Required(CONF_COOL_DRY_OUT, default=stored[CONF_COOL_DRY_OUT]): BooleanSelector(),
        vol.Required(CONF_COOL_DRY_OUT_MINUTES, default=stored[CONF_COOL_DRY_OUT_MINUTES]): _number_box(
            MIN_COOL_DRY_OUT_MINUTES, MAX_COOL_DRY_OUT_MINUTES, COOL_DRY_OUT_MINUTES_STEP, "min"),
    }


def write_cooling_settings(
    ui_config: dict[str, Any], entity_id: str, settings: Mapping[str, Any], *, seed: Mapping[str, Any],
) -> None:
    """Write one device's cooling regulation block into ui_config.devices.<entity_id>; nothing else changes.

    A device with no stored entry starts from `seed`, the entry a first device-page save would write
    (entity id, capabilities, idle, compressor and every cooling key).
    """
    unknown = set(settings) - set(COOLING_REGULATION_KEYS)
    if unknown:
        raise TypeError(f"unknown cooling regulation settings: {sorted(unknown)}")
    devices = ui_config.get(CONF_DEVICES)
    devices = dict(devices) if isinstance(devices, dict) else {}
    stored = devices.get(entity_id)
    entry = dict(stored) if isinstance(stored, dict) else dict(seed)
    entry.update({key: settings[key] for key in COOLING_REGULATION_KEYS})
    devices[entity_id] = entry
    ui_config[CONF_DEVICES] = devices
    ui_config[CONF_UI_VERSION] = UI_VERSION
