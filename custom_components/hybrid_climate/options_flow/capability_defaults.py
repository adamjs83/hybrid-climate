"""Purpose: Derive and safely extend device capabilities in the options UI.

Key dependencies: Home Assistant cached climate states and shared config keys.
Used by: Device editor and zone stage save.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant

from ..const import (
    ATTR_HVAC_MODES, CAPABILITY_COOL, CAPABILITY_HEAT, CAPABILITY_UI_COOL_FIELD,
    CAPABILITY_UI_HEAT_FIELD, CLIMATE_ENTITY_PREFIX,
    CONF_CAPABILITIES, CONF_COOL_STAGES, CONF_DEVICE, CONF_DEVICES, CONF_ENTITY_ID,
    CONF_HEAT_STAGES, HVAC_MODE_AUTO, HVAC_MODE_HEAT_COOL,
)

_LOGGER = logging.getLogger(__name__)


def capabilities_from_hvac_modes(modes: Iterable[str] | None) -> list[str]:
    """Map climate HVAC modes to the directions the entity can serve."""
    available = set(modes or ())
    result: list[str] = []
    if available.intersection((CAPABILITY_HEAT, HVAC_MODE_HEAT_COOL, HVAC_MODE_AUTO)):
        result.append(CAPABILITY_HEAT)
    if available.intersection((CAPABILITY_COOL, HVAC_MODE_HEAT_COOL, HVAC_MODE_AUTO)):
        result.append(CAPABILITY_COOL)
    return result


def merge_capabilities(stored: Iterable[str], required: Iterable[str]) -> list[str]:
    """Keep stored order and append only missing capabilities."""
    return list(dict.fromkeys((*stored, *required)))


def entity_capabilities(hass: HomeAssistant, entity_id: str) -> list[str] | None:
    """Read climate mode support from a cached Home Assistant entity."""
    states = getattr(hass, "states", None)
    if states is None:
        return None
    state = states.get(entity_id)
    if state is None:
        return None
    modes = state.attributes.get(ATTR_HVAC_MODES)
    return capabilities_from_hvac_modes(modes) if isinstance(modes, (list, tuple, set)) else None


def device_form_capabilities(
    hass: HomeAssistant, entity_id: str, stored: Mapping[str, Any] | None,
    fallback: list[str],
) -> list[str]:
    """Prefer stored UI capabilities, then entity modes, then legacy defaults."""
    if stored is not None and CONF_CAPABILITIES in stored:
        return list(stored[CONF_CAPABILITIES])
    return entity_capabilities(hass, entity_id) or fallback


def submitted_capabilities(user_input: Mapping[str, Any]) -> list[str]:
    """Read the two capability checkboxes using their existing defaults."""
    return [direction for direction, enabled in (
        (CAPABILITY_HEAT, user_input.get(CAPABILITY_UI_HEAT_FIELD, True)),
        (CAPABILITY_COOL, user_input.get(CAPABILITY_UI_COOL_FIELD, False)),
    ) if enabled]


def add_stage_capabilities(hass: HomeAssistant, ui_config: dict[str, Any], zone: Mapping[str, Any]) -> None:
    """Add supported stage directions to stored device entries without removing any."""
    devices = deepcopy(ui_config.get(CONF_DEVICES, {}))
    for direction, stage_key in ((CAPABILITY_HEAT, CONF_HEAT_STAGES), (CAPABILITY_COOL, CONF_COOL_STAGES)):
        for stage in zone.get(stage_key, []):
            for reference in stage.get(CONF_DEVICES, []):
                entity_id = ((reference.get(CONF_ENTITY_ID) or reference.get(CONF_DEVICE))
                             if isinstance(reference, dict) else reference)
                if not entity_id:
                    continue
                if not entity_id.startswith(CLIMATE_ENTITY_PREFIX):
                    entity_id = f"{CLIMATE_ENTITY_PREFIX}{entity_id}"
                if entity_id not in devices:
                    # No stored UI entry: leave it for config_converter.ensure_devices_exist,
                    # which auto-creates it with both directions. Writing a narrowed entry
                    # here (only this stage's direction) would silently drop the other one.
                    continue
                supported = entity_capabilities(hass, entity_id)
                if supported is None or direction not in supported:
                    continue
                entry = devices[entity_id]
                old = list(entry.get(CONF_CAPABILITIES, []))
                new = merge_capabilities(old, [direction])
                if new != old:
                    entry[CONF_CAPABILITIES] = new
                    ui_config[CONF_DEVICES] = devices
                    _LOGGER.info("Added %s capability to device %s from zone stage", direction, entity_id)
