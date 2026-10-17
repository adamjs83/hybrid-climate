"""Purpose: Load, transform, and delete zone wizard configuration.

Handles loading and transforming zone configuration data between the
options flow UI and the stored config format, and deleting zones.
Saving lives in zone_save.py; the canonical stage form and merge baseline in zone_merge.py.

Key dependencies: Options flow storage; zone_merge.py.
Used by: the zone pages (zone_pages/*, via _load_zone_for_edit), zones.py, zone_save.py.
"""
from __future__ import annotations

from copy import deepcopy
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
    CONF_OCCUPANCY_OFF_DELAY,
    DEFAULT_OCCUPANCY_OFF_DELAY,
    CONF_OCCUPANCY_ON_DELAY,
    DEFAULT_OCCUPANCY_ON_DELAY,
    CONF_SENSORS,
    CONF_SMOOTHING_SAMPLES,
    CONF_WEIGHTS,
    CONF_TOU,
    CONF_ZONES,
    DEFAULT_HYSTERESIS,
    DEFAULT_MIN_RUNTIME,
    DEFAULT_OPEN_DELAY,
    DEFAULT_CLOSE_DELAY,
    DEFAULT_SMOOTHING_SAMPLES,
    REGULATION_PI,
)
from .zone_merge import canonical_stages, edit_baseline


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

        # Canonical stages (UI or YAML source, allow_command kept) are both the pages'
        # starting point and the save's merge baseline (zone_merge.py).
        baseline = edit_baseline(zone_conf, self._get_yaml_config().get(CONF_DEVICES, {}))
        heat_stages = deepcopy(baseline["heat_stages"])
        cool_stages = deepcopy(baseline["cool_stages"])

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
            CONF_OCCUPANCY_OFF_DELAY: setpoints.get(CONF_OCCUPANCY_OFF_DELAY, DEFAULT_OCCUPANCY_OFF_DELAY),
            CONF_OCCUPANCY_ON_DELAY: setpoints.get(CONF_OCCUPANCY_ON_DELAY, DEFAULT_OCCUPANCY_ON_DELAY),
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
            "_edit_baseline": baseline,
        }

    def _parse_stages_for_edit(self, stages: list) -> list[dict]:
        """Parse stage config for editing: canonical UI stages, allow_command flags preserved."""
        return canonical_stages(stages, self._get_yaml_config().get(CONF_DEVICES, {}))

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
