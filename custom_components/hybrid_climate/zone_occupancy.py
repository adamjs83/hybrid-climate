"""Purpose: Delay a zone occupancy sensor's transitions (on delay and off delay).

Key dependencies: Home Assistant clock and zone setpoint configuration.
Used by: setpoint_manager occupancy selection.
"""
from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import OCCUPANCY_ON_STATES
from .models import ZoneConfig


# On-since value for a sensor already on at the first observation: the on delay counts as served.
_LONG_AGO = datetime(1970, 1, 1, tzinfo=UTC)


def _in_off_grace(
    zone: ZoneConfig, last_observed_occupied: dict[str, datetime], now: datetime,
) -> bool:
    """Return True while inside the off-delay grace since this integration last saw occupied."""
    delay = zone.setpoints.occupancy_off_delay
    observed = last_observed_occupied.get(zone.zone_id)
    return bool(delay and observed is not None and (now - observed).total_seconds() < delay)


def get_occupancy(
    hass: HomeAssistant, zone: ZoneConfig, last_observed_occupied: dict[str, datetime],
    presence_on_since: dict[str, datetime | None] | None = None, now: datetime | None = None,
) -> bool | None:
    """Return occupancy: presence must stay on for the on delay; the off delay is a grace afterwards."""
    entity_id = zone.setpoints.occupancy_entity
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    now = now or dt_util.utcnow()
    on_since = presence_on_since if presence_on_since is not None else {}
    zone_id = zone.zone_id
    if state.state not in OCCUPANCY_ON_STATES:
        on_since[zone_id] = None
        return _in_off_grace(zone, last_observed_occupied, now)
    if zone_id not in on_since:
        on_since[zone_id] = _LONG_AGO  # First observation is on: occupied at once (restart rule)
    elif on_since[zone_id] is None:
        on_since[zone_id] = now
    started = on_since[zone_id]
    if started is not None and (now - started).total_seconds() >= zone.setpoints.occupancy_on_delay:
        last_observed_occupied[zone_id] = now  # Only a served on delay refreshes the off-delay grace
        return True
    # Pending: a blip shorter than the on delay changes nothing
    return _in_off_grace(zone, last_observed_occupied, now)
