"""Purpose: Build the heat-capable device choices for the PI wizard step.

Key dependencies: Device capabilities in UI or YAML configuration.
Used by: The zone PI settings step.
"""

from __future__ import annotations

from typing import Any

from ..const import (
    CAPABILITY_HEAT, CLIMATE_ENTITY_PREFIX, CONF_CAPABILITIES, CONF_COOL_STAGES, CONF_DEVICES,
    CONF_ENTITY_ID, CONF_HEAT_STAGES,
)


def _entity_id(reference: Any, yaml_devices: dict[str, Any]) -> str | None:
    if isinstance(reference, dict):
        reference = reference.get(CONF_ENTITY_ID)
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
