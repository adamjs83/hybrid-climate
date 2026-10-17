"""Purpose: Seed every zone's operating targets once at startup, before the first dispatch (#491).

The coordinator is built before the master climate restores its preset, before the setpoint
numbers exist and before occupancy sensors are necessarily readable, so targets computed in its
constructor can be stale. This seed runs after the platforms (and their restored state) are set
up and before the first refresh; until it has run, the coordinator skips the whole control
cycle (no zone update, takeover arming or dispatch). A zone whose occupancy sensor has no state yet
and whose climate restored no `occupied` attribute (the first restart onto v0.18.0, #496) is
`occupancy_pending`: `resolve_pending_occupancy` keeps skipping cycles until the sensor reports or
`SEED_OCCUPANCY_WAIT_SECONDS` pass, then applies the saved targets before the first dispatch.

Key dependencies: setpoint_manager.py (occupancy lookup, mode setpoint application), hold.py
(expiry of restored holds and their held targets).
Used by: __init__.py (async_setup_entry, between platform setup and the first refresh).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from . import setpoint_manager
from .const import SEED_OCCUPANCY_WAIT_SECONDS
from .hold import apply_held_targets, expire_holds

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


def seed_targets(coordinator: HybridClimateCoordinator) -> None:
    """Apply saved (or held) targets once, after entities restored and before the first dispatch."""
    pending: set[str] = set()
    for zone_id, zone in coordinator.config.zones.items():
        if not zone.setpoints.occupancy_entity:
            # No sensor configured (e.g. removed in options): a restored value would never be replaced.
            coordinator._zone_restored_occupancy.pop(zone_id, None)
            coordinator._zone_occupancy[zone_id] = None
            continue
        live = setpoint_manager.get_zone_occupancy(coordinator, zone)
        # An unreadable sensor falls back to the occupancy the zone climate last published.
        if live is None and zone_id in coordinator._zone_restored_occupancy:
            coordinator._zone_occupancy[zone_id] = coordinator._zone_restored_occupancy[zone_id]
        else:
            coordinator._zone_occupancy[zone_id] = live
            if live is None:
                # Nothing to fall back to: wait for the sensor rather than dispatch default targets.
                pending.add(zone_id)
    coordinator.occupancy_pending = pending
    coordinator.occupancy_wait_until = (
        dt_util.utcnow() + timedelta(seconds=SEED_OCCUPANCY_WAIT_SECONDS) if pending else None)
    if pending:
        _LOGGER.info("Startup seed: occupancy unknown for %s; waiting up to %ds for the sensors before the first command",
                     sorted(pending), SEED_OCCUPANCY_WAIT_SECONDS)
    # A restored hold whose end passed while HA was down resumes; live holds keep their values.
    expire_holds(coordinator, dt_util.utcnow())
    setpoint_manager.apply_mode_setpoints(coordinator)  # skips held zones
    apply_held_targets(coordinator)
    coordinator.targets_seeded = True
    _LOGGER.info("Startup seed applied targets for %d zones", len(coordinator.config.zones))


def resolve_pending_occupancy(coordinator: HybridClimateCoordinator, now: datetime) -> bool:
    """Apply targets for pending zones whose sensor now reports; return whether control may run this cycle."""
    # Test doubles without the attribute have nothing pending.
    pending = getattr(coordinator, "occupancy_pending", None)
    if not pending:
        return True
    for zone_id in sorted(pending):
        zone = coordinator.config.zones.get(zone_id)
        live = setpoint_manager.get_zone_occupancy(coordinator, zone) if zone is not None else None
        if zone is not None and live is None:
            continue
        if zone is not None:
            coordinator._zone_occupancy[zone_id] = live
            setpoint_manager.apply_mode_setpoints(coordinator, zone_id)  # skips a held zone
        pending.discard(zone_id)
    if not pending:
        return True
    if coordinator.occupancy_wait_until is not None and now < coordinator.occupancy_wait_until:
        _LOGGER.debug("Occupancy still unknown for %s; skipping control cycle", sorted(pending))
        return False
    # The sensors never reported: control on the saved default targets rather than wait forever.
    _LOGGER.warning("Occupancy sensors of %s did not report within %ds of startup; controlling on default targets",
                    sorted(pending), SEED_OCCUPANCY_WAIT_SECONDS)
    pending.clear()
    return True
