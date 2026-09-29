"""Purpose: Apply one idle action to unowned active devices after startup.

Key dependencies: Zone references, device manager, and release disabled rules.
Used by: The coordinator's successful update cycles.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .const import HVAC_MODE_COOL, HVAC_MODE_HEAT, HVAC_MODE_OFF, IDLE_ACTION_SETBACK, REGULATION_PI
from .device_release import zone_disabled
from .idle_floor import idle_heat_floor
from .zone_helpers import get_all_zone_devices

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator
    from .models import Device, ZoneConfig, ZoneState

_LOGGER = logging.getLogger(__name__)


class StartupTakeover:
    """Queue a single successful idle action for each eligible startup device."""

    def __init__(self) -> None:
        """Initialize the one-time takeover state."""
        self.armed = False
        self.finished = False
        self.done: set[str] = set()
        self.applied_at: dict[str, datetime | None] = {}
        self._candidates: set[str] = set()
        self._queued: set[str] = set()
        self._queued_active: dict[str, Device] = {}
        self._queued_devices: dict[str, Device] = {}

    def arm(self, coordinator: HybridClimateCoordinator) -> None:
        """Capture control-referenced devices after the first successful cycle."""
        self._candidates = set().union(*(
            get_all_zone_devices(zone) for zone in coordinator.config.zones.values()
        ))
        self.done = {
            device_id
            for zone in coordinator.config.zones.values()
            if zone.regulation and zone.regulation.type == REGULATION_PI
            for device_id in zone.regulation.devices
        }
        self.armed = True
        self.finished = self._candidates <= self.done

    @staticmethod
    def _enabled(
        coordinator: HybridClimateCoordinator, state: ZoneState,
    ) -> bool:
        """Check whether a referencing zone may currently request control."""
        return not (zone_disabled(coordinator, state) or state.opening_lockout)

    @staticmethod
    def _target(
        zones: list[tuple[ZoneConfig, ZoneState]], device_id: str, heating: bool,
    ) -> tuple[float | None, list[str]]:
        """Choose the most conservative target for the physical direction."""
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

    async def queue(self, coordinator: HybridClimateCoordinator) -> None:
        """Queue takeover actions after normal zone demand has been collected."""
        if not self.armed or self.finished:
            return
        manager = coordinator.device_manager
        for device_id in sorted(self._candidates - self.done):
            # Existing ownership or a normal request hands control to the normal path.
            if any(device_id in state.active_devices for state in coordinator.zone_states.values()):
                self.done.add(device_id)
                continue
            if manager.has_pending_device(device_id):
                self.done.add(device_id)
                continue
            device = manager.get_device(device_id)
            if device is None:
                _LOGGER.warning("Startup takeover: device %s not found", device_id)
                self.done.add(device_id)
                continue
            if not device.is_available:
                continue
            if device.current_mode not in (HVAC_MODE_HEAT, HVAC_MODE_COOL):
                self.done.add(device_id)
                continue
            referenced = [
                (zone, coordinator.zone_states[zone_id])
                for zone_id, zone in coordinator.config.zones.items()
                if device_id in get_all_zone_devices(zone)
            ]
            enabled = [
                (zone, state) for zone, state in referenced
                if self._enabled(coordinator, state)
            ]
            # Missing readings in any enabled zone may hide imminent demand.
            if any(state.current_temperature is None for _, state in enabled):
                continue
            if not enabled:
                await manager.turn_off_device(device, force_off=True)
            else:
                heating = device.can_heat() and (
                    not device.can_cool() or device.current_mode != HVAC_MODE_COOL
                )
                target, suppliers = self._target(enabled, device_id, heating)
                if target is None or not (device.can_heat() or device.can_cool()):
                    await manager.turn_off_device(device)
                else:
                    await manager.set_device_idle(
                        device, target, heating,
                        heat_floor=idle_heat_floor(
                            coordinator.config, coordinator.conflict_resolver, suppliers,
                        ) if heating else None,
                    )
                    if device.idle_config.action == IDLE_ACTION_SETBACK:
                        self._queued_active[device_id] = device
            self._queued.add(device_id)
            self._queued_devices[device_id] = device
        if self._candidates <= self.done:
            self.finished = True

    def record(self, command_results: dict[str, bool]) -> None:
        """Finish successful requests and leave blocked requests eligible to retry."""
        for device_id in self._queued:
            if command_results.get(device_id) is True:
                self.done.add(device_id)
                device = self._queued_devices.get(device_id)
                # A short-circuit success (nothing sent this cycle) still records the
                # device's current last_command_at, possibly None.
                self.applied_at[device_id] = device.last_command_at if device is not None else None
                active_device = self._queued_active.get(device_id)
                if active_device is not None and active_device.current_mode == HVAC_MODE_OFF:
                    _LOGGER.info("Startup takeover: %s turned off by device mutex", device_id)
                else:
                    _LOGGER.info("Startup takeover: applied idle action to %s", device_id)
            else:
                _LOGGER.debug("Startup takeover: pending retry for %s", device_id)
        self._queued.clear()
        self._queued_active.clear()
        self._queued_devices.clear()
        if self.armed and self._candidates <= self.done:
            self.finished = True
