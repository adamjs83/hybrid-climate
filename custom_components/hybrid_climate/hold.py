"""Purpose: Zone holds (spec v0.18.0 §1): start, end with resume, release, expiry and the seed apply.

A hold pins a zone's heat and cool targets so mode changes, occupancy flips and number edits
cannot move them (`setpoint_manager.apply_mode_setpoints` skips a held zone). It ends through
`end_hold` (switch off, preset `none`, the service), `expire_holds` (`until` reached) or Vacation,
all of which resume the saved temperatures; an external thermostat change uses `release_hold`,
which clears the hold without the resume. The switch, the zone preset and the service all call
these functions; there is no second code path.

Key dependencies: models.py (HoldState, ZoneState), setpoint_manager.py (mode setpoints, device push).
Used by: switch.py, zone_hold_attrs.py, setpoint_manager.py, external_sync.py, startup_seed.py,
coordinator.py, agent_api/service_handlers.py (set_hold), agent_api/status.py.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from . import setpoint_manager
from .const import HVAC_MODE_COOL, HVAC_MODE_HEAT
from .models import HoldState

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)

# Zone preset values and target sources (const.py is at its size limit; these live here).
HOLD_PRESET = "hold"
PRESET_NONE_VALUE = "none"
TARGET_SOURCE_HOLD = "hold"
TARGET_SOURCE_THERMOSTAT = "thermostat"
# Hold switch translation key and attribute names (switch and zone climate).
HOLD_KEY = "hold"
ATTR_HOLD_SINCE = "hold_since"
ATTR_HOLD_UNTIL = "hold_until"
ATTR_HELD_HEAT = "held_heat"
ATTR_HELD_COOL = "held_cool"
ATTR_TARGET_SOURCE = "target_source"


def hold_payload(hold: HoldState | None) -> dict[str, Any] | None:
    """Serialize a hold for get_status and set_hold: None, or ISO times and held targets."""
    if hold is None:
        return None
    return {
        "since": hold.since.isoformat(),
        "until": hold.until.isoformat() if hold.until else None,
        "heat": hold.heat,
        "cool": hold.cool,
    }


def _notify(coordinator: HybridClimateCoordinator) -> None:
    """Publish the switch and zone climate at once (absent on the isolated test coordinator)."""
    update = getattr(coordinator, "async_update_listeners", None)
    if callable(update):
        update()


def is_held(coordinator: HybridClimateCoordinator, zone_id: str) -> bool:
    """Return whether the zone has an active hold."""
    zone_state = coordinator.zone_states.get(zone_id)
    return zone_state is not None and zone_state.hold is not None


def start_hold(
    coordinator: HybridClimateCoordinator, zone_id: str, until: datetime | None = None,
) -> HoldState | None:
    """Hold the zone at its current heat and cool targets; on a held zone only update `until`."""
    zone_state = coordinator.zone_states.get(zone_id)
    if zone_state is None:
        _LOGGER.warning("Hold requested for unknown zone %s", zone_id)
        return None
    if zone_state.hold is not None:
        # A held zone keeps its targets and start time; only an explicit end time changes.
        if until is not None:
            zone_state.hold.until = until
            _LOGGER.info("Zone %s: hold now ends %s", zone_id, until.isoformat())
            _notify(coordinator)
        return zone_state.hold
    zone_state.hold = HoldState(
        since=dt_util.utcnow(), until=until,
        heat=coordinator._zone_target_temps.get(zone_id),
        cool=coordinator._zone_target_temps_cool.get(zone_id),
    )
    zone_state.target_source = TARGET_SOURCE_HOLD
    _LOGGER.info("Zone %s: hold started (heat=%s cool=%s until=%s)", zone_id,
                 zone_state.hold.heat, zone_state.hold.cool, until)
    _notify(coordinator)
    return zone_state.hold


def update_held_target(
    coordinator: HybridClimateCoordinator, zone_id: str, direction: str, temperature: float,
) -> None:
    """Record a card edit: update a held zone's value in that direction, or start a hold."""
    zone_state = coordinator.zone_states.get(zone_id)
    if zone_state is None or zone_state.hold is None:
        # start_hold captures both current targets, so a one-direction edit fills both.
        start_hold(coordinator, zone_id)
        return
    if direction == HVAC_MODE_COOL:
        zone_state.hold.cool = temperature
    else:
        zone_state.hold.heat = temperature
    # A range-card edit starts the hold on its first value; log the second so the
    # "hold started" line is not the last word on what is held (#495).
    _LOGGER.info("Zone %s: held %s target now %s", zone_id, direction, temperature)


def resume_hold_targets(coordinator: HybridClimateCoordinator, zone_id: str) -> bool:
    """Clear a hold and re-apply the zone's saved mode targets; return whether it was held.

    Synchronous so the seed, the cycle's expiry and Vacation can use it; the cycle then
    dispatches the resumed targets. `end_hold` also pushes them to active devices at once.
    """
    zone_state = coordinator.zone_states.get(zone_id)
    if zone_state is None or zone_state.hold is None:
        return False
    zone_state.hold = None
    setpoint_manager.apply_mode_setpoints(coordinator, zone_id)
    _LOGGER.info("Zone %s: hold ended, saved temperatures resumed", zone_id)
    _notify(coordinator)
    return True


async def end_hold(coordinator: HybridClimateCoordinator, zone_id: str) -> None:
    """End the hold, resume saved temperatures and push them to the zone's active devices."""
    if not resume_hold_targets(coordinator, zone_id):
        return
    # Heat first, then cool; each push only reaches active devices in that direction.
    for direction, targets in ((HVAC_MODE_HEAT, coordinator._zone_target_temps),
                               (HVAC_MODE_COOL, coordinator._zone_target_temps_cool)):
        target = targets.get(zone_id)
        if target is not None:
            await setpoint_manager._immediate_device_update(coordinator, zone_id, direction, target)


def release_hold(coordinator: HybridClimateCoordinator, zone_id: str) -> None:
    """Clear a hold without resuming (an accepted external thermostat change, decision 9)."""
    zone_state = coordinator.zone_states.get(zone_id)
    if zone_state is None or zone_state.hold is None:
        return
    zone_state.hold = None
    _LOGGER.info("Zone %s: hold released by an external thermostat change", zone_id)
    _notify(coordinator)


def expire_holds(coordinator: HybridClimateCoordinator, now: datetime) -> list[str]:
    """End every timed hold whose `until` has passed (resume path); return their zone ids."""
    expired = [
        zone_id for zone_id, zone_state in coordinator.zone_states.items()
        if zone_state.hold is not None and zone_state.hold.until is not None
        and zone_state.hold.until <= now
    ]
    for zone_id in expired:
        resume_hold_targets(coordinator, zone_id)
    return expired


def end_holds_for_vacation(coordinator: HybridClimateCoordinator) -> None:
    """End every hold before Vacation applies (a forgotten hold must not heat an empty house)."""
    for zone_id in [z for z, state in coordinator.zone_states.items() if state.hold is not None]:
        resume_hold_targets(coordinator, zone_id)


def apply_held_targets(coordinator: HybridClimateCoordinator) -> None:
    """Set each held zone's targets from its hold (the seed; apply_mode_setpoints skips them)."""
    for zone_id, zone_state in coordinator.zone_states.items():
        hold = zone_state.hold
        if hold is None:
            continue
        if hold.heat is not None:
            coordinator._zone_target_temps[zone_id] = hold.heat
            zone_state.target_temperature = hold.heat
        if hold.cool is not None:
            coordinator._zone_target_temps_cool[zone_id] = hold.cool
            zone_state.target_temperature_cool = hold.cool
        zone_state.target_source = TARGET_SOURCE_HOLD
