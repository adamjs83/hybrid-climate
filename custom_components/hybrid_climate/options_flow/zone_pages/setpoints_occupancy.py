"""Purpose: The Setpoints & occupancy zone page (v0.17.0 §1): names the zone's setpoint number entities and edits
occupancy (enabled, entity, off delay in minutes, occupied/unoccupied offsets); saves alone.

Key dependencies: options_flow/page_const.py, base.py (minute conversions), number_definitions.SETPOINT_NUMBERS,
entity registry; zone_helpers.py (_load_zone_for_edit), page_save.py (_save_zone_block), menu.py via the composed flow.
Used by: options_flow/handler.py composes SetpointsPageMixin; zone_menu opens zone_setpoints.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
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
    CONF_NAME,
    CONF_OCCUPANCY_ENTITY,
    CONF_OCCUPANCY_OFF_DELAY,
    CONF_SETPOINTS,
    DEFAULT_OCCUPANCY_OFF_DELAY,
    DOMAIN,
    MAX_OCCUPANCY_OFF_DELAY,
    OCCUPANCY_OFF_DELAY_MINUTES_STEP,
    SECONDS_PER_MINUTE,
)
from ...number_definitions import SETPOINT_NUMBERS
from ..base import OptionsFlowBase, minutes_to_seconds, seconds_to_minutes
from ..page_const import (
    CONF_SETPOINT_DEFAULT,
    CONF_SETPOINT_OCCUPIED,
    CONF_SETPOINT_UNOCCUPIED,
    FALLBACK_DEFAULT_SETPOINT,
    FIELD_OCCUPANCY_ENABLED,
    FIELD_OCCUPIED_OFFSET,
    FIELD_UNOCCUPIED_OFFSET,
    MINUTES_UNIT,
    NAV_CANCEL,
    NAV_FIELD,
    NAV_SAVE,
    NUMBER_DOMAIN,
    OCCUPANCY_OFFSET_RANGE,
    PAGE_NAV_OPTIONS,
    SETPOINT_NUMBERS_NONE_TEXT,
    STEP_ZONE_SETPOINTS,
    TEMPERATURE_UNIT,
)

OCCUPANCY_DOMAINS = ["binary_sensor", "input_boolean"]
# Stored setpoint keys owned by occupancy; disabling it removes them all.
OCCUPANCY_KEYS = (FIELD_OCCUPANCY_ENABLED, CONF_OCCUPANCY_ENTITY, CONF_OCCUPANCY_OFF_DELAY,
                  CONF_SETPOINT_OCCUPIED, CONF_SETPOINT_UNOCCUPIED)


def occupancy_values(user_input: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    """Return the page's occupancy values from a submit, in wizard-state keys (off delay in seconds)."""
    entity = user_input.get(CONF_OCCUPANCY_ENTITY)
    return {
        FIELD_OCCUPANCY_ENABLED: bool(user_input.get(FIELD_OCCUPANCY_ENABLED, False)),
        CONF_OCCUPANCY_ENTITY: entity.strip() if isinstance(entity, str) and entity.strip() else None,
        # The form shows minutes; storage stays in seconds.
        CONF_OCCUPANCY_OFF_DELAY: minutes_to_seconds(
            user_input.get(CONF_OCCUPANCY_OFF_DELAY), DEFAULT_OCCUPANCY_OFF_DELAY),
        FIELD_OCCUPIED_OFFSET: user_input.get(FIELD_OCCUPIED_OFFSET, loaded.get(FIELD_OCCUPIED_OFFSET)),
        FIELD_UNOCCUPIED_OFFSET: user_input.get(FIELD_UNOCCUPIED_OFFSET, loaded.get(FIELD_UNOCCUPIED_OFFSET)),
    }


def _occupancy_view(values: dict[str, Any]) -> tuple[Any, ...]:
    """Reduce occupancy values to what they store; a disabled occupancy stores nothing."""
    if not values.get(FIELD_OCCUPANCY_ENABLED):
        return (False,)
    return (True, values.get(CONF_OCCUPANCY_ENTITY), values.get(CONF_OCCUPANCY_OFF_DELAY),
            values.get(FIELD_OCCUPIED_OFFSET), values.get(FIELD_UNOCCUPIED_OFFSET))


def apply_setpoints(zone: dict[str, Any], values: dict[str, Any], loaded: dict[str, Any]) -> None:
    """Write occupancy into the stored setpoints block (same rules as the old wizard save), only if changed."""
    if _occupancy_view(values) == _occupancy_view(loaded):
        return
    setpoints = dict(zone.get(CONF_SETPOINTS) or {CONF_SETPOINT_DEFAULT: FALLBACK_DEFAULT_SETPOINT})
    if not values[FIELD_OCCUPANCY_ENABLED]:
        for key in OCCUPANCY_KEYS:
            setpoints.pop(key, None)
        zone[CONF_SETPOINTS] = setpoints
        return
    # Enabled (even before an entity is chosen): the flag and delay are stored.
    setpoints[FIELD_OCCUPANCY_ENABLED] = True
    setpoints[CONF_OCCUPANCY_OFF_DELAY] = values[CONF_OCCUPANCY_OFF_DELAY]
    entity = values[CONF_OCCUPANCY_ENTITY]
    if entity:
        # Offsets are relative to the default setpoint (heating; cooling has its own numbers).
        default = setpoints.get(CONF_SETPOINT_DEFAULT, FALLBACK_DEFAULT_SETPOINT)
        setpoints[CONF_OCCUPANCY_ENTITY] = entity
        setpoints[CONF_SETPOINT_OCCUPIED] = default + values[FIELD_OCCUPIED_OFFSET]
        setpoints[CONF_SETPOINT_UNOCCUPIED] = default + values[FIELD_UNOCCUPIED_OFFSET]
    else:
        setpoints.pop(CONF_OCCUPANCY_ENTITY, None)
    zone[CONF_SETPOINTS] = setpoints


def _offset_selector() -> NumberSelector:
    """Return the occupied/unoccupied offset selector (°F)."""
    low, high, step = OCCUPANCY_OFFSET_RANGE
    return NumberSelector(NumberSelectorConfig(
        min=low, max=high, step=step, unit_of_measurement=TEMPERATURE_UNIT, mode=NumberSelectorMode.BOX))


class SetpointsPageMixin(OptionsFlowBase):
    """Mixin providing the zone_setpoints step."""

    _zone_edit_id: str | None = None

    async def async_step_zone_setpoints(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show or save Setpoints & occupancy for the zone being edited."""
        zone_id = self._zone_edit_id
        if not zone_id:
            return await self.async_step_zones()
        loaded = self._load_zone_for_edit(zone_id)
        if user_input is None:
            return self._setpoints_form(zone_id, loaded)
        if user_input.get(NAV_FIELD, NAV_SAVE) == NAV_CANCEL:
            return await self.async_step_zone_menu()
        values = occupancy_values(user_input, loaded)
        return self._save_zone_block(zone_id, lambda zone, _ui_config: apply_setpoints(zone, values, loaded))

    def _setpoint_number_ids(self, zone_id: str) -> str:
        """Name the zone's setpoint number entities, resolved from the entity registry by unique id."""
        registry = er.async_get(self.hass)
        # Unique ids are hybrid_climate_<zone_id>_<key> (number_entities.py); the entity id is never built.
        found = [
            registry.async_get_entity_id(NUMBER_DOMAIN, DOMAIN, f"{DOMAIN}_{zone_id}_{description.key}")
            for description in SETPOINT_NUMBERS
        ]
        entity_ids = [entity_id for entity_id in found if entity_id]
        return ", ".join(entity_ids) if entity_ids else SETPOINT_NUMBERS_NONE_TEXT

    def _setpoints_form(self, zone_id: str, loaded: dict[str, Any]) -> FlowResult:
        """Render the page from the stored zone; the entity picker stays blank when unset."""
        off_delay = seconds_to_minutes(loaded.get(CONF_OCCUPANCY_OFF_DELAY) or DEFAULT_OCCUPANCY_OFF_DELAY)
        schema: dict[Any, Any] = {
            vol.Required(NAV_FIELD, default=NAV_SAVE): SelectSelector(
                SelectSelectorConfig(options=PAGE_NAV_OPTIONS, mode=SelectSelectorMode.LIST)
            ),
            vol.Required(FIELD_OCCUPANCY_ENABLED, default=bool(loaded.get(FIELD_OCCUPANCY_ENABLED))):
                BooleanSelector(),
            vol.Optional(
                CONF_OCCUPANCY_ENTITY, description={"suggested_value": loaded.get(CONF_OCCUPANCY_ENTITY)},
            ): EntitySelector(EntitySelectorConfig(domain=OCCUPANCY_DOMAINS)),
            vol.Optional(CONF_OCCUPANCY_OFF_DELAY, default=off_delay): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=MAX_OCCUPANCY_OFF_DELAY / SECONDS_PER_MINUTE,
                    step=OCCUPANCY_OFF_DELAY_MINUTES_STEP,
                    unit_of_measurement=MINUTES_UNIT,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(FIELD_OCCUPIED_OFFSET, default=loaded.get(FIELD_OCCUPIED_OFFSET)): _offset_selector(),
            vol.Optional(FIELD_UNOCCUPIED_OFFSET, default=loaded.get(FIELD_UNOCCUPIED_OFFSET)): _offset_selector(),
        }
        return self.async_show_form(
            step_id=STEP_ZONE_SETPOINTS,
            data_schema=vol.Schema(schema),
            description_placeholders={
                "zone_name": loaded.get(CONF_NAME, zone_id),
                "setpoint_numbers": self._setpoint_number_ids(zone_id),
            },
        )
