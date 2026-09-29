"""Purpose: Project cached per-zone TOU state into Agent API status responses.

Key dependencies: TouManager's per-zone adjustment cache and the rate sensor's
cached HA state (a plain state read, never a control call).
Used by: Agent API get_status zone projection (status.py).
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from ..const import TOU_STATE_PEAK_RELAXED, TOU_STATE_PRE_CONDITIONING
from ..models import ZoneConfig
from ..tou_manager import TouManager
from .const import TOU_MODE_PEAK_RELAXATION, TOU_MODE_PRE_CONDITIONING

# The internal TOU state machine spells peak relaxation "peak_relaxed"; the
# Agent API publishes the more descriptive "peak_relaxation" instead. Normal
# state (and any other value) maps to None, matching "before first application".
_MODE_MAP = {
    TOU_STATE_PEAK_RELAXED: TOU_MODE_PEAK_RELAXATION,
    TOU_STATE_PRE_CONDITIONING: TOU_MODE_PRE_CONDITIONING,
}


def _rate_period(hass: HomeAssistant, rate_sensor: str | None) -> str | None:
    """Read the rate sensor's cached HA state; unconfigured/unavailable is None."""
    if not rate_sensor:
        return None
    state = hass.states.get(rate_sensor)
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    return state.state


def zone_tou(
    hass: HomeAssistant, tou_manager: TouManager, rate_sensor: str | None, zone: ZoneConfig,
) -> dict[str, Any]:
    """Describe a zone's TOU configuration and last-applied adjustment, read-only."""
    if zone.tou is None:
        # Per spec §7.1, "Zones without TOU" is the complete inactive shape.
        # The cache is never consulted here: TOU can be removed from a zone by
        # a reload without another get_adjusted_setpoints call happening first
        # (that call only runs from the zone update loop), so a cached peak or
        # pre-conditioning adjustment from before removal must never leak into
        # an inactive zone's projection.
        return {
            "active": False, "period": None, "mode": None,
            "relaxation_applied_heat": 0.0, "relaxation_applied_cool": 0.0,
        }
    adjustment = tou_manager.last_adjustment(zone.zone_id)
    return {
        "active": True,
        "period": _rate_period(hass, rate_sensor),
        "mode": _MODE_MAP.get(adjustment["tou_state"]),
        "relaxation_applied_heat": adjustment["relaxation_applied_heat"],
        "relaxation_applied_cool": adjustment["relaxation_applied_cool"],
    }
