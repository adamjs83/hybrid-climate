"""Purpose: Attribute each saved Agent API edit across three audit destinations.

Key dependencies: HA persistent notifications, logbook, and Python logging.
Used by: Agent API configuration save transaction.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components import logbook, persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from ..const import DOMAIN
from .const import (
    AUDIT_LOGBOOK_NAME, AUDIT_NOTIFICATION_TITLE, ERROR_AUDIT_FAILED, REASON_KEY,
)
from .patch_validation import issue

_LOGGER = logging.getLogger(__name__)


def audit_saved(
    hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall,
    data: dict[str, Any], result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attempt every audit destination after a save, reporting delivery failures."""
    record = {
        "entry_id": entry.entry_id, "user_id": call.context.user_id,
        "reason": data[REASON_KEY], "diff": result["diff"],
        "revision_before": result["revision_before"],
        "revision_proposed": result["revision_proposed"],
        "revision_after": result["revision_after"],
        "saved": result["saved"], "reloaded": result["reloaded"],
        "pending": result["pending"], "errors": result["errors"],
    }
    message = json.dumps(record, sort_keys=True, allow_nan=False)
    notification_message = (
        f"{message}\n{result['recovery']}" if result["pending"] else message
    )
    _LOGGER.warning("Agent API configuration saved: %s", message)
    failures: list[dict[str, Any]] = []
    destinations = (
        ("persistent_notification", lambda: persistent_notification.async_create(
            hass, notification_message, title=AUDIT_NOTIFICATION_TITLE,
            notification_id=f"hybrid_climate_agent_{call.context.id}")),
        ("logbook", lambda: logbook.async_log_entry(
            hass, AUDIT_LOGBOOK_NAME, message, domain=DOMAIN, context=call.context)),
    )
    # Each callback is independent so one failed destination does not hide another.
    for name, publish in destinations:
        try:
            publish()
        except Exception as error:
            _LOGGER.exception("Agent API %s audit delivery failed", name)
            failures.append(issue(None, ERROR_AUDIT_FAILED, f"{name}: {error}"))
    return failures
