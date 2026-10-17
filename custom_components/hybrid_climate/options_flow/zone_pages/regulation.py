"""Purpose: The Regulation zone page (v0.17.0 §2, owner decision 5): a `heating` section (type Direct/PI, the
heating thermostats PI adjusts incl. stages 3+, minimum command change, minimum time between changes in minutes)
and one `cool_device_N` section per cooling device (regulation_cooling.py); the description carries read-only
lines naming the zone's PI number entities with their values. Heat-only zones show only `heating`, cool-only zones
only the cooling sections. Saves alone: heating PI merges into the stored block (gains and advanced keys kept,
default gains seeded), Direct drops it; each changed cooling block is written to its device entry.

Key dependencies: options_flow/regulation_devices.py, zone_pages/regulation_cooling.py, zone_merge.merge_regulation,
number_lookup.HEAT_PI_NUMBER_KEYS, page_const.py, const.py; zone_helpers.py (_load_zone_for_edit), devices.py
(_load_device_config), page_save.py (_save_zone_block) via the composed flow.
Used by: options_flow/handler.py composes RegulationPageMixin; zone_menu opens zone_regulation.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ...const import (
    CONF_COOL_STAGES,
    CONF_ZONES,
    CONF_DEVICES,
    CONF_HEAT_STAGES,
    CONF_NAME,
    CONF_REGULATION,
    CONF_REGULATION_MIN_PERIOD,
    CONF_REGULATION_THRESHOLD,
    CONF_REGULATION_TYPE,
    DEFAULT_REGULATION_MIN_PERIOD,
    DEFAULT_REGULATION_THRESHOLD,
    MAX_REGULATION_MIN_PERIOD,
    MAX_REGULATION_THRESHOLD,
    MIN_REGULATION_MIN_PERIOD,
    MIN_REGULATION_THRESHOLD,
    REGULATION_DIRECT,
    REGULATION_PI,
)
from ...cool_pi_const import CONF_ZONE_COOL_REGULATION
from ...number_lookup import HEAT_PI_NUMBER_KEYS
from ..base import OptionsFlowBase
from ..page_const import (
    FIELD_PI_DEVICES,
    FIELD_REGULATION_TYPE,
    HEAT_NUMBERS_DIRECT,
    HEATING_NOTE,
    MINUTES_UNIT,
    NAV_CANCEL,
    NAV_FIELD,
    NAV_SAVE,
    PAGE_NAV_OPTIONS,
    REGULATION_DIRECT_LABEL,
    REGULATION_NUMBERS_NEW,
    REGULATION_PI_LABEL,
    SECTION_ADVANCED_COOLING,
    SECTION_ADVANCED_HEATING,
    SECTION_HEATING,
    STEP_ZONE_REGULATION,
    TEMPERATURE_UNIT,
)
from ..regulation_devices import all_zones, heat_capable_stage_devices, selected_pi_devices, zone_cool_devices
from ..zone_merge import merge_regulation
from .regulation_advanced import (
    advanced_cooling_defaults,
    advanced_cooling_fields,
    advanced_heating_defaults,
    advanced_heating_fields,
    advanced_values,
    apply_advanced_cooling,
    apply_advanced_heating,
)
from .regulation_cooling import (
    CoolBlock,
    apply_cooling,
    cool_blocks,
    cooling_note,
    cooling_sections,
    number_values_line,
)

# The wizard-state keys _load_zone_for_edit fills for regulation.
LOADED_REGULATION_TYPE = "regulation_type"
LOADED_PI_CONFIG = "pi_config"
REGULATION_THRESHOLD_STEP = 0.1
REGULATION_MIN_PERIOD_STEP = 1


def regulation_defaults(loaded: dict[str, Any], choices: list[str], yaml_devices: dict[str, Any]) -> dict[str, Any]:
    """Return the heating section's values for the loaded zone (the form defaults)."""
    pi_config = loaded.get(LOADED_PI_CONFIG) or {}
    return {
        FIELD_REGULATION_TYPE: loaded.get(LOADED_REGULATION_TYPE, REGULATION_DIRECT),
        FIELD_PI_DEVICES: selected_pi_devices(pi_config.get(CONF_DEVICES), choices, yaml_devices),
        CONF_REGULATION_THRESHOLD: pi_config.get(CONF_REGULATION_THRESHOLD, DEFAULT_REGULATION_THRESHOLD),
        CONF_REGULATION_MIN_PERIOD: pi_config.get(CONF_REGULATION_MIN_PERIOD, DEFAULT_REGULATION_MIN_PERIOD),
    }


def regulation_values(user_input: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Return the heating section's values from a submit (the period is whole minutes)."""
    return {
        FIELD_REGULATION_TYPE: user_input.get(FIELD_REGULATION_TYPE, defaults[FIELD_REGULATION_TYPE]),
        FIELD_PI_DEVICES: list(user_input.get(FIELD_PI_DEVICES, defaults[FIELD_PI_DEVICES])),
        CONF_REGULATION_THRESHOLD: user_input.get(CONF_REGULATION_THRESHOLD, defaults[CONF_REGULATION_THRESHOLD]),
        CONF_REGULATION_MIN_PERIOD: int(
            user_input.get(CONF_REGULATION_MIN_PERIOD, defaults[CONF_REGULATION_MIN_PERIOD])),
    }


def _regulation_view(values: dict[str, Any]) -> tuple[Any, ...]:
    """Reduce the section to what it stores: Direct stores no PI settings."""
    if values[FIELD_REGULATION_TYPE] != REGULATION_PI:
        return (REGULATION_DIRECT,)
    return (REGULATION_PI, values[FIELD_PI_DEVICES], values[CONF_REGULATION_THRESHOLD],
            values[CONF_REGULATION_MIN_PERIOD])


def apply_regulation(zone: dict[str, Any], values: dict[str, Any], defaults: dict[str, Any]) -> None:
    """Write the heating regulation block as the old wizard save did, only when the section changed."""
    if _regulation_view(values) == _regulation_view(defaults):
        return
    if values[FIELD_REGULATION_TYPE] != REGULATION_PI:
        # Direct drops the block (gains included), as _save_zone_config did.
        zone.pop(CONF_REGULATION, None)
        return
    page = {
        CONF_REGULATION_TYPE: REGULATION_PI,
        CONF_DEVICES: values[FIELD_PI_DEVICES],
        CONF_REGULATION_THRESHOLD: values[CONF_REGULATION_THRESHOLD],
        CONF_REGULATION_MIN_PERIOD: values[CONF_REGULATION_MIN_PERIOD],
    }
    stored = zone.get(CONF_REGULATION)
    # Stored gains and advanced keys are kept; a new block is seeded with the default gains.
    zone[CONF_REGULATION] = merge_regulation(stored if isinstance(stored, dict) else None, page)


class RegulationPageMixin(OptionsFlowBase):
    """Mixin providing the zone_regulation step (heating and cooling sections)."""

    _zone_edit_id: str | None = None

    async def async_step_zone_regulation(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show or save Regulation for the zone being edited."""
        zone_id = self._zone_edit_id
        if not zone_id:
            return await self.async_step_zones()
        loaded = self._load_zone_for_edit(zone_id)
        yaml_config = self._get_yaml_config()
        yaml_devices = yaml_config.get(CONF_DEVICES) or {}
        ui_config = self._get_ui_config()
        # Section set (§2): no cool stages → heating only; no heat stages (but cool stages) → cooling only.
        show_cooling = bool(loaded.get(CONF_COOL_STAGES))
        show_heating = bool(loaded.get(CONF_HEAT_STAGES)) or not show_cooling
        choices = heat_capable_stage_devices(loaded, ui_config.get(CONF_DEVICES) or {}, yaml_devices)
        defaults = regulation_defaults(loaded, choices, yaml_devices)
        blocks, beyond = (cool_blocks(self.hass, zone_cool_devices(loaded, yaml_devices), self._load_device_config)
                          if show_cooling else ([], []))
        adv_heat = advanced_heating_defaults(loaded.get(LOADED_PI_CONFIG))
        adv_cool = advanced_cooling_defaults(self._stored_cool_block(zone_id, yaml_config, ui_config))
        if user_input is None:
            placeholders = {
                "zone_name": loaded.get(CONF_NAME, zone_id),
                "heating_note": self._heating_note(zone_id, loaded) if show_heating else "",
                "cooling_note": cooling_note(self.hass, zone_id, blocks, beyond,
                                             all_zones(ui_config, yaml_config), yaml_devices) if show_cooling else "",
            }
            return self._regulation_form(placeholders, defaults if show_heating else None, choices, blocks,
                                         adv_heat, adv_cool if show_cooling else None)
        if user_input.get(NAV_FIELD, NAV_SAVE) == NAV_CANCEL:
            return await self.async_step_zone_menu()
        values = regulation_values(user_input.get(SECTION_HEATING) or {}, defaults)
        heat_adv = advanced_values(user_input.get(SECTION_ADVANCED_HEATING), adv_heat)
        cool_adv = advanced_values(user_input.get(SECTION_ADVANCED_COOLING), adv_cool)

        def apply(zone: dict[str, Any], stored_ui: dict[str, Any]) -> None:
            """Write the heating block to the zone (when shown) and each changed cooling block to its device."""
            if show_heating:
                apply_regulation(zone, values, defaults)
                apply_advanced_heating(zone, heat_adv, adv_heat)
            apply_cooling(stored_ui, blocks, user_input)
            if show_cooling:
                apply_advanced_cooling(zone, cool_adv, adv_cool)

        return self._save_zone_block(zone_id, apply)

    @staticmethod
    def _stored_cool_block(zone_id: str, yaml_config: dict[str, Any], ui_config: dict[str, Any]) -> dict[str, Any] | None:
        """Return the zone's cool_regulation block: UI storage first, a YAML-only zone's own block otherwise."""
        zone = (ui_config.get(CONF_ZONES) or {}).get(zone_id) or (yaml_config.get(CONF_ZONES) or {}).get(zone_id) or {}
        block = zone.get(CONF_ZONE_COOL_REGULATION)
        return block if isinstance(block, dict) else None

    def _heating_note(self, zone_id: str, loaded: dict[str, Any]) -> str:
        """Return the heating note with the five PI numbers and values; none yet says when they appear."""
        numbers = number_values_line(self.hass, zone_id, HEAT_PI_NUMBER_KEYS.values())
        if numbers is None:
            # PI numbers exist only for a PI zone: a Direct zone gets them once PI is chosen and saved.
            pi_stored = loaded.get(LOADED_REGULATION_TYPE) == REGULATION_PI
            numbers = REGULATION_NUMBERS_NEW if pi_stored else HEAT_NUMBERS_DIRECT
        return HEATING_NOTE.format(numbers=numbers)

    def _regulation_form(
        self, placeholders: dict[str, str], defaults: dict[str, Any] | None, choices: list[str],
        blocks: list[CoolBlock], adv_heat: dict[str, float], adv_cool: dict[str, float] | None,
    ) -> FlowResult:
        """Render nav, the heating section (when `defaults` is given) and the cooling sections."""
        schema: dict[Any, Any] = {
            vol.Required(NAV_FIELD, default=NAV_SAVE): SelectSelector(
                SelectSelectorConfig(options=PAGE_NAV_OPTIONS, mode=SelectSelectorMode.LIST)
            ),
        }
        if defaults is not None:
            # Optional with no default: a section left out of a submission stays absent and changes nothing.
            schema[vol.Optional(SECTION_HEATING)] = section(
                vol.Schema(_heating_fields(defaults, choices)))
            schema[vol.Optional(SECTION_ADVANCED_HEATING)] = section(
                vol.Schema(advanced_heating_fields(adv_heat)), {"collapsed": True})
        schema.update(cooling_sections(blocks))
        if adv_cool is not None:
            schema[vol.Optional(SECTION_ADVANCED_COOLING)] = section(
                vol.Schema(advanced_cooling_fields(adv_cool)), {"collapsed": True})
        return self.async_show_form(
            step_id=STEP_ZONE_REGULATION,
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
        )


def _heating_fields(defaults: dict[str, Any], choices: list[str]) -> dict[Any, Any]:
    """Return the heating section's fields: type, thermostats, change and period."""
    return {
        vol.Required(FIELD_REGULATION_TYPE, default=defaults[FIELD_REGULATION_TYPE]): SelectSelector(
            SelectSelectorConfig(
                options=[{"value": REGULATION_DIRECT, "label": REGULATION_DIRECT_LABEL},
                         {"value": REGULATION_PI, "label": REGULATION_PI_LABEL}],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(FIELD_PI_DEVICES, default=defaults[FIELD_PI_DEVICES]): SelectSelector(
            SelectSelectorConfig(
                options=[{"value": entity_id, "label": entity_id} for entity_id in choices],
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        ),
        vol.Required(CONF_REGULATION_THRESHOLD, default=defaults[CONF_REGULATION_THRESHOLD]): NumberSelector(
            NumberSelectorConfig(min=MIN_REGULATION_THRESHOLD, max=MAX_REGULATION_THRESHOLD,
                                 step=REGULATION_THRESHOLD_STEP, unit_of_measurement=TEMPERATURE_UNIT,
                                 mode=NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_REGULATION_MIN_PERIOD, default=defaults[CONF_REGULATION_MIN_PERIOD]): NumberSelector(
            NumberSelectorConfig(min=MIN_REGULATION_MIN_PERIOD, max=MAX_REGULATION_MIN_PERIOD,
                                 step=REGULATION_MIN_PERIOD_STEP, unit_of_measurement=MINUTES_UNIT,
                                 mode=NumberSelectorMode.BOX)
        ),
    }
