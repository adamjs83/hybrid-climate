"""Purpose: Reduce keyed sensor readings to one zone temperature.

Key dependencies: AggregationMethod and sensor weight constants.
Used by: sensor_manager.py and Agent API sensor views.
"""
from __future__ import annotations

from collections.abc import Mapping
from statistics import median

from .const import DEFAULT_SENSOR_WEIGHT
from .models import AggregationMethod


def aggregate(
    method: AggregationMethod,
    values: Mapping[str, float],
    weights: Mapping[str, float],
) -> float:
    """Aggregate nonempty readings using the configured method and weights."""
    if method == AggregationMethod.MIN:
        return min(values.values())
    if method == AggregationMethod.MAX:
        return max(values.values())
    if method == AggregationMethod.MEDIAN:
        return median(values.values())
    if method == AggregationMethod.WEIGHTED:
        total_weight = sum(weights.get(key, DEFAULT_SENSOR_WEIGHT) for key in values)
        return sum(value * weights.get(key, DEFAULT_SENSOR_WEIGHT) for key, value in values.items()) / total_weight
    return sum(values.values()) / len(values)
