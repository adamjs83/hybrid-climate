"""Purpose: Set up and unload the Hybrid Climate integration.

Key dependencies: Home Assistant lifecycle, config preparation, coordinator.
Used by: Home Assistant integration loader.
"""
# pyright: reportMissingImports=false
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .agent_api import async_register_services
from .agent_api.revision import ledger, stored_revision
from .capability_check import warn_load_mismatches
from .config_converter import build_config_from_ui, import_yaml_to_ui_config
from .config_loader import CONFIG_SCHEMA as YAML_CONFIG_SCHEMA, load_config
from .config_prepare import prepare_runtime_config
from .const import (
    CONF_NUMBER_VALUES,
    CONF_UI_CONFIG,
    DATA_ACTIVE_REVISION,
    DATA_PREPARED_OPTIONS,
    DOMAIN,
)
from .coordinator import HybridClimateCoordinator
from .dashboard_api import async_setup_dashboard
from .device_release import release_removed_config_devices

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.NUMBER, Platform.SENSOR, Platform.BINARY_SENSOR]

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
    await async_register_services(hass)
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

    # Select the UI source before taking an isolated preparation snapshot.
    # Check for _version key which indicates valid UI config (even with empty zones/devices)
    if ui_config.get("_version") or ui_config.get("_yaml_imported") or "zones" in ui_config or "devices" in ui_config:
        # UI config is source of truth.
        _LOGGER.debug("Building config from UI config (version=%s, yaml_imported=%s)", ui_config.get("_version"), ui_config.get("_yaml_imported"))

        # YAML merge is deprecated - UI config is now the sole source of truth
        # If you need to add new settings, use the UI options flow

    elif yaml_config:
        # YAML exists but not imported yet - import it now (one-time migration)
        _LOGGER.info(
            "YAML configuration detected - performing one-time import to UI storage. "
            "YAML file will be ignored after this import."
        )
        ui_config = import_yaml_to_ui_config(yaml_config)

        # Merge any existing options into the imported config
        existing_ui = entry.options.get(CONF_UI_CONFIG, {})
        if existing_ui.get(CONF_NUMBER_VALUES):
            ui_config[CONF_NUMBER_VALUES] = existing_ui[CONF_NUMBER_VALUES]

        # Save the imported config to entry.options
        new_options = dict(entry.options)
        new_options[CONF_UI_CONFIG] = ui_config
        hass.config_entries.async_update_entry(entry, options=new_options)
        _LOGGER.info("YAML import complete - UI config is now the source of truth")

    else:
        # No config at all - create minimal empty config
        _LOGGER.warning("No configuration found - creating minimal config")

    # Hash the same prepared options used for this setup, before awaited work.
    prepared_options = deepcopy(dict(entry.options))
    if not (ui_config.get("_version") or ui_config.get("_yaml_imported")
            or "zones" in ui_config or "devices" in ui_config):
        prepared_options[CONF_UI_CONFIG] = {}
    try:
        config = prepare_runtime_config(prepared_options)
        prepared_hash = stored_revision(prepared_options)
    except (vol.Invalid, ValueError) as error:
        _LOGGER.error("Invalid Hybrid Climate configuration: %s", error)
        return False
    _LOGGER.info(
        "Loaded Hybrid Climate config: %d zones, %d devices",
        len(config.zones), len(config.devices),
    )
    warn_load_mismatches(config, entry.entry_id)

    # Activate the prepared config only after platforms and first refresh succeed.
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

    hass.data[DOMAIN][entry.entry_id][DATA_ACTIVE_REVISION] = prepared_hash
    ledger(hass)["active"][entry.entry_id] = prepared_hash
    source_options = deepcopy(prepared_options)
    source_options.get(CONF_UI_CONFIG, {}).pop(CONF_NUMBER_VALUES, None)
    hass.data[DOMAIN][entry.entry_id][DATA_PREPARED_OPTIONS] = source_options

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
