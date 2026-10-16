"""Purpose: The Cooling stages zone page (v0.17.0 §1): enable, stage 1 and 2 devices, thresholds and escalation in
minutes (no outdoor minimum); stages 3+ kept as saved. Saves alone when editing; the add path's last page saves the
new zone and closes the flow (owner decision 3).

Key dependencies: zone_pages/stage_page.py (StagePageMixin, StagePageSpec), page_const.py, const.py;
zone_save.py (_save_zone_config) via the composed flow.
Used by: options_flow/handler.py composes CoolStagesPageMixin; zone_menu and the add path open zone_cool_stages.
"""
from __future__ import annotations

from typing import Any

from homeassistant.data_entry_flow import FlowResult

from ...const import CONF_COOL_STAGES
from ..page_const import FIELD_HAS_COOL_STAGES, STEP_ZONE_COOL_STAGES
from .stage_page import StagePageMixin, StagePageSpec

COOL_PAGE = StagePageSpec(
    stage_key=CONF_COOL_STAGES,
    step_id=STEP_ZONE_COOL_STAGES,
    toggle=FIELD_HAS_COOL_STAGES,
    include_outdoor_min=False,
    new_zone_enabled=False,
    last_of_add_path=True,
)


class CoolStagesPageMixin(StagePageMixin):
    """Mixin providing the zone_cool_stages step."""

    async def async_step_zone_cool_stages(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show or save Cooling stages; on the add path Back is Heating stages and Save stores the new zone."""
        return await self._stage_page(COOL_PAGE, user_input, self.async_step_zone_heat_stages, self._save_new_zone)

    async def _save_new_zone(self) -> FlowResult:
        """Store the zone the add path collected (the flow then closes and reloads)."""
        return self._save_zone_config()
