"""Static entity descriptions for number platform.

Defines the setpoint and PI parameter number entities, their ranges,
defaults, and display properties.

Key dependencies: const.py
Used by: number.py (async_setup_entry creates entities from these)
"""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTemperature
from .const import COOL_SLIDER_MAX, COOL_SLIDER_MIN, COOL_SLIDER_STEP


@dataclass(frozen=True)
class HybridClimateNumberEntityDescription(NumberEntityDescription):
    """Describes a Hybrid Climate number entity."""

    param_type: str = ""  # "setpoint" or "pi"
    setpoint_mode: str | None = None  # For setpoints: default, away, sleep, etc.
    is_cooling: bool = False  # For setpoints: heat vs cool
    pi_param: str | None = None  # For PI: kp, ki, k_ext, offset_max, balance_point


# Setpoint number definitions
SETPOINT_NUMBERS: tuple[HybridClimateNumberEntityDescription, ...] = (
    # Heat setpoints
    HybridClimateNumberEntityDescription(
        key="default_heat_temp",
        name="Default Heat",
        icon="mdi:thermometer",
        native_min_value=50,
        native_max_value=90,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.SLIDER,
        param_type="setpoint",
        setpoint_mode="default",
        is_cooling=False,
    ),
    HybridClimateNumberEntityDescription(
        key="away_heat_temp",
        name="Away Heat",
        icon="mdi:home-export-outline",
        native_min_value=50,
        native_max_value=90,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.SLIDER,
        param_type="setpoint",
        setpoint_mode="away",
        is_cooling=False,
    ),
    HybridClimateNumberEntityDescription(
        key="sleep_heat_temp",
        name="Sleep Heat",
        icon="mdi:sleep",
        native_min_value=50,
        native_max_value=90,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.SLIDER,
        param_type="setpoint",
        setpoint_mode="sleep",
        is_cooling=False,
    ),
    HybridClimateNumberEntityDescription(
        key="vacation_heat_temp",
        name="Vacation Heat",
        icon="mdi:beach",
        native_min_value=40,
        native_max_value=80,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.SLIDER,
        param_type="setpoint",
        setpoint_mode="vacation",
        is_cooling=False,
    ),
    # Cool setpoints
    HybridClimateNumberEntityDescription(
        key="default_cool_temp",
        name="Default Cool",
        icon="mdi:thermometer",
        native_min_value=60,
        native_max_value=90,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.SLIDER,
        param_type="setpoint",
        setpoint_mode="default",
        is_cooling=True,
    ),
    HybridClimateNumberEntityDescription(
        key="away_cool_temp",
        name="Away Cool",
        icon="mdi:home-export-outline",
        native_min_value=60,
        native_max_value=95,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.SLIDER,
        param_type="setpoint",
        setpoint_mode="away",
        is_cooling=True,
    ),
    HybridClimateNumberEntityDescription(
        key="occupied_cool_temp",
        name="Occupied Cool",
        icon="mdi:home-account",
        native_min_value=COOL_SLIDER_MIN,
        native_max_value=COOL_SLIDER_MAX,
        native_step=COOL_SLIDER_STEP,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.SLIDER,
        param_type="setpoint",
        setpoint_mode="occupied",
        is_cooling=True,
    ),
    HybridClimateNumberEntityDescription(
        key="unoccupied_cool_temp",
        name="Unoccupied Cool",
        icon="mdi:home-export-outline",
        native_min_value=COOL_SLIDER_MIN,
        native_max_value=COOL_SLIDER_MAX,
        native_step=COOL_SLIDER_STEP,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.SLIDER,
        param_type="setpoint",
        setpoint_mode="unoccupied",
        is_cooling=True,
    ),
    HybridClimateNumberEntityDescription(
        key="sleep_cool_temp",
        name="Sleep Cool",
        icon="mdi:sleep",
        native_min_value=60,
        native_max_value=90,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.SLIDER,
        param_type="setpoint",
        setpoint_mode="sleep",
        is_cooling=True,
    ),
    HybridClimateNumberEntityDescription(
        key="vacation_cool_temp",
        name="Vacation Cool",
        icon="mdi:beach",
        native_min_value=70,
        native_max_value=95,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.SLIDER,
        param_type="setpoint",
        setpoint_mode="vacation",
        is_cooling=True,
    ),
)

# PI parameter number definitions
PI_NUMBERS: tuple[HybridClimateNumberEntityDescription, ...] = (
    HybridClimateNumberEntityDescription(
        key="pi_kp",
        name="PI Kp",
        icon="mdi:chart-bell-curve",
        native_min_value=0.1,
        native_max_value=5.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        param_type="pi",
        pi_param="kp",
    ),
    HybridClimateNumberEntityDescription(
        key="pi_ki",
        name="PI Ki",
        icon="mdi:sigma",
        native_min_value=0.001,
        native_max_value=0.5,
        native_step=0.001,
        mode=NumberMode.BOX,
        param_type="pi",
        pi_param="ki",
    ),
    HybridClimateNumberEntityDescription(
        key="pi_k_ext",
        name="PI K_ext",
        icon="mdi:weather-partly-cloudy",
        native_min_value=0.0,
        native_max_value=1.0,
        native_step=0.05,
        mode=NumberMode.BOX,
        param_type="pi",
        pi_param="k_ext",
    ),
    HybridClimateNumberEntityDescription(
        key="pi_offset_max",
        name="PI Max Offset",
        icon="mdi:arrow-expand-vertical",
        native_min_value=1,
        native_max_value=20,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.BOX,
        param_type="pi",
        pi_param="offset_max",
    ),
    HybridClimateNumberEntityDescription(
        key="pi_balance_point",
        name="PI Balance Point",
        icon="mdi:scale-balance",
        native_min_value=30,
        native_max_value=80,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        mode=NumberMode.BOX,
        param_type="pi",
        pi_param="balance_point",
    ),
)
