"""Purpose: Validate Agent API service request envelopes.

Key dependencies: Voluptuous and Agent API wire constants.
Used by: Agent API service registration and direct handler calls.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.helpers import config_validation as cv

from .const import (
    DEVICES_KEY, DRY_RUN_KEY, DURATION_KEY, ENTITY_ID_KEY, ENTRY_ID_KEY, EXPECTED_HASH_KEY,
    GLOBAL_KEY, HOLD_DURATION_MAX, HOLD_DURATION_MIN, HOLD_KEY, INCLUDE_STRUCTURE_KEY,
    REASON_KEY, REASON_REQUIRED_MESSAGE, UNTIL_KEY, ZONE_ID_KEY, ZONES_KEY,
)

COMMON = {vol.Optional(ENTRY_ID_KEY): str}
READ = {**COMMON, vol.Optional(ZONE_ID_KEY): str}
STATUS_SCHEMA = vol.Schema(READ, extra=vol.PREVENT_EXTRA)
CONFIG_SCHEMA = vol.Schema(
    {**READ, vol.Optional(INCLUDE_STRUCTURE_KEY, default=False): bool},
    extra=vol.PREVENT_EXTRA,
)
# Same fields as a read selector (spec §2.1): an optional entry and an optional zone.
RESTORE_SCHEMA = vol.Schema(READ, extra=vol.PREVENT_EXTRA)
# Field types only; the cross-field rules (until/duration exclusive, both need hold: true, a
# future until) are checked by the handler after the admin check (spec v0.18.0 §1).
SET_HOLD_SCHEMA = vol.Schema(
    {
        vol.Required(ENTITY_ID_KEY): cv.entity_id,
        vol.Required(HOLD_KEY): cv.boolean,
        vol.Optional(UNTIL_KEY): cv.datetime,
        vol.Optional(DURATION_KEY): vol.All(
            vol.Coerce(int), vol.Range(min=HOLD_DURATION_MIN, max=HOLD_DURATION_MAX)),
    },
    extra=vol.PREVENT_EXTRA,
)


def _require_reason(reason: str) -> str:
    """Reject a reason containing only whitespace."""
    if not reason.strip():
        raise vol.Invalid(REASON_REQUIRED_MESSAGE)
    return reason


_SET_FIELDS = vol.Schema(
    {
        **COMMON,
        vol.Required(REASON_KEY): vol.All(str, vol.Length(min=1), _require_reason),
        vol.Optional(DRY_RUN_KEY, default=True): bool,
        vol.Optional(EXPECTED_HASH_KEY): str,
        vol.Optional(GLOBAL_KEY): {str: object},
        vol.Optional(ZONES_KEY): {str: {str: object}},
        vol.Optional(DEVICES_KEY): {str: {str: object}},
    },
    extra=vol.PREVENT_EXTRA,
)


def _require_apply_hash(data: dict[str, Any]) -> dict[str, Any]:
    """Reject an apply without a hash during HA's schema validation stage."""
    if not data[DRY_RUN_KEY] and not data.get(EXPECTED_HASH_KEY, "").strip():
        raise vol.Invalid("expected_hash is required for apply")
    return data


SET_SCHEMA = vol.All(_SET_FIELDS, _require_apply_hash)
