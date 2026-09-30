"""Purpose: Project noneditable active configuration and compressor groups.

Key dependencies: Loaded models and the prepared options snapshot.
Used by: Agent API get_config service.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ..const import (
    CONF_ALLOW_COMMAND, CONF_CAPABILITIES, CONF_DEVICE, CONF_DEVICES, CONF_ENTITY_ID, CONF_IDLE_ACTION,
    CONF_IDLE_SETBACK, CONF_NEVER_COOL_BELOW, CONF_NEVER_HEAT_ABOVE, CONF_OUTDOOR_RESET,
    CONF_OUTDOOR_SENSOR, CONF_OUTDOOR_SENSORS, CONF_REGULATION, CONF_SENSORS, CONF_SETTINGS,
    CONF_UI_CONFIG, CONF_WEIGHTS, IDLE_ACTIONS, CONF_UI_GLOBAL, CONF_ZONES,
    OUTDOOR_LOCKOUT_HYSTERESIS,
)
from ..models import HybridClimateConfig, ZoneConfig
from .const import (
    MALFORMED_STAGE_STORAGE_WARNING, OUTDOOR_THRESHOLDS_FIELD, READ_ONLY_DESCRIPTIONS,
    READ_ONLY_TEMPERATURE_UNIT, SENSORS_WEIGHTS_FIELD, SOURCE_AUTO_CREATED, SOURCE_DEFAULT,
    SOURCE_UI, SOURCE_UI_CONFIG, SOURCE_YAML,
)

_LOGGER = logging.getLogger(__name__)


def _entry(value: Any, source: str, kind: str, description: str) -> dict[str, Any]:
    return {"value": value, "source": source, "type": kind,
            "description": READ_ONLY_DESCRIPTIONS[description], "writable": False}


def _outdoor_thresholds(
    never_heat_above: float | None, never_cool_below: float | None,
) -> dict[str, Any]:
    """Describe outdoor lockout limits, mirroring conflict_resolver's release math exactly.

    Release limits use conflict_resolver's own comparison operators (~150-180):
    heating releases once outdoor temp drops to or below never_heat_above minus the
    hysteresis (hence `_at_or_below`); cooling releases once it rises to or above
    never_cool_below plus the hysteresis (hence `_at_or_above`).
    """
    heat_resume = (
        round(never_heat_above - OUTDOOR_LOCKOUT_HYSTERESIS, 2)
        if never_heat_above is not None else None
    )
    cool_resume = (
        round(never_cool_below + OUTDOOR_LOCKOUT_HYSTERESIS, 2)
        if never_cool_below is not None else None
    )
    band = None
    if (never_heat_above is not None and never_cool_below is not None
            and never_heat_above < never_cool_below):
        band = {"low": never_heat_above, "high": never_cool_below}
    return {
        "never_heat_above": never_heat_above,
        "heat_resume_at_or_below": heat_resume,
        "never_cool_below": never_cool_below,
        "cool_resume_at_or_above": cool_resume,
        "hysteresis_degrees": OUTDOOR_LOCKOUT_HYSTERESIS,
        "no_operation_band": band,
    }


def _effective_zone_limits(
    model: HybridClimateConfig, zone: ZoneConfig,
) -> tuple[float | None, float | None]:
    """Mirror conflict_resolver's global/zone-override selection (~104-121)."""
    global_reset = model.conflicts.outdoor_reset
    zone_reset = zone.settings.outdoor_reset
    never_heat_above = (
        zone_reset.never_heat_above if zone_reset and zone_reset.heat_override_set
        else global_reset.never_heat_above
    )
    never_cool_below = (
        zone_reset.never_cool_below if zone_reset and zone_reset.cool_override_set
        else global_reset.never_cool_below
    )
    return never_heat_above, never_cool_below


def readonly_global(model: HybridClimateConfig, options: Mapping[str, Any]) -> dict[str, Any]:
    """Describe the active outdoor sensor(s) and effective lockout thresholds."""
    global_options = options.get(CONF_UI_CONFIG, {}).get(CONF_UI_GLOBAL, {})
    source = SOURCE_UI_CONFIG if CONF_OUTDOOR_SENSOR in global_options or CONF_OUTDOOR_SENSORS in global_options else SOURCE_DEFAULT
    threshold_source = (
        SOURCE_UI_CONFIG
        if CONF_NEVER_HEAT_ABOVE in global_options or CONF_NEVER_COOL_BELOW in global_options
        else SOURCE_DEFAULT
    )
    global_reset = model.conflicts.outdoor_reset
    return {
        CONF_OUTDOOR_SENSOR: _entry(model.outdoor_sensor, source, "entity_id", CONF_OUTDOOR_SENSOR),
        CONF_OUTDOOR_SENSORS: _entry(list(model.outdoor_sensors), source, "entity_ids", CONF_OUTDOOR_SENSORS),
        OUTDOOR_THRESHOLDS_FIELD: _entry(
            _outdoor_thresholds(global_reset.never_heat_above, global_reset.never_cool_below),
            threshold_source, "object", OUTDOOR_THRESHOLDS_FIELD,
        ),
    }


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
    # UI entries are explicit; a referenced device without one was synthesized by
    # ensure_devices_exist. A remaining loaded device originated outside UI stages.
    source = (SOURCE_UI if device.entity_id in options.get(CONF_UI_CONFIG, {}).get(CONF_DEVICES, {})
              else SOURCE_AUTO_CREATED if any(device_id in zone.get_all_device_ids() for zone in model.zones.values())
              else SOURCE_YAML)
    return {
        "idle": idle, CONF_ALLOW_COMMAND: permission,
        CONF_CAPABILITIES: _entry([item.value for item in device.capabilities], source, "list", CONF_CAPABILITIES),
        "capabilities_source": _entry(source, source, "enum", "capabilities_source"),
    }


def readonly_zone(
    model: HybridClimateConfig, options: Mapping[str, Any], zone_id: str,
) -> dict[str, Any]:
    """Describe a zone's active regulation type, device IDs, and sensor weights."""
    zone = model.zones[zone_id]
    regulation = zone.regulation
    value = None if regulation is None else {
        "type": regulation.type, "devices": list(regulation.devices),
        "ignored_devices": list(regulation.ignored_devices),
    }
    stored = options.get(CONF_UI_CONFIG, {}).get(CONF_ZONES, {}).get(zone_id, {})
    source = SOURCE_UI_CONFIG if CONF_REGULATION in stored else SOURCE_DEFAULT
    # Weights are configured only through the options UI wizard (Task 4), never via
    # set_config; report the effective weight for every configured indoor sensor.
    weights = {entity_id: zone.sensors.weight_for(entity_id) for entity_id in zone.sensors.indoor}
    weights_source = (
        SOURCE_UI_CONFIG if CONF_WEIGHTS in stored.get(CONF_SENSORS, {}) else SOURCE_DEFAULT
    )
    threshold_source = (
        SOURCE_UI_CONFIG if CONF_OUTDOOR_RESET in stored.get(CONF_SETTINGS, {}) else SOURCE_DEFAULT
    )
    never_heat_above, never_cool_below = _effective_zone_limits(model, zone)
    return {
        CONF_REGULATION: _entry(value, source, "object", CONF_REGULATION),
        SENSORS_WEIGHTS_FIELD: _entry(weights, weights_source, "object", SENSORS_WEIGHTS_FIELD),
        OUTDOOR_THRESHOLDS_FIELD: _entry(
            _outdoor_thresholds(never_heat_above, never_cool_below),
            threshold_source, "object", OUTDOOR_THRESHOLDS_FIELD,
        ),
    }


def compressor_groups(model: HybridClimateConfig, zone_id: str | None) -> dict[str, Any]:
    """List complete compressor groups touching the selected zone."""
    allowed = set(model.zones[zone_id].get_all_device_ids()) if zone_id else None
    groups: dict[str, list[str]] = {}
    for device_id, device in model.devices.items():
        if device.compressor_group:
            groups.setdefault(device.compressor_group, []).append(device_id)
    return {group_id: {"devices": sorted(members)} for group_id, members in groups.items()
            if allowed is None or allowed.intersection(members)}
