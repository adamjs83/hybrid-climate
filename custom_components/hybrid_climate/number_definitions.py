"""Static entity descriptions for number platform.

Defines the setpoint and heating PI parameter number entities (cooling PI ones: cool_pi_numbers.py), their ranges,
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
from homeassistant.helpers.entity import EntityCategory
from .const import COOL_SLIDER_MAX, COOL_SLIDER_MIN, COOL_SLIDER_STEP


@dataclass(frozen=True)
class HybridClimateNumberEntityDescription(NumberEntityDescription):
    """Describes a Hybrid Climate number entity."""

    param_type: str = ""  # "setpoint", "pi" (heating) or "cool_pi" (cooling)
    setpoint_mode: str | None = None  # For setpoints: default, away, sleep, etc.
    is_cooling: bool = False  # For setpoints: heat vs cool
    pi_param: str | None = None  # For PI: kp, ki, k_ext, offset_max, balance_point (cooling: kp, ki, offset_max, k_ext, balance_point)


# Setpoint number definitions
SETPOINT_NUMBERS: tuple[HybridClimateNumberEntityDescription, ...] = (
    # Heat setpoints
    HybridClimateNumberEntityDescription(
        key="default_heat_temp",
        translation_key="heat_home",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="heat_away",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="heat_sleep",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="heat_vacation",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="cool_home",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="cool_away",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="cool_occupied",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="cool_unoccupied",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="cool_sleep",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="cool_vacation",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="pi_kp",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="pi_ki",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="pi_k_ext",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="pi_offset_max",
        entity_category=EntityCategory.CONFIG,
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
        translation_key="pi_balance_point",
        entity_category=EntityCategory.CONFIG,
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
