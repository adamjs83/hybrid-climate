"""Purpose: Run a cooling device in fan_only after a release to dry its coil.

Key dependencies: DeviceManager (set_device_mode, set_device_idle, has_pending_device),
idle_floor.idle_target, device_release.zone_disabled, zone_helpers.get_all_zone_devices.
Used by: device_release.reconcile_devices (start_dry_out) and the coordinator cycle
(CoilDryOut.queue, before the failed-command cleanup, retained demand and mutex releases).
dispatch_requests clears dry_out_until on any successful non-fan_only command.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import COMMAND_TIMEOUT_SECONDS, HVAC_MODE_FAN_ONLY, IDLE_ACTION_OFF
from .idle_floor import idle_target
from .zone_helpers import get_all_zone_devices

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator
    from .models import Device

_LOGGER = logging.getLogger(__name__)


async def start_dry_out(coordinator: HybridClimateCoordinator, device: Device, now: datetime) -> bool:
    """Queue fan_only for a released cooling device and stamp its dry-out window."""
    success = await coordinator.device_manager.set_device_mode(device, HVAC_MODE_FAN_ONLY)
    if success:
        # Stamped when queued: a failed dispatch keeps ownership, so the device
        # still reports cool and the next release re-queues and re-stamps it.
        device.dry_out_until = now + timedelta(minutes=device.cool_dry_out_minutes)
        _LOGGER.info("Device %s: drying coil in fan_only until %s", device.device_id, device.dry_out_until)
    return success


def _fan_only_in_flight(device: Device, now: datetime) -> bool:
    """Return True while our own fan_only command awaits the device's report."""
    return (
        device.is_commanding() and device.desired_mode == HVAC_MODE_FAN_ONLY
        and device.command_sent_at is not None
        and (now - device.command_sent_at).total_seconds() < COMMAND_TIMEOUT_SECONDS
    )


def _owned_devices(coordinator: HybridClimateCoordinator) -> set[str]:
    """Return every device a zone currently owns."""
    return {
        device_id for state in coordinator.zone_states.values() for device_id in state.active_devices
    }


class CoilDryOut:
    """Recover dry-out windows after a restart and finish them when they expire."""

    def __init__(self) -> None:
        """Start with recovery still pending for every device in this process."""
        # Device IDs whose restart recovery has been decided; a device is
        # decided on its first available observation, not on the first cycle.
        self.recovered: set[str] = set()

    async def queue(self, coordinator: HybridClimateCoordinator) -> None:
        """Queue the idle action for expired windows; recover open ones once per device.

        The stamp is cleared by dispatch when that idle action succeeds; a failed
        send keeps it, so the same idle action is queued again next cycle.
        """
        manager = coordinator.device_manager
        now = dt_util.utcnow()
        owned = _owned_devices(coordinator)
        for device in manager.devices.values():
            if device.device_id in self.recovered or not device.is_available:
                continue
            # A restart mid-window leaves the unit in fan_only with no stamp;
            # give it one bounded window rather than leaving it running.
            self.recovered.add(device.device_id)
            if (device.cool_dry_out and device.current_mode == HVAC_MODE_FAN_ONLY
                    and device.device_id not in owned and device.dry_out_until is None):
                device.dry_out_until = now + timedelta(minutes=device.cool_dry_out_minutes)
                _LOGGER.info("Device %s: recovered coil dry-out until %s",
                             device.device_id, device.dry_out_until)

        for device in manager.devices.values():
            if device.dry_out_until is None:
                continue
            # A request queued this cycle (the dry-out itself, new demand) is
            # settled by dispatch; the reported mode is not current yet.
            if manager.has_pending_device(device.device_id):
                continue
            if device.current_mode != HVAC_MODE_FAN_ONLY:
                # A stale report while our fan_only is still in flight is not a
                # change; keep the window until the device reports fan_only.
                if _fan_only_in_flight(device, now):
                    continue
                # Dispatch clears the stamp for our own commands; this catches a
                # mode changed outside the integration (remote, HA UI).
                device.dry_out_until = None
                continue
            if now < device.dry_out_until or device.device_id in owned or not device.is_available:
                continue
            await self._queue_idle(coordinator, device)

    @staticmethod
    async def _queue_idle(coordinator: HybridClimateCoordinator, device: Device) -> None:
        """Queue the device's normal cooling idle action for its enabled zones."""
        # Imported here: device_release imports this module for start_dry_out.
        from .device_release import zone_disabled

        manager = coordinator.device_manager
        enabled = [
            (zone, coordinator.zone_states[zone_id])
            for zone_id, zone in coordinator.config.zones.items()
            if device.device_id in get_all_zone_devices(zone)
            and not zone_disabled(coordinator, coordinator.zone_states[zone_id])
        ]
        target, _ = idle_target(enabled, device.device_id, heating=False) if enabled else (None, [])
        _LOGGER.info("Device %s: coil dry-out finished, applying idle action", device.device_id)
        if device.idle_config.action == IDLE_ACTION_OFF or target is None:
            await manager.turn_off_device(device)
        else:
            await manager.set_device_idle(device, target, False)
