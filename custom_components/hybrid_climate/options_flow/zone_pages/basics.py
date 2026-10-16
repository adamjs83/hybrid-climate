"""Purpose: The Basics & sensors zone page (v0.17.0 §1): name, sensors, aggregation, smoothing and inline weights;
saves alone when editing, and is the first page of the add-zone path (§0.5).

Key dependencies: options_flow/page_const.py, sensor_weights.py (aggregation_selector, weight_fields), const.py;
zone_helpers.py (_load_zone_for_edit), page_save.py (_save_zone_block) and menu.py via the composed flow.
Used by: options_flow/handler.py composes BasicsPageMixin; zone_menu and zones (add) open zone_basics.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
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
    AGGREGATION_AVERAGE,
    AGGREGATION_WEIGHTED,
    CONF_AGGREGATION,
    CONF_INDOOR,
    CONF_NAME,
    CONF_SENSORS,
    CONF_SMOOTHING_SAMPLES,
    CONF_WEIGHTS,
    CONF_ZONES,
    DEFAULT_SMOOTHING_SAMPLES,
    MAX_SMOOTHING_SAMPLES,
    MIN_SMOOTHING_SAMPLES,
    NEW_ZONE_TITLE,
)
from ..base import OptionsFlowBase
from ..page_const import (
    CREATE_FIRST_NAV_OPTIONS,
    ERROR_BASE,
    ERROR_WEIGHTS_NEEDED,
    ERROR_ZONE_ID_EXISTS,
    ERROR_ZONE_ID_REQUIRED,
    ERROR_ZONE_NAME_REQUIRED,
    FIELD_ZONE_ID,
    NAV_CANCEL,
    NAV_FIELD,
    NAV_NEXT,
    NAV_SAVE,
    PAGE_NAV_OPTIONS,
    STEP_ZONE_BASICS,
)
from ..sensor_weights import aggregation_selector, weight_fields

SENSOR_DOMAIN = "sensor"


def basics_values(user_input: dict[str, Any], previous_weights: dict[str, Any]) -> dict[str, Any]:
    """Return the page's values from a submit, in wizard-state keys; weights kept for selected sensors."""
    sensors = [eid for eid in user_input.get(CONF_SENSORS) or [] if eid]
    # Weights survive a method change; a removed sensor's weight goes, a shown field's value wins.
    weights = {eid: weight for eid, weight in previous_weights.items() if eid in sensors}
    weights.update({eid: user_input[eid] for eid in sensors if eid in user_input})
    return {
        CONF_NAME: str(user_input.get(CONF_NAME) or "").strip(),
        CONF_SENSORS: sensors,
        CONF_AGGREGATION: user_input.get(CONF_AGGREGATION, AGGREGATION_AVERAGE),
        CONF_SMOOTHING_SAMPLES: int(user_input.get(CONF_SMOOTHING_SAMPLES, DEFAULT_SMOOTHING_SAMPLES)),
        CONF_WEIGHTS: weights,
    }


def weights_missing(user_input: dict[str, Any], values: dict[str, Any]) -> bool:
    """Return True when weighted is chosen but a selected sensor had no weight field on the form."""
    # Business rule (Review Focus 2): never save a weighted zone with silent default weights.
    return values[CONF_AGGREGATION] == AGGREGATION_WEIGHTED and any(
        eid not in user_input for eid in values[CONF_SENSORS])


def _sensors_view(values: dict[str, Any]) -> tuple[Any, ...]:
    """Reduce page values to what the sensors block stores (weights only for selected sensors)."""
    sensors = list(values.get(CONF_SENSORS) or [])
    weights = {eid: w for eid, w in (values.get(CONF_WEIGHTS) or {}).items() if eid in sensors}
    return (sensors, values.get(CONF_AGGREGATION), values.get(CONF_SMOOTHING_SAMPLES), weights)


def apply_basics(zone: dict[str, Any], values: dict[str, Any], loaded: dict[str, Any]) -> None:
    """Write the page's name and sensors block into a stored zone, touching only what changed."""
    if values[CONF_NAME] != loaded.get(CONF_NAME):
        zone[CONF_NAME] = values[CONF_NAME]
    # An unchanged sensors view leaves the stored block exactly as saved (no keys added).
    if _sensors_view(values) == _sensors_view(loaded):
        return
    stored = zone.get(CONF_SENSORS)
    block = dict(stored) if isinstance(stored, dict) else {}
    block[CONF_INDOOR] = list(values[CONF_SENSORS])
    block[CONF_AGGREGATION] = values[CONF_AGGREGATION]
    block[CONF_SMOOTHING_SAMPLES] = values[CONF_SMOOTHING_SAMPLES]
    weights = _sensors_view(values)[3]
    if weights:
        block[CONF_WEIGHTS] = weights
    else:
        block.pop(CONF_WEIGHTS, None)
    zone[CONF_SENSORS] = block


def _sanitized_zone_id(raw: Any) -> str:
    """Return a zone id as the old wizard stored it: trimmed, lowercase, spaces as underscores."""
    return str(raw or "").strip().lower().replace(" ", "_")


class BasicsPageMixin(OptionsFlowBase):
    """Mixin providing the zone_basics step (edit page and add-path first page)."""

    _zone_edit_id: str | None = None
    _zone_wip: dict[str, Any] | None = None

    async def async_step_zone_basics(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show or save Basics & sensors; while adding a zone, collect it and go to Heating stages."""
        if self._zone_edit_id is None:
            return await self._create_basics(user_input)
        zone_id = self._zone_edit_id
        loaded = self._load_zone_for_edit(zone_id)
        if user_input is None:
            return self._basics_form(loaded, loaded.get(CONF_NAME, zone_id), create=False)
        if user_input.get(NAV_FIELD, NAV_SAVE) == NAV_CANCEL:
            return await self.async_step_zone_menu()
        values = basics_values(user_input, loaded.get(CONF_WEIGHTS) or {})
        errors: dict[str, str] = {}
        if not values[CONF_NAME]:
            errors[CONF_NAME] = ERROR_ZONE_NAME_REQUIRED
        elif weights_missing(user_input, values):
            errors[ERROR_BASE] = ERROR_WEIGHTS_NEEDED
        if errors:
            return self._basics_form(values, loaded.get(CONF_NAME, zone_id), create=False, errors=errors)
        return self._save_zone_block(zone_id, lambda zone, _ui_config: apply_basics(zone, values, loaded))

    async def _create_basics(self, user_input: dict[str, Any] | None) -> FlowResult:
        """Add path page 1: validate the new zone id and name, keep the values in the flow."""
        wip = self._zone_wip or {}
        if user_input is None:
            return self._basics_form(wip, NEW_ZONE_TITLE, create=True)
        if user_input.get(NAV_FIELD, NAV_NEXT) == NAV_CANCEL:
            self._zone_wip = None
            return await self.async_step_zones()
        values = basics_values(user_input, wip.get(CONF_WEIGHTS) or {})
        values[FIELD_ZONE_ID] = zone_id = _sanitized_zone_id(user_input.get(FIELD_ZONE_ID))
        errors: dict[str, str] = {}
        if not zone_id:
            errors[FIELD_ZONE_ID] = ERROR_ZONE_ID_REQUIRED
        elif not values[CONF_NAME]:
            errors[CONF_NAME] = ERROR_ZONE_NAME_REQUIRED
        elif (zone_id in (self._get_yaml_config().get(CONF_ZONES) or {})
              or zone_id in (self._get_ui_config().get(CONF_ZONES) or {})):
            errors[FIELD_ZONE_ID] = ERROR_ZONE_ID_EXISTS
        elif weights_missing(user_input, values):
            errors[ERROR_BASE] = ERROR_WEIGHTS_NEEDED
        if errors:
            return self._basics_form(values, NEW_ZONE_TITLE, create=True, errors=errors)
        self._zone_wip = {**wip, **values}
        return await self.async_step_zone_heat_stages()

    def _basics_form(
        self, values: dict[str, Any], zone_name: str, *, create: bool, errors: dict[str, str] | None = None,
    ) -> FlowResult:
        """Render the page from wizard-state values; weight fields inline when weighted."""
        sensors = list(values.get(CONF_SENSORS) or [])
        aggregation = values.get(CONF_AGGREGATION, AGGREGATION_AVERAGE)
        nav_options, nav_default = (CREATE_FIRST_NAV_OPTIONS, NAV_NEXT) if create else (PAGE_NAV_OPTIONS, NAV_SAVE)
        schema: dict[Any, Any] = {
            vol.Required(NAV_FIELD, default=nav_default): SelectSelector(
                SelectSelectorConfig(options=nav_options, mode=SelectSelectorMode.LIST)
            ),
        }
        # Only a new zone asks for its id; an edited zone keeps the one it has.
        if create:
            schema[vol.Required(FIELD_ZONE_ID, default=values.get(FIELD_ZONE_ID, ""))] = str
        schema.update({
            vol.Required(CONF_NAME, default=values.get(CONF_NAME, "")): str,
            vol.Optional(CONF_SENSORS, default=sensors): EntitySelector(
                EntitySelectorConfig(domain=SENSOR_DOMAIN, multiple=True)
            ),
            vol.Required(CONF_AGGREGATION, default=aggregation): aggregation_selector(),
            vol.Required(
                CONF_SMOOTHING_SAMPLES, default=values.get(CONF_SMOOTHING_SAMPLES, DEFAULT_SMOOTHING_SAMPLES),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SMOOTHING_SAMPLES, max=MAX_SMOOTHING_SAMPLES, step=1, mode=NumberSelectorMode.BOX,
                )
            ),
        })
        if aggregation == AGGREGATION_WEIGHTED:
            schema.update(weight_fields(sensors, values.get(CONF_WEIGHTS) or {}))
        return self.async_show_form(
            step_id=STEP_ZONE_BASICS,
            data_schema=vol.Schema(schema),
            errors=errors or {},
            description_placeholders={"zone_name": zone_name},
        )
