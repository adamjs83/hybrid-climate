"""Purpose: Serialize configured topology through an explicit safe allowlist.

Key dependencies: Loaded Hybrid Climate configuration model.
Used by: Agent API get_config structure option.
"""

from __future__ import annotations

from typing import Any

from ..models import HybridClimateConfig


def get_structure(config: HybridClimateConfig, zone_id: str | None) -> dict[str, Any]:
    """Expose only configured topology and explicitly named UI-only fields."""
    selected = {zone_id: config.zones[zone_id]} if zone_id else config.zones
    zones: dict[str, Any] = {}
    for ident, zone in selected.items():
        # Preserve loaded stage list positions and configured stage numbers separately.
        stages = {}
        for direction in ("heat", "cool"):
            stages[direction] = [
                {"index": index, "stage": stage.stage_number,
                 "devices": [{"id": device.device_id, "allow_command": device.allow_command}
                             for device in stage.devices]}
                for index, stage in enumerate(getattr(zone, direction + "_stages"))
            ]
        tou = {}
        if zone.tou:
            for direction in ("heat", "cool"):
                mode = getattr(zone.tou, direction)
                if mode:
                    tou[direction] = {"pre_condition_minutes": mode.pre_condition_minutes,
                                      "relaxation_amount": mode.relaxation_amount}
        zones[ident] = {"name": zone.name, "stages": stages, "tou": tou,
                        "sensors": list(zone.sensors.indoor),
                        "openings": list(zone.openings.entities) if zone.openings else []}
    mutex = [
        {"device_id": rule.device_id, "mode": rule.mode, "for_zone": rule.for_zone,
         "block_heat": list(rule.block_heat), "block_cool": list(rule.block_cool),
         "blocked_devices_heat": list(rule.blocked_devices_heat),
         "blocked_devices_cool": list(rule.blocked_devices_cool)}
        for rule in config.conflicts.device_mutex
    ]
    return {"zones": zones, "device_mutex": mutex,
            "tou_rate_sensor": config.tou_global.rate_sensor}
