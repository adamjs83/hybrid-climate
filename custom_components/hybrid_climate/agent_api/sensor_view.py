"""Purpose: Project cached zone sensor readings and temperature aggregation.

Key dependencies: Cached ZoneState sensor readings and zone sensor configuration.
Used by: Agent API get_status zone projection.
"""

from __future__ import annotations

from collections.abc import Mapping
from statistics import median
from typing import Any

from ..aggregation import aggregate
from ..models import AggregationMethod, ZoneConfig, ZoneState
from .const import OUTLIER_ACTION_FLAGGED_ONLY, OUTLIER_COMPARE_EPSILON, SENSOR_OUTLIER_THRESHOLD


def sensor_values(sensor_view: Mapping[str, Any], state: ZoneState, entity_id: str) -> dict[str, Any]:
    """Add the cached raw/smoothed reading and deviation to an existing sensor entry."""
    value = state.sensor_values.get(entity_id)
    smoothed = state.sensor_smoothed_values.get(entity_id)
    deviation = (
        round(smoothed - state.current_temperature, 2)
        if smoothed is not None and state.current_temperature is not None else None
    )
    return {**sensor_view, "value": value, "smoothed_value": smoothed, "deviation": deviation}


def _outliers(
    inputs: Mapping[str, float], method: AggregationMethod, weights: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Flag inputs far from the median of the others; a hint, never used for control."""
    items = list(inputs.items())
    if len(items) < 3:
        return []
    result: list[dict[str, Any]] = []
    for entity_id, value in items:
        # Kept entity-keyed (not a plain list) so a weighted zone's aggregate_without
        # can look up each remaining sensor's configured weight.
        others = {other_id: other_value for other_id, other_value in items if other_id != entity_id}
        median_of_others = median(others.values())
        raw_difference = abs(value - median_of_others)
        # Compare the raw (unrounded) difference with a small epsilon so float
        # subtraction noise at the exact threshold (e.g. 64.02 - 62.52 ==
        # 1.499999999999993) is not missed, without rounding a true difference
        # like 1.496 up into a false positive. The reported `difference` is
        # still rounded to 2dp for display.
        if raw_difference >= SENSOR_OUTLIER_THRESHOLD - OUTLIER_COMPARE_EPSILON:
            result.append({
                "entity_id": entity_id,
                "value": round(value, 2),
                "median_of_others": round(median_of_others, 2),
                "difference": round(raw_difference, 2),
                "aggregate_without": round(aggregate(method, others, weights), 2),
            })
    return result


def temperature_aggregation(zone: ZoneConfig, state: ZoneState) -> dict[str, Any]:
    """Describe the cached inputs and method behind a zone's current temperature."""
    inputs = dict(state.sensor_smoothed_values)
    values = list(inputs.values())
    method = zone.sensors.aggregation
    # Always report every configured indoor sensor, even one that has not read yet,
    # so a weighted zone's tuning is visible before any reading arrives.
    weights = {entity_id: zone.sensors.weight_for(entity_id) for entity_id in zone.sensors.indoor}
    return {
        "method": method.value,
        # `value` is kept as a back-compat alias; `control_value` is the same cached
        # reading and is the name the docs say drives control.
        "value": state.current_temperature,
        "control_value": state.current_temperature,
        "inputs": inputs,
        "weights": weights,
        "spread": round(max(values) - min(values), 2) if len(values) >= 2 else None,
        "outlier_threshold": SENSOR_OUTLIER_THRESHOLD,
        "outlier_action": OUTLIER_ACTION_FLAGGED_ONLY,
        "outliers": _outliers(inputs, method, weights),
    }
