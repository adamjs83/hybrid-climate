"""Purpose: Select idle heat floors, the takeover pass's cross-zone idle
target (idle_target), and track dispatched setback basis.

Key dependencies: Loaded config, conflict resolver latch, and device manager.
Used by: Regular release, startup takeover, and device dispatch.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .const import (
    HVAC_MODE_COOL, HVAC_MODE_HEAT, IDLE_SETPOINT_BASIS_LOCKOUT_FLOOR,
    IDLE_SETPOINT_BASIS_SETBACK,
)

if TYPE_CHECKING:
    from .conflict_resolver import ConflictResolver
    from .device_arbitration import DeviceRequest
    from .device_manager import DeviceManager
    from .models import Device, HybridClimateConfig, ZoneConfig, ZoneState

_LOGGER = logging.getLogger(__name__)


def idle_heat_floor(
    config: HybridClimateConfig, resolver: ConflictResolver, zone_ids: Iterable[str],
) -> float | None:
    """Return the floor only when every target-supplying zone is locked out."""
    selected = tuple(zone_ids)
    if selected and all(resolver.outdoor_heat_locked(zone_id) for zone_id in selected):
        return config.lockout_heat_floor
    return None


def idle_target(
    zones: list[tuple[ZoneConfig, ZoneState]], device_id: str, heating: bool,
) -> tuple[float | None, list[str]]:
    """Choose the most conservative idle target for the physical direction.

    Used by the startup-takeover/restore pass to pick a single idle target
    for a device referenced by more than one zone.
    """
    directional = [
        (zone, state) for zone, state in zones
        if any(device_id in stage.get_device_ids() for stage in
               (zone.heat_stages if heating else zone.cool_stages))
    ]
    selected = directional or zones
    targets = [
        (state.target_temperature if state.target_temperature is not None
         else zone.setpoints.default) if heating else state.target_temperature_cool
        for zone, state in selected
    ]
    available = [target for target in targets if target is not None]
    target = (min(available) if heating else max(available)) if available else None
    return target, [state.zone_id for _, state in selected]


def heat_idle_setpoint(target: float, setback: float, floor: float | None) -> tuple[float, str]:
    """Choose the lower heat setpoint and its recorded basis."""
    normal = target - setback
    if floor is not None and floor < normal:
        return floor, IDLE_SETPOINT_BASIS_LOCKOUT_FLOOR
    return normal, IDLE_SETPOINT_BASIS_SETBACK


class IdleBasisTracker:
    """Attach an idle heat basis only to a matching physical send."""

    def __init__(self) -> None:
        """Start with no queued idle requests or service sends."""
        self.pending: dict[str, tuple[float, str]] = {}
        self.sent_serial = 0

    def clear(self) -> None:
        """Discard queued idle requests at a cycle boundary."""
        self.pending.clear()

    def sent(self, device: Device) -> None:
        """Clear stale basis after any physical service send."""
        self.sent_serial += 1
        device.idle_setpoint_basis = None

    def record_idle(
        self, device: Device, target: float, basis: str, before_send: int,
        collecting: bool, success: bool,
    ) -> None:
        """Queue or attach a successful idle heat request's basis."""
        if not success:
            return
        if collecting:
            self.pending[device.device_id] = (target, basis)
        elif (self.sent_serial != before_send and device.desired_mode == HVAC_MODE_HEAT
              and device.desired_temp == target):
            device.idle_setpoint_basis = basis

    def attach_dispatched(
        self, device: Device, mode: str, target: float | None,
        owners: set[str], requests: list[DeviceRequest], before_send: int, success: bool,
    ) -> None:
        """Attach basis only when dispatch sent the queued idle heat target."""
        idle = self.pending.get(device.device_id)
        if (success and idle is not None and not owners and mode == HVAC_MODE_HEAT
                and target == idle[0] and (mode, target, None) in requests
                and self.sent_serial != before_send
                and device.desired_mode == mode and device.desired_temp == target):
            device.idle_setpoint_basis = idle[1]


async def apply_idle_setback(
    manager: DeviceManager, device: Device, zone_target_temp: float,
    was_heating: bool, heat_floor: float | None,
) -> bool:
    """Send an idle setback and record its basis after a matching heat send."""
    if was_heating:
        target, basis = heat_idle_setpoint(
            zone_target_temp, device.idle_config.setback, heat_floor,
        )
        mode = HVAC_MODE_HEAT
    else:
        target = zone_target_temp + device.idle_config.setback
        mode = HVAC_MODE_COOL
    _LOGGER.debug(
        "Device %s idle action: setback to %s in %s mode",
        device.device_id, target, mode,
    )
    # Desired state is updated by set_device_mode so external changes do not
    # propagate this idle setback back into the zone target.
    before_send = manager.idle_basis.sent_serial
    success = await manager.set_device_mode(device, mode, target)
    if was_heating:
        manager.idle_basis.record_idle(
            device, target, basis, before_send, manager._collecting, success,
        )
    return success
