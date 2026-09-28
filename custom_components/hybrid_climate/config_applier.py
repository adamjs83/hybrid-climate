"""Post-load config option application.

Applies UI option overrides (global settings, device config, preset modes)
to the parsed HybridClimateConfig object.

Key dependencies: models.py (HybridClimateConfig, MasterModeConfig)
Used by: __init__.py (async_setup_entry, after load_config)
"""
# pyright: reportMissingImports=false
from __future__ import annotations

import logging
from typing import Any

from .const import (
    CONF_IDLE_ACTION,
    CONF_IDLE_SETBACK,
    CONF_MASTER_NAME,
    CONF_NEVER_COOL_BELOW,
    CONF_NEVER_HEAT_ABOVE,
    CONF_OCCUPANCY_ENTITY,
    CONF_OUTDOOR_SENSOR,
    CONF_UI_CONFIG,
    CONF_UI_GLOBAL,
    DEFAULT_IDLE_ACTION,
    DEFAULT_IDLE_SETBACK,
)
from .models import (
    DeviceIdleConfig,
    HybridClimateConfig,
    MasterMode,
    MasterModeConfig,
)

_LOGGER = logging.getLogger(__name__)


def apply_options_to_config(config: HybridClimateConfig, options: dict[str, Any]) -> None:
    """Apply options overrides to the parsed config object.

    This handles:
    - Global settings (master name, outdoor sensor, occupancy, outdoor reset)
    - Device idle behavior overrides
    """
    ui_config = options.get(CONF_UI_CONFIG, {})
    global_options = ui_config.get(CONF_UI_GLOBAL, {})

    # Apply global settings
    if global_options:
        master_name = global_options.get(CONF_MASTER_NAME)
        if master_name:
            config.master.name = master_name
            _LOGGER.debug("Applied UI master name: %s", master_name)

        occupancy_entity = global_options.get(CONF_OCCUPANCY_ENTITY)
        if occupancy_entity is not None:
            config.master.occupancy_entity = occupancy_entity or None
            _LOGGER.debug("Applied UI occupancy entity: %s", occupancy_entity)

        outdoor_sensor = global_options.get(CONF_OUTDOOR_SENSOR)
        if outdoor_sensor is not None:
            config.outdoor_sensor = outdoor_sensor or None
            _LOGGER.debug("Applied UI outdoor sensor: %s", outdoor_sensor)

    # Apply outdoor reset limits (check both global and legacy locations)
    heat_limit = options.get(CONF_NEVER_HEAT_ABOVE)
    cool_limit = options.get(CONF_NEVER_COOL_BELOW)

    if heat_limit is None and global_options:
        heat_limit = global_options.get(CONF_NEVER_HEAT_ABOVE)
    if cool_limit is None and global_options:
        cool_limit = global_options.get(CONF_NEVER_COOL_BELOW)

    if heat_limit is not None:
        config.conflicts.outdoor_reset.never_heat_above = heat_limit
        _LOGGER.debug("Applied option never_heat_above: %s", heat_limit)

    if cool_limit is not None:
        config.conflicts.outdoor_reset.never_cool_below = cool_limit
        _LOGGER.debug("Applied option never_cool_below: %s", cool_limit)

    # Apply device config overrides (capabilities, idle behavior)
    # Note: devices are already processed in build_config_from_ui
    # This handles post-load updates to the Device objects (e.g., idle config)
    ui_devices = ui_config.get("devices", {})
    if ui_devices:
        _apply_device_overrides(config, ui_devices)

    # Apply preset mode overrides
    ui_modes = ui_config.get("modes", {})
    if ui_modes:
        _apply_preset_mode_overrides(config, ui_modes)


def _apply_device_overrides(
    config: HybridClimateConfig, ui_devices: dict[str, Any]
) -> None:
    """Apply device config overrides from UI (capabilities, idle behavior).

    UI devices are keyed by entity_id.
    """
    for entity_id, dev_conf in ui_devices.items():
        # Find matching device in config by entity_id
        device = None
        for dev in config.devices.values():
            if dev.entity_id == entity_id:
                device = dev
                break

        if device:
            # Apply idle config
            action = dev_conf.get(CONF_IDLE_ACTION, DEFAULT_IDLE_ACTION)
            setback = dev_conf.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK)
            device.idle_config = DeviceIdleConfig(
                action=action,
                setback=setback,
            )
            _LOGGER.debug(
                "Applied UI device config for %s: action=%s, setback=%s",
                device.device_id,
                device.idle_config.action,
                device.idle_config.setback,
            )
        else:
            _LOGGER.debug(
                "Device override for entity not in config: %s (may be UI-only device)",
                entity_id
            )


def _apply_preset_mode_overrides(config: HybridClimateConfig, ui_modes: dict[str, Any]) -> None:
    """Apply preset mode overrides from UI config.

    UI modes format:
    {
        "home": {"use_zone_defaults": True},
        "away": {"use_zone_setpoint": "away", "setpoint_offset": -2},
        "sleep": {"use_zone_setpoint": "sleep"},
        "vacation": {"use_zone_setpoint": "vacation", "setpoint_offset": -5},
        "boost": {"skip_time_escalation": True},
        "off": {"disable_all": True},
    }
    """
    mode_name_to_enum = {
        "home": MasterMode.HOME,
        "away": MasterMode.AWAY,
        "sleep": MasterMode.SLEEP,
        "vacation": MasterMode.VACATION,
        "boost": MasterMode.BOOST,
        "off": MasterMode.OFF,
    }

    for mode_name, mode_conf in ui_modes.items():
        mode_enum = mode_name_to_enum.get(mode_name.lower())
        if mode_enum is None:
            _LOGGER.warning("Unknown mode in UI config: %s", mode_name)
            continue

        # Build MasterModeConfig from UI settings
        master_mode_config = MasterModeConfig(
            use_zone_defaults=mode_conf.get("use_zone_defaults", False),
            use_zone_setpoint=mode_conf.get("use_zone_setpoint"),
            setpoint_offset=mode_conf.get("setpoint_offset", 0),
            skip_time_escalation=mode_conf.get("skip_time_escalation", False),
            disable_all=mode_conf.get("disable_all", False),
        )

        config.master.modes[mode_enum] = master_mode_config
        _LOGGER.debug(
            "Applied UI mode config for %s: %s",
            mode_name, master_mode_config
        )
