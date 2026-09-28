"""Preset mode configuration flow for Hybrid Climate options."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ..const import (
    CONF_DISABLE_ALL,
    CONF_MODES,
    CONF_SETPOINT_OFFSET,
    CONF_SKIP_TIME_ESCALATION,
    CONF_UI_CONFIG,
    CONF_UI_VERSION,
    CONF_USE_ZONE_SETPOINT,
    MODE_AWAY,
    MODE_BOOST,
    MODE_HOME,
    MODE_OFF,
    MODE_SLEEP,
    MODE_VACATION,
)
from .base import OptionsFlowBase


# Action constants
PRESET_ACTION_BACK = "back"


class PresetFlowMixin(OptionsFlowBase):
    """Mixin providing preset mode configuration flow steps."""

    _preset_edit_mode: str | None = None

    async def async_step_presets(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show preset mode list with edit options."""
        if user_input is not None:
            action = user_input.get("action")
            if action == PRESET_ACTION_BACK:
                return await self.async_step_menu()
            elif action and action.startswith("edit_"):
                mode = action[5:]
                self._preset_edit_mode = mode
                return await self.async_step_preset_edit()

        # Build preset list for display
        yaml_modes = self._get_yaml_config().get("master", {}).get(CONF_MODES, {})
        ui_modes = self._get_ui_config().get(CONF_MODES, {})

        preset_options = [
            {"value": PRESET_ACTION_BACK, "label": "← Back to Menu"},
        ]

        mode_labels = {
            MODE_HOME: "Home",
            MODE_AWAY: "Away",
            MODE_SLEEP: "Sleep",
            MODE_VACATION: "Vacation",
            MODE_BOOST: "Boost",
            MODE_OFF: "Off",
        }

        for mode in [MODE_HOME, MODE_AWAY, MODE_SLEEP, MODE_VACATION, MODE_BOOST, MODE_OFF]:
            mode_conf = ui_modes.get(mode, yaml_modes.get(mode, {}))
            
            # Build status summary
            status_parts = []
            if mode_conf.get(CONF_USE_ZONE_SETPOINT):
                status_parts.append(f"use {mode_conf[CONF_USE_ZONE_SETPOINT]} setpoint")
            if mode_conf.get(CONF_SETPOINT_OFFSET):
                offset = mode_conf[CONF_SETPOINT_OFFSET]
                status_parts.append(f"{offset:+.0f}° offset")
            if mode_conf.get(CONF_SKIP_TIME_ESCALATION):
                status_parts.append("skip escalation")
            if mode_conf.get(CONF_DISABLE_ALL):
                status_parts.append("disabled")
            
            status = ", ".join(status_parts) if status_parts else "default"
            
            preset_options.append({
                "value": f"edit_{mode}",
                "label": f"✏️ {mode_labels.get(mode, mode)} ({status})",
            })

        return self.async_show_form(
            step_id="presets",
            data_schema=vol.Schema({
                vol.Required("action"): SelectSelector(
                    SelectSelectorConfig(
                        options=preset_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def async_step_preset_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit a preset mode configuration."""
        errors: dict[str, str] = {}
        mode = self._preset_edit_mode

        if not mode:
            return await self.async_step_presets()

        if user_input is not None:
            # Handle navigation
            nav_action = user_input.get("nav_action", "save")
            if nav_action == "cancel":
                self._preset_edit_mode = None
                return await self.async_step_presets()
            
            return self._save_preset_config(mode, user_input)

        # Load current values
        current = self._load_preset_for_edit(mode)

        # Build schema based on mode
        schema_dict = {}

        if mode != MODE_OFF:
            schema_dict[vol.Required(
                CONF_USE_ZONE_SETPOINT,
                default=current.get(CONF_USE_ZONE_SETPOINT, "default"),
            )] = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "default", "label": "Default setpoint"},
                        {"value": "away", "label": "Away setpoint"},
                        {"value": "sleep", "label": "Sleep setpoint"},
                        {"value": "vacation", "label": "Vacation setpoint"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )

            schema_dict[vol.Optional(
                CONF_SETPOINT_OFFSET,
                default=current.get(CONF_SETPOINT_OFFSET, 0),
            )] = NumberSelector(
                NumberSelectorConfig(
                    min=-20,
                    max=20,
                    step=1,
                    unit_of_measurement="°F",
                    mode=NumberSelectorMode.BOX,
                )
            )

        if mode == MODE_BOOST:
            schema_dict[vol.Required(
                CONF_SKIP_TIME_ESCALATION,
                default=current.get(CONF_SKIP_TIME_ESCALATION, True),
            )] = BooleanSelector()

        if mode == MODE_OFF:
            schema_dict[vol.Required(
                CONF_DISABLE_ALL,
                default=current.get(CONF_DISABLE_ALL, True),
            )] = BooleanSelector()

        mode_labels = {
            MODE_HOME: "Home",
            MODE_AWAY: "Away",
            MODE_SLEEP: "Sleep",
            MODE_VACATION: "Vacation",
            MODE_BOOST: "Boost",
            MODE_OFF: "Off",
        }

        # Add navigation at the end
        schema_dict[vol.Required("nav_action", default="save")] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": "cancel", "label": "← Cancel"},
                    {"value": "save", "label": "Save →"},
                ],
                mode=SelectSelectorMode.LIST,
            )
        )

        return self.async_show_form(
            step_id="preset_edit",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "mode_name": mode_labels.get(mode, mode),
            },
        )

    def _load_preset_for_edit(self, mode: str) -> dict[str, Any]:
        """Load existing preset config for editing."""
        yaml_modes = self._get_yaml_config().get("master", {}).get(CONF_MODES, {})
        ui_modes = self._get_ui_config().get(CONF_MODES, {})

        # UI takes precedence
        mode_conf = ui_modes.get(mode, yaml_modes.get(mode, {}))

        return {
            CONF_USE_ZONE_SETPOINT: mode_conf.get(CONF_USE_ZONE_SETPOINT, "default"),
            CONF_SETPOINT_OFFSET: mode_conf.get(CONF_SETPOINT_OFFSET, 0),
            CONF_SKIP_TIME_ESCALATION: mode_conf.get(CONF_SKIP_TIME_ESCALATION, mode == MODE_BOOST),
            CONF_DISABLE_ALL: mode_conf.get(CONF_DISABLE_ALL, mode == MODE_OFF),
        }

    def _save_preset_config(self, mode: str, user_input: dict[str, Any]) -> FlowResult:
        """Save preset mode configuration."""
        stored_config = dict(self._get_ui_config())
        stored_config[CONF_UI_VERSION] = 1
        
        modes = stored_config.get(CONF_MODES, {})
        if not isinstance(modes, dict):
            modes = {}
        
        mode_config = {}
        
        if CONF_USE_ZONE_SETPOINT in user_input:
            setpoint = user_input[CONF_USE_ZONE_SETPOINT]
            if setpoint != "default":
                mode_config[CONF_USE_ZONE_SETPOINT] = setpoint
        
        if CONF_SETPOINT_OFFSET in user_input:
            offset = user_input[CONF_SETPOINT_OFFSET]
            if offset != 0:
                mode_config[CONF_SETPOINT_OFFSET] = offset
        
        if CONF_SKIP_TIME_ESCALATION in user_input:
            mode_config[CONF_SKIP_TIME_ESCALATION] = user_input[CONF_SKIP_TIME_ESCALATION]
        
        if CONF_DISABLE_ALL in user_input:
            mode_config[CONF_DISABLE_ALL] = user_input[CONF_DISABLE_ALL]
        
        modes[mode] = mode_config
        stored_config[CONF_MODES] = modes

        self._preset_edit_mode = None
        return self._save_ui_config(stored_config)
