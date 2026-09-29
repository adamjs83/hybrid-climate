"""Hybrid Climate Integration for Home Assistant.

A whole-home HVAC orchestration system that coordinates multiple climate
devices across zones with intelligent staging and conflict resolution.
"""
# pyright: reportMissingImports=false
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .config_applier import apply_options_to_config
from .config_converter import build_config_from_ui, import_yaml_to_ui_config, merge_new_yaml_settings
from .config_loader import CONFIG_SCHEMA as YAML_CONFIG_SCHEMA, load_config
from .const import (
    CONF_UI_CONFIG,
    DOMAIN,
)
from .coordinator import HybridClimateCoordinator
from .dashboard_api import async_setup_dashboard
from .device_release import release_removed_config_devices

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.NUMBER, Platform.SENSOR]

# YAML configuration schema
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: YAML_CONFIG_SCHEMA,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up Hybrid Climate from YAML configuration."""
    hass.data.setdefault(DOMAIN, {})
    await async_setup_dashboard(hass)

    if DOMAIN not in config:
        return True

    # Store YAML config for use by config entries
    hass.data[DOMAIN]["yaml_config"] = config[DOMAIN]
    _LOGGER.info("Hybrid Climate YAML configuration loaded")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hybrid Climate from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    ui_config = entry.options.get(CONF_UI_CONFIG, {})
    yaml_config = hass.data[DOMAIN].get("yaml_config")

    _LOGGER.debug(
        "Config startup: yaml_present=%s, ui_present=%s",
        bool(yaml_config), bool(ui_config),
    )

    # Determine config source and build config dict for load_config()
    # Check for _version key which indicates valid UI config (even with empty zones/devices)
    if ui_config.get("_version") or ui_config.get("_yaml_imported") or "zones" in ui_config or "devices" in ui_config:
        # UI config is source of truth - build config from UI
        _LOGGER.debug("Building config from UI config (version=%s, yaml_imported=%s)", ui_config.get("_version"), ui_config.get("_yaml_imported"))

        # YAML merge is deprecated - UI config is now the sole source of truth
        # If you need to add new settings, use the UI options flow

        raw_config = build_config_from_ui(ui_config)
    elif yaml_config:
        # YAML exists but not imported yet - import it now (one-time migration)
        _LOGGER.info(
            "YAML configuration detected - performing one-time import to UI storage. "
            "YAML file will be ignored after this import."
        )
        ui_config = import_yaml_to_ui_config(yaml_config)

        # Merge any existing options into the imported config
        existing_ui = entry.options.get(CONF_UI_CONFIG, {})
        if existing_ui.get("number_values"):
            ui_config["number_values"] = existing_ui["number_values"]

        # Save the imported config to entry.options
        new_options = dict(entry.options)
        new_options[CONF_UI_CONFIG] = ui_config
        hass.config_entries.async_update_entry(entry, options=new_options)
        _LOGGER.info("YAML import complete - UI config is now the source of truth")

        # Build config from the newly imported UI config
        raw_config = build_config_from_ui(ui_config)
    else:
        # No config at all - create minimal empty config
        _LOGGER.warning("No configuration found - creating minimal config")
        raw_config = build_config_from_ui({})

    try:
        config = load_config(raw_config)
        _LOGGER.info(
            "Loaded Hybrid Climate config: %d zones, %d devices",
            len(config.zones),
            len(config.devices),
        )
    except vol.Invalid as e:
        _LOGGER.error("Invalid Hybrid Climate configuration: %s", e)
        return False

    # Apply post-load options overrides (device capabilities, idle behavior)
    apply_options_to_config(config, entry.options)

    # Create coordinator
    coordinator = HybridClimateCoordinator(hass, config, entry)

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "config": config,
    }

    # NOTE: We use OptionsFlowWithReload which handles reload automatically.
    # Do NOT register an update listener here - it's incompatible with OptionsFlowWithReload.
    # entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Forward to climate and number platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Initial refresh
    await coordinator.async_config_entry_first_refresh()

    _LOGGER.info("Hybrid Climate integration setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    existing = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if existing:
        # OptionsFlowWithReload updates entry.options before unloading the old coordinator.
        ui_config = entry.options.get(CONF_UI_CONFIG, {})
        if ui_config:
            try:
                new_config = load_config(build_config_from_ui(ui_config))
            except vol.Invalid as error:
                _LOGGER.warning("Cannot reconcile removed devices with invalid config: %s", error)
                return False
            else:
                if not await release_removed_config_devices(existing["coordinator"], new_config):
                    return False
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.info("Hybrid Climate integration unloaded")

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    if await async_unload_entry(hass, entry):
        await async_setup_entry(hass, entry)
