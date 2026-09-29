"""Purpose: Resolve shared demand and reconcile zones after physical dispatch.

Key dependencies: device manager, conflict resolver, zone state models.
Used by: coordinator and device manager during each control cycle.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import HVAC_MODE_COOL, HVAC_MODE_HEAT, HVAC_MODE_OFF
from .models import DeviceMutexRule, HvacAction, ZoneState

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator
    from .device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)

DeviceRequest = tuple[str, float | None, str | None]


def resolve_requests(requests: list[DeviceRequest]) -> tuple[str, float | None, set[str]]:
    """Prefer active demand, then heat over cool, with max heat or min cool."""
    active = [request for request in requests if request[2] is not None]
    selected = active or requests
    for mode, aggregate in ((HVAC_MODE_HEAT, max), (HVAC_MODE_COOL, min)):
        matching = [request for request in selected if request[0] == mode]
        if matching:
            targets = [temp for _, temp, _ in matching if temp is not None]
            return mode, aggregate(targets) if targets else None, {
                zone_id for _, _, zone_id in matching if zone_id is not None
            }
    return HVAC_MODE_OFF, None, set()


async def queue_retained_demand(coordinator: HybridClimateCoordinator) -> None:
    """Include unchanged owners held by minimum runtime or sensor failure."""
    manager = coordinator.device_manager
    for zone_id, state in coordinator.zone_states.items():
        if state.hvac_action not in (HvacAction.HEATING, HvacAction.COOLING):
            continue
        for device_id in state.active_devices:
            if manager.has_pending_zone_request(device_id, zone_id):
                continue
            device = manager.get_device(device_id)
            if device is None or not device.is_available:
                continue
            # Sensor loss holds the physical command; minimum runtime retains
            # this zone's own target so a shared owner cannot overwrite it.
            mode = HVAC_MODE_HEAT if state.hvac_action == HvacAction.HEATING else HVAC_MODE_COOL
            target = state.target_temperature if mode == HVAC_MODE_HEAT else state.target_temperature_cool
            regulation = coordinator.config.zones[zone_id].regulation
            if regulation and device_id in regulation.devices and mode == HVAC_MODE_HEAT:
                target = state.regulated_setpoint
            if not state.is_available:
                mode, target = device.current_mode, device.current_target_temp
            if mode in (HVAC_MODE_HEAT, HVAC_MODE_COOL):
                await manager.set_device_mode(device, mode, target, zone_id=zone_id)


async def queue_mutex_releases(coordinator: HybridClimateCoordinator) -> None:
    """Filter incompatible demand and queue releases in the same dispatch batch."""
    manager = coordinator.device_manager
    # Filtering can reveal a previously losing direction on a shared device.
    # Re-evaluate until no new rule activates; requests only disappear, so this
    # terminates even for cyclic mutex configurations.
    processed: set[int] = set()
    while True:
        active_rules = [
            (index, rule) for index, rule in enumerate(coordinator.config.conflicts.device_mutex)
            if index not in processed and (
                coordinator.conflict_resolver.mutex_rule_active(rule)
                or manager.has_pending_mode(rule.device_id, rule.mode)
            )
        ]
        if not active_rules:
            return
        for index, rule in active_rules:
            processed.add(index)
            for mode, device_ids, zone_ids in (
                (HVAC_MODE_HEAT, rule.blocked_devices_heat, rule.block_heat),
                (HVAC_MODE_COOL, rule.blocked_devices_cool, rule.block_cool),
            ):
                for device_id in device_ids:
                    device = manager.get_device(device_id)
                    # Include running devices even when their zone supplied no demand.
                    if device and device.current_mode == mode:
                        _LOGGER.warning("Mutex: %s blocks %s in %s", rule.device_id, device_id, mode)
                        await manager.turn_off_device(device, force_off=True)
                    manager.block_pending_mode(device_id, mode)
                for zone_id in zone_ids:
                    manager.block_pending_mode(rule.device_id, mode, zone_id)


def reconcile_dispatch(
    coordinator: HybridClimateCoordinator,
    previous: dict[str, ZoneState],
    results: dict[str, bool],
) -> None:
    """Commit ownership and PI growth only for successful, accepted demand."""
    manager = coordinator.device_manager
    for zone_id, state in coordinator.zone_states.items():
        before = previous[zone_id]
        requested = set(state.active_devices)
        failed_owned = {d for d in before.active_devices if results.get(d) is False}
        accepted = {
            d for d in requested if results.get(d, True)
            and (d not in results or zone_id in manager.accepted_zone_requests[d]
                 or (state.hvac_action == HvacAction.IDLE
                     and manager.get_device(d).current_mode == HVAC_MODE_HEAT
                     and not manager.accepted_zone_requests[d]))
        }
        state.active_devices = sorted(accepted | failed_owned)
        if failed_owned:
            # A rejected release has not started the reversal delay.
            state.last_direction_stop_time = before.last_direction_stop_time
        elif before.active_devices and not state.active_devices:
            state.last_direction_stop_time = dt_util.utcnow()

        regulation = coordinator.config.zones[zone_id].regulation
        if (regulation and state.hvac_action == HvacAction.HEATING
                and requested.intersection(regulation.devices)
                and not any(
                    d in accepted and results.get(d) is True
                    and zone_id in manager.accepted_zone_requests[d]
                    and manager.get_device(d).current_mode == HVAC_MODE_HEAT
                    for d in regulation.devices
                )):
            state.accumulated_error = before.accumulated_error
            state.last_pi_update_time = before.last_pi_update_time
            state.regulation_offset = before.regulation_offset
            state.regulated_setpoint = before.regulated_setpoint

        if not accepted:
            # Preserve prior control state on failed release/refresh; a new
            # failed or arbitration-losing activation must not latch a direction.
            state.last_active_action = before.last_active_action
            if failed_owned:
                state.hvac_mode = before.hvac_mode
                state.hvac_action = before.hvac_action
                state.current_stage = before.current_stage
                state.stage_start_time = before.stage_start_time
                state.escalated_at = before.escalated_at
            else:
                if state.hvac_action in (HvacAction.HEATING, HvacAction.COOLING):
                    state.hvac_action = HvacAction.IDLE
                state.current_stage = None
                state.stage_start_time = None
                state.escalated_at = None


async def dispatch_requests(
    manager: DeviceManager, rules: list[DeviceMutexRule],
) -> dict[str, bool]:
    """Dispatch aggregate commands after incompatible equipment is stopped."""
    results: dict[str, bool] = {}
    commands = {
        device_id: resolve_requests(requests)
        for device_id, requests in manager._pending_commands.items()
    }
    # OFF commands run first so a new priority direction cannot start before
    # its incompatible equipment has successfully stopped.
    for device_id in sorted(commands, key=lambda key: commands[key][0] != HVAC_MODE_OFF):
        mode, target, owners = commands[device_id]
        manager.accepted_zone_requests[device_id] = owners
        requests = manager._pending_commands[device_id]
        if (any(r[0] == HVAC_MODE_HEAT for r in requests)
                and any(r[0] == HVAC_MODE_COOL for r in requests)):
            _LOGGER.warning("Device %s has conflicting heat/cool demand; %s wins", device_id, mode)
        # Failed mutex releases must not permit a conflicting start.
        blocked = any(
            rule.device_id == device_id and rule.mode == mode
            and any(
                (device := manager.get_device(other_id)) is not None
                and device.current_mode == other_mode
                for other_mode, ids in (
                    (HVAC_MODE_HEAT, rule.blocked_devices_heat),
                    (HVAC_MODE_COOL, rule.blocked_devices_cool),
                ) for other_id in ids
            ) for rule in rules or []
        )
        if blocked:
            _LOGGER.warning("Device %s: waiting for mutex equipment to release", device_id)
            results[device_id] = False
            continue
        results[device_id] = await manager._dispatch_device_mode(
            manager.devices[device_id], mode, target,
            force_off=device_id in manager._forced_off_devices,
        )
    manager._pending_commands.clear()
    manager._forced_off_devices.clear()
    return results
