"""Purpose: Seed every zone's operating targets once at startup, before the first dispatch (#491).

The coordinator is built before the master climate restores its preset, before the setpoint
numbers exist and before occupancy sensors are necessarily readable, so targets computed in its
constructor can be stale. This seed runs after the platforms (and their restored state) are set
up and before the first refresh; until it has run, the coordinator skips the whole control
cycle (no zone update, takeover arming or dispatch).

Key dependencies: setpoint_manager.py (occupancy lookup, mode setpoint application), hold.py
(expiry of restored holds and their held targets).
Used by: __init__.py (async_setup_entry, between platform setup and the first refresh).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from . import setpoint_manager
from .hold import apply_held_targets, expire_holds

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


def seed_targets(coordinator: HybridClimateCoordinator) -> None:
    """Apply saved (or held) targets once, after entities restored and before the first dispatch."""
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
    # A restored hold whose end passed while HA was down resumes; live holds keep their values.
    expire_holds(coordinator, dt_util.utcnow())
    setpoint_manager.apply_mode_setpoints(coordinator)  # skips held zones
    apply_held_targets(coordinator)
    coordinator.targets_seeded = True
    _LOGGER.info("Startup seed applied targets for %d zones", len(coordinator.config.zones))
