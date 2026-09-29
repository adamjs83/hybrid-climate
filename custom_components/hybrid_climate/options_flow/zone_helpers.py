"""Zone configuration data helpers.

Handles loading, saving, and transforming zone configuration data
between the options flow UI and the stored config format.

Key dependencies: options_flow/base.py (BaseFlowMixin)
Used by: options_flow/zone_steps.py (called from step methods)
"""
from __future__ import annotations

from typing import Any

from homeassistant.data_entry_flow import FlowResult

from ..const import (
    AGGREGATION_AVERAGE,
    CONF_AGGREGATION,
    CONF_DEVICES,
    CONF_HYSTERESIS,
    CONF_MIN_RUNTIME,
    CONF_OPENINGS,
    CONF_OPENING_ENTITIES,
    CONF_OPEN_DELAY,
    CONF_CLOSE_DELAY,
    CONF_NAME,
    CONF_OCCUPANCY_ENTITY,
    CONF_SENSORS,
    CONF_SMOOTHING_SAMPLES,
    CONF_WEIGHTS,
    CONF_TOU,
    CONF_UI_VERSION,
    CONF_ZONES,
    DEFAULT_BALANCE_POINT,
    DEFAULT_HYSTERESIS,
    DEFAULT_KP,
    DEFAULT_KI,
    DEFAULT_K_EXT,
    DEFAULT_MIN_RUNTIME,
    DEFAULT_OPEN_DELAY,
    DEFAULT_CLOSE_DELAY,
    DEFAULT_OFFSET_MAX,
    DEFAULT_SMOOTHING_SAMPLES,
    REGULATION_PI,
)


class ZoneHelpersMixin:
    """Mixin providing zone data helper methods."""

    def _extract_entity_ids(self, devices: list) -> list[str]:
        """Extract entity_ids from device list.

        Devices can be dicts with entity_id key or strings.
        """
        result = []
        for d in devices:
            if isinstance(d, dict):
                entity_id = d.get("entity_id", "")
                if entity_id:
                    result.append(entity_id)
            elif isinstance(d, str) and d:
                result.append(d)
        return result

    def _get_all_stage_device_ids(self) -> list[str]:
        """Get the union of all device entity_ids across heat and cool stages.

        Used for the allow_command selector on the zone settings step.
        Returns deduplicated list preserving first-seen order.
        """
        wip = self._zone_wip or {}
        seen: set[str] = set()
        result: list[str] = []
        for stage_key in ("heat_stages", "cool_stages"):
            for stage in wip.get(stage_key, []):
                for eid in self._extract_entity_ids(stage.get("devices", [])):
                    if eid not in seen:
                        seen.add(eid)
                        result.append(eid)
        return result

    def _get_existing_allow_command_ids(self) -> list[str]:
        """Get entity_ids that currently have allow_command=True across all stages.

        Used to pre-populate the allow_command selector default.
        """
        wip = self._zone_wip or {}
        result: set[str] = set()
        for stage_key in ("heat_stages", "cool_stages"):
            for stage in wip.get(stage_key, []):
                for d in stage.get("devices", []):
                    if isinstance(d, dict) and d.get("allow_command", False):
                        entity_id = d.get("entity_id", "")
                        if entity_id:
                            result.add(entity_id)
        return list(result)

    def _propagate_allow_command(self, allow_cmd_entities: set[str]) -> None:
        """Propagate allow_command selection to every device instance across all stages.

        One toggle per device applies consistently across all stage occurrences.
        """
        wip = self._zone_wip or {}
        for stage_key in ("heat_stages", "cool_stages"):
            for stage in wip.get(stage_key, []):
                for dev in stage.get("devices", []):
                    if isinstance(dev, dict):
                        dev["allow_command"] = dev.get("entity_id", "") in allow_cmd_entities

    def _load_zone_for_edit(self, zone_id: str) -> dict[str, Any]:
        """Load existing zone config for editing.

        IMPORTANT: Preserves all existing values including setpoints and
        allow_command flags so that editing a zone doesn't lose config.
        """
        yaml_zones = self._get_yaml_config().get(CONF_ZONES, {})
        ui_zones = self._get_ui_config().get(CONF_ZONES, {})

        # UI config takes precedence over YAML
        zone_conf = ui_zones.get(zone_id, yaml_zones.get(zone_id, {}))

        # Parse sensors
        sensors = zone_conf.get(CONF_SENSORS, {})
        indoor_sensors = sensors.get("indoor", []) if isinstance(sensors, dict) else []
        aggregation = sensors.get(CONF_AGGREGATION, AGGREGATION_AVERAGE) if isinstance(sensors, dict) else AGGREGATION_AVERAGE
        smoothing = sensors.get(CONF_SMOOTHING_SAMPLES, DEFAULT_SMOOTHING_SAMPLES) if isinstance(sensors, dict) else DEFAULT_SMOOTHING_SAMPLES
        weights = sensors.get(CONF_WEIGHTS, {}) if isinstance(sensors, dict) else {}

        # Parse ALL setpoints (preserve them for save)
        setpoints = zone_conf.get("setpoints", {})
        occupancy_entity = setpoints.get(CONF_OCCUPANCY_ENTITY)
        # Check for explicit occupancy_enabled flag, or infer from entity presence (backwards compat)
        occupancy_enabled = setpoints.get("occupancy_enabled", occupancy_entity is not None)

        # Calculate occupancy offsets from actual values
        default_setpoint = setpoints.get("default", 72)
        occupied_temp = setpoints.get("occupied")
        unoccupied_temp = setpoints.get("unoccupied")
        occupied_offset = (occupied_temp - default_setpoint) if occupied_temp is not None else 2
        unoccupied_offset = (unoccupied_temp - default_setpoint) if unoccupied_temp is not None else -2

        # Parse settings
        settings = zone_conf.get("settings", {})

        # Parse outdoor reset override from settings
        # Respect existing *_override_set flags if present, otherwise infer from key presence
        outdoor_reset_conf = settings.get("outdoor_reset", {})
        outdoor_reset = {}
        if outdoor_reset_conf:
            # Check if override was explicitly enabled (new flag)
            if "override_enabled" in outdoor_reset_conf:
                outdoor_reset["override_enabled"] = outdoor_reset_conf["override_enabled"]

            if "never_heat_above" in outdoor_reset_conf or outdoor_reset_conf.get("heat_override_set"):
                outdoor_reset["never_heat_above"] = outdoor_reset_conf.get("never_heat_above")
                outdoor_reset["heat_override_set"] = outdoor_reset_conf.get("heat_override_set", True)
            if "never_cool_below" in outdoor_reset_conf or outdoor_reset_conf.get("cool_override_set"):
                outdoor_reset["never_cool_below"] = outdoor_reset_conf.get("never_cool_below")
                outdoor_reset["cool_override_set"] = outdoor_reset_conf.get("cool_override_set", True)

            # If config exists but no override_enabled flag, add it for backwards compat
            if outdoor_reset and "override_enabled" not in outdoor_reset:
                outdoor_reset["override_enabled"] = True

        # Parse opportunistic heating
        opportunistic_conf = zone_conf.get("opportunistic", {})
        opportunistic = {
            "enabled": opportunistic_conf.get("enabled", False),
            "threshold": opportunistic_conf.get("threshold", 0.5),
        }

        # Parse stages (preserving allow_command flags)
        heat_stages = self._parse_stages_for_edit(zone_conf.get("heat_stages", []))
        cool_stages = self._parse_stages_for_edit(zone_conf.get("cool_stages", []))

        # Parse regulation
        regulation = zone_conf.get("regulation", {})

        # Parse TOU config if present
        tou_config = zone_conf.get(CONF_TOU, {})

        return {
            "zone_id": zone_id,
            CONF_NAME: zone_conf.get(CONF_NAME, zone_id),
            CONF_SENSORS: indoor_sensors,
            CONF_AGGREGATION: aggregation,
            CONF_SMOOTHING_SAMPLES: smoothing,
            CONF_WEIGHTS: dict(weights),
            "occupancy_enabled": occupancy_enabled,
            CONF_OCCUPANCY_ENTITY: occupancy_entity,
            "occupied_offset": occupied_offset,
            "unoccupied_offset": unoccupied_offset,
            "heat_stages": heat_stages,
            "cool_stages": cool_stages,
            CONF_HYSTERESIS: settings.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS),
            CONF_MIN_RUNTIME: settings.get(CONF_MIN_RUNTIME, DEFAULT_MIN_RUNTIME),
            CONF_OPENING_ENTITIES: zone_conf.get(CONF_OPENINGS, {}).get(CONF_OPENING_ENTITIES, []),
            CONF_OPEN_DELAY: zone_conf.get(CONF_OPENINGS, {}).get(CONF_OPEN_DELAY, DEFAULT_OPEN_DELAY),
            CONF_CLOSE_DELAY: zone_conf.get(CONF_OPENINGS, {}).get(CONF_CLOSE_DELAY, DEFAULT_CLOSE_DELAY),
            "regulation_type": regulation.get("type", "direct") if regulation else "direct",
            "pi_config": regulation if regulation and regulation.get("type") == REGULATION_PI else None,
            "opportunistic": opportunistic,
            "outdoor_reset": outdoor_reset,
            CONF_TOU: tou_config,
            # Preserve full setpoints dict for save
            "_original_setpoints": setpoints,
        }

    def _parse_stages_for_edit(self, stages: list) -> list[dict]:
        """Parse stage config for editing.

        Converts device refs to entity IDs while PRESERVING allow_command flags.
        """
        result = []
        yaml_devices = self._get_yaml_config().get(CONF_DEVICES, {})

        for stage in stages:
            stage_data = {
                "stage": stage.get("stage", 1),
                "threshold": stage.get("threshold", 1.0),
            }

            # Handle devices - preserve allow_command for each
            devices = stage.get("devices", [])
            parsed_devices = []

            for d in devices:
                if isinstance(d, dict):
                    # Already in object format - could have device_id or entity_id
                    device_ref = d.get("device") or d.get("device_id") or d.get("entity_id", "")
                    allow_command = d.get("allow_command", False)

                    # Convert device_id to entity_id if needed
                    if device_ref in yaml_devices:
                        entity_id = yaml_devices[device_ref].get("entity_id", device_ref)
                    else:
                        entity_id = device_ref

                    parsed_devices.append({
                        "entity_id": entity_id,
                        "allow_command": allow_command,
                    })
                else:
                    # String device ID - resolve to entity_id
                    entity_id = yaml_devices.get(d, {}).get("entity_id", d)
                    parsed_devices.append({
                        "entity_id": entity_id,
                        "allow_command": False,
                    })

            stage_data["devices"] = parsed_devices

            if stage.get("time_escalation"):
                stage_data["time_escalation"] = stage["time_escalation"]

            conditions = stage.get("conditions") or {}
            for key in ("outdoor_temp_min", "outdoor_temp_max"):
                value = conditions.get(key, stage.get(key))
                if value is not None:
                    stage_data[key] = value

            result.append(stage_data)
        return result

    def _save_zone_config(self) -> FlowResult:
        """Save zone configuration to options storage.

        IMPORTANT: Preserves original setpoints when editing a zone.
        """
        wip = self._zone_wip or {}
        zone_id = wip.get("zone_id")

        if not zone_id:
            return self.async_abort(reason="no_zone_id")

        # Start with original setpoints if editing, otherwise use defaults
        original_setpoints = wip.get("_original_setpoints", {})
        setpoints = dict(original_setpoints) if original_setpoints else {"default": 72}

        # Update occupancy settings if enabled
        if wip.get("occupancy_enabled"):
            # Save that occupancy is enabled (even without entity selected yet)
            setpoints["occupancy_enabled"] = True
            if wip.get(CONF_OCCUPANCY_ENTITY):
                setpoints[CONF_OCCUPANCY_ENTITY] = wip[CONF_OCCUPANCY_ENTITY]
                default_temp = setpoints.get("default", 72)
                setpoints["occupied"] = default_temp + wip.get("occupied_offset", 2)
                setpoints["unoccupied"] = default_temp + wip.get("unoccupied_offset", -2)
        else:
            # Remove occupancy settings if disabled
            setpoints.pop("occupancy_enabled", None)
            setpoints.pop(CONF_OCCUPANCY_ENTITY, None)
            setpoints.pop("occupied", None)
            setpoints.pop("unoccupied", None)

        # Build settings with optional outdoor_reset
        settings_config = {
            CONF_HYSTERESIS: wip.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS),
            CONF_MIN_RUNTIME: wip.get(CONF_MIN_RUNTIME, DEFAULT_MIN_RUNTIME),
        }

        # Add outdoor_reset if configured (must include *_override_set flags)
        outdoor_reset = wip.get("outdoor_reset", {})
        if outdoor_reset:
            settings_config["outdoor_reset"] = {
                "override_enabled": outdoor_reset.get("override_enabled", True),
                "never_heat_above": outdoor_reset.get("never_heat_above"),
                "never_cool_below": outdoor_reset.get("never_cool_below"),
                "heat_override_set": outdoor_reset.get("heat_override_set", False),
                "cool_override_set": outdoor_reset.get("cool_override_set", False),
            }

        # Build zone config structure matching the expected format
        zone_config = {
            CONF_NAME: wip.get(CONF_NAME, zone_id),
            CONF_SENSORS: {
                "indoor": wip.get(CONF_SENSORS, []),
                CONF_AGGREGATION: wip.get(CONF_AGGREGATION, AGGREGATION_AVERAGE),
                CONF_SMOOTHING_SAMPLES: wip.get(CONF_SMOOTHING_SAMPLES, DEFAULT_SMOOTHING_SAMPLES),
            },
            "setpoints": setpoints,
            "heat_stages": self._build_stages_config(wip.get("heat_stages", [])),
            "cool_stages": self._build_stages_config(wip.get("cool_stages", [])),
            "settings": settings_config,
        }
        # Keep weights for any method, but only for sensors still selected.
        selected_sensors = set(wip.get(CONF_SENSORS, []))
        weights = {
            entity_id: weight for entity_id, weight in wip.get(CONF_WEIGHTS, {}).items()
            if entity_id in selected_sensors
        }
        if weights:
            zone_config[CONF_SENSORS][CONF_WEIGHTS] = weights
        opening_entities = wip.get(CONF_OPENING_ENTITIES, [])
        if opening_entities:
            zone_config[CONF_OPENINGS] = {
                CONF_OPENING_ENTITIES: opening_entities,
                CONF_OPEN_DELAY: wip.get(CONF_OPEN_DELAY, DEFAULT_OPEN_DELAY),
                CONF_CLOSE_DELAY: wip.get(CONF_CLOSE_DELAY, DEFAULT_CLOSE_DELAY),
            }

        # Add opportunistic heating if configured
        opportunistic = wip.get("opportunistic", {})
        if opportunistic.get("enabled", False):
            zone_config["opportunistic"] = {
                "enabled": True,
                "threshold": opportunistic.get("threshold", 0.5),
            }

        # Add PI regulation if configured
        if wip.get("regulation_type") == REGULATION_PI and wip.get("pi_config"):
            pi = wip["pi_config"]
            zone_config["regulation"] = {
                "type": REGULATION_PI,
                "devices": pi.get("devices", []),
                "kp": pi.get("kp", DEFAULT_KP),
                "ki": pi.get("ki", DEFAULT_KI),
                "k_ext": pi.get("k_ext", DEFAULT_K_EXT),
                "offset_max": pi.get("offset_max", DEFAULT_OFFSET_MAX),
                "balance_point": pi.get("balance_point", DEFAULT_BALANCE_POINT),
            }

        # Add TOU config if enabled
        tou_config = wip.get(CONF_TOU, {})
        if tou_config.get("enabled", False):
            zone_config[CONF_TOU] = tou_config

        # Update UI config
        stored_config = dict(self._get_ui_config())
        stored_config[CONF_UI_VERSION] = 1
        zones = stored_config.get(CONF_ZONES, {})
        if not isinstance(zones, dict):
            zones = {}
        zones[zone_id] = zone_config
        stored_config[CONF_ZONES] = zones

        # Clear WIP state
        self._zone_wip = None
        self._zone_edit_id = None

        return self._save_ui_config(stored_config)

    def _build_stages_config(self, stages: list[dict]) -> list[dict]:
        """Build stage config in the format expected by config_loader.

        PRESERVES allow_command flags from the parsed devices.
        """
        result = []
        for stage in stages:
            devices = stage.get("devices", [])
            if not devices:
                continue

            # Build device list preserving allow_command
            device_configs = []
            for d in devices:
                if isinstance(d, dict):
                    # Already parsed with allow_command
                    device_configs.append({
                        "entity_id": d.get("entity_id", ""),
                        "allow_command": d.get("allow_command", False),
                    })
                else:
                    # String entity_id (shouldn't happen after _parse_stages_for_edit)
                    device_configs.append({
                        "entity_id": str(d),
                        "allow_command": False,
                    })

            # Filter out empty entity_ids
            device_configs = [d for d in device_configs if d["entity_id"]]
            if not device_configs:
                continue

            stage_config = {
                "stage": stage.get("stage", len(result) + 1),
                "devices": device_configs,
                "threshold": stage.get("threshold", 1.0),
            }

            if stage.get("time_escalation"):
                stage_config["time_escalation"] = stage["time_escalation"]

            # Add conditions if present
            conditions = {}
            if stage.get("outdoor_temp_min") is not None:
                conditions["outdoor_temp_min"] = stage["outdoor_temp_min"]
            if stage.get("outdoor_temp_max") is not None:
                conditions["outdoor_temp_max"] = stage["outdoor_temp_max"]
            if conditions:
                stage_config["conditions"] = conditions

            result.append(stage_config)
        return result

    def _delete_zone(self, zone_id: str) -> FlowResult:
        """Delete a zone from UI config."""
        stored_config = dict(self._get_ui_config())
        zones = stored_config.get(CONF_ZONES, {})

        if isinstance(zones, dict) and zone_id in zones:
            del zones[zone_id]
            stored_config[CONF_ZONES] = zones

            # Mark helpers for deletion on reload
            helpers_to_delete = stored_config.get("_helpers_to_delete", [])
            if zone_id not in helpers_to_delete:
                helpers_to_delete.append(zone_id)
            stored_config["_helpers_to_delete"] = helpers_to_delete

            return self._save_ui_config(stored_config)

        # If not in UI config, can't delete YAML zones from UI
        # Just return to zone list
        return self.async_abort(reason="cannot_delete_yaml_zone")
