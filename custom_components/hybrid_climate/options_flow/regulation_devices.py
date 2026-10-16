"""Purpose: Device lookups for the Regulation page: the heat-capable PI thermostat choices, a zone's cooling
devices (every cool stage), and the zones whose cool stages use a device (shared-device line, device page line).

Key dependencies: Device capabilities and zones in UI or YAML configuration.
Used by: options_flow/zone_pages/regulation.py, zone_pages/regulation_cooling.py, options_flow/devices.py.
"""

from __future__ import annotations

from typing import Any

from ..const import (
    CAPABILITY_HEAT, CLIMATE_ENTITY_PREFIX, CONF_CAPABILITIES, CONF_COOL_STAGES, CONF_DEVICE, CONF_DEVICES,
    CONF_ENTITY_ID, CONF_HEAT_STAGES, CONF_NAME, CONF_ZONES,
)


def _entity_id(reference: Any, yaml_devices: dict[str, Any]) -> str | None:
    """Resolve a stage device reference (entity id, YAML device id or either as an object) to an entity id."""
    if isinstance(reference, dict):
        reference = reference.get(CONF_ENTITY_ID) or reference.get(CONF_DEVICE)
    if not isinstance(reference, str) or not reference:
        return None
    if reference in yaml_devices:
        return yaml_devices[reference].get(CONF_ENTITY_ID)
    if reference.startswith(CLIMATE_ENTITY_PREFIX):
        return reference
    return None


def heat_capable_stage_devices(
    wip: dict[str, Any], ui_devices: dict[str, Any], yaml_devices: dict[str, Any],
) -> list[str]:
    """Return ordered, unique heat-capable stage entity IDs."""
    capabilities = {
        data.get(CONF_ENTITY_ID): data.get(CONF_CAPABILITIES, [CAPABILITY_HEAT])
        for data in yaml_devices.values()
    }
    capabilities.update({
        entity_id: data.get(CONF_CAPABILITIES, [CAPABILITY_HEAT])
        for entity_id, data in ui_devices.items()
    })
    devices: list[str] = []
    for stage in wip.get(CONF_HEAT_STAGES, []) + wip.get(CONF_COOL_STAGES, []):
        for reference in stage.get(CONF_DEVICES, []):
            entity_id = _entity_id(reference, yaml_devices)
            if (entity_id and entity_id not in devices
                    and CAPABILITY_HEAT in capabilities.get(entity_id, [])):
                devices.append(entity_id)
    return devices


def selected_pi_devices(
    configured: list[Any] | None, choices: list[str], yaml_devices: dict[str, Any],
) -> list[str]:
    """Normalize stored PI references and discard unavailable choices."""
    if not configured:
        return choices.copy()
    selected = [_entity_id(reference, yaml_devices) for reference in configured]
    return list(dict.fromkeys(entity_id for entity_id in selected if entity_id in choices))


def zone_cool_devices(zone: dict[str, Any], yaml_devices: dict[str, Any]) -> list[str]:
    """Return a zone's cooling devices: ordered, unique entity IDs of every cool stage."""
    devices: list[str] = []
    for stage in zone.get(CONF_COOL_STAGES) or []:
        for reference in stage.get(CONF_DEVICES, []):
            entity_id = _entity_id(reference, yaml_devices)
            if entity_id and entity_id not in devices:
                devices.append(entity_id)
    return devices


def all_zones(ui_config: dict[str, Any], yaml_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return every zone by id: YAML zones overlaid by the UI zones (UI wins, as the zone list shows)."""
    return {**(yaml_config.get(CONF_ZONES) or {}), **(ui_config.get(CONF_ZONES) or {})}


def zones_cooling_with(
    zones: dict[str, dict[str, Any]], entity_id: str, yaml_devices: dict[str, Any],
) -> list[tuple[str, str]]:
    """Return (zone id, zone name) of every zone whose cool stages use the device, in zone order."""
    return [(zone_id, zone.get(CONF_NAME, zone_id)) for zone_id, zone in zones.items()
            if entity_id in zone_cool_devices(zone, yaml_devices)]
