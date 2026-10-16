"""Purpose: Static number entity descriptions for the cooling PI gains and outdoor term.

Key dependencies: number_definitions.HybridClimateNumberEntityDescription, cool_pi_const.py
Used by: number.py, dashboard_api.py, agent_api/controls.py
"""
from __future__ import annotations

from homeassistant.components.number import NumberMode
from homeassistant.const import UnitOfTemperature

from .cool_pi_const import (
    MAX_COOL_PI_BALANCE_POINT,
    MAX_COOL_PI_K_EXT,
    MAX_COOL_PI_KI,
    MAX_COOL_PI_KP,
    MAX_COOL_PI_OFFSET_MAX,
    MIN_COOL_PI_BALANCE_POINT,
    MIN_COOL_PI_K_EXT,
    MIN_COOL_PI_KI,
    MIN_COOL_PI_KP,
    MIN_COOL_PI_OFFSET_MAX,
    NUMBER_KEY_COOL_PI_BALANCE_POINT,
    NUMBER_KEY_COOL_PI_K_EXT,
    NUMBER_KEY_COOL_PI_KI,
    NUMBER_KEY_COOL_PI_KP,
    NUMBER_KEY_COOL_PI_OFFSET_MAX,
    PARAM_TYPE_COOL_PI,
    STEP_COOL_PI_BALANCE_POINT,
    STEP_COOL_PI_K_EXT,
    STEP_COOL_PI_KI,
    STEP_COOL_PI_KP,
    STEP_COOL_PI_OFFSET_MAX,
)
from .number_definitions import HybridClimateNumberEntityDescription

# Created for zones with cool stages.
COOL_PI_NUMBERS: tuple[HybridClimateNumberEntityDescription, ...] = (
    HybridClimateNumberEntityDescription(
        key=NUMBER_KEY_COOL_PI_KP,
        name="Cooling PI proportional gain",
        icon="mdi:chart-bell-curve",
        native_min_value=MIN_COOL_PI_KP,
        native_max_value=MAX_COOL_PI_KP,
        native_step=STEP_COOL_PI_KP,
        mode=NumberMode.BOX,
        param_type=PARAM_TYPE_COOL_PI,
        pi_param="kp",
    ),
    HybridClimateNumberEntityDescription(
        key=NUMBER_KEY_COOL_PI_KI,
        name="Cooling PI integral gain",
        icon="mdi:sigma",
        native_min_value=MIN_COOL_PI_KI,
        native_max_value=MAX_COOL_PI_KI,
        native_step=STEP_COOL_PI_KI,
        mode=NumberMode.BOX,
        param_type=PARAM_TYPE_COOL_PI,
        pi_param="ki",
    ),
    HybridClimateNumberEntityDescription(
        key=NUMBER_KEY_COOL_PI_OFFSET_MAX,
        name="Cooling PI maximum push",
        icon="mdi:snowflake-thermometer",
        native_min_value=MIN_COOL_PI_OFFSET_MAX,
        native_max_value=MAX_COOL_PI_OFFSET_MAX,
        native_step=STEP_COOL_PI_OFFSET_MAX,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.BOX,
        param_type=PARAM_TYPE_COOL_PI,
        pi_param="offset_max",
    ),
    HybridClimateNumberEntityDescription(
        key=NUMBER_KEY_COOL_PI_K_EXT,
        name="Cooling PI outdoor gain",
        icon="mdi:weather-sunny",
        native_min_value=MIN_COOL_PI_K_EXT,
        native_max_value=MAX_COOL_PI_K_EXT,
        native_step=STEP_COOL_PI_K_EXT,
        mode=NumberMode.BOX,
        param_type=PARAM_TYPE_COOL_PI,
        pi_param="k_ext",
    ),
    HybridClimateNumberEntityDescription(
        key=NUMBER_KEY_COOL_PI_BALANCE_POINT,
        name="Cooling PI outdoor balance point",
        icon="mdi:scale-balance",
        native_min_value=MIN_COOL_PI_BALANCE_POINT,
        native_max_value=MAX_COOL_PI_BALANCE_POINT,
        native_step=STEP_COOL_PI_BALANCE_POINT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.BOX,
        param_type=PARAM_TYPE_COOL_PI,
        pi_param="balance_point",
    ),
)
