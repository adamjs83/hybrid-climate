"""Config flow for Hybrid Climate integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
)

from .const import CONF_UI_CONFIG, DOMAIN
from .options_flow import HybridClimateOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)


class HybridClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hybrid Climate.

    Supports two setup modes:
    1. YAML Import: If YAML config exists, import it and use as starting point
    2. Pure UI: Create empty config and configure everything via options flow
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Check if YAML config exists
        yaml_config = self.hass.data.get(DOMAIN, {}).get("yaml_config")

        if user_input is not None:
            master_name = user_input.get("master_name", "Home HVAC")
            
            if yaml_config:
                # YAML exists - will be imported on first setup
                _LOGGER.info("Creating config entry - YAML will be imported on setup")
                return self.async_create_entry(
                    title=master_name,
                    data={},  # YAML import happens in async_setup_entry
                )
            else:
                # No YAML - create minimal UI config
                _LOGGER.info("Creating config entry with empty UI config")
                ui_config = {
                    "_version": 1,
                    "global": {
                        "master_name": master_name,
                    },
                    "devices": {},
                    "zones": {},
                }
                return self.async_create_entry(
                    title=master_name,
                    data={},
                    options={CONF_UI_CONFIG: ui_config},
                )

        if yaml_config:
            # Show confirmation that YAML config was found
            zone_count = len(yaml_config.get("zones", {}))
            device_count = len(yaml_config.get("devices", {}))
            master_name = yaml_config.get("master", {}).get("name", "Home HVAC")

            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required("master_name", default=master_name): TextSelector(
                        TextSelectorConfig(type="text")
                    ),
                }),
                description_placeholders={
                    "zone_count": str(zone_count),
                    "device_count": str(device_count),
                    "has_yaml": "true",
                },
            )
        else:
            # No YAML config - pure UI setup
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required("master_name", default="Home HVAC"): TextSelector(
                        TextSelectorConfig(type="text")
                    ),
                }),
                description_placeholders={
                    "zone_count": "0",
                    "device_count": "0",
                    "has_yaml": "false",
                },
            )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler.
        
        Note: In HA 2024.x+, the OptionsFlow base class automatically
        receives config_entry via self.config_entry. We don't need to
        pass it manually.
        """
        return HybridClimateOptionsFlowHandler()
