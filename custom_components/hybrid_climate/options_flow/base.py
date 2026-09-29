"""Base class and utilities for options flow handlers."""
# pyright: reportMissingImports=false
from __future__ import annotations

import copy
import logging
from typing import Any


from homeassistant.config_entries import ConfigEntry, OptionsFlow, OptionsFlowWithReload
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from ..const import (
    CONF_CONFLICTS,
    CONF_DEVICES,
    CONF_MASTER,
    CONF_LEGACY_RATE_SENSOR,
    CONF_MASTER_NAME,
    CONF_NAME,
    CONF_NEVER_COOL_BELOW,
    CONF_NEVER_HEAT_ABOVE,
    CONF_OCCUPANCY_ENTITY,
    CONF_OUTDOOR_RESET,
    CONF_OUTDOOR_SENSOR,
    CONF_TOU_RATE_SENSOR,
    CONF_UI_CONFIG,
    CONF_UI_GLOBAL,
    CONF_UI_VERSION,
    CONF_ZONES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def replace_changed_subtrees(
    fresh: dict[str, Any], original: dict[str, Any], edited: dict[str, Any],
) -> dict[str, Any]:
    """Apply edited child blocks to fresh storage, including explicit deletions."""
    result = copy.deepcopy(fresh)
    for key in original.keys() - edited.keys():
        result.pop(key, None)
    for key, value in edited.items():
        previous = original.get(key)
        if key in original and value == previous:
            continue
        if isinstance(value, dict) and isinstance(previous, dict):
            current = result.get(key, {})
            if isinstance(current, dict):
                result[key] = replace_changed_subtrees(current, previous, value)
                continue
        result[key] = copy.deepcopy(value)
    return result


# Defaults for outdoor reset
DEFAULT_NEVER_HEAT_ABOVE = 75.0
DEFAULT_NEVER_COOL_BELOW = 55.0


class OptionsFlowBase(OptionsFlowWithReload):
    """Base class for options flow with shared utilities.
    
    Using OptionsFlowWithReload ensures the integration is properly reloaded
    after options change, and handles storage persistence correctly.
    
    Note: self.config_entry is provided by the OptionsFlow base class
    starting in HA 2025.x. We no longer assign it manually.
    """
    
    # No __init__ override needed - OptionsFlow provides config_entry

    @property
    def _hass(self) -> HomeAssistant:
        """Get Home Assistant instance."""
        return self.hass

    def _get_yaml_config(self) -> dict[str, Any]:
        """Return the YAML configuration stored during setup."""
        return self._hass.data.get(DOMAIN, {}).get("yaml_config", {})

    def _get_ui_config(self) -> dict[str, Any]:
        """Get the UI config blob from options.
        
        IMPORTANT: We get a fresh reference to the config entry from hass
        to ensure we have the latest options after any updates.
        """
        # Get fresh entry reference from hass to ensure we have latest options
        entry = self.hass.config_entries.async_get_entry(self.config_entry.entry_id)
        if entry is None:
            entry = self.config_entry
        ui_config = copy.deepcopy(entry.options.get(CONF_UI_CONFIG, {}))
        self._ui_config_snapshot = copy.deepcopy(ui_config)
        _LOGGER.debug(
            "_get_ui_config: entry_id=%s, zones=%s",
            entry.entry_id,
            list(ui_config.get("zones", {}).keys()) if isinstance(ui_config, dict) else "NOT_DICT",
        )
        return ui_config

    def _get_ui_global(self) -> dict[str, Any]:
        """Get global settings from UI config."""
        ui_config = self._get_ui_config()
        return ui_config.get(CONF_UI_GLOBAL, {}) if isinstance(ui_config, dict) else {}

    def _current_global_settings(self) -> dict[str, Any]:
        """Merge YAML defaults with any saved UI overrides."""
        yaml_config = self._get_yaml_config()
        ui_global = self._get_ui_global()

        master_conf = yaml_config.get(CONF_MASTER, {})
        conflicts = yaml_config.get(CONF_CONFLICTS, {})
        outdoor_reset = conflicts.get(CONF_OUTDOOR_RESET, {})

        master_name = (
            ui_global.get(CONF_MASTER_NAME)
            or master_conf.get(CONF_NAME)
            or "Hybrid Climate"
        )

        return {
            CONF_MASTER_NAME: master_name,
            CONF_OUTDOOR_SENSOR: ui_global.get(
                CONF_OUTDOOR_SENSOR, yaml_config.get(CONF_OUTDOOR_SENSOR)
            ),
            CONF_OCCUPANCY_ENTITY: ui_global.get(
                CONF_OCCUPANCY_ENTITY, master_conf.get(CONF_OCCUPANCY_ENTITY)
            ),
            CONF_NEVER_HEAT_ABOVE: ui_global.get(
                CONF_NEVER_HEAT_ABOVE,
                outdoor_reset.get(CONF_NEVER_HEAT_ABOVE, DEFAULT_NEVER_HEAT_ABOVE),
            ),
            CONF_NEVER_COOL_BELOW: ui_global.get(
                CONF_NEVER_COOL_BELOW,
                outdoor_reset.get(CONF_NEVER_COOL_BELOW, DEFAULT_NEVER_COOL_BELOW),
            ),
            CONF_TOU_RATE_SENSOR: ui_global.get(
                CONF_TOU_RATE_SENSOR, ui_global.get(CONF_LEGACY_RATE_SENSOR)
            ),
        }

    def _build_summary_placeholders(self) -> dict[str, str]:
        """Generate placeholders for summary displays."""
        yaml_config = self._get_yaml_config()
        ui_config = self._get_ui_config()

        ui_zones = ui_config.get("zones") if isinstance(ui_config, dict) else None
        ui_devices = ui_config.get("devices") if isinstance(ui_config, dict) else None

        zone_count = (
            len(ui_zones)
            if isinstance(ui_zones, dict)
            else len(yaml_config.get(CONF_ZONES, {}))
        )
        device_count = (
            len(ui_devices)
            if isinstance(ui_devices, dict)
            else len(yaml_config.get(CONF_DEVICES, {}))
        )

        current = self._current_global_settings()

        return {
            "zone_count": str(zone_count),
            "device_count": str(device_count),
            "master_name": current.get(CONF_MASTER_NAME, "Hybrid Climate"),
        }

    def _save_ui_config(self, ui_config: dict[str, Any]) -> FlowResult:
        """Save UI config to options and create entry.

        Apply snapshot differences so omitted nested keys stay deleted.

        Using OptionsFlowWithReload as base class ensures the integration is
        automatically reloaded and options are persisted when async_create_entry
        is called.
        """
        # Get fresh entry reference from hass to ensure we have latest options
        entry = self.hass.config_entries.async_get_entry(self.config_entry.entry_id)
        if entry is None:
            _LOGGER.error("_save_ui_config: Could not find config entry %s", self.config_entry.entry_id)
            entry = self.config_entry

        # Get fresh UI config from storage (not from our potentially stale copy)
        fresh_options = copy.deepcopy(dict(entry.options))
        fresh_ui_config = fresh_options.get(CONF_UI_CONFIG, {})

        # Log pre-save state for debugging
        _LOGGER.debug(
            "_save_ui_config PRE-MERGE: fresh_zones=%s, incoming_zones=%s",
            list(fresh_ui_config.get("zones", {}).keys()) if isinstance(fresh_ui_config, dict) else "N/A",
            list(ui_config.get("zones", {}).keys()) if isinstance(ui_config, dict) else "N/A",
        )

        # A flow edits a snapshot. Apply only its changed blocks to fresh storage;
        # a removed child stays removed while unrelated concurrent edits survive.
        snapshot = getattr(self, "_ui_config_snapshot", None)
        if snapshot is None:
            merged_ui_config = {**fresh_ui_config, **copy.deepcopy(ui_config)}
        else:
            merged_ui_config = replace_changed_subtrees(fresh_ui_config, snapshot, ui_config)

        # Build new options with merged UI config
        new_options = fresh_options
        new_options[CONF_UI_CONFIG] = merged_ui_config

        # Also copy temperature limits to top-level for backwards compat
        global_settings = merged_ui_config.get(CONF_UI_GLOBAL, {})
        if CONF_NEVER_HEAT_ABOVE in global_settings:
            new_options[CONF_NEVER_HEAT_ABOVE] = global_settings[CONF_NEVER_HEAT_ABOVE]
        if CONF_NEVER_COOL_BELOW in global_settings:
            new_options[CONF_NEVER_COOL_BELOW] = global_settings[CONF_NEVER_COOL_BELOW]

        _LOGGER.debug(
            "Saved UI config: %d zones, %d devices, %d mutex rules",
            len(merged_ui_config.get("zones", {})),
            len(merged_ui_config.get("devices", {})),
            len(merged_ui_config.get("device_mutex", [])),
        )

        # OptionsFlowWithReload handles reload and persistence automatically
        return self.async_create_entry(title="", data=new_options)

    @staticmethod
    def normalize_optional_str(value: str | None) -> str | None:
        """Normalize blank strings from form inputs to None."""
        if value is None:
            return None
        value = value.strip()
        return value or None
