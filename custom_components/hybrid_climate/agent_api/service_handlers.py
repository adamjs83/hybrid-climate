"""Purpose: Authorize and route Agent API service calls to loaded entries.

Key dependencies: Home Assistant auth, runtime markers, and Agent API views.
Used by: Agent API service registration.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ..const import DATA_ACTIVE_REVISION, DOMAIN
from ..control_restore import async_restore
from ..hold import HOLD_KEY as HOLD_SWITCH_KEY, end_hold, hold_payload, start_hold
from .config_patch import async_set_config
from .config_view import get_config
from .const import (
    DEVICES_KEY, DURATION_KEY, ENTITY_ID_KEY, ENTRY_ID_KEY, HOLD_EXCLUSIVE_MESSAGE, HOLD_KEY,
    HOLD_PAST_UNTIL_MESSAGE, HOLD_TARGET_MESSAGE, HOLD_TIMING_NEEDS_HOLD_MESSAGE,
    INCLUDE_STRUCTURE_KEY, SERVICE_GET_CONFIG, SERVICE_GET_STATUS, SERVICE_SET_CONFIG,
    STAGE_PATCH_KEY, UNTIL_KEY, ZONE_ID_KEY, ZONES_KEY,
)
from .service_schemas import (
    CONFIG_SCHEMA, RESTORE_SCHEMA, SET_HOLD_SCHEMA, SET_SCHEMA, STATUS_SCHEMA,
)
from .status import async_get_status


class APIServiceValidationError(ServiceValidationError, vol.Invalid):
    """Preserve service validation semantics while HA REST maps the error to 400."""


async def async_require_admin(hass: HomeAssistant, call: ServiceCall) -> None:
    """Reject missing, deleted, and non-administrator users for every service."""
    user_id = call.context.user_id
    user = await hass.auth.async_get_user(user_id) if user_id else None
    if user is None or not user.is_admin:
        raise Unauthorized()


def resolve_entry(hass: HomeAssistant, entry_id: str | None) -> ConfigEntry:
    """Resolve an explicit entry or the only runtime that completed setup."""
    entries = hass.config_entries.async_entries(DOMAIN)
    runtimes = hass.data.get(DOMAIN, {})
    loaded = [entry for entry in entries if entry.domain == DOMAIN
              and isinstance(runtimes.get(entry.entry_id), dict)
              and "coordinator" in runtimes[entry.entry_id]
              and DATA_ACTIVE_REVISION in runtimes[entry.entry_id]]
    if entry_id is None:
        if len(loaded) != 1:
            raise APIServiceValidationError("entry_id is required unless exactly one entry is loaded")
        return loaded[0]
    for entry in loaded:
        if entry.entry_id == entry_id:
            return entry
    raise APIServiceValidationError("Unknown or unloaded hybrid_climate entry")


def check_targets(runtime: Mapping[str, Any], data: Mapping[str, Any]) -> None:
    """Raise for unknown target IDs and malformed stage envelopes."""
    config = runtime["config"]
    zone_ids = set(data.get(ZONES_KEY, {}))
    if ZONE_ID_KEY in data:
        zone_ids.add(data[ZONE_ID_KEY])
    if zone_ids - config.zones.keys():
        raise APIServiceValidationError("Unknown zone ID")
    if set(data.get(DEVICES_KEY, {})) - config.devices.keys():
        raise APIServiceValidationError("Unknown device ID")
    # Envelope validation checks shape; patch validation checks stage addresses.
    for values in data.get(ZONES_KEY, {}).values():
        if STAGE_PATCH_KEY in values:
            stages = values[STAGE_PATCH_KEY]
            if not isinstance(stages, list) or any(
                not isinstance(stage, dict) for stage in stages
            ):
                raise APIServiceValidationError("stages must be a list of mappings")


async def async_handle_service(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Authorize and resolve before dispatching one of the three API services."""
    await async_require_admin(hass, call)
    schema = {SERVICE_GET_STATUS: STATUS_SCHEMA, SERVICE_GET_CONFIG: CONFIG_SCHEMA,
              SERVICE_SET_CONFIG: SET_SCHEMA}.get(call.service)
    if schema is None:
        raise APIServiceValidationError("Unknown Agent API service")
    try:
        data = schema(dict(call.data))
    except vol.Invalid as error:
        raise APIServiceValidationError(str(error)) from error
    entry = resolve_entry(hass, data.get(ENTRY_ID_KEY))
    check_targets(hass.data[DOMAIN][entry.entry_id], data)
    if call.service == SERVICE_GET_STATUS:
        return await async_get_status(hass, entry, data.get(ZONE_ID_KEY))
    if call.service == SERVICE_GET_CONFIG:
        return get_config(hass, entry, data.get(ZONE_ID_KEY), data[INCLUDE_STRUCTURE_KEY])
    return await async_set_config(hass, entry, call, data)


async def async_handle_restore_control(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Authorize, resolve the entry, and run one manual restore pass (spec §2.1)."""
    await async_require_admin(hass, call)
    try:
        data = RESTORE_SCHEMA(dict(call.data))
    except vol.Invalid as error:
        raise APIServiceValidationError(str(error)) from error
    entry = resolve_entry(hass, data.get(ENTRY_ID_KEY))
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    return await async_restore(coordinator, data.get(ZONE_ID_KEY))


def resolve_hold_target(hass: HomeAssistant, entity_id: str) -> tuple[ConfigEntry, str]:
    """Map a zone climate or hold switch to its loaded entry and zone id via the entity registry."""
    registry_entry = er.async_get(hass).async_get(entity_id)
    if (registry_entry is None or registry_entry.platform != DOMAIN
            or registry_entry.config_entry_id is None):
        raise APIServiceValidationError(HOLD_TARGET_MESSAGE)
    entry = resolve_entry(hass, registry_entry.config_entry_id)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    # Match the registered unique id against each zone's own ids; never parse entity_id.
    zone_ids = coordinator.config.zones
    if registry_entry.domain == "climate":
        unique_ids = {f"{DOMAIN}_{entry.entry_id}_{zone_id}": zone_id for zone_id in zone_ids}
    elif registry_entry.domain == "switch":
        unique_ids = {f"{DOMAIN}_{zone_id}_{HOLD_SWITCH_KEY}": zone_id for zone_id in zone_ids}
    else:
        unique_ids = {}
    zone_id = unique_ids.get(registry_entry.unique_id)
    if zone_id is None:
        raise APIServiceValidationError(HOLD_TARGET_MESSAGE)
    return entry, zone_id


def hold_until(data: Mapping[str, Any]) -> datetime | None:
    """Return the UTC end of a requested hold, or None; raise for invalid timing combinations."""
    until, duration = data.get(UNTIL_KEY), data.get(DURATION_KEY)
    if until is not None and duration is not None:
        raise APIServiceValidationError(HOLD_EXCLUSIVE_MESSAGE)
    if not data[HOLD_KEY]:
        # Ending a hold takes no timing; reject rather than silently ignore it.
        if until is not None or duration is not None:
            raise APIServiceValidationError(HOLD_TIMING_NEEDS_HOLD_MESSAGE)
        return None
    now = dt_util.utcnow()
    if duration is not None:
        return now + timedelta(minutes=duration)
    if until is None:
        return None
    # A naive until is local time in HA's configured zone (as_utc assumes it).
    until = dt_util.as_utc(until)
    if until <= now:
        raise APIServiceValidationError(HOLD_PAST_UNTIL_MESSAGE)
    return until


async def async_handle_set_hold(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Start, retime or end one zone's hold (spec v0.18.0 §1) and return its hold state."""
    await async_require_admin(hass, call)
    try:
        data = SET_HOLD_SCHEMA(dict(call.data))
    except vol.Invalid as error:
        raise APIServiceValidationError(str(error)) from error
    until = hold_until(data)
    entry, zone_id = resolve_hold_target(hass, data[ENTITY_ID_KEY])
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    if data[HOLD_KEY]:
        start_hold(coordinator, zone_id, until)
    else:
        await end_hold(coordinator, zone_id)
    await coordinator.async_request_refresh()
    return {ZONE_ID_KEY: zone_id, HOLD_KEY: hold_payload(coordinator.zone_states[zone_id].hold)}
