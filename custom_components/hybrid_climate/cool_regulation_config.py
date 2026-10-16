"""Purpose: Zone-level cooling PI regulation config: dataclass, YAML schema and parser.

Key dependencies: voluptuous; cool_pi_const.py (defaults, bounds); const.py (shared PI key names).
Used by: models.py (ZoneConfig.cool_regulation), config_schemas.py (ZONE_SCHEMA), config_parsers.py (parse_zone).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import inf, isfinite
from typing import Any

import voluptuous as vol

from .const import (
    CONF_ACCUMULATED_ERROR_THRESHOLD,
    CONF_BALANCE_POINT,
    CONF_INTEGRAL_DECAY_HALFLIFE,
    CONF_K_EXT,
    CONF_KI,
    CONF_KP,
    CONF_OFFSET_MAX,
    CONF_STABILIZATION_THRESHOLD,
)
from .cool_pi_const import (
    DEFAULT_COOL_PI_BALANCE_POINT,
    DEFAULT_COOL_PI_K_EXT,
    DEFAULT_COOL_PI_ERROR_CAP,
    DEFAULT_COOL_PI_HALFLIFE,
    DEFAULT_COOL_PI_KI,
    DEFAULT_COOL_PI_KP,
    DEFAULT_COOL_PI_OFFSET_MAX,
    DEFAULT_COOL_PI_STABILIZATION,
    MAX_COOL_PI_BALANCE_POINT,
    MAX_COOL_PI_K_EXT,
    MAX_COOL_PI_OFFSET_MAX,
    MIN_COOL_PI_BALANCE_POINT,
    MIN_COOL_PI_K_EXT,
    MIN_COOL_PI_OFFSET_MAX,
)


@dataclass(frozen=True)
class CoolRegulationConfig:
    """Cooling PI gains and limits for one zone (with an optional outdoor term)."""
    kp: float = DEFAULT_COOL_PI_KP
    ki: float = DEFAULT_COOL_PI_KI
    offset_max: float = DEFAULT_COOL_PI_OFFSET_MAX
    stabilization_threshold: float = DEFAULT_COOL_PI_STABILIZATION
    accumulated_error_threshold: float = DEFAULT_COOL_PI_ERROR_CAP
    integral_decay_halflife: float = DEFAULT_COOL_PI_HALFLIFE
    k_ext: float = DEFAULT_COOL_PI_K_EXT
    balance_point: float = DEFAULT_COOL_PI_BALANCE_POINT


def _finite_float(name: str, minimum: float = 0.0, maximum: float = inf) -> Callable[[Any], float]:
    """Build a validator for a finite, non-bool float within [minimum, maximum]."""
    def validate(value: Any) -> float:
        """Reject bools, non-numbers, non-finite values and values outside the bounds."""
        if type(value) is bool:
            raise vol.Invalid(f"{name} must be a number")
        number = vol.Coerce(float)(value)
        if not isfinite(number) or not minimum <= number <= maximum:
            raise vol.Invalid(f"{name} must be finite and between {minimum} and {maximum}")
        return number
    return validate


# Absent keys stay absent so the stored shape is unchanged; the parser fills defaults.
COOL_REGULATION_SCHEMA = vol.Schema({
    vol.Optional(CONF_KP): _finite_float(CONF_KP),
    vol.Optional(CONF_KI): _finite_float(CONF_KI),
    vol.Optional(CONF_OFFSET_MAX): _finite_float(CONF_OFFSET_MAX, MIN_COOL_PI_OFFSET_MAX, MAX_COOL_PI_OFFSET_MAX),
    vol.Optional(CONF_STABILIZATION_THRESHOLD): _finite_float(CONF_STABILIZATION_THRESHOLD),
    vol.Optional(CONF_ACCUMULATED_ERROR_THRESHOLD): _finite_float(CONF_ACCUMULATED_ERROR_THRESHOLD),
    vol.Optional(CONF_INTEGRAL_DECAY_HALFLIFE): _finite_float(CONF_INTEGRAL_DECAY_HALFLIFE),
    vol.Optional(CONF_K_EXT): _finite_float(CONF_K_EXT, MIN_COOL_PI_K_EXT, MAX_COOL_PI_K_EXT),
    vol.Optional(CONF_BALANCE_POINT): _finite_float(
        CONF_BALANCE_POINT, MIN_COOL_PI_BALANCE_POINT, MAX_COOL_PI_BALANCE_POINT),
})


def parse_cool_regulation(data: Mapping[str, Any] | None) -> CoolRegulationConfig:
    """Parse a validated zone cool_regulation block; None or empty gives the defaults."""
    if not data:
        return CoolRegulationConfig()
    return CoolRegulationConfig(
        kp=data.get(CONF_KP, DEFAULT_COOL_PI_KP),
        ki=data.get(CONF_KI, DEFAULT_COOL_PI_KI),
        offset_max=data.get(CONF_OFFSET_MAX, DEFAULT_COOL_PI_OFFSET_MAX),
        stabilization_threshold=data.get(CONF_STABILIZATION_THRESHOLD, DEFAULT_COOL_PI_STABILIZATION),
        accumulated_error_threshold=data.get(CONF_ACCUMULATED_ERROR_THRESHOLD, DEFAULT_COOL_PI_ERROR_CAP),
        integral_decay_halflife=data.get(CONF_INTEGRAL_DECAY_HALFLIFE, DEFAULT_COOL_PI_HALFLIFE),
        k_ext=data.get(CONF_K_EXT, DEFAULT_COOL_PI_K_EXT),
        balance_point=data.get(CONF_BALANCE_POINT, DEFAULT_COOL_PI_BALANCE_POINT),
    )
