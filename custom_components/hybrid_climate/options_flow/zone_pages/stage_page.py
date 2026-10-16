"""Purpose: Shared body of the Heating stages and Cooling stages zone pages (v0.17.0 §1): the form, the edit save
("stages 3+ kept as saved" through merge_stages) and the add-path page (§0.5).

Key dependencies: options_flow/stage_fields.py (stage_form_fields, submitted_stages), capability_defaults.py,
page_const.py, const.py; zone_helpers.py, zone_save.py (_stages_for_save), page_save.py and menu.py via the
composed flow.
Used by: zone_pages/heating_stages.py and zone_pages/cooling_stages.py.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ...const import CONF_DEVICES, CONF_NAME, CONF_STAGE, NEW_ZONE_TITLE, STAGES_DISABLED_KEYS
from ..base import OptionsFlowBase
from ..capability_defaults import add_stage_capabilities
from ..page_const import (
    CREATE_LAST_NAV_OPTIONS,
    CREATE_MIDDLE_NAV_OPTIONS,
    NAV_BACK,
    NAV_CANCEL,
    NAV_FIELD,
    NAV_NEXT,
    NAV_SAVE,
    PAGE_NAV_OPTIONS,
)
from ..stage_fields import stage_form_fields, submitted_stages

EDIT_BASELINE = "_edit_baseline"


@dataclass(frozen=True)
class StagePageSpec:
    """What differs between the heating and cooling stage pages."""

    stage_key: str  # heat_stages / cool_stages
    step_id: str
    toggle: str  # has_heat_stages / has_cool_stages
    include_outdoor_min: bool  # only heating shows stage 2's outdoor minimum
    new_zone_enabled: bool  # a new zone starts with heating on and cooling off
    last_of_add_path: bool  # cooling is the add path's last page (it saves)


def apply_stage_list(zone: dict[str, Any], stage_key: str, stages: list[dict[str, Any]]) -> bool:
    """Store one merged stage list in the zone; return whether it changed (an absent empty list stays absent)."""
    if not stages and stage_key not in zone:
        return False
    if zone.get(stage_key) == stages:
        return False
    zone[stage_key] = stages
    return True


def _stage(stages: list[dict[str, Any]], number: int) -> dict[str, Any]:
    """Return the stage with this number, or an empty dict."""
    return next((stage for stage in stages if stage.get(CONF_STAGE) == number), {})


class StagePageMixin(OptionsFlowBase):
    """Mixin running a stage page for a StagePageSpec (edit page or add-path page)."""

    _zone_edit_id: str | None = None
    _zone_wip: dict[str, Any] | None = None

    async def _stage_page(
        self, spec: StagePageSpec, user_input: dict[str, Any] | None,
        back: Callable[[], Awaitable[FlowResult]], forward: Callable[[], Awaitable[FlowResult]],
    ) -> FlowResult:
        """Show or save a stage page; while adding a zone, Back / forward move along the add path."""
        if self._zone_edit_id is None:
            return await self._create_stage_page(spec, user_input, back, forward)
        zone_id = self._zone_edit_id
        loaded = self._load_zone_for_edit(zone_id)
        current = loaded.get(spec.stage_key, [])
        if user_input is None:
            return self._stage_form(spec, current, bool(current), loaded.get(CONF_NAME, zone_id), create=False)
        if user_input.get(NAV_FIELD, NAV_SAVE) == NAV_CANCEL:
            return await self.async_step_zone_menu()
        enabled = bool(user_input.get(spec.toggle, spec.new_zone_enabled))
        baseline = loaded[EDIT_BASELINE]
        # Stages 1-2 from the form, stored 3+ carried; the save merge keeps unshown keys and conditions.
        stages = submitted_stages(user_input, current, baseline.get(spec.stage_key, []),
                                  enabled=enabled, include_outdoor_min=spec.include_outdoor_min)
        merged = self._stages_for_save(
            {spec.stage_key: stages, STAGES_DISABLED_KEYS[spec.stage_key]: not enabled}, spec.stage_key, baseline)

        def apply(zone: dict[str, Any], ui_config: dict[str, Any]) -> None:
            """Store the list; new stage devices gain the direction on their device entry (as the wizard did)."""
            if apply_stage_list(zone, spec.stage_key, merged):
                add_stage_capabilities(self.hass, ui_config, zone)

        return self._save_zone_block(zone_id, apply)

    async def _create_stage_page(
        self, spec: StagePageSpec, user_input: dict[str, Any] | None,
        back: Callable[[], Awaitable[FlowResult]], forward: Callable[[], Awaitable[FlowResult]],
    ) -> FlowResult:
        """Add path: keep the page's stages in the flow; the cooling page saves the new zone."""
        wip = self._zone_wip or {}
        current = wip.get(spec.stage_key, [])
        if user_input is None:
            enabled_default = bool(current) or spec.new_zone_enabled
            return self._stage_form(spec, current, enabled_default, wip.get(CONF_NAME, NEW_ZONE_TITLE), create=True)
        if user_input.get(NAV_FIELD, NAV_NEXT) == NAV_BACK:
            return await back()
        enabled = bool(user_input.get(spec.toggle, spec.new_zone_enabled))
        wip[spec.stage_key] = submitted_stages(user_input, current, [], enabled=enabled,
                                               include_outdoor_min=spec.include_outdoor_min)
        wip[STAGES_DISABLED_KEYS[spec.stage_key]] = not enabled
        self._zone_wip = wip
        return await forward()

    def _stage_form(
        self, spec: StagePageSpec, stages: list[dict[str, Any]], enabled_default: bool, zone_name: str,
        *, create: bool,
    ) -> FlowResult:
        """Render a stage page: nav first, the enable toggle, then the stage 1 and 2 fields."""
        stage1, stage2 = _stage(stages, 1), _stage(stages, 2)
        if not create:
            nav_options, nav_default = PAGE_NAV_OPTIONS, NAV_SAVE
        elif spec.last_of_add_path:
            nav_options, nav_default = CREATE_LAST_NAV_OPTIONS, NAV_SAVE
        else:
            nav_options, nav_default = CREATE_MIDDLE_NAV_OPTIONS, NAV_NEXT
        return self.async_show_form(
            step_id=spec.step_id,
            data_schema=vol.Schema({
                vol.Required(NAV_FIELD, default=nav_default): SelectSelector(
                    SelectSelectorConfig(options=nav_options, mode=SelectSelectorMode.LIST)
                ),
                vol.Required(spec.toggle, default=enabled_default): BooleanSelector(),
                **stage_form_fields(
                    stage1, stage2,
                    self._extract_entity_ids(stage1.get(CONF_DEVICES, [])),
                    self._extract_entity_ids(stage2.get(CONF_DEVICES, [])),
                    include_outdoor_min=spec.include_outdoor_min,
                ),
            }),
            description_placeholders={"zone_name": zone_name},
        )
