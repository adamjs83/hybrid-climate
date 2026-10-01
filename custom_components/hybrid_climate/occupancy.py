"""Purpose: Auto-switch master home/away mode and reapply zone occupancy setpoints.

Key dependencies: setpoint_manager (setpoint reapplication), models.MasterMode.
Used by: coordinator.py's update cycle (moved out per v0.13.2 §1 amendment A12).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import setpoint_manager
from .const import OCCUPANCY_ON_STATES
from .models import MasterMode

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


def check_master_occupancy(coordinator: HybridClimateCoordinator) -> None:
    """Check master occupancy entity and auto-switch home/away mode.

    Only switches between HOME and AWAY modes automatically. Other modes
    (VACATION, BOOST, OFF) are not affected. A settled auto-switch notes a
    mode change for the restore-control debounce (spec §1.2, ruling S5).
    """
    occupancy_entity = coordinator.config.master.occupancy_entity
    if not occupancy_entity:
        return

    # Only auto-switch if currently in HOME or AWAY mode
    if coordinator.master_state.mode not in (MasterMode.HOME, MasterMode.AWAY):
        return

    state = coordinator.hass.states.get(occupancy_entity)
    if state is None:
        _LOGGER.debug(
            "Master occupancy entity %s not found",
            occupancy_entity,
        )
        return

    is_occupied = state.state in OCCUPANCY_ON_STATES

    # Auto-switch based on occupancy
    if is_occupied and coordinator.master_state.mode == MasterMode.AWAY:
        _LOGGER.info(
            "Master occupancy: home detected, switching from AWAY to HOME"
        )
        coordinator.master_state.mode = MasterMode.HOME
        setpoint_manager.apply_mode_setpoints(coordinator)
        coordinator.control_restore.note_mode_change()
    elif not is_occupied and coordinator.master_state.mode == MasterMode.HOME:
        _LOGGER.info(
            "Master occupancy: away detected, switching from HOME to AWAY"
        )
        coordinator.master_state.mode = MasterMode.AWAY
        setpoint_manager.apply_mode_setpoints(coordinator)
        coordinator.control_restore.note_mode_change()


def check_zone_occupancy(coordinator: HybridClimateCoordinator) -> None:
    """Reapply a zone's effective targets when its occupancy changes.

    This is a setpoint recalculation, not a master mode change, so it never
    notes a mode change for the restore-control debounce.
    """
    for zone_id, zone in coordinator.config.zones.items():
        occupied = setpoint_manager.get_zone_occupancy(coordinator, zone)
        previous = coordinator._zone_occupancy.get(zone_id)
        if occupied is None:
            continue
        if occupied != previous:
            coordinator._zone_occupancy[zone_id] = occupied
            mode_config = setpoint_manager.get_current_mode_config(coordinator)
            # Ignore occupancy changes when the selected preset does not use it.
            if setpoint_manager._selected_setpoint_name(
                coordinator.master_state.mode, mode_config, previous
            ) != setpoint_manager._selected_setpoint_name(
                coordinator.master_state.mode, mode_config, occupied
            ):
                setpoint_manager.apply_mode_setpoints(coordinator, zone_id)
