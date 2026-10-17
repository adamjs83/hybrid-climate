"""Purpose: Zone climate hold attributes, the hold preset, and attributes that survive a restart.

Publishes `hold_until`, `target_source` and the zone's last known occupancy (`occupied`, which
the startup seed uses when the occupancy sensor is unreadable at setup, #491), and maps the zone
climate's `hold`/`none` preset onto hold.py.

Key dependencies: coordinator.py (`_zone_occupancy`, `_zone_restored_occupancy`), hold.py.
Used by: zone.py (async_added_to_hass restore, extra_state_attributes, preset mode).
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .const import ATTR_OCCUPIED
from .hold import (
    ATTR_HOLD_UNTIL, ATTR_TARGET_SOURCE, HOLD_PRESET, PRESET_NONE_VALUE, end_hold, is_held,
    start_hold,
)

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


def restore_zone_attributes(
    coordinator: HybridClimateCoordinator, zone_id: str, attributes: Mapping[str, Any],
) -> None:
    """Store a zone's restored attributes on the coordinator for the startup seed."""
    occupied = attributes.get(ATTR_OCCUPIED)
    if isinstance(occupied, bool):
        coordinator._zone_restored_occupancy[zone_id] = occupied
        _LOGGER.debug("Zone %s: restored occupied %s", zone_id, occupied)


def zone_hold_attributes(coordinator: HybridClimateCoordinator, zone_id: str) -> dict[str, Any]:
    """Return the zone climate's hold end, target source and last known occupancy."""
    zone_state = coordinator.zone_states.get(zone_id)
    hold = zone_state.hold if zone_state is not None else None
    return {
        ATTR_HOLD_UNTIL: hold.until.isoformat() if hold is not None and hold.until else None,
        ATTR_TARGET_SOURCE: zone_state.target_source if zone_state is not None else None,
        ATTR_OCCUPIED: coordinator._zone_occupancy.get(zone_id),
    }


def zone_preset_mode(coordinator: HybridClimateCoordinator, zone_id: str) -> str:
    """Return the zone climate preset: `hold` while held, otherwise `none`."""
    return HOLD_PRESET if is_held(coordinator, zone_id) else PRESET_NONE_VALUE


async def async_set_zone_preset(
    coordinator: HybridClimateCoordinator, zone_id: str, preset: str,
) -> None:
    """Start an untimed hold for `hold`; end the hold (resume) for `none`."""
    if preset == HOLD_PRESET:
        start_hold(coordinator, zone_id)
    elif preset == PRESET_NONE_VALUE:
        await end_hold(coordinator, zone_id)
    else:
        _LOGGER.warning("Zone %s: unsupported preset %s", zone_id, preset)
