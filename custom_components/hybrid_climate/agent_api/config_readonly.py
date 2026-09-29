"""Purpose: Project noneditable active configuration and compressor groups.

Key dependencies: Loaded models and the prepared options snapshot.
Used by: Agent API get_config service.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ..const import (
    CONF_ALLOW_COMMAND, CONF_DEVICE, CONF_DEVICES, CONF_ENTITY_ID, CONF_IDLE_ACTION,
    CONF_IDLE_SETBACK, CONF_OUTDOOR_SENSOR, CONF_REGULATION, CONF_UI_CONFIG, IDLE_ACTIONS,
    CONF_UI_GLOBAL, CONF_ZONES,
)
from ..models import HybridClimateConfig
from .const import (
    MALFORMED_STAGE_STORAGE_WARNING, READ_ONLY_DESCRIPTIONS, READ_ONLY_TEMPERATURE_UNIT,
    SOURCE_DEFAULT, SOURCE_UI_CONFIG,
)

_LOGGER = logging.getLogger(__name__)


def _entry(value: Any, source: str, kind: str, description: str) -> dict[str, Any]:
    return {"value": value, "source": source, "type": kind,
            "description": READ_ONLY_DESCRIPTIONS[description], "writable": False}


def readonly_global(model: HybridClimateConfig, options: Mapping[str, Any]) -> dict[str, Any]:
    """Describe the active outdoor sensor and its prepared storage source."""
    global_options = options.get(CONF_UI_CONFIG, {}).get(CONF_UI_GLOBAL, {})
    source = SOURCE_UI_CONFIG if CONF_OUTDOOR_SENSOR in global_options else SOURCE_DEFAULT
    return {CONF_OUTDOOR_SENSOR: _entry(model.outdoor_sensor, source, "entity_id", CONF_OUTDOOR_SENSOR)}


def readonly_device(
    model: HybridClimateConfig, options: Mapping[str, Any], device_id: str,
) -> dict[str, Any]:
    """Describe a device's idle behavior and stage command permission."""
    device = model.devices[device_id]
    storage = options.get(CONF_UI_CONFIG, {}).get(CONF_DEVICES, {}).get(device.entity_id, {})
    idle: dict[str, Any] = {}
    for key, value, kind in (
        (CONF_IDLE_ACTION, device.idle_config.action, "enum"),
        (CONF_IDLE_SETBACK, device.idle_config.setback, "float"),
    ):
        source = SOURCE_UI_CONFIG if key in storage else SOURCE_DEFAULT
        field = _entry(value, source, kind, f"idle.{key}")
        if key == CONF_IDLE_ACTION:
            field["enum"] = list(IDLE_ACTIONS)
        else:
            field["unit"] = READ_ONLY_TEMPERATURE_UNIT
        idle[key] = field

    zones = [zone_id for zone_id, zone in model.zones.items()
             if device_id in zone.get_allow_command_device_ids()]
    ui_zones = options.get(CONF_UI_CONFIG, {}).get(CONF_ZONES, {})
    # The converter reads allow_command on stage device entries, including explicit false.
    try:
        stored = any(
            isinstance(ref, Mapping)
            and (ref.get(CONF_ENTITY_ID) or ref.get(CONF_DEVICE)) == device.entity_id
            and CONF_ALLOW_COMMAND in ref
            for zone in ui_zones.values()
            for direction in ("heat_stages", "cool_stages")
            for stage in zone.get(direction, [])
            for ref in stage.get(CONF_DEVICES, [])
        )
    except (AttributeError, TypeError):
        # Malformed stage storage cannot establish reliable provenance.
        _LOGGER.warning(MALFORMED_STAGE_STORAGE_WARNING, device_id)
        stored = False
    permission = _entry(bool(zones), SOURCE_UI_CONFIG if stored else SOURCE_DEFAULT,
                        "bool", CONF_ALLOW_COMMAND)
    permission["zones"] = zones
    return {"idle": idle, CONF_ALLOW_COMMAND: permission}


def readonly_zone(
    model: HybridClimateConfig, options: Mapping[str, Any], zone_id: str,
) -> dict[str, Any]:
    """Describe a zone's active regulation type and device IDs."""
    regulation = model.zones[zone_id].regulation
    value = None if regulation is None else {
        "type": regulation.type, "devices": list(regulation.devices),
    }
    stored = options.get(CONF_UI_CONFIG, {}).get(CONF_ZONES, {}).get(zone_id, {})
    source = SOURCE_UI_CONFIG if CONF_REGULATION in stored else SOURCE_DEFAULT
    return {CONF_REGULATION: _entry(value, source, "object", CONF_REGULATION)}


def compressor_groups(model: HybridClimateConfig, zone_id: str | None) -> dict[str, Any]:
    """List complete compressor groups touching the selected zone."""
    allowed = set(model.zones[zone_id].get_all_device_ids()) if zone_id else None
    groups: dict[str, list[str]] = {}
    for device_id, device in model.devices.items():
        if device.compressor_group:
            groups.setdefault(device.compressor_group, []).append(device_id)
    return {group_id: {"devices": sorted(members)} for group_id, members in groups.items()
            if allowed is None or allowed.intersection(members)}
