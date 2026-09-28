"""Main options flow handler for Hybrid Climate integration."""
from __future__ import annotations

from typing import Any

from homeassistant.data_entry_flow import FlowResult

from .base import OptionsFlowBase
from .conflicts import ConflictFlowMixin
from .devices import DeviceFlowMixin
from .global_settings import GlobalSettingsMixin
from .heat_sources import HeatSourceFlowMixin
from .presets import PresetFlowMixin
from .zones import ZoneFlowMixin


# Menu action constants
MENU_GLOBAL_SETTINGS = "global_settings"
MENU_ZONES = "zones"
MENU_DEVICES = "devices"
MENU_HEAT_SOURCES = "heat_sources"
MENU_PRESETS = "presets"
MENU_CONFLICTS = "conflicts"


class HybridClimateOptionsFlowHandler(
    GlobalSettingsMixin,
    ZoneFlowMixin,
    DeviceFlowMixin,
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
        if user_input is not None:
            next_step = user_input.get("next_step")
            if next_step == MENU_GLOBAL_SETTINGS:
                return await self.async_step_global_settings()
            elif next_step == MENU_ZONES:
                return await self.async_step_zones()
            elif next_step == MENU_DEVICES:
                return await self.async_step_devices()
            elif next_step == MENU_HEAT_SOURCES:
                return await self.async_step_heat_sources()
            elif next_step == MENU_PRESETS:
                return await self.async_step_presets()
            elif next_step == MENU_CONFLICTS:
                return await self.async_step_conflicts()

        return self.async_show_menu(
            step_id="menu",
            menu_options=[
                MENU_GLOBAL_SETTINGS,
                MENU_ZONES,
                MENU_HEAT_SOURCES,
                MENU_PRESETS,
                MENU_CONFLICTS,
                MENU_DEVICES,
            ],
            description_placeholders=self._build_summary_placeholders(),
        )
