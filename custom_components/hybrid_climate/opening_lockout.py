"""Per-zone door and window contact lockout state machine."""
from __future__ import annotations

from datetime import datetime

from homeassistant.core import HomeAssistant

from .models import OpeningConfig, ZoneState


def update_opening_lockout(
    hass: HomeAssistant, config: OpeningConfig | None, state: ZoneState, now: datetime
) -> bool:
    """Return whether equipment must be released for contact state.

    Any missing, unknown, or unavailable contact is locked immediately. A
    confirmed open contact uses the open delay; after a lockout, every contact
    must remain closed for the close delay before equipment may restart.
    """
    if config is None or not config.entities:
        state.opening_status = "disabled"
        state.opening_lockout = False
        state.opening_changed_at = None
        return False

    values = [hass.states.get(entity_id) for entity_id in config.entities]
    if any(value is None or value.state not in ("on", "off") for value in values):
        state.opening_status = "unknown"
        state.opening_lockout = True
        state.opening_changed_at = now
        return True

    if any(value.state == "on" for value in values):
        # An already-open contact on startup has an unknown open duration.
        if state.opening_status == "disabled":
            state.opening_status = "open"
            state.opening_lockout = True
            state.opening_changed_at = now
            return True
        if state.opening_status not in ("open", "open_pending"):
            state.opening_changed_at = now
        if state.opening_lockout or config.open_delay == 0 or (
            state.opening_changed_at is not None
            and (now - state.opening_changed_at).total_seconds() >= config.open_delay
        ):
            state.opening_status = "open"
            state.opening_lockout = True
        else:
            state.opening_status = "open_pending"
        return state.opening_lockout

    if state.opening_lockout:
        if state.opening_status != "close_pending":
            state.opening_changed_at = now
        if config.close_delay == 0 or (
            state.opening_changed_at is not None
            and (now - state.opening_changed_at).total_seconds() >= config.close_delay
        ):
            state.opening_lockout = False
            state.opening_status = "closed"
        else:
            state.opening_status = "close_pending"
    else:
        state.opening_status = "closed"
    return state.opening_lockout
