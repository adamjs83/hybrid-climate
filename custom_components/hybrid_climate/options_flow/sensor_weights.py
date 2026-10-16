"""Purpose: Build the aggregation choices and the inline per-sensor weight fields of the Basics page.

Key dependencies: Home Assistant selectors and shared aggregation constants.
Used by: options_flow/zone_pages/basics.py.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ..const import (
    AGGREGATION_AVERAGE,
    AGGREGATION_MAX,
    AGGREGATION_MEDIAN,
    AGGREGATION_MIN,
    AGGREGATION_WEIGHTED,
    DEFAULT_SENSOR_WEIGHT,
    MAX_SENSOR_WEIGHT,
    MIN_SENSOR_WEIGHT,
    SENSOR_WEIGHT_STEP,
)


def aggregation_selector() -> SelectSelector:
    """Return the zone basics aggregation selector with every supported method."""
    return SelectSelector(SelectSelectorConfig(
        options=[
            {"value": AGGREGATION_AVERAGE, "label": "Average"},
            {"value": AGGREGATION_MIN, "label": "Minimum (coldest)"},
            {"value": AGGREGATION_MAX, "label": "Maximum (warmest)"},
            {"value": AGGREGATION_MEDIAN, "label": "Median (ignores one outlier)"},
            {"value": AGGREGATION_WEIGHTED, "label": "Weighted"},
        ],
        mode=SelectSelectorMode.DROPDOWN,
    ))


def weight_fields(sensors: list[str], weights: dict[str, Any]) -> dict[Any, Any]:
    """Return one weight field per selected sensor, keyed by its entity id (stored weight or 1.0)."""
    return {
        vol.Required(entity_id, default=weights.get(entity_id, DEFAULT_SENSOR_WEIGHT)): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SENSOR_WEIGHT,
                max=MAX_SENSOR_WEIGHT,
                step=SENSOR_WEIGHT_STEP,
                mode=NumberSelectorMode.BOX,
            ))
        for entity_id in sensors
    }
