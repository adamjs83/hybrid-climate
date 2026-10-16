"""Purpose: Classify an options save as structural (changes what the takeover must re-check) or not.

Structural (spec v0.17.0 §1 "Structural?" column, owner decision 4): the zone id set, each
zone's indoor sensors and heat/cool stage device lists, the device id set and capabilities,
the mutex rules and the heat source groups. Names, setpoints, thresholds, allow_command,
regulation, time-of-use and global settings are not.

Key dependencies: const.py config keys.
Used by: options_flow/base.py (_save_ui_config writes the result into the save marker).
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from ..const import (
    CONF_CAPABILITIES,
    CONF_COOL_STAGES,
    CONF_DEVICE,
    CONF_DEVICE_MUTEX,
    CONF_DEVICES,
    CONF_ENTITY_ID,
    CONF_HEAT_SOURCES,
    CONF_HEAT_STAGES,
    CONF_INDOOR,
    CONF_SENSORS,
    CONF_STAGE,
    CONF_ZONES,
)


def _stage_entity(device: Any) -> str:
    """Return a stage device reference's entity id (stored as an object or a bare string)."""
    if isinstance(device, Mapping):
        return str(device.get(CONF_ENTITY_ID) or device.get(CONF_DEVICE) or "")
    return str(device) if device else ""


def _stages_view(stages: Any) -> list[tuple[Any, list[str]]]:
    """Reduce stages to (stage number, sorted entity ids); thresholds and flags are dropped."""
    if not isinstance(stages, list):
        return []
    return [
        (stage.get(CONF_STAGE), sorted(_stage_entity(device) for device in stage.get(CONF_DEVICES, [])))
        for stage in stages if isinstance(stage, Mapping)
    ]


def structural_view(ui_config: Mapping[str, Any]) -> dict[str, Any]:
    """Project a ui_config onto the fields whose change is structural."""
    zones = ui_config.get(CONF_ZONES) or {}
    devices = ui_config.get(CONF_DEVICES) or {}
    zone_view = {}
    for zone_id, zone in zones.items():
        sensors = zone.get(CONF_SENSORS) or {}
        zone_view[zone_id] = {
            CONF_INDOOR: sorted(sensors.get(CONF_INDOOR) or []),
            CONF_HEAT_STAGES: _stages_view(zone.get(CONF_HEAT_STAGES)),
            CONF_COOL_STAGES: _stages_view(zone.get(CONF_COOL_STAGES)),
        }
    return {
        CONF_ZONES: zone_view,
        CONF_DEVICES: {
            entity_id: sorted((conf or {}).get(CONF_CAPABILITIES) or [])
            for entity_id, conf in devices.items()
        },
        CONF_DEVICE_MUTEX: deepcopy(ui_config.get(CONF_DEVICE_MUTEX) or []),
        CONF_HEAT_SOURCES: deepcopy(ui_config.get(CONF_HEAT_SOURCES) or {}),
    }


def is_structural(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """Return whether a save from `before` to `after` changes any structural field."""
    return structural_view(before) != structural_view(after)
