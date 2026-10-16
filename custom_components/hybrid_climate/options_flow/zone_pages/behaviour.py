"""Purpose: The Behaviour zone page (v0.17.0 §1, §0.6): start/stop buffer and minimum runtime, door contacts and
delays, opportunistic heating, outdoor limits per direction (house limit / no limit / value) and the wall
thermostats that follow hand changes (allow_command on stage devices); saves alone.

Key dependencies: zone_pages/behaviour_values.py (defaults, submit values, apply), options_flow/page_const.py,
const.py; zone_helpers.py (_load_zone_for_edit), page_save.py (_save_zone_block) and menu.py via the composed flow.
Used by: options_flow/handler.py composes BehaviourPageMixin; zone_menu opens zone_behaviour.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ...const import (
    CONF_CLOSE_DELAY,
    CONF_HYSTERESIS,
    CONF_MIN_RUNTIME,
    CONF_NAME,
    CONF_OPEN_DELAY,
    CONF_OPENING_ENTITIES,
)
from ..base import OptionsFlowBase
from ..page_const import (
    FIELD_ALLOW_COMMAND_DEVICES,
    FIELD_COOL_LIMIT_MODE,
    FIELD_HEAT_LIMIT_MODE,
    FIELD_OPPORTUNISTIC_ENABLED,
    FIELD_OPPORTUNISTIC_THRESHOLD,
    FIELD_ZONE_NEVER_COOL_BELOW,
    FIELD_ZONE_NEVER_HEAT_ABOVE,
    HYSTERESIS_RANGE,
    LIMIT_MODE_OPTIONS,
    MIN_RUNTIME_RANGE,
    NAV_CANCEL,
    NAV_FIELD,
    NAV_SAVE,
    NEVER_COOL_BELOW_RANGE,
    NEVER_HEAT_ABOVE_RANGE,
    OPENING_DELAY_RANGE,
    OPENING_DOMAIN,
    OPPORTUNISTIC_THRESHOLD_RANGE,
    PAGE_NAV_OPTIONS,
    SECONDS_UNIT,
    STEP_ZONE_BEHAVIOUR,
    TEMPERATURE_UNIT,
)
from .behaviour_values import apply_behaviour, behaviour_defaults, behaviour_values, stage_device_ids


def _number(
    limits: tuple[float, float, float], unit: str, mode: NumberSelectorMode = NumberSelectorMode.BOX,
) -> NumberSelector:
    """Return a number selector for a (min, max, step) range."""
    low, high, step = limits
    return NumberSelector(NumberSelectorConfig(min=low, max=high, step=step, unit_of_measurement=unit, mode=mode))


def _limit_mode_selector() -> SelectSelector:
    """Return the per-direction outdoor limit mode dropdown."""
    return SelectSelector(SelectSelectorConfig(options=LIMIT_MODE_OPTIONS, mode=SelectSelectorMode.DROPDOWN))


class BehaviourPageMixin(OptionsFlowBase):
    """Mixin providing the zone_behaviour step."""

    _zone_edit_id: str | None = None

    async def async_step_zone_behaviour(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show or save Behaviour for the zone being edited."""
        zone_id = self._zone_edit_id
        if not zone_id:
            return await self.async_step_zones()
        loaded = self._load_zone_for_edit(zone_id)
        defaults = behaviour_defaults(loaded)
        if user_input is None:
            return self._behaviour_form(loaded.get(CONF_NAME, zone_id), defaults, stage_device_ids(loaded))
        if user_input.get(NAV_FIELD, NAV_SAVE) == NAV_CANCEL:
            return await self.async_step_zone_menu()
        values = behaviour_values(user_input, defaults)
        return self._save_zone_block(zone_id, lambda zone, _ui_config: apply_behaviour(zone, values, defaults))

    def _behaviour_form(self, zone_name: str, defaults: dict[str, Any], devices: list[str]) -> FlowResult:
        """Render the page: nav, settings, contacts, opportunistic, outdoor limits, then thermostat sync."""
        schema: dict[Any, Any] = {
            vol.Required(NAV_FIELD, default=NAV_SAVE): SelectSelector(
                SelectSelectorConfig(options=PAGE_NAV_OPTIONS, mode=SelectSelectorMode.LIST)
            ),
            vol.Required(CONF_HYSTERESIS, default=defaults[CONF_HYSTERESIS]):
                _number(HYSTERESIS_RANGE, TEMPERATURE_UNIT, NumberSelectorMode.SLIDER),
            vol.Required(CONF_MIN_RUNTIME, default=defaults[CONF_MIN_RUNTIME]):
                _number(MIN_RUNTIME_RANGE, SECONDS_UNIT),
            vol.Optional(CONF_OPENING_ENTITIES, default=defaults[CONF_OPENING_ENTITIES]): EntitySelector(
                EntitySelectorConfig(domain=OPENING_DOMAIN, multiple=True)
            ),
            vol.Required(CONF_OPEN_DELAY, default=defaults[CONF_OPEN_DELAY]):
                _number(OPENING_DELAY_RANGE, SECONDS_UNIT),
            vol.Required(CONF_CLOSE_DELAY, default=defaults[CONF_CLOSE_DELAY]):
                _number(OPENING_DELAY_RANGE, SECONDS_UNIT),
            vol.Required(FIELD_OPPORTUNISTIC_ENABLED, default=defaults[FIELD_OPPORTUNISTIC_ENABLED]):
                BooleanSelector(),
            vol.Optional(FIELD_OPPORTUNISTIC_THRESHOLD, default=defaults[FIELD_OPPORTUNISTIC_THRESHOLD]):
                _number(OPPORTUNISTIC_THRESHOLD_RANGE, TEMPERATURE_UNIT),
            # Outdoor limits: a mode per direction plus its value (a value counts only in value mode).
            vol.Required(FIELD_HEAT_LIMIT_MODE, default=defaults[FIELD_HEAT_LIMIT_MODE]): _limit_mode_selector(),
            vol.Optional(
                FIELD_ZONE_NEVER_HEAT_ABOVE, description={"suggested_value": defaults[FIELD_ZONE_NEVER_HEAT_ABOVE]},
            ): _number(NEVER_HEAT_ABOVE_RANGE, TEMPERATURE_UNIT),
            vol.Required(FIELD_COOL_LIMIT_MODE, default=defaults[FIELD_COOL_LIMIT_MODE]): _limit_mode_selector(),
            vol.Optional(
                FIELD_ZONE_NEVER_COOL_BELOW, description={"suggested_value": defaults[FIELD_ZONE_NEVER_COOL_BELOW]},
            ): _number(NEVER_COOL_BELOW_RANGE, TEMPERATURE_UNIT),
        }
        # Thermostat sync only when the zone has stage devices (every stage, 3+ included).
        if devices:
            schema[vol.Optional(FIELD_ALLOW_COMMAND_DEVICES, default=defaults[FIELD_ALLOW_COMMAND_DEVICES])] = (
                SelectSelector(SelectSelectorConfig(
                    options=[{"value": entity_id, "label": entity_id} for entity_id in devices],
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                ))
            )
        return self.async_show_form(
            step_id=STEP_ZONE_BEHAVIOUR,
            data_schema=vol.Schema(schema),
            description_placeholders={"zone_name": zone_name},
        )
