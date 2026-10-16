"""Purpose: The Heating stages zone page (v0.17.0 §1): enable, stage 1 and 2 devices, thresholds, escalation in
minutes and stage 2's outdoor minimum; stages 3+ kept as saved. Saves alone when editing; page 2 of the add path.

Key dependencies: zone_pages/stage_page.py (StagePageMixin, StagePageSpec), page_const.py, const.py.
Used by: options_flow/handler.py composes HeatStagesPageMixin; zone_menu and the add path open zone_heat_stages.
"""
from __future__ import annotations

from typing import Any

from homeassistant.data_entry_flow import FlowResult

from ...const import CONF_HEAT_STAGES
from ..page_const import FIELD_HAS_HEAT_STAGES, STEP_ZONE_HEAT_STAGES
from .stage_page import StagePageMixin, StagePageSpec

HEAT_PAGE = StagePageSpec(
    stage_key=CONF_HEAT_STAGES,
    step_id=STEP_ZONE_HEAT_STAGES,
    toggle=FIELD_HAS_HEAT_STAGES,
    include_outdoor_min=True,
    new_zone_enabled=True,
    last_of_add_path=False,
)


class HeatStagesPageMixin(StagePageMixin):
    """Mixin providing the zone_heat_stages step."""

    async def async_step_zone_heat_stages(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show or save Heating stages; on the add path Back is Basics and Next is Cooling stages."""
        return await self._stage_page(
            HEAT_PAGE, user_input, self.async_step_zone_basics, self.async_step_zone_cool_stages)
