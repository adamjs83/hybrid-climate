"""Purpose: Serialize Agent API configuration saves and verify reload activation.

Key dependencies: Revision ledger, patch validation, HA config entry manager, audit.
Used by: Agent API set_config service.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from ..const import DOMAIN
from .audit import audit_saved
from .const import (
    COMPAT_KEYS, DRY_RUN_KEY, ERROR_ENTRY_REMOVED, ERROR_PENDING, FAILED_UNLOAD_STATE,
    ERROR_RELOAD_FAILED, ERROR_STALE_REVISION, EXPECTED_HASH_KEY,
    PENDING_MESSAGE, PENDING_SETUP_RECOVERY_MESSAGE, PENDING_UNLOAD_RECOVERY_MESSAGE,
    REASON_KEY, RELOAD_FAILED_MESSAGE, STALE_MESSAGE,
)
from .patch_validation import empty_result, issue, validate_patch
from .revision import ledger, revision_state, stored_revision

_LOGGER = logging.getLogger(__name__)


async def async_set_config(
    hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall,
) -> dict[str, Any]:
    """Serialize a validated save, reload once, and report actual activation."""
    if not isinstance(call.data.get(REASON_KEY), str) or not call.data[REASON_KEY].strip():
        raise ServiceValidationError("reason is required")
    dry_run = call.data.get(DRY_RUN_KEY, True)
    expected_hash = call.data.get(EXPECTED_HASH_KEY)
    if not dry_run and (not isinstance(expected_hash, str) or not expected_hash.strip()):
        raise ServiceValidationError("expected_hash is required for apply")
    state = ledger(hass)
    lock = state["locks"].setdefault(entry.entry_id, asyncio.Lock())
    async with lock:
        # Validate against a newly read entry, including after waiting for a writer.
        fresh = hass.config_entries.async_get_entry(entry.entry_id)
        runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        if fresh is None or "active_revision" not in runtime:
            raise ServiceValidationError("Entry is no longer loaded")
        before = revision_state(fresh.options, state["active"].get(entry.entry_id))
        result = empty_result(fresh.options, dry_run)
        result.update(revision_before=before, revision_after=before, pending=before["pending"])
        if before["pending"] and not dry_run:
            result["valid"] = False
            result["errors"].append(issue(None, ERROR_PENDING, PENDING_MESSAGE))
            return result
        candidate, result = validate_patch(fresh.options, call.data)
        result.update(revision_before=before, revision_after=before, pending=before["pending"])
        result["revision_proposed"] = revision_state(candidate, before["active"])
        if not result["valid"] or dry_run:
            return result

        # No await separates the final comparison and the synchronous save.
        latest = hass.config_entries.async_get_entry(entry.entry_id)
        if latest is None:
            raise ServiceValidationError("Entry no longer exists")
        current = stored_revision(latest.options)
        if current != before["stored"] or current != call.data[EXPECTED_HASH_KEY]:
            result["valid"] = False
            result["errors"].append(issue(None, ERROR_STALE_REVISION, STALE_MESSAGE))
            result["revision_after"] = revision_state(
                latest.options, state["active"].get(entry.entry_id),
            )
            result["pending"] = result["revision_after"]["pending"]
            return result
        if not result["diff"]:
            return result
        latest_ui = latest.options.get("ui_config", {})
        if "number_values" in latest_ui:
            candidate["ui_config"]["number_values"] = deepcopy(latest_ui["number_values"])
        else:
            candidate["ui_config"].pop("number_values", None)
        saved_options = deepcopy(dict(latest.options))
        saved_options["ui_config"] = candidate["ui_config"]
        for key in COMPAT_KEYS:
            if key in candidate:
                saved_options[key] = candidate[key]
        hass.config_entries.async_update_entry(latest, options=saved_options)
        result["saved"] = True
        proposed = stored_revision(saved_options)

        # A successful manager reload still needs the new runtime marker and ledger hash.
        try:
            reload_ok = await hass.config_entries.async_reload(entry.entry_id)
            active_runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
            result["reloaded"] = bool(
                reload_ok and state["active"].get(entry.entry_id) == proposed
                and active_runtime.get("active_revision") == proposed
            )
            if not result["reloaded"]:
                result["errors"].append(issue(None, ERROR_RELOAD_FAILED, RELOAD_FAILED_MESSAGE))
        except Exception as error:
            _LOGGER.exception("Agent API reload failed for %s", entry.entry_id)
            result["errors"].append(issue(None, ERROR_RELOAD_FAILED, str(error)))
        finally:
            current_entry = hass.config_entries.async_get_entry(entry.entry_id)
            if current_entry is None:
                result["reloaded"] = False
                result["errors"].append(issue(None, ERROR_ENTRY_REMOVED, "Entry was removed during reload"))
                # A historic ledger value cannot prove a removed entry has an active runtime.
                after = revision_state(saved_options, None)
            else:
                runtime_marker = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("active_revision")
                active = state["active"].get(entry.entry_id)
                # A ledger hash without a matching runtime marker is not activation.
                after = revision_state(
                    current_entry.options, active if runtime_marker == active else None,
                )
            result.update(revision_after=after, pending=after["pending"], applied=result["reloaded"])
            if result["pending"]:
                state_name = getattr(getattr(current_entry, "state", None), "name", None)
                recovery = (PENDING_UNLOAD_RECOVERY_MESSAGE if state_name == FAILED_UNLOAD_STATE
                            else PENDING_SETUP_RECOVERY_MESSAGE)
                result["errors"].append(issue(None, ERROR_RELOAD_FAILED, recovery))
                result["recovery"] = recovery
            result["warnings"].extend(audit_saved(hass, latest, call, result))
        return result
