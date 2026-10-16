"""Purpose: Save the zone wizard's work-in-progress to options storage, keeping stored keys no page shows.

When a zone is edited (stored in UI storage or only in YAML), stages and the PI regulation block are
merged into the canonical baseline `_load_zone_for_edit` built (zone_merge.py), so stage 3+, unshown
stage keys and conditions, and PI gains/advanced keys survive; the result is written to UI storage.
New zones are built from the pages. The page-owned key sets live in const.py (PAGE_* constants).

Key dependencies: const.py; zone_merge.py; capability_defaults.add_stage_capabilities; OptionsFlowBase storage.
Used by: options_flow/zones.py (ZoneFlowMixin), zone_pages/cooling_stages.py (add-zone save),
zone_pages/stage_page.py (_stages_for_save).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.data_entry_flow import FlowResult

from ..const import (
    AGGREGATION_AVERAGE,
    CONF_AGGREGATION,
    CONF_CLOSE_DELAY,
    CONF_HYSTERESIS,
    CONF_MIN_RUNTIME,
    CONF_NAME,
    CONF_OCCUPANCY_ENTITY,
    CONF_OCCUPANCY_OFF_DELAY,
    CONF_OPEN_DELAY,
    CONF_OPENING_ENTITIES,
    CONF_OPENINGS,
    CONF_SENSORS,
    CONF_SMOOTHING_SAMPLES,
    CONF_TOU,
    CONF_UI_VERSION,
    CONF_WEIGHTS,
    CONF_ZONES,
    DEFAULT_CLOSE_DELAY,
    DEFAULT_HYSTERESIS,
    DEFAULT_MIN_RUNTIME,
    DEFAULT_OCCUPANCY_OFF_DELAY,
    DEFAULT_OPEN_DELAY,
    DEFAULT_REGULATION_MIN_PERIOD,
    DEFAULT_REGULATION_THRESHOLD,
    DEFAULT_SMOOTHING_SAMPLES,
    PAGE_CONDITION_KEYS,
    PAGE_STAGE_KEYS,
    REGULATION_PI,
    STAGES_DISABLED_KEYS,
)
from .capability_defaults import add_stage_capabilities
from .zone_merge import (
    STAGE_LISTS,
    is_page_stage,
    merge_regulation,
    merge_stages,
    stage_conditions,
)


class ZoneSaveMixin:
    """Mixin saving the zone wizard's work-in-progress to options storage."""

    def _save_zone_config(self) -> FlowResult:
        """Save zone configuration to options storage.

        IMPORTANT: Preserves original setpoints when editing a zone, and merges stages and
        regulation into the edited zone's canonical baseline (UI or YAML zone).
        """
        wip = self._zone_wip or {}
        zone_id = wip.get("zone_id")

        if not zone_id:
            return self.async_abort(reason="no_zone_id")

        stored_config = dict(self._get_ui_config())
        zones = stored_config.get(CONF_ZONES, {})
        if not isinstance(zones, dict):
            zones = {}
        zone_config = self._zone_config_from_wip(wip, zone_id, editing=bool(self._zone_edit_id))

        # Update UI config
        stored_config[CONF_UI_VERSION] = 1
        zones[zone_id] = zone_config
        stored_config[CONF_ZONES] = zones
        add_stage_capabilities(self.hass, stored_config, zone_config)

        # Clear WIP state
        self._zone_wip = None
        self._zone_edit_id = None

        return self._save_ui_config(stored_config)

    def _zone_config_from_wip(self, wip: dict[str, Any], zone_id: str, *, editing: bool) -> dict[str, Any]:
        """Build the stored zone dict from wizard state; an edit merges stages and PI into its baseline."""
        # Start with original setpoints if editing, otherwise use defaults
        original_setpoints = wip.get("_original_setpoints", {})
        setpoints = dict(original_setpoints) if original_setpoints else {"default": 72}

        # Update occupancy settings if enabled
        if wip.get("occupancy_enabled"):
            # Save that occupancy is enabled (even without entity selected yet)
            setpoints["occupancy_enabled"] = True
            setpoints[CONF_OCCUPANCY_OFF_DELAY] = wip.get(CONF_OCCUPANCY_OFF_DELAY, DEFAULT_OCCUPANCY_OFF_DELAY)
            if wip.get(CONF_OCCUPANCY_ENTITY):
                setpoints[CONF_OCCUPANCY_ENTITY] = wip[CONF_OCCUPANCY_ENTITY]
                default_temp = setpoints.get("default", 72)
                setpoints["occupied"] = default_temp + wip.get("occupied_offset", 2)
                setpoints["unoccupied"] = default_temp + wip.get("unoccupied_offset", -2)
        else:
            # Remove occupancy settings if disabled
            setpoints.pop("occupancy_enabled", None)
            setpoints.pop(CONF_OCCUPANCY_ENTITY, None)
            setpoints.pop(CONF_OCCUPANCY_OFF_DELAY, None)
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

        # Add TOU config if enabled
        tou_config = wip.get(CONF_TOU, {})
        if tou_config.get("enabled", False):
            zone_config[CONF_TOU] = tou_config

        # An edit merges into the canonical baseline of the zone (UI or YAML); a new zone does not.
        baseline = self._edit_baseline(wip, zone_id) if editing else None
        for stage_key in STAGE_LISTS:
            zone_config[stage_key] = self._stages_for_save(wip, stage_key, baseline)

        # Add PI regulation if configured; Direct drops the block
        if wip.get("regulation_type") == REGULATION_PI and wip.get("pi_config"):
            pi = wip["pi_config"]
            page_regulation = {
                "type": REGULATION_PI,
                "devices": pi.get("devices", []),
                "regulation_threshold": pi.get("regulation_threshold", DEFAULT_REGULATION_THRESHOLD),
                "regulation_min_period": pi.get("regulation_min_period", DEFAULT_REGULATION_MIN_PERIOD),
            }
            # Stored gains and advanced keys are kept; a new block is seeded with default gains.
            zone_config["regulation"] = merge_regulation(
                baseline.get("regulation") if baseline else None, page_regulation)
        return zone_config

    def _edit_baseline(self, wip: dict[str, Any], zone_id: str) -> dict[str, Any]:
        """Return the edited zone's merge baseline (built at load; rebuilt from storage if absent)."""
        baseline = wip.get("_edit_baseline")
        if isinstance(baseline, dict):
            return baseline
        return self._load_zone_for_edit(zone_id)["_edit_baseline"]

    def _stages_for_save(
        self, wip: dict[str, Any], stage_key: str, baseline: dict[str, Any] | None,
    ) -> list[dict]:
        """Return one stage list to store: page stages rebuilt, stages 3+ as held, merged on an edit."""
        stages = wip.get(stage_key, [])
        # Stages 1-2 are rebuilt from the page state; 3+ are already canonical (zone_merge).
        built = self._build_stages_config([s for s in stages if is_page_stage(s)]) + [
            deepcopy(s) for s in stages if not is_page_stage(s)]
        if baseline is None:
            return built
        # A mode the page disabled keeps none of its stored stages (3+ included).
        stored = [] if wip.get(STAGES_DISABLED_KEYS[stage_key]) else baseline.get(stage_key, [])
        return merge_stages(stored, built, PAGE_CONDITION_KEYS[stage_key], PAGE_STAGE_KEYS[stage_key])

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
                    # String entity_id (shouldn't happen after canonical_stages)
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

            # Nested conditions, or legacy top-level limits from an older stage
            conditions = stage_conditions(stage)
            if conditions:
                stage_config["conditions"] = conditions

            result.append(stage_config)
        return result
