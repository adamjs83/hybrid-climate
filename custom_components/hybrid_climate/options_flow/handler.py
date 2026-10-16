"""Purpose: Main options flow handler for Hybrid Climate: composes the page mixins and shows the top menu.

Key dependencies: every options_flow mixin, options_flow/page_const.py.
Used by: config_flow.py (async_get_options_flow) via options_flow/__init__.py.
"""
from __future__ import annotations

from typing import Any

from homeassistant.data_entry_flow import FlowResult

from .base import OptionsFlowBase
from .conflicts import ConflictFlowMixin
from .devices import DeviceFlowMixin
from .global_settings import GlobalSettingsMixin
from .heat_sources import HeatSourceFlowMixin
from .page_const import (
    STEP_DEVICES,
    STEP_GLOBAL_SETTINGS,
    STEP_MENU,
    STEP_PRESETS,
    STEP_SHARED_EQUIPMENT,
    STEP_ZONES,
)
from .presets import PresetFlowMixin
from .shared_equipment import SharedEquipmentMixin
from .zone_pages.basics import BasicsPageMixin
from .zone_pages.behaviour import BehaviourPageMixin
from .zone_pages.cooling_stages import CoolStagesPageMixin
from .zone_pages.delete_confirm import DeleteConfirmMixin
from .zone_pages.heating_stages import HeatStagesPageMixin
from .zone_pages.menu import ZoneMenuMixin
from .zone_pages.page_save import ZonePageSaveMixin
from .zone_pages.regulation import RegulationPageMixin
from .zone_pages.setpoints_occupancy import SetpointsPageMixin
from .zone_pages.time_of_use import TimeOfUsePageMixin
from .zones import ZoneFlowMixin

# Top menu (spec v0.17.0 §1): Global settings · Zones · Devices · Presets · Shared equipment.
# HA routes a menu choice straight to async_step_<option>.
TOP_MENU_OPTIONS: list[str] = [
    STEP_GLOBAL_SETTINGS,
    STEP_ZONES,
    STEP_DEVICES,
    STEP_PRESETS,
    STEP_SHARED_EQUIPMENT,
]


class HybridClimateOptionsFlowHandler(
    GlobalSettingsMixin,
    ZoneMenuMixin,
    BasicsPageMixin,
    SetpointsPageMixin,
    HeatStagesPageMixin,
    CoolStagesPageMixin,
    BehaviourPageMixin,
    RegulationPageMixin,
    TimeOfUsePageMixin,
    ZonePageSaveMixin,
    DeleteConfirmMixin,
    ZoneFlowMixin,
    DeviceFlowMixin,
    SharedEquipmentMixin,
    HeatSourceFlowMixin,
    PresetFlowMixin,
    ConflictFlowMixin,
    OptionsFlowBase,
):
    """Handle options flow for Hybrid Climate.

    Uses mixin pattern to compose flow steps from separate modules.
    Inheritance order matters: mixins first, then base class.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Entry point - show main menu."""
        return await self.async_step_menu()

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show main configuration menu."""
        return self.async_show_menu(
            step_id=STEP_MENU,
            menu_options=list(TOP_MENU_OPTIONS),
            description_placeholders=self._build_summary_placeholders(),
        )
