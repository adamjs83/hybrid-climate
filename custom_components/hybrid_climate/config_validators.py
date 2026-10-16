"""Purpose: YAML coercion validators shared by the configuration schemas.

Key dependencies: voluptuous; const.py (cooling regulation modes, idle actions).
Used by: config_schemas.py (DEVICE_IDLE_SCHEMA, DEVICE_SCHEMA).
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from .const import (
    COOL_REGULATION_MODES,
    COOL_REGULATION_OFF,
    IDLE_ACTION_OFF,
    IDLE_ACTIONS,
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
