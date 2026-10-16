"""Purpose: Pure value mapping of the Behaviour zone page (v0.17.0 §1, §0.6): form defaults from the loaded zone,
submitted values, the outdoor-limit mode → settings.outdoor_reset mapping (the v0.16.x zone_settings rules), and the
writer that changes only the blocks whose values changed (settings, openings, opportunistic, allow_command).

Key dependencies: const.py, options_flow/page_const.py; the loaded zone from zone_helpers._load_zone_for_edit.
Used by: zone_pages/behaviour.py.
"""
from __future__ import annotations

from typing import Any

from ...const import (
    CONF_ALLOW_COMMAND,
    CONF_CLOSE_DELAY,
    CONF_COOL_STAGES,
    CONF_DEVICES,
    CONF_ENTITY_ID,
    CONF_HEAT_STAGES,
    CONF_HYSTERESIS,
    CONF_MIN_RUNTIME,
    CONF_NEVER_COOL_BELOW,
    CONF_NEVER_HEAT_ABOVE,
    CONF_OPEN_DELAY,
    CONF_OPENING_ENTITIES,
    CONF_OPENINGS,
    CONF_OPPORTUNISTIC,
    CONF_OUTDOOR_RESET,
    CONF_SETTINGS,
    CONF_THRESHOLD,
    DEFAULT_CLOSE_DELAY,
    DEFAULT_HYSTERESIS,
    DEFAULT_MIN_RUNTIME,
    DEFAULT_OPEN_DELAY,
    DEFAULT_OPPORTUNISTIC_THRESHOLD,
)
from ..page_const import (
    CONF_COOL_OVERRIDE_SET,
    CONF_ENABLED,
    CONF_HEAT_OVERRIDE_SET,
    CONF_OVERRIDE_ENABLED,
    FIELD_ALLOW_COMMAND_DEVICES,
    FIELD_COOL_LIMIT_MODE,
    FIELD_HEAT_LIMIT_MODE,
    FIELD_OPPORTUNISTIC_ENABLED,
    FIELD_OPPORTUNISTIC_THRESHOLD,
    FIELD_ZONE_NEVER_COOL_BELOW,
    FIELD_ZONE_NEVER_HEAT_ABOVE,
    LIMIT_MODE_DISABLED,
    LIMIT_MODE_INHERIT,
    LIMIT_MODE_VALUE,
)

STAGE_KEYS = (CONF_HEAT_STAGES, CONF_COOL_STAGES)
# (mode field, value field, stored limit key, stored "override set" flag) per direction.
DIRECTIONS = (
    (FIELD_HEAT_LIMIT_MODE, FIELD_ZONE_NEVER_HEAT_ABOVE, CONF_NEVER_HEAT_ABOVE, CONF_HEAT_OVERRIDE_SET),
    (FIELD_COOL_LIMIT_MODE, FIELD_ZONE_NEVER_COOL_BELOW, CONF_NEVER_COOL_BELOW, CONF_COOL_OVERRIDE_SET),
)


def _direction(mode: str, value: float | None) -> tuple[str, float | None]:
    """Normalise one direction: a value only counts in value mode; value mode without one is inherit."""
    if mode == LIMIT_MODE_VALUE and value is not None:
        return LIMIT_MODE_VALUE, value
    if mode == LIMIT_MODE_DISABLED:
        return LIMIT_MODE_DISABLED, None
    return LIMIT_MODE_INHERIT, None


def outdoor_reset_block(
    heat_mode: str, heat_value: float | None, cool_mode: str, cool_value: float | None,
) -> dict[str, Any]:
    """Return settings.outdoor_reset for the two directions as the old page stored it ({} = remove the block).

    Business rule (v0.16.x): any direction not inheriting turns the zone override on; "no limit" stores the
    limit as None with its flag set; a value stores the value with its flag set; an inheriting direction
    stores None with its flag unset.
    """
    block: dict[str, Any] = {CONF_OVERRIDE_ENABLED: True}
    any_override = False
    for (mode, value), (_m, _v, limit_key, set_key) in zip(
        (_direction(heat_mode, heat_value), _direction(cool_mode, cool_value)), DIRECTIONS,
    ):
        block[limit_key] = value
        block[set_key] = mode != LIMIT_MODE_INHERIT
        any_override = any_override or block[set_key]
    if not any_override:
        return {}
    return {key: block[key] for key in (CONF_OVERRIDE_ENABLED, CONF_NEVER_HEAT_ABOVE, CONF_NEVER_COOL_BELOW,
                                        CONF_HEAT_OVERRIDE_SET, CONF_COOL_OVERRIDE_SET)}


def limit_mode(loaded_block: dict[str, Any], limit_key: str, set_key: str) -> tuple[str, float | None]:
    """Return (mode, value) of one direction from the loaded outdoor block, as the old page showed it."""
    value = loaded_block.get(limit_key)
    if loaded_block.get(set_key, False) and value is None:
        return LIMIT_MODE_DISABLED, None
    if value is not None:
        return LIMIT_MODE_VALUE, value
    return LIMIT_MODE_INHERIT, None


def _device_entity(device: Any) -> str:
    """Return a stage device reference's entity id (object or bare string)."""
    if isinstance(device, dict):
        return str(device.get(CONF_ENTITY_ID) or "")
    return device if isinstance(device, str) else ""


def stage_device_ids(zone: dict[str, Any]) -> list[str]:
    """Return every stage device of the zone (all stages, heat then cool), first-seen order."""
    found: list[str] = []
    for key in STAGE_KEYS:
        for stage in zone.get(key) or []:
            for device in stage.get(CONF_DEVICES) or []:
                entity_id = _device_entity(device)
                if entity_id and entity_id not in found:
                    found.append(entity_id)
    return found


def allow_command_ids(zone: dict[str, Any]) -> list[str]:
    """Return the stage devices with allow_command on, in stage_device_ids order."""
    allowed = {
        _device_entity(device)
        for key in STAGE_KEYS for stage in zone.get(key) or [] for device in stage.get(CONF_DEVICES) or []
        if isinstance(device, dict) and device.get(CONF_ALLOW_COMMAND, False)
    }
    return [entity_id for entity_id in stage_device_ids(zone) if entity_id in allowed]


def apply_allow_command(zone: dict[str, Any], selected: set[str]) -> None:
    """Set allow_command on every instance of each stage device (stages 3+ included); flags already right stay."""
    for key in STAGE_KEYS:
        for stage in zone.get(key) or []:
            devices = stage.get(CONF_DEVICES) or []
            for index, device in enumerate(devices):
                if isinstance(device, dict):
                    wanted = device.get(CONF_ENTITY_ID) in selected
                    if bool(device.get(CONF_ALLOW_COMMAND, False)) != wanted:
                        device[CONF_ALLOW_COMMAND] = wanted
                elif isinstance(device, str) and device in selected:
                    # A bare entity id has no flag; it becomes the object form to carry one.
                    devices[index] = {CONF_ENTITY_ID: device, CONF_ALLOW_COMMAND: True}


def behaviour_defaults(loaded: dict[str, Any]) -> dict[str, Any]:
    """Return the page's values for the loaded zone (the form defaults)."""
    opportunistic = loaded.get(CONF_OPPORTUNISTIC) or {}
    outdoor = loaded.get(CONF_OUTDOOR_RESET) or {}
    values: dict[str, Any] = {
        CONF_HYSTERESIS: loaded.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS),
        CONF_MIN_RUNTIME: loaded.get(CONF_MIN_RUNTIME, DEFAULT_MIN_RUNTIME),
        CONF_OPENING_ENTITIES: list(loaded.get(CONF_OPENING_ENTITIES) or []),
        CONF_OPEN_DELAY: loaded.get(CONF_OPEN_DELAY, DEFAULT_OPEN_DELAY),
        CONF_CLOSE_DELAY: loaded.get(CONF_CLOSE_DELAY, DEFAULT_CLOSE_DELAY),
        FIELD_OPPORTUNISTIC_ENABLED: bool(opportunistic.get(CONF_ENABLED, False)),
        FIELD_OPPORTUNISTIC_THRESHOLD: opportunistic.get(CONF_THRESHOLD, DEFAULT_OPPORTUNISTIC_THRESHOLD),
        FIELD_ALLOW_COMMAND_DEVICES: allow_command_ids(loaded),
    }
    for mode_field, value_field, limit_key, set_key in DIRECTIONS:
        values[mode_field], values[value_field] = limit_mode(outdoor, limit_key, set_key)
    return values


def behaviour_values(user_input: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Return the page's values from a submit; the thermostat field is absent when the zone has no devices."""
    values: dict[str, Any] = {
        CONF_HYSTERESIS: user_input.get(CONF_HYSTERESIS, defaults[CONF_HYSTERESIS]),
        CONF_MIN_RUNTIME: int(user_input.get(CONF_MIN_RUNTIME, defaults[CONF_MIN_RUNTIME])),
        CONF_OPENING_ENTITIES: list(user_input.get(CONF_OPENING_ENTITIES) or []),
        CONF_OPEN_DELAY: int(user_input.get(CONF_OPEN_DELAY, defaults[CONF_OPEN_DELAY])),
        CONF_CLOSE_DELAY: int(user_input.get(CONF_CLOSE_DELAY, defaults[CONF_CLOSE_DELAY])),
        FIELD_OPPORTUNISTIC_ENABLED: bool(user_input.get(FIELD_OPPORTUNISTIC_ENABLED, False)),
        FIELD_OPPORTUNISTIC_THRESHOLD: user_input.get(
            FIELD_OPPORTUNISTIC_THRESHOLD, defaults[FIELD_OPPORTUNISTIC_THRESHOLD]),
        FIELD_ALLOW_COMMAND_DEVICES: list(
            user_input.get(FIELD_ALLOW_COMMAND_DEVICES, defaults[FIELD_ALLOW_COMMAND_DEVICES])),
    }
    for mode_field, value_field, _limit_key, _set_key in DIRECTIONS:
        values[mode_field], values[value_field] = _direction(
            user_input.get(mode_field, LIMIT_MODE_INHERIT), user_input.get(value_field))
    return values


def _openings_view(values: dict[str, Any]) -> tuple[Any, ...]:
    """Reduce contacts to what they store: without contacts the delays are not stored."""
    if not values[CONF_OPENING_ENTITIES]:
        return ()
    return (values[CONF_OPENING_ENTITIES], values[CONF_OPEN_DELAY], values[CONF_CLOSE_DELAY])


def _opportunistic_view(values: dict[str, Any]) -> tuple[Any, ...]:
    """Reduce opportunistic heating to what it stores: disabled stores nothing."""
    if not values[FIELD_OPPORTUNISTIC_ENABLED]:
        return ()
    return (True, values[FIELD_OPPORTUNISTIC_THRESHOLD])


def _outdoor_view(values: dict[str, Any]) -> tuple[Any, ...]:
    """Reduce the outdoor limits to their normalised (mode, value) pairs."""
    return tuple(_direction(values[mode], values[value]) for mode, value, _l, _s in DIRECTIONS)


def apply_behaviour(zone: dict[str, Any], values: dict[str, Any], defaults: dict[str, Any]) -> None:
    """Write the page into the stored zone, touching only blocks whose values changed (unchanged = identical)."""
    settings = dict(zone.get(CONF_SETTINGS) or {})
    settings_changed = False
    for key in (CONF_HYSTERESIS, CONF_MIN_RUNTIME):
        if values[key] != defaults[key]:
            settings[key] = values[key]
            settings_changed = True
    if _outdoor_view(values) != _outdoor_view(defaults):
        block = outdoor_reset_block(*(value for pair in _outdoor_view(values) for value in pair))
        if block:
            settings[CONF_OUTDOOR_RESET] = block
        else:
            settings.pop(CONF_OUTDOOR_RESET, None)
        settings_changed = True
    if settings_changed:
        zone[CONF_SETTINGS] = settings

    # Contacts: stored with both delays, or the block removed when none are chosen (old wizard rule).
    if _openings_view(values) != _openings_view(defaults):
        if values[CONF_OPENING_ENTITIES]:
            zone[CONF_OPENINGS] = {**(zone.get(CONF_OPENINGS) or {}),
                                   CONF_OPENING_ENTITIES: values[CONF_OPENING_ENTITIES],
                                   CONF_OPEN_DELAY: values[CONF_OPEN_DELAY],
                                   CONF_CLOSE_DELAY: values[CONF_CLOSE_DELAY]}
        else:
            zone.pop(CONF_OPENINGS, None)

    # Opportunistic heating: stored only while enabled (old wizard rule).
    if _opportunistic_view(values) != _opportunistic_view(defaults):
        if values[FIELD_OPPORTUNISTIC_ENABLED]:
            zone[CONF_OPPORTUNISTIC] = {**(zone.get(CONF_OPPORTUNISTIC) or {}), CONF_ENABLED: True,
                                        CONF_THRESHOLD: values[FIELD_OPPORTUNISTIC_THRESHOLD]}
        else:
            zone.pop(CONF_OPPORTUNISTIC, None)

    if set(values[FIELD_ALLOW_COMMAND_DEVICES]) != set(defaults[FIELD_ALLOW_COMMAND_DEVICES]):
        apply_allow_command(zone, set(values[FIELD_ALLOW_COMMAND_DEVICES]))
