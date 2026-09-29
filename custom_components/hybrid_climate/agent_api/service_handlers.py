"""Purpose: Authorize and route Agent API service calls to loaded entries.

Key dependencies: Home Assistant auth, runtime markers, and Agent API views.
Used by: Agent API service registration.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError, Unauthorized

from ..const import DATA_ACTIVE_REVISION, DOMAIN
from .config_patch import async_set_config
from .config_view import get_config
from .const import (
    DEVICES_KEY, DRY_RUN_KEY, ENTRY_ID_KEY, EXPECTED_HASH_KEY,
    INCLUDE_STRUCTURE_KEY, REASON_KEY, SERVICE_GET_CONFIG, SERVICE_GET_STATUS,
    SERVICE_SET_CONFIG, STAGE_PATCH_KEY, ZONE_ID_KEY, ZONES_KEY,
)
from .service_schemas import CONFIG_SCHEMA, SET_SCHEMA, STATUS_SCHEMA
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
    if call.service == SERVICE_SET_CONFIG:
        if not data[REASON_KEY].strip():
            raise APIServiceValidationError("reason is required")
        if not data[DRY_RUN_KEY] and not data.get(EXPECTED_HASH_KEY, "").strip():
            raise APIServiceValidationError("expected_hash is required for apply")
    entry = resolve_entry(hass, data.get(ENTRY_ID_KEY))
    check_targets(hass.data[DOMAIN][entry.entry_id], data)
    if call.service == SERVICE_GET_STATUS:
        return await async_get_status(hass, entry, data.get(ZONE_ID_KEY))
    if call.service == SERVICE_GET_CONFIG:
        return get_config(hass, entry, data.get(ZONE_ID_KEY), data[INCLUDE_STRUCTURE_KEY])
    return await async_set_config(hass, entry, call)
