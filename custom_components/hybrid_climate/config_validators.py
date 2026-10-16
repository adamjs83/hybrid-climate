"""Purpose: YAML coercion validators shared by the configuration schemas.

Key dependencies: voluptuous; const.py (cooling regulation modes, idle actions).
Used by: config_schemas.py (DEVICE_IDLE_SCHEMA, DEVICE_SCHEMA, REGULATION_SCHEMA).
"""
from __future__ import annotations

from math import isfinite
from typing import Any

import voluptuous as vol

from .const import (
    COOL_REGULATION_MODES,
    COOL_REGULATION_OFF,
    IDLE_ACTION_OFF,
    IDLE_ACTIONS,
    MAX_REGULATION_MIN_PERIOD,
    MAX_REGULATION_THRESHOLD,
    MIN_REGULATION_MIN_PERIOD,
    MIN_REGULATION_THRESHOLD,
)


def _strict_bool(value: Any) -> bool:
    """Accept only a real boolean (no "yes"/1 coercion)."""
    if type(value) is not bool:
        raise vol.Invalid("value must be true or false")
    return value


def _cool_regulation_mode(value: Any) -> str:
    """Accept a cooling regulation mode; bare YAML off arrives as boolean false."""
    # YAML 1.1 reads an unquoted off as False. Only exactly False maps to off;
    # True and every other non-string still fail the enum check below.
    if type(value) is bool and value is False:
        value = COOL_REGULATION_OFF
    return vol.In(COOL_REGULATION_MODES)(value)


def _idle_action(value: Any) -> str:
    """Accept a device idle action; bare YAML off arrives as boolean false."""
    # YAML 1.1 reads an unquoted off as False. Only exactly False maps to off;
    # True and every other non-string still fail the enum check below.
    if type(value) is bool and value is False:
        value = IDLE_ACTION_OFF
    return vol.In(IDLE_ACTIONS)(value)


def _regulation_threshold(value: Any) -> float:
    """Accept a finite numeric threshold but never a boolean."""
    if isinstance(value, bool):
        raise vol.Invalid("regulation_threshold must be a number")
    threshold = vol.Coerce(float)(value)
    if not isfinite(threshold):
        raise vol.Invalid("regulation_threshold must be finite")
    return vol.Range(min=MIN_REGULATION_THRESHOLD, max=MAX_REGULATION_THRESHOLD)(threshold)


def _regulation_min_period(value: Any) -> int:
    """Accept only whole minute counts, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise vol.Invalid("regulation_min_period must be an integer")
    return vol.Range(min=MIN_REGULATION_MIN_PERIOD, max=MAX_REGULATION_MIN_PERIOD)(value)
