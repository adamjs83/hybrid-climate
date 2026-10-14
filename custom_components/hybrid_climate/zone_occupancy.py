"""Purpose: Delay only a zone occupancy sensor's transition to unoccupied.

Key dependencies: Home Assistant clock and zone setpoint configuration.
Used by: setpoint_manager occupancy selection.
"""
from __future__ import annotations

from datetime import datetime

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import OCCUPANCY_ON_STATES
from .models import ZoneConfig


def get_occupancy(
    hass: HomeAssistant, zone: ZoneConfig, last_observed_occupied: dict[str, datetime],
) -> bool | None:
    """Return occupancy with a grace period since this integration last saw occupied."""
    entity_id = zone.setpoints.occupancy_entity
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    if state.state in OCCUPANCY_ON_STATES:
        last_observed_occupied[zone.zone_id] = dt_util.utcnow()
        return True
    delay = zone.setpoints.occupancy_off_delay
    observed = last_observed_occupied.get(zone.zone_id)
    if delay and observed is not None and (dt_util.utcnow() - observed).total_seconds() < delay:
        return True
    return False
