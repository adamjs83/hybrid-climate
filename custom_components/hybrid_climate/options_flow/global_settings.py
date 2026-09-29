"""Global settings flow for Hybrid Climate options."""
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

from ..const import (
    CONF_MASTER_NAME,
    CONF_NEVER_COOL_BELOW,
    CONF_NEVER_HEAT_ABOVE,
    CONF_LOCKOUT_HEAT_FLOOR,
    MIN_LOCKOUT_HEAT_FLOOR,
    MAX_LOCKOUT_HEAT_FLOOR,
    LOCKOUT_HEAT_FLOOR_STEP,
    CONF_OCCUPANCY_ENTITY,
    CONF_OUTDOOR_SENSORS,
    OUTDOOR_ENTITY_DOMAINS,
    CONF_TOU_RATE_SENSOR,
    CONF_UI_CONFIG,
    CONF_UI_GLOBAL,
    CONF_UI_VERSION,
)
from .base import OptionsFlowBase


class GlobalSettingsMixin(OptionsFlowBase):
    """Mixin providing global settings flow step."""

    async def async_step_global_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure master + outdoor reset settings."""
        errors: dict[str, str] = {}
        current = self._current_global_settings()

        if user_input is not None:
            # Handle navigation
            nav_action = user_input.get("nav_action", "save")
            if nav_action == "cancel":
                return await self.async_step_menu()
            
            master_name = user_input.get(CONF_MASTER_NAME, "").strip()
            heat_above = user_input.get(CONF_NEVER_HEAT_ABOVE)
            cool_below = user_input.get(CONF_NEVER_COOL_BELOW)

            if not master_name:
                errors[CONF_MASTER_NAME] = "master_name_required"

            if heat_above is not None and cool_below is not None:
                # never_heat_above should be LESS than never_cool_below
                # e.g., don't heat when outdoor > 55°F, don't cool when outdoor < 63°F
                if heat_above >= cool_below:
                    errors["base"] = "invalid_temp_range"

            if not errors:
                settings = {
                    CONF_MASTER_NAME: master_name,
                    CONF_OUTDOOR_SENSORS: list(user_input.get(CONF_OUTDOOR_SENSORS) or []),
                    CONF_OCCUPANCY_ENTITY: self.normalize_optional_str(
                        user_input.get(CONF_OCCUPANCY_ENTITY)
                    ),
                    CONF_TOU_RATE_SENSOR: self.normalize_optional_str(
                        user_input.get(CONF_TOU_RATE_SENSOR)
                    ),
                    CONF_NEVER_HEAT_ABOVE: heat_above,
                    CONF_LOCKOUT_HEAT_FLOOR: user_input.get(
                        CONF_LOCKOUT_HEAT_FLOOR, current[CONF_LOCKOUT_HEAT_FLOOR],
                    ),
                    CONF_NEVER_COOL_BELOW: cool_below,
                }
                return self._save_global_settings(settings)

        outdoor_sensors_default = current.get(CONF_OUTDOOR_SENSORS) or []
        occupancy_default = current.get(CONF_OCCUPANCY_ENTITY) or ""
        tou_rate_sensor_default = current.get(CONF_TOU_RATE_SENSOR) or ""

        return self.async_show_form(
            step_id="global_settings",
            data_schema=vol.Schema(
                {
                    vol.Required("nav_action", default="save"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": "cancel", "label": "← Cancel"},
                                {"value": "save", "label": "Save →"},
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required(
                        CONF_MASTER_NAME,
                        default=current[CONF_MASTER_NAME],
                    ): str,
                    vol.Optional(
                        CONF_OUTDOOR_SENSORS,
                        default=outdoor_sensors_default,
                    ): EntitySelector(EntitySelectorConfig(domain=list(OUTDOOR_ENTITY_DOMAINS), multiple=True)),
                    vol.Optional(
                        CONF_OCCUPANCY_ENTITY,
                        default=occupancy_default,
                    ): str,
                    vol.Optional(
                        CONF_TOU_RATE_SENSOR,
                        description={"suggested_value": tou_rate_sensor_default},
                    ): EntitySelector(EntitySelectorConfig(domain="sensor")),
                    vol.Required(
                        CONF_NEVER_HEAT_ABOVE,
                        default=current[CONF_NEVER_HEAT_ABOVE],
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=30,
                            max=100,
                            step=1,
                            unit_of_measurement="°F",
                            mode=NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Required(
                        CONF_LOCKOUT_HEAT_FLOOR,
                        default=current[CONF_LOCKOUT_HEAT_FLOOR],
                    ): NumberSelector(NumberSelectorConfig(
                        min=MIN_LOCKOUT_HEAT_FLOOR, max=MAX_LOCKOUT_HEAT_FLOOR,
                        step=LOCKOUT_HEAT_FLOOR_STEP, unit_of_measurement="°F",
                        mode=NumberSelectorMode.SLIDER,
                    )),
                    vol.Required(
                        CONF_NEVER_COOL_BELOW,
                        default=current[CONF_NEVER_COOL_BELOW],
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=30,
                            max=100,
                            step=1,
                            unit_of_measurement="°F",
                            mode=NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    def _save_global_settings(self, settings: dict[str, Any]) -> FlowResult:
        """Persist global settings into options storage."""
        stored_config = dict(self._get_ui_config())
        stored_config[CONF_UI_VERSION] = 1
        stored_config[CONF_UI_GLOBAL] = settings

        return self._save_ui_config(stored_config)
