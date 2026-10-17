"""Purpose: Resolve a device's target step and round dispatched targets to it.

Key dependencies: Home Assistant climate attributes and const.py.
Used by: device_manager, setpoint_limits, manual_override and command_ack.
"""
from __future__ import annotations

import math

from homeassistant.components.climate.const import ATTR_TARGET_TEMP_STEP
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_TARGET_TEMP_STEP_C,
    DEFAULT_TARGET_TEMP_STEP_F,
    EXTERNAL_CHANGE_TOLERANCE_F,
    HVAC_MODE_COOL,
    TARGET_RESEND_FRACTION,
    TARGET_ROUND_DIGITS,
    TARGET_TIE_EPSILON,
)
from .models import Device


def is_finite_number(value: object) -> bool:
    """Return whether a value is a finite real number (a bool is not)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def resolve_step(hass: HomeAssistant, device: Device) -> float:
    """Return the device's target_temp_step, or HA's per-unit default."""
    state = hass.states.get(device.entity_id)
    step = state.attributes.get(ATTR_TARGET_TEMP_STEP) if state else None
    if is_finite_number(step) and step > 0:
        return float(step)
    units = getattr(getattr(hass, "config", None), "units", None)
    unit = getattr(units, "temperature_unit", None)
    return DEFAULT_TARGET_TEMP_STEP_C if unit == UnitOfTemperature.CELSIUS else DEFAULT_TARGET_TEMP_STEP_F


def quantize_target(target: float, step: float, mode: str) -> float:
    """Round to the nearest step; an exact tie goes toward the demand (heat up, cool down)."""
    ratio = target / step
    lower = math.floor(ratio)
    fraction = ratio - lower
    if abs(fraction - 0.5) <= TARGET_TIE_EPSILON:
        # Exact tie: cooling demands a lower target, everything else a higher one.
        count = lower if mode == HVAC_MODE_COOL else lower + 1
    else:
        count = lower + 1 if fraction > 0.5 else lower
    return round(count * step, TARGET_ROUND_DIGITS)


def target_tolerance(step: float | None) -> float:
    """Return how far a reported target may sit from the commanded one and still match."""
    return max(EXTERNAL_CHANGE_TOLERANCE_F, (step or 0.0) / 2)


def needs_resend(reported: object, target: float, step: float) -> bool:
    """Return whether the reported target is far enough from the raw one to send again."""
    if not is_finite_number(reported):
        return True
    return abs(reported - target) > step * TARGET_RESEND_FRACTION


def accepted_target(reported: object, target: float | None) -> float | None:
    """Return the physical target to record when no send was needed (the report, if usable)."""
    return float(reported) if target is not None and is_finite_number(reported) else target
