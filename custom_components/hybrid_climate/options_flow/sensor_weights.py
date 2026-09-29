"""Purpose: Build aggregation choices and edit per-sensor wizard weights.

Key dependencies: Home Assistant selectors and shared aggregation constants.
Used by: ZoneFlowMixin and the zone basics step.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
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
    CONF_AGGREGATION,
    CONF_NAME,
    CONF_SENSORS,
    CONF_WEIGHTS,
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


class SensorWeightsMixin:
    """Provide the per-sensor weight wizard step."""

    def _needs_weights_step(self) -> bool:
        """Return whether the selected sensors need a weights step."""
        wip = self._zone_wip or {}
        return wip.get(CONF_AGGREGATION) == AGGREGATION_WEIGHTED and bool(wip.get(CONF_SENSORS))

    async def async_step_zone_sensor_weights(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Edit selected sensor weights before occupancy settings."""
        wip = self._zone_wip or {}
        sensors = wip.get(CONF_SENSORS, [])

        if user_input is not None:
            if user_input.get("nav_action", "next") == "back":
                return await self.async_step_zone_basics()
            # Retain values for method toggles; saving later filters removed sensors.
            weights = dict(wip.get(CONF_WEIGHTS, {}))
            weights.update({entity_id: user_input.get(entity_id, weights.get(
                entity_id, DEFAULT_SENSOR_WEIGHT)) for entity_id in sensors})
            wip[CONF_WEIGHTS] = weights
            self._zone_wip = wip
            return await self.async_step_zone_occupancy()

        schema: dict[Any, Any] = {
            vol.Required("nav_action", default="next"): SelectSelector(
                SelectSelectorConfig(options=[
                    {"value": "back", "label": "← Back"},
                    {"value": "next", "label": "Next →"},
                ], mode=SelectSelectorMode.LIST)
            ),
        }
        for entity_id in sensors:
            schema[vol.Required(entity_id, default=wip.get(CONF_WEIGHTS, {}).get(
                entity_id, DEFAULT_SENSOR_WEIGHT))] = NumberSelector(NumberSelectorConfig(
                    min=MIN_SENSOR_WEIGHT,
                    max=MAX_SENSOR_WEIGHT,
                    step=SENSOR_WEIGHT_STEP,
                    mode=NumberSelectorMode.BOX,
                ))

        return self.async_show_form(
            step_id="zone_sensor_weights",
            data_schema=vol.Schema(schema),
            description_placeholders={"zone_name": wip.get(CONF_NAME, "Zone")},
        )
