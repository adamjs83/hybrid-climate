"""Purpose: Decide whether a reload follows a non-structural options save and skip its takeover.

One-shot (owner decision 7): only the reload right after the save skips. The first setup that
sees a save marker records its timestamp as consumed in the revision ledger, which survives
entry unloads within one HA run, so any later reload (Reload button, set_config, restart) arms.

Key dependencies: agent_api/revision.py ledger, options_flow/page_const.py marker keys.
Used by: __init__.py async_setup_entry, right after the coordinator is built.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from .agent_api.revision import ledger
from .const import CONF_UI_CONFIG
from .options_flow.page_const import (
    CONF_LAST_SAVE,
    LAST_SAVE_AT,
    LAST_SAVE_STRUCTURAL,
    LEDGER_CONSUMED_SAVES,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .startup_takeover import StartupTakeover

_LOGGER = logging.getLogger(__name__)


def should_skip_takeover(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Return True once for a reload right after a non-structural save; consume the marker."""
    marker = entry.options.get(CONF_UI_CONFIG, {}).get(CONF_LAST_SAVE)
    if not isinstance(marker, Mapping):
        return False
    state = ledger(hass)
    consumed = state.setdefault(LEDGER_CONSUMED_SAVES, {})
    at = marker.get(LAST_SAVE_AT)
    already_consumed = consumed.get(entry.entry_id) == at
    # Always record the marker as consumed, so only this setup can act on it.
    consumed[entry.entry_id] = at
    # A reload within one HA run has an active revision; HA start does not.
    reload = entry.entry_id in state["active"]
    return reload and marker.get(LAST_SAVE_STRUCTURAL) is False and not already_consumed


def skip_startup_pass(takeover: StartupTakeover) -> None:
    """Mark the startup pass done without queuing; rearm requests still apply (it is armed)."""
    takeover.armed = True
    takeover.finished = True
    takeover.skipped_reload = True
    _LOGGER.info("Startup takeover skipped: reload after a non-structural options save")
