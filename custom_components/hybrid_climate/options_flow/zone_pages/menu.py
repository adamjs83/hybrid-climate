"""Purpose: The per-zone options menu (a real HA menu) opened from the zone list (v0.17.0 §0.4).

Key dependencies: options_flow/page_const.py, zone_helpers.py (_load_zone_for_edit) via the composed flow.
Used by: options_flow/zones.py (edit_<id> opens it); handler.py composes ZoneMenuMixin.
"""
from __future__ import annotations

from typing import Any

from homeassistant.data_entry_flow import FlowResult

from ...const import CONF_NAME
from ..base import OptionsFlowBase
from ..page_const import (
    STEP_ZONE_BASICS,
    STEP_ZONE_BEHAVIOUR,
    STEP_ZONE_COOL_STAGES,
    STEP_ZONE_HEAT_STAGES,
    STEP_ZONE_MENU,
    STEP_ZONE_REGULATION,
    STEP_ZONE_SETPOINTS,
    STEP_ZONE_TOU,
    STEP_ZONES,
)

# The zone menu's choices, in order (spec §1 page table), then "Back to zones".
ZONE_MENU_OPTIONS: list[str] = [
    STEP_ZONE_BASICS,
    STEP_ZONE_SETPOINTS,
    STEP_ZONE_HEAT_STAGES,
    STEP_ZONE_COOL_STAGES,
    STEP_ZONE_BEHAVIOUR,
    STEP_ZONE_REGULATION,
    STEP_ZONE_TOU,
    STEP_ZONES,
]


class ZoneMenuMixin(OptionsFlowBase):
    """Mixin providing the zone menu step."""

    _zone_edit_id: str | None = None
    _zone_wip: dict[str, Any] | None = None

    async def async_step_zone_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the menu for the zone being edited (HA routes each choice to its step)."""
        zone_id = self._zone_edit_id
        if not zone_id:
            return await self.async_step_zones()
        # Reload on every visit so each page starts from stored values.
        self._zone_wip = self._load_zone_for_edit(zone_id)
        return self.async_show_menu(
            step_id=STEP_ZONE_MENU,
            menu_options=list(ZONE_MENU_OPTIONS),
            description_placeholders={"zone_name": self._zone_wip.get(CONF_NAME, zone_id)},
        )
