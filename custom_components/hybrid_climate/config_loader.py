"""YAML configuration loader for Hybrid Climate integration.

Key dependencies: config_schemas.py, config_parsers.py
Used by: __init__.py (async_setup_entry)
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from .const import (
    CONF_CONFLICTS,
    CONF_DEVICES,
    CONF_HEAT_SOURCES,
    CONF_LEGACY_RATE_SENSOR,
    CONF_MASTER,
    CONF_OUTDOOR_SENSOR,
    CONF_OUTDOOR_SENSORS,
    CONF_LOCKOUT_HEAT_FLOOR,
    DEFAULT_LOCKOUT_HEAT_FLOOR,
    CONF_TOU_RATE_SENSOR,
    CONF_ZONES,
)
from .models import HybridClimateConfig, TouGlobalConfig
from .regulation_filter import filter_regulation_devices

# Re-export schemas for __init__.py
from .config_schemas import CONFIG_SCHEMA  # noqa: F401

# Re-export parse functions used elsewhere
from .config_parsers import (  # noqa: F401
    normalize_mutex_device_ids,
    parse_conflicts,
    parse_device,
    parse_heat_source,
    parse_master,
    parse_zone,
)


def load_config(raw_config: dict[str, Any]) -> HybridClimateConfig:
    """Load and parse the full configuration.

    Args:
        raw_config: Raw YAML configuration dict

    Returns:
        Parsed HybridClimateConfig

    Raises:
        vol.Invalid: If configuration is invalid
    """
    # Validate schema
    validated = CONFIG_SCHEMA(raw_config)

    # Parse devices
    devices = {
        device_id: parse_device(device_id, device_data)
        for device_id, device_data in validated[CONF_DEVICES].items()
    }
    # Parse zones
    zones = {
        zone_id: parse_zone(zone_id, zone_data)
        for zone_id, zone_data in validated[CONF_ZONES].items()
    }

    # Parse heat sources
    heat_sources = {
        source_id: parse_heat_source(source_id, source_data)
        for source_id, source_data in validated.get(CONF_HEAT_SOURCES, {}).items()
    }

    # Validate that all devices referenced in zones exist
    for zone_id, zone_config in zones.items():
        for stage in zone_config.heat_stages + zone_config.cool_stages:
            for stage_device in stage.devices:
                if stage_device.device_id not in devices:
                    raise vol.Invalid(
                        f"Zone '{zone_id}' references unknown device '{stage_device.device_id}'"
                    )

    # Validate that all devices referenced in heat sources exist
    for source_id, source_config in heat_sources.items():
        for device_id in source_config.devices:
            if device_id not in devices:
                raise vol.Invalid(
                    f"Heat source '{source_id}' references unknown device '{device_id}'"
                )

    tou_global = TouGlobalConfig(
        rate_sensor=validated.get(CONF_TOU_RATE_SENSOR, validated.get(CONF_LEGACY_RATE_SENSOR)),
    )

    conflicts = parse_conflicts(validated.get(CONF_CONFLICTS, {}))
    try:
        normalize_mutex_device_ids(conflicts, devices)
    except ValueError as error:
        raise vol.Invalid(str(error)) from error

    config = HybridClimateConfig(
        lockout_heat_floor=validated.get(CONF_LOCKOUT_HEAT_FLOOR, DEFAULT_LOCKOUT_HEAT_FLOOR),
        outdoor_sensors=validated.get(CONF_OUTDOOR_SENSORS, [validated[CONF_OUTDOOR_SENSOR]]
                                      if validated.get(CONF_OUTDOOR_SENSOR) else []),
        master=parse_master(validated[CONF_MASTER]),
        conflicts=conflicts,
        devices=devices,
        zones=zones,
        heat_sources=heat_sources,
        tou_global=tou_global,
    )
    filter_regulation_devices(config)
    return config
