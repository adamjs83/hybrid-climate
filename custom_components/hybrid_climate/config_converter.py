"""UI config <-> YAML config format conversion.

Handles bidirectional translation between the UI config format (stored in
config_entry.options) and the YAML format consumed by config_loader.load_config().

Key dependencies: config_loader.py (load_config), const.py
Used by: __init__.py (async_setup_entry)
"""
# pyright: reportMissingImports=false
from __future__ import annotations

import logging
from typing import Any

from .const import (
    CONF_DEVICES,
    CONF_ENTITY_ID,
    CONF_IDLE,
    CONF_IDLE_ACTION,
    CONF_IDLE_SETBACK,
    CONF_MASTER_NAME,
    CONF_NEVER_COOL_BELOW,
    CONF_NEVER_HEAT_ABOVE,
    CONF_LOCKOUT_HEAT_FLOOR,
    CONF_OCCUPANCY_ENTITY,
    CONF_OUTDOOR_SENSOR,
    CONF_OUTDOOR_SENSORS,
    CONF_LEGACY_RATE_SENSOR,
    CONF_TOU_RATE_SENSOR,
    CONF_ZONES,
    DEFAULT_IDLE_ACTION,
    DEFAULT_IDLE_SETBACK,
    DEFAULT_TOU_PRE_CONDITION_MINUTES,
    DEFAULT_TOU_RELAXATION_AMOUNT,
)

_LOGGER = logging.getLogger(__name__)


def build_config_from_ui(ui_config: dict[str, Any]) -> dict[str, Any]:
    """Build a config dict from UI config that can be passed to load_config().

    UI config is the source of truth. This converts UI format to the dict
    format expected by config_loader.CONFIG_SCHEMA.
    """
    global_conf = ui_config.get("global", {})
    ui_devices = ui_config.get("devices", {})
    ui_zones = ui_config.get("zones", {})
    ui_heat_sources = ui_config.get("heat_sources", {})
    ui_modes = ui_config.get("modes", {})
    ui_mutex = ui_config.get("device_mutex", [])

    # Build devices dict (keyed by device_id, not entity_id)
    devices = {}
    for entity_id, dev_conf in ui_devices.items():
        device_id = entity_id.replace("climate.", "").replace(".", "_")
        devices[device_id] = {
            CONF_ENTITY_ID: entity_id,
            "capabilities": dev_conf.get("capabilities", ["heat"]),
        }
        for key in ("compressor_group", "min_compressor_runtime", "min_compressor_off_time"):
            if dev_conf.get(key) is not None and dev_conf.get(key) != "":
                devices[device_id][key] = dev_conf[key]
        # Add idle config if present
        action = dev_conf.get(CONF_IDLE_ACTION)
        setback = dev_conf.get(CONF_IDLE_SETBACK)
        if action:
            devices[device_id][CONF_IDLE] = {
                CONF_IDLE_ACTION: action,
                CONF_IDLE_SETBACK: setback if setback is not None else DEFAULT_IDLE_SETBACK,
            }

    # Build zones dict
    zones = {}
    for zone_id, zone_conf in ui_zones.items():
        converted_zone = convert_ui_zone_to_yaml(zone_conf, devices)
        zones[zone_id] = converted_zone
        # Ensure devices referenced in stages exist
        ensure_devices_exist(converted_zone, devices, ui_devices)

    # Build heat sources dict
    heat_sources = {}
    for source_id, source_conf in ui_heat_sources.items():
        converted_source = convert_ui_heat_source_to_yaml(source_conf, devices)
        heat_sources[source_id] = converted_source

    # Build master config
    master = {
        "name": global_conf.get(CONF_MASTER_NAME, "Home HVAC"),
    }
    if global_conf.get(CONF_OCCUPANCY_ENTITY):
        master[CONF_OCCUPANCY_ENTITY] = global_conf[CONF_OCCUPANCY_ENTITY]

    # Build modes
    if ui_modes:
        master["modes"] = {}
        for mode_name, mode_conf in ui_modes.items():
            master["modes"][mode_name] = mode_conf

    # Build conflicts config
    conflicts = {}

    # Outdoor reset
    outdoor_reset = {}
    if global_conf.get(CONF_NEVER_HEAT_ABOVE) is not None:
        outdoor_reset[CONF_NEVER_HEAT_ABOVE] = global_conf[CONF_NEVER_HEAT_ABOVE]
    if global_conf.get(CONF_NEVER_COOL_BELOW) is not None:
        outdoor_reset[CONF_NEVER_COOL_BELOW] = global_conf[CONF_NEVER_COOL_BELOW]
    if outdoor_reset:
        conflicts["outdoor_reset"] = outdoor_reset

    # Device mutex
    if ui_mutex:
        conflicts["device_mutex"] = [
            {
                "when": {
                    "device": entity_id_to_device_id(rule["device"], devices),
                    "mode": rule.get("mode", "heat"),
                    "for_zone": rule.get("for_zone", ""),
                },
                "then": {
                    "block_heat": rule.get("block_heat", []),
                    "block_cool": rule.get("block_cool", []),
                    "blocked_devices_heat": rule.get("blocked_devices_heat", []),
                    "blocked_devices_cool": rule.get("blocked_devices_cool", []),
                }
            }
            for rule in ui_mutex
            if rule.get("device") and rule.get("for_zone")
        ]

    # Build final config
    result = {
        "master": master,
        CONF_DEVICES: devices,
        CONF_ZONES: zones,
    }
    if CONF_LOCKOUT_HEAT_FLOOR in global_conf:
        result[CONF_LOCKOUT_HEAT_FLOOR] = global_conf[CONF_LOCKOUT_HEAT_FLOOR]

    if CONF_OUTDOOR_SENSORS in global_conf:
        result[CONF_OUTDOOR_SENSORS] = global_conf[CONF_OUTDOOR_SENSORS]
    elif global_conf.get(CONF_OUTDOOR_SENSOR):
        result[CONF_OUTDOOR_SENSOR] = global_conf[CONF_OUTDOOR_SENSOR]

    rate_sensor = global_conf.get(CONF_TOU_RATE_SENSOR, global_conf.get(CONF_LEGACY_RATE_SENSOR))
    if rate_sensor:
        result[CONF_TOU_RATE_SENSOR] = rate_sensor

    if conflicts:
        result["conflicts"] = conflicts

    if heat_sources:
        result["heat_sources"] = heat_sources

    _LOGGER.debug(
        "Built config from UI: %d devices, %d zones, %d heat sources",
        len(devices), len(zones), len(heat_sources)
    )

    return result


def entity_id_to_device_id(entity_id: str, devices: dict[str, Any]) -> str:
    """Convert entity_id to device_id, looking up in devices dict first."""
    for device_id, dev_conf in devices.items():
        if dev_conf.get(CONF_ENTITY_ID) == entity_id:
            return device_id
    # Fallback: derive from entity_id
    return entity_id.replace("climate.", "").replace(".", "_")


def merge_new_yaml_settings(ui_config: dict[str, Any], yaml_config: dict[str, Any]) -> dict[str, Any]:
    """Merge new YAML settings into existing UI config.

    This handles the case where YAML was imported previously but new settings
    were added to YAML afterward (e.g., outdoor_reset, opportunistic).

    Only merges settings that don't exist in UI config - UI takes precedence.
    Also ensures *_override_set flags are present on outdoor_reset.
    """
    _LOGGER.debug("merge_new_yaml_settings called")
    ui_zones = ui_config.get("zones", {})
    yaml_zones = yaml_config.get(CONF_ZONES, {})
    _LOGGER.debug("UI zones: %s, YAML zones: %s", list(ui_zones.keys()), list(yaml_zones.keys()))
    changed = False

    for zone_id, yaml_zone in yaml_zones.items():
        if zone_id not in ui_zones:
            _LOGGER.debug("Zone %s in YAML but not in UI zones, skipping merge", zone_id)
            continue

        ui_zone = ui_zones[zone_id]
        yaml_settings = yaml_zone.get("settings", {})
        ui_settings = ui_zone.get("settings", {})

        # Merge outdoor_reset if in YAML but not in UI
        # Check if key exists (not just value truthy) because value could be {"never_cool_below": null}
        if "outdoor_reset" in yaml_settings and "outdoor_reset" not in ui_settings:
            if "settings" not in ui_zone:
                ui_zone["settings"] = {}
            # Add override_set flags
            yaml_outdoor_reset = yaml_settings["outdoor_reset"] or {}
            outdoor_reset = dict(yaml_outdoor_reset)
            outdoor_reset["heat_override_set"] = CONF_NEVER_HEAT_ABOVE in yaml_outdoor_reset
            outdoor_reset["cool_override_set"] = CONF_NEVER_COOL_BELOW in yaml_outdoor_reset
            ui_zone["settings"]["outdoor_reset"] = outdoor_reset
            _LOGGER.debug("Merged outdoor reset from YAML for zone %s", zone_id)
            changed = True

        # Ensure *_override_set flags are present if outdoor_reset exists in UI but lacks flags
        # This handles zones imported before the flags were added
        elif "outdoor_reset" in ui_settings:
            ui_outdoor_reset = ui_settings["outdoor_reset"] or {}
            if "heat_override_set" not in ui_outdoor_reset or "cool_override_set" not in ui_outdoor_reset:
                # Rebuild from YAML if available, otherwise infer from existing keys
                yaml_outdoor_reset = yaml_settings.get("outdoor_reset", {}) or {}
                outdoor_reset = dict(ui_outdoor_reset)
                # Use YAML to determine flags if available
                if yaml_outdoor_reset:
                    outdoor_reset["heat_override_set"] = CONF_NEVER_HEAT_ABOVE in yaml_outdoor_reset
                    outdoor_reset["cool_override_set"] = CONF_NEVER_COOL_BELOW in yaml_outdoor_reset
                else:
                    # Infer from existing UI keys
                    outdoor_reset["heat_override_set"] = CONF_NEVER_HEAT_ABOVE in ui_outdoor_reset
                    outdoor_reset["cool_override_set"] = CONF_NEVER_COOL_BELOW in ui_outdoor_reset
                ui_settings["outdoor_reset"] = outdoor_reset
                _LOGGER.debug("Added outdoor reset override flags for zone %s", zone_id)
                changed = True

        # Merge opportunistic if in YAML but not in UI
        if yaml_zone.get("opportunistic") and not ui_zone.get("opportunistic"):
            ui_zone["opportunistic"] = yaml_zone["opportunistic"]
            _LOGGER.debug("Merged opportunistic settings from YAML for zone %s", zone_id)
            changed = True

    if changed:
        _LOGGER.info("Merged new YAML settings into UI config")

    return ui_config


def import_yaml_to_ui_config(yaml_config: dict[str, Any]) -> dict[str, Any]:
    """Convert YAML config to UI config format for storage in entry.options.

    This is a one-time import that converts YAML format to UI format.
    After import, UI config becomes the source of truth.

    YAML format uses device_ids as keys and references.
    UI format uses entity_ids as keys and references.
    """
    ui_config: dict[str, Any] = {
        "_yaml_imported": True,
        "_version": 1,
    }

    yaml_devices = yaml_config.get(CONF_DEVICES, {})
    yaml_zones = yaml_config.get(CONF_ZONES, {})
    yaml_master = yaml_config.get("master", {})
    yaml_conflicts = yaml_config.get("conflicts", {})
    yaml_heat_sources = yaml_config.get("heat_sources", {})

    # Build device_id -> entity_id mapping
    device_id_to_entity: dict[str, str] = {}
    for device_id, dev_conf in yaml_devices.items():
        entity_id = dev_conf.get(CONF_ENTITY_ID, f"climate.{device_id}")
        device_id_to_entity[device_id] = entity_id

    # Convert devices (keyed by entity_id in UI)
    ui_devices = {}
    for device_id, dev_conf in yaml_devices.items():
        entity_id = dev_conf.get(CONF_ENTITY_ID, f"climate.{device_id}")
        ui_devices[entity_id] = {
            CONF_ENTITY_ID: entity_id,
            "capabilities": dev_conf.get("capabilities", ["heat"]),
        }
        for key in ("compressor_group", "min_compressor_runtime", "min_compressor_off_time"):
            if key in dev_conf:
                ui_devices[entity_id][key] = dev_conf[key]
        # Add idle config
        idle_conf = dev_conf.get(CONF_IDLE, {})
        if idle_conf:
            ui_devices[entity_id][CONF_IDLE_ACTION] = idle_conf.get(CONF_IDLE_ACTION, DEFAULT_IDLE_ACTION)
            ui_devices[entity_id][CONF_IDLE_SETBACK] = idle_conf.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK)

    if ui_devices:
        ui_config["devices"] = ui_devices

    # Convert zones
    ui_zones = {}
    for zone_id, zone_conf in yaml_zones.items():
        ui_zone = convert_yaml_zone_to_ui(zone_conf, device_id_to_entity)
        ui_zones[zone_id] = ui_zone

    if ui_zones:
        ui_config["zones"] = ui_zones

    # Convert global settings
    global_conf = {}
    if yaml_master.get("name"):
        global_conf[CONF_MASTER_NAME] = yaml_master["name"]
    if yaml_master.get(CONF_OCCUPANCY_ENTITY):
        global_conf[CONF_OCCUPANCY_ENTITY] = yaml_master[CONF_OCCUPANCY_ENTITY]
    if CONF_OUTDOOR_SENSORS in yaml_config:
        global_conf[CONF_OUTDOOR_SENSORS] = list(yaml_config[CONF_OUTDOOR_SENSORS])
    elif yaml_config.get(CONF_OUTDOOR_SENSOR):
        global_conf[CONF_OUTDOOR_SENSOR] = yaml_config[CONF_OUTDOOR_SENSOR]
    rate_sensor = yaml_config.get(CONF_TOU_RATE_SENSOR, yaml_config.get(CONF_LEGACY_RATE_SENSOR))
    if rate_sensor:
        global_conf[CONF_TOU_RATE_SENSOR] = rate_sensor

    if CONF_LOCKOUT_HEAT_FLOOR in yaml_config:
        global_conf[CONF_LOCKOUT_HEAT_FLOOR] = yaml_config[CONF_LOCKOUT_HEAT_FLOOR]

    # Outdoor reset
    outdoor_reset = yaml_conflicts.get("outdoor_reset", {})
    if outdoor_reset.get(CONF_NEVER_HEAT_ABOVE) is not None:
        global_conf[CONF_NEVER_HEAT_ABOVE] = outdoor_reset[CONF_NEVER_HEAT_ABOVE]
    if outdoor_reset.get(CONF_NEVER_COOL_BELOW) is not None:
        global_conf[CONF_NEVER_COOL_BELOW] = outdoor_reset[CONF_NEVER_COOL_BELOW]

    if global_conf:
        ui_config["global"] = global_conf

    # Convert modes
    yaml_modes = yaml_master.get("modes", {})
    if yaml_modes:
        ui_config["modes"] = yaml_modes

    # Convert heat sources
    ui_heat_sources = {}
    for source_id, source_conf in yaml_heat_sources.items():
        # Convert device_ids to entity_ids
        device_entity_ids = [
            device_id_to_entity.get(did, f"climate.{did}")
            for did in source_conf.get("devices", [])
        ]
        ui_heat_sources[source_id] = {
            "name": source_conf.get("name", source_id),
            "devices": device_entity_ids,
        }

    if ui_heat_sources:
        ui_config["heat_sources"] = ui_heat_sources

    # Convert device mutex rules
    yaml_mutex = yaml_conflicts.get("device_mutex", [])
    if yaml_mutex:
        ui_mutex = []
        for rule in yaml_mutex:
            when = rule.get("when", {})
            then = rule.get("then", {})
            device_id = when.get("device", "")
            entity_id = device_id_to_entity.get(device_id, f"climate.{device_id}")
            ui_mutex.append({
                "device": entity_id,
                "mode": when.get("mode", "heat"),
                "for_zone": when.get("for_zone", ""),
                "block_heat": then.get("block_heat", []),
                "block_cool": then.get("block_cool", []),
                "blocked_devices_heat": then.get("blocked_devices_heat", []),
                "blocked_devices_cool": then.get("blocked_devices_cool", []),
            })
        ui_config["device_mutex"] = ui_mutex

    _LOGGER.info(
        "Imported YAML config to UI: %d devices, %d zones, %d heat sources",
        len(ui_devices), len(ui_zones), len(ui_heat_sources)
    )

    return ui_config


def convert_yaml_zone_to_ui(
    zone_conf: dict[str, Any], device_id_to_entity: dict[str, str]
) -> dict[str, Any]:
    """Convert a YAML zone config to UI format."""
    settings = dict(zone_conf.get("settings", {}))  # Make a copy

    # Add *_override_set flags to outdoor_reset if present
    # These flags indicate that the user explicitly set the value (even to None/null)
    if "outdoor_reset" in settings:
        outdoor_reset = dict(settings["outdoor_reset"] or {})
        # Check if keys exist in the original data (not just truthy)
        outdoor_reset["heat_override_set"] = outdoor_reset.get("heat_override_set", CONF_NEVER_HEAT_ABOVE in outdoor_reset)
        outdoor_reset["cool_override_set"] = outdoor_reset.get("cool_override_set", CONF_NEVER_COOL_BELOW in outdoor_reset)
        settings["outdoor_reset"] = outdoor_reset
    ui_zone = {
        "name": zone_conf.get("name", "Zone"),
        "sensors": zone_conf.get("sensors", {"indoor": [], "aggregation": "average"}),
        "setpoints": zone_conf.get("setpoints", {"default": 72}),
        "settings": settings,
    }
    if zone_conf.get("openings"):
        ui_zone["openings"] = dict(zone_conf["openings"])

    # Convert heat stages
    heat_stages = []
    for stage in zone_conf.get("heat_stages", []):
        converted = convert_yaml_stage_to_ui(stage, device_id_to_entity)
        if converted:
            heat_stages.append(converted)
    if heat_stages:
        ui_zone["heat_stages"] = heat_stages

    # Convert cool stages
    cool_stages = []
    for stage in zone_conf.get("cool_stages", []):
        converted = convert_yaml_stage_to_ui(stage, device_id_to_entity)
        if converted:
            cool_stages.append(converted)
    if cool_stages:
        ui_zone["cool_stages"] = cool_stages

    # Copy regulation and opportunistic if present
    if zone_conf.get("regulation"):
        # Convert device_ids to entity_ids in regulation
        reg = dict(zone_conf["regulation"])
        if "devices" in reg:
            reg["devices"] = [
                device_id_to_entity.get(did, f"climate.{did}")
                for did in reg["devices"]
            ]
        ui_zone["regulation"] = reg

    if zone_conf.get("opportunistic"):
        ui_zone["opportunistic"] = zone_conf["opportunistic"]

    if zone_conf.get("tou"):
        ui_zone["tou"] = zone_conf["tou"]

    return ui_zone


def convert_yaml_stage_to_ui(
    stage: dict[str, Any], device_id_to_entity: dict[str, str]
) -> dict[str, Any] | None:
    """Convert a YAML stage config to UI format."""
    devices = stage.get("devices", [])
    if not devices:
        return None

    # Convert device references to entity_ids
    ui_devices = []
    for dev in devices:
        if isinstance(dev, dict):
            device_id = dev.get("device", "")
            allow_command = dev.get("allow_command", False)
        else:
            device_id = str(dev)
            allow_command = False

        entity_id = device_id_to_entity.get(device_id, f"climate.{device_id}")
        ui_devices.append({
            "entity_id": entity_id,
            "allow_command": allow_command,
        })

    result = {
        "stage": stage.get("stage", 1),
        "devices": ui_devices,
        "threshold": stage.get("threshold", 1.0),
    }

    if stage.get("time_escalation"):
        result["time_escalation"] = stage["time_escalation"]

    conditions = stage.get("conditions", {})
    conditions = {
        key: conditions.get(key, stage.get(key))
        for key in ("outdoor_temp_min", "outdoor_temp_max")
        if conditions.get(key, stage.get(key)) is not None
    }
    if conditions:
        result["conditions"] = conditions.copy()

    return result


def convert_ui_heat_source_to_yaml(
    ui_source: dict[str, Any], yaml_devices: dict[str, Any]
) -> dict[str, Any]:
    """Convert UI heat source format to YAML-compatible format."""
    # UI stores entity_ids, YAML needs device_ids
    device_ids = []
    for entity_id in ui_source.get("devices", []):
        device_id = get_or_create_device_id(entity_id, yaml_devices)
        device_ids.append(device_id)

        # Ensure device entry exists
        if device_id not in yaml_devices:
            yaml_devices[device_id] = {
                "entity_id": entity_id,
                "capabilities": ["heat"],  # Heat sources are for heating
            }

    return {
        "name": ui_source.get("name", "Heat Source"),
        "devices": device_ids,
    }


def convert_ui_zone_to_yaml(
    ui_zone: dict[str, Any], yaml_devices: dict[str, Any]
) -> dict[str, Any]:
    """Convert UI zone format to YAML-compatible format."""
    settings = ui_zone.get("settings", {})
    zone = {
        "name": ui_zone.get("name", "Zone"),
        "sensors": ui_zone.get("sensors", {"indoor": [], "aggregation": "average"}),
        "setpoints": ui_zone.get("setpoints", {"default": 72}),
        "settings": settings,
    }
    if ui_zone.get("openings"):
        zone["openings"] = dict(ui_zone["openings"])

    # Convert heat_stages - UI uses entity_ids, YAML uses device IDs
    heat_stages = []
    for stage in ui_zone.get("heat_stages", []):
        converted_stage = convert_ui_stage_to_yaml(stage, yaml_devices)
        if converted_stage:
            heat_stages.append(converted_stage)
    if heat_stages:
        zone["heat_stages"] = heat_stages

    # Convert cool_stages
    cool_stages = []
    for stage in ui_zone.get("cool_stages", []):
        converted_stage = convert_ui_stage_to_yaml(stage, yaml_devices)
        if converted_stage:
            cool_stages.append(converted_stage)
    if cool_stages:
        zone["cool_stages"] = cool_stages

    # Copy regulation config if present, converting entity_ids to device_ids
    if ui_zone.get("regulation"):
        reg = dict(ui_zone["regulation"])
        if "devices" in reg:
            # Convert entity_ids back to device_ids
            reg["devices"] = [
                get_or_create_device_id(entity_id, yaml_devices)
                for entity_id in reg["devices"]
            ]
        zone["regulation"] = reg

    # Copy opportunistic config if present
    if ui_zone.get("opportunistic"):
        zone["opportunistic"] = ui_zone["opportunistic"]

    # TOU zone config
    ui_tou = ui_zone.get("tou")
    if ui_tou:
        tou_block = {}
        if "heat" in ui_tou:
            tou_block["heat"] = {
                "pre_condition_minutes": ui_tou["heat"].get("pre_condition_minutes", DEFAULT_TOU_PRE_CONDITION_MINUTES),
                "relaxation_amount": ui_tou["heat"].get("relaxation_amount", DEFAULT_TOU_RELAXATION_AMOUNT),
            }
        if "cool" in ui_tou:
            tou_block["cool"] = {
                "pre_condition_minutes": ui_tou["cool"].get("pre_condition_minutes", DEFAULT_TOU_PRE_CONDITION_MINUTES),
                "relaxation_amount": ui_tou["cool"].get("relaxation_amount", DEFAULT_TOU_RELAXATION_AMOUNT),
            }
        if tou_block:
            zone["tou"] = tou_block

    return zone


def convert_ui_stage_to_yaml(
    stage: dict[str, Any], yaml_devices: dict[str, Any]
) -> dict[str, Any] | None:
    """Convert UI stage format to YAML format."""
    devices = stage.get("devices", [])
    if not devices:
        return None

    # Build device list - convert entity_ids to device references
    device_refs = []
    for device in devices:
        if isinstance(device, dict):
            # Already in object format
            entity_id = device.get("entity_id") or device.get("device") or ""
            allow_command = device.get("allow_command", False)
        else:
            # String entity_id
            entity_id = str(device) if device else ""
            allow_command = False

        if not entity_id:
            continue

        # Find or create device ID for this entity
        device_id = get_or_create_device_id(entity_id, yaml_devices)
        device_refs.append({"device": device_id, "allow_command": allow_command})

    result = {
        "stage": stage.get("stage", 1),
        "devices": device_refs,
        "threshold": stage.get("threshold", 1.0),
    }

    if stage.get("time_escalation"):
        result["time_escalation"] = stage["time_escalation"]

    # Add conditions if present
    # Saved UI stages use conditions; older UI stages stored limits at top level.
    stored_conditions = stage.get("conditions") or {}
    conditions = {}
    for key in ("outdoor_temp_min", "outdoor_temp_max"):
        value = stored_conditions.get(key, stage.get(key))
        if value is not None:
            conditions[key] = value
    if conditions:
        result["conditions"] = conditions

    return result


def get_or_create_device_id(
    entity_id: str, yaml_devices: dict[str, Any]
) -> str:
    """Get existing device ID for entity or create a new one."""
    # Check if entity already has a device entry
    for device_id, device_conf in yaml_devices.items():
        if device_conf.get("entity_id") == entity_id:
            return device_id

    # Create new device ID from entity_id
    # climate.living_room_thermostat -> living_room_thermostat
    device_id = entity_id.replace("climate.", "").replace(".", "_")
    return device_id


def ensure_devices_exist(
    zone_conf: dict[str, Any],
    yaml_devices: dict[str, Any],
    ui_devices: dict[str, Any] | None = None,
) -> None:
    """Ensure all devices referenced in zone stages exist in device dict.

    If ui_devices is provided, use its capabilities info for new devices.
    """
    ui_devices = ui_devices or {}

    for stage in zone_conf.get("heat_stages", []) + zone_conf.get("cool_stages", []):
        for device_ref in stage.get("devices", []):
            if isinstance(device_ref, dict):
                device_id = device_ref.get("device")
            else:
                device_id = device_ref

            if not device_id:
                continue

            device_id = str(device_id)

            if device_id not in yaml_devices:
                # Need to find the entity_id - check if we stored it during conversion
                # For now, assume device_id is derived from entity_id
                entity_id = f"climate.{device_id}"

                # Check if UI has capabilities info for this device
                ui_dev_conf = ui_devices.get(entity_id, {})
                capabilities = ui_dev_conf.get("capabilities", ["heat", "cool"])

                yaml_devices[device_id] = {
                    "entity_id": entity_id,
                    "capabilities": capabilities,
                }
                _LOGGER.debug("Auto-created device entry: %s -> %s (caps: %s)", device_id, entity_id, capabilities)
