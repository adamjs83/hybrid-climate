"""Purpose: The Shared equipment menu: heat source groups and equipment that cannot run together (v0.17.0 §0.7).

Key dependencies: options_flow/base.py, options_flow/page_const.py.
Used by: options_flow/handler.py (top menu item; heat_sources.py and conflicts.py return here).
"""
from __future__ import annotations

from typing import Any

from homeassistant.data_entry_flow import FlowResult

from .base import OptionsFlowBase
from .page_const import STEP_CONFLICTS, STEP_HEAT_SOURCES, STEP_MENU, STEP_SHARED_EQUIPMENT

SHARED_EQUIPMENT_OPTIONS: list[str] = [STEP_HEAT_SOURCES, STEP_CONFLICTS, STEP_MENU]


class SharedEquipmentMixin(OptionsFlowBase):
    """Mixin providing the Shared equipment menu step."""

    async def async_step_shared_equipment(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the Shared equipment menu (HA routes each choice to its step)."""
        return self.async_show_menu(
            step_id=STEP_SHARED_EQUIPMENT,
            menu_options=list(SHARED_EQUIPMENT_OPTIONS),
        )
