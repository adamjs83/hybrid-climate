"""Purpose: The Time-of-use zone page (v0.17.0 §1): per direction, enable plus pre-condition minutes and relaxation
amount (the old zone_tou step's fields), saving the zone's tou block alone; a note says when no global TOU rate
sensor is set.

Key dependencies: options_flow/page_const.py, const.py, base.py (_current_global_settings); zone_helpers.py
(_load_zone_for_edit), page_save.py (_save_zone_block) and menu.py via the composed flow.
Used by: options_flow/handler.py composes TimeOfUsePageMixin; zone_menu opens zone_tou.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ...const import (
    CONF_NAME,
    CONF_TOU,
    CONF_TOU_COOL,
    CONF_TOU_HEAT,
    CONF_TOU_PRE_CONDITION_MINUTES,
    CONF_TOU_RATE_SENSOR,
    CONF_TOU_RELAXATION_AMOUNT,
    DEFAULT_TOU_PRE_CONDITION_MINUTES,
    DEFAULT_TOU_RELAXATION_AMOUNT,
)
from ..base import OptionsFlowBase
from ..page_const import (
    CONF_ENABLED,
    FIELD_TOU_COOL_ENABLED,
    FIELD_TOU_COOL_PRE,
    FIELD_TOU_COOL_RELAX,
    FIELD_TOU_HEAT_ENABLED,
    FIELD_TOU_HEAT_PRE,
    FIELD_TOU_HEAT_RELAX,
    MINUTES_UNIT,
    NAV_CANCEL,
    NAV_FIELD,
    NAV_SAVE,
    PAGE_NAV_OPTIONS,
    STEP_ZONE_TOU,
    TEMPERATURE_UNIT,
    TOU_NO_RATE_SENSOR_NOTE,
    TOU_PRE_CONDITION_RANGE,
    TOU_RELAXATION_RANGE,
)

# (stored direction key, enable field, pre-condition field, relaxation field) per direction.
TOU_DIRECTIONS = (
    (CONF_TOU_HEAT, FIELD_TOU_HEAT_ENABLED, FIELD_TOU_HEAT_PRE, FIELD_TOU_HEAT_RELAX),
    (CONF_TOU_COOL, FIELD_TOU_COOL_ENABLED, FIELD_TOU_COOL_PRE, FIELD_TOU_COOL_RELAX),
)


def tou_defaults(tou: dict[str, Any]) -> dict[str, Any]:
    """Return the page's values for a stored tou block (a direction is on when its block is present)."""
    values: dict[str, Any] = {}
    for direction, enabled, pre, relax in TOU_DIRECTIONS:
        block = tou.get(direction) or {}
        values[enabled] = direction in tou
        values[pre] = block.get(CONF_TOU_PRE_CONDITION_MINUTES, DEFAULT_TOU_PRE_CONDITION_MINUTES)
        values[relax] = block.get(CONF_TOU_RELAXATION_AMOUNT, DEFAULT_TOU_RELAXATION_AMOUNT)
    return values


def tou_values(user_input: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Return the page's values from a submit (minutes whole, amounts as floats)."""
    values: dict[str, Any] = {}
    for _direction, enabled, pre, relax in TOU_DIRECTIONS:
        values[enabled] = bool(user_input.get(enabled, False))
        values[pre] = int(user_input.get(pre, defaults[pre]))
        values[relax] = float(user_input.get(relax, defaults[relax]))
    return values


def _tou_view(values: dict[str, Any]) -> tuple[Any, ...]:
    """Reduce the page to what it stores: a disabled direction stores nothing."""
    return tuple((values[pre], values[relax]) if values[enabled] else None
                 for _direction, enabled, pre, relax in TOU_DIRECTIONS)


def apply_tou(zone: dict[str, Any], values: dict[str, Any], defaults: dict[str, Any]) -> None:
    """Write the tou block as the old step did (enabled with its directions, or removed), only if changed."""
    if _tou_view(values) == _tou_view(defaults):
        return
    if not any(values[enabled] for _direction, enabled, _pre, _relax in TOU_DIRECTIONS):
        zone.pop(CONF_TOU, None)
        return
    block = {**(zone.get(CONF_TOU) or {}), CONF_ENABLED: True}
    for direction, enabled, pre, relax in TOU_DIRECTIONS:
        if values[enabled]:
            block[direction] = {CONF_TOU_PRE_CONDITION_MINUTES: values[pre],
                                CONF_TOU_RELAXATION_AMOUNT: values[relax]}
        else:
            block.pop(direction, None)
    zone[CONF_TOU] = block


class TimeOfUsePageMixin(OptionsFlowBase):
    """Mixin providing the zone_tou step."""

    _zone_edit_id: str | None = None

    async def async_step_zone_tou(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show or save Time-of-use for the zone being edited."""
        zone_id = self._zone_edit_id
        if not zone_id:
            return await self.async_step_zones()
        loaded = self._load_zone_for_edit(zone_id)
        defaults = tou_defaults(loaded.get(CONF_TOU) or {})
        if user_input is None:
            return self._tou_form(loaded.get(CONF_NAME, zone_id), defaults)
        if user_input.get(NAV_FIELD, NAV_SAVE) == NAV_CANCEL:
            return await self.async_step_zone_menu()
        values = tou_values(user_input, defaults)
        return self._save_zone_block(zone_id, lambda zone, _ui_config: apply_tou(zone, values, defaults))

    def _tou_form(self, zone_name: str, defaults: dict[str, Any]) -> FlowResult:
        """Render the page: nav, then heating and cooling (enable, pre-condition, relaxation)."""
        schema: dict[Any, Any] = {
            vol.Required(NAV_FIELD, default=NAV_SAVE): SelectSelector(
                SelectSelectorConfig(options=PAGE_NAV_OPTIONS, mode=SelectSelectorMode.LIST)
            ),
        }
        for _direction, enabled, pre, relax in TOU_DIRECTIONS:
            schema[vol.Required(enabled, default=defaults[enabled])] = BooleanSelector()
            for field, (low, high, step), unit in ((pre, TOU_PRE_CONDITION_RANGE, MINUTES_UNIT),
                                                   (relax, TOU_RELAXATION_RANGE, TEMPERATURE_UNIT)):
                schema[vol.Optional(field, default=defaults[field])] = NumberSelector(NumberSelectorConfig(
                    min=low, max=high, step=step, unit_of_measurement=unit, mode=NumberSelectorMode.BOX))
        # The note says when no global rate sensor is set (the adjustments then have no effect).
        has_sensor = bool(self._current_global_settings().get(CONF_TOU_RATE_SENSOR))
        return self.async_show_form(
            step_id=STEP_ZONE_TOU,
            data_schema=vol.Schema(schema),
            description_placeholders={"zone_name": zone_name, "tou_note": "" if has_sensor else TOU_NO_RATE_SENSOR_NOTE},
        )
