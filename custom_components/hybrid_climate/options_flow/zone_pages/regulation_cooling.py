"""Purpose: The Regulation page's cooling part (v0.17.0 §2, owner decision 5): one `cool_device_N` form section per
cooling device of the zone (at most MAX_REGULATION_COOL_DEVICES), the description note listing the devices with
the shared-device and beyond-cap lines and the cooling PI numbers with values, and the device writes on save.
Also the read-only number line (registry ids and current values) the heating note uses.

Key dependencies: options_flow/device_cooling.py (block fields, coercion, write_cooling_settings),
regulation_devices.py (zones using a device), capability_defaults.py (first-save capabilities),
zone_helpers.resolve_number_entity_id (registry lookup by unique id), page_const.py.
Used by: options_flow/zone_pages/regulation.py.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section

from ...const import CAPABILITY_COOL, CAPABILITY_HEAT, CONF_CAPABILITIES, CONF_ENTITY_ID
from ...number_lookup import COOL_PI_NUMBER_KEYS
from ...zone_helpers import resolve_number_entity_id
from ..capability_defaults import device_form_capabilities, merge_capabilities
from ..device_cooling import (
    cooling_regulation_fields,
    regulation_form_values,
    regulation_settings_from_input,
    write_cooling_settings,
)
from ..page_const import (
    COOL_BEYOND_CAP_LINE,
    COOL_DEVICE_LINE,
    COOL_SHARED_MANY,
    COOL_SHARED_ONE,
    COOLING_NOTE,
    LIST_JOIN,
    MAX_REGULATION_COOL_DEVICES,
    REGULATION_NUMBER_VALUE,
    REGULATION_NUMBERS_NEW,
    SECTION_COOL_DEVICE,
)
from ..regulation_devices import zones_cooling_with


@dataclass(frozen=True)
class CoolBlock:
    """One shown cooling device: its section key, entity id, stored config, form values and first-save entry."""

    section: str
    entity_id: str
    current: Mapping[str, Any]
    defaults: Mapping[str, Any]
    seed: Mapping[str, Any]


def seed_entry(hass: HomeAssistant, entity_id: str, loaded: Mapping[str, Any]) -> dict[str, Any]:
    """Return the entry a first device-page save writes for a device with no stored entry.

    The capabilities are the ones the device page pre-fills; cooling is kept in them, since the device sits in
    a cool stage and an entry without it would stop the device cooling.
    """
    capabilities = device_form_capabilities(
        hass, entity_id, None, list(loaded.get(CONF_CAPABILITIES, [CAPABILITY_HEAT])))
    return {CONF_ENTITY_ID: entity_id, **loaded,
            CONF_CAPABILITIES: merge_capabilities(capabilities, [CAPABILITY_COOL])}


def cool_blocks(
    hass: HomeAssistant, devices: list[str], load: Callable[[str], Mapping[str, Any]],
) -> tuple[list[CoolBlock], list[str]]:
    """Return the shown blocks (the first MAX_REGULATION_COOL_DEVICES devices) and the entity ids beyond the cap.

    `load(entity_id)` returns the device's stored config (UI, else YAML, else defaults).
    """
    blocks = []
    for index, entity_id in enumerate(devices[:MAX_REGULATION_COOL_DEVICES], start=1):
        current = load(entity_id)
        blocks.append(CoolBlock(SECTION_COOL_DEVICE.format(index=index), entity_id, current,
                                regulation_form_values(current), seed_entry(hass, entity_id, current)))
    return blocks, devices[MAX_REGULATION_COOL_DEVICES:]


def cooling_sections(blocks: list[CoolBlock]) -> dict[Any, Any]:
    """Return the form's cooling sections.

    Optional with no default: a section left out of a submission stays absent after HA's schema validation
    (a default would be filled in and read as a submitted block that cleared the sensor).
    """
    return {vol.Optional(block.section): section(vol.Schema(cooling_regulation_fields(block.current)))
            for block in blocks}


def apply_cooling(ui_config: dict[str, Any], blocks: list[CoolBlock], user_input: Mapping[str, Any]) -> None:
    """Write each changed block to its device entry; omitted or unchanged blocks and devices beyond the cap stay."""
    for block in blocks:
        # An omitted section changes nothing; a submitted one without the sensor key clears the sensor.
        if block.section not in user_input:
            continue
        values = regulation_settings_from_input(user_input[block.section] or {}, block.defaults)
        if values != dict(block.defaults):
            write_cooling_settings(ui_config, block.entity_id, values, seed=block.seed)


def number_values_line(hass: HomeAssistant, zone_id: str, keys: Iterable[str]) -> str | None:
    """Return "number.x = 1.0, ..." for the zone's number entities by unique id; None when none is registered.

    A key with no registered entity shows as the key; an entity with no state shows its id only.
    """
    parts: list[str] = []
    found = False
    for key in keys:
        entity_id = resolve_number_entity_id(hass, zone_id, key)
        if not entity_id:
            parts.append(key)
            continue
        found = True
        state = hass.states.get(entity_id)
        parts.append(entity_id if state is None
                     else REGULATION_NUMBER_VALUE.format(entity_id=entity_id, value=state.state))
    return LIST_JOIN.join(parts) if found else None


def _device_name(hass: HomeAssistant, entity_id: str) -> str:
    """Return the device's friendly name, or its entity id."""
    state = hass.states.get(entity_id)
    return (state.attributes.get(ATTR_FRIENDLY_NAME) if state is not None else None) or entity_id


def cooling_note(
    hass: HomeAssistant, zone_id: str, blocks: list[CoolBlock], beyond: list[str],
    zones: dict[str, dict[str, Any]], yaml_devices: dict[str, Any],
) -> str:
    """Return the description's cooling note: one line per device (shared zones named), the cap line, the numbers."""
    lines = []
    for index, block in enumerate(blocks, start=1):
        line = COOL_DEVICE_LINE.format(index=index, name=_device_name(hass, block.entity_id),
                                       entity_id=block.entity_id)
        others = [name for other_id, name in zones_cooling_with(zones, block.entity_id, yaml_devices)
                  if other_id != zone_id]
        if others:
            # The device's block is the same on every zone that cools with it.
            shared = COOL_SHARED_ONE if len(others) == 1 else COOL_SHARED_MANY
            line += shared.format(zones=LIST_JOIN.join(others))
        lines.append(line)
    if beyond:
        lines.append(COOL_BEYOND_CAP_LINE.format(cap=MAX_REGULATION_COOL_DEVICES, devices=LIST_JOIN.join(beyond)))
    numbers = number_values_line(hass, zone_id, COOL_PI_NUMBER_KEYS.values()) or REGULATION_NUMBERS_NEW
    return COOLING_NOTE.format(devices="\n".join(lines), numbers=numbers)
