"""Purpose: Run a re-armable idle-takeover pass over unowned active devices.

One pass applies a single successful idle action (or forced OFF) to each
unowned, control-referenced device, retried every cycle until it succeeds or
a done-rule applies. `arm()` starts the original startup pass; `rearm()`/
`request_rearm()` let a master-mode-change or manual restore start a new pass
over the same machinery (spec v0.13.2 §1, amendments A1-A4/A9/A16). `outcomes`
always belongs to `pass_id`, the pass currently applied; a caller holding a
different id was superseded before its request ever became current (A2).

Key dependencies: Zone references, device manager, and release disabled rules.
Used by: The coordinator's successful update cycles and control_restore.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .const import (
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    IDLE_ACTION_SETBACK,
    REGULATION_PI,
    RESTORE_OUTCOME_BLOCKED_RETRY,
    RESTORE_OUTCOME_IN_FLIGHT_RETRY,
    RESTORE_OUTCOME_MISSING_TEMPERATURE_RETRY,
    RESTORE_OUTCOME_NOT_FOUND,
    RESTORE_OUTCOME_NOT_HEAT_OR_COOL,
    RESTORE_OUTCOME_OWNED,
    RESTORE_OUTCOME_PENDING_NORMAL_REQUEST,
    RESTORE_OUTCOME_PI_REGULATED,
    RESTORE_OUTCOME_SENT,
    RESTORE_OUTCOME_UNAVAILABLE_RETRY,
    RESTORE_OUTCOME_UNCHANGED,
    RESTORE_SOURCE_STARTUP,
)
from .device_release import zone_disabled
from .idle_floor import idle_heat_floor, idle_target
from .restore_scope import merge_zone_scope, zones_for_scope
from .zone_helpers import get_all_zone_devices

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator
    from .models import Device, ZoneState

_LOGGER = logging.getLogger(__name__)


@dataclass
class PassOutcome:
    """One device's result within the current takeover/restore pass."""

    code: str
    mode: str | None = None
    target: float | None = None


class StartupTakeover:
    """Queue a single successful idle action per device for the current pass."""

    def __init__(self) -> None:
        """Initialize with no armed pass and no pending rearm request."""
        self.armed = False
        self.finished = False
        self.done: set[str] = set()
        self.applied_at: dict[str, datetime | None] = {}
        self.applied_source: dict[str, str] = {}
        self.source: str = RESTORE_SOURCE_STARTUP
        self.pass_id: int = 0
        self.outcomes: dict[str, PassOutcome] = {}
        self._candidates: set[str] = set()
        self._queued: set[str] = set()
        self._queued_active: dict[str, Device] = {}
        self._queued_devices: dict[str, Device] = {}
        self._queued_last_command_at: dict[str, datetime | None] = {}
        self._pending_requests: list[tuple[str, str | frozenset[str] | None, int]] = []
        self._pass_request_seq: int = 0

    def arm(self, coordinator: HybridClimateCoordinator) -> None:
        """Capture control-referenced devices after the first successful cycle."""
        self.rearm(coordinator, RESTORE_SOURCE_STARTUP)

    def request_rearm(self, source: str, zone_id: str | frozenset[str] | None = None) -> int:
        """Queue a pending rearm request, applied at the start of queue() (A2).

        Keeps its own entry until applied, merging with any others still
        waiting only then (review round 2 item 1) -- cancelling one request
        never drops another still-waiting one.
        """
        self._pass_request_seq += 1
        pass_id = self._pass_request_seq
        self._pending_requests.append((source, zone_id, pass_id))
        return pass_id

    def is_pending(self, device_id: str) -> bool:
        """Return whether a device is still a candidate of the current pass (A4)."""
        return device_id in self._candidates and device_id not in self.done

    def is_request_pending(self, pass_id: int) -> bool:
        """Return whether a still-unapplied request owns this pass_id."""
        return any(entry[2] == pass_id for entry in self._pending_requests)

    def cancel_pending_request(self, pass_id: int) -> None:
        """Drop only this still-unapplied request; any others keep waiting."""
        self._pending_requests = [
            entry for entry in self._pending_requests if entry[2] != pass_id
        ]

    def rearm(
        self,
        coordinator: HybridClimateCoordinator,
        source: str = RESTORE_SOURCE_STARTUP,
        zone_id: str | frozenset[str] | None = None,
        *,
        pass_id: int | None = None,
    ) -> None:
        """Start a new pass; its scope unions any still-pending devices (A4)."""
        zones = zones_for_scope(coordinator.config, zone_id)
        scope_candidates: set[str] = (
            set().union(*(get_all_zone_devices(zone) for zone in zones.values()))
            if zones else set()
        )
        # A new pass replaces the old one, but never drops a still-pending device.
        previous_pending = (
            {device_id for device_id in self._candidates if self.is_pending(device_id)}
            if self.armed else set()
        )
        carried_outcomes = {
            device_id: outcome for device_id, outcome in self.outcomes.items()
            if device_id in previous_pending
        }
        self._candidates = scope_candidates | previous_pending
        pi_regulated = {
            device_id
            for zone in coordinator.config.zones.values()
            if zone.regulation and zone.regulation.type == REGULATION_PI
            for device_id in zone.regulation.devices
        }
        self.done = pi_regulated & self._candidates
        self.outcomes = carried_outcomes
        for device_id in self.done:
            self.outcomes[device_id] = PassOutcome(RESTORE_OUTCOME_PI_REGULATED)
        self.source = source
        if pass_id is not None:
            self.pass_id = pass_id
        self.armed = True
        self.finished = self._candidates <= self.done
        self._queued.clear()
        self._queued_active.clear()
        self._queued_devices.clear()
        self._queued_last_command_at.clear()

    def _apply_pending_rearm(self, coordinator: HybridClimateCoordinator) -> None:
        """Merge and apply every pending request (A2); ignored before the
        startup pass has armed (A1). The merged pass takes its source/pass_id
        from the last request -- both map to the same awaiting/applied
        reason, so this is harmless (review round 2 item 2)."""
        if not self._pending_requests:
            return
        if not self.armed:
            _LOGGER.debug("%s takeover: ignoring requests made before arming",
                          self.source.replace("_", "-").capitalize())
            self._pending_requests = []
            return
        source, zone_id, pass_id = self._pending_requests[0]
        for next_source, next_zone_id, next_pass_id in self._pending_requests[1:]:
            zone_id = merge_zone_scope(zone_id, next_zone_id)
            source, pass_id = next_source, next_pass_id
        self._pending_requests = []
        self.rearm(coordinator, source, zone_id, pass_id=pass_id)

    @staticmethod
    def _enabled(
        coordinator: HybridClimateCoordinator, state: ZoneState,
    ) -> bool:
        """Check whether a referencing zone may currently request control."""
        return not (zone_disabled(coordinator, state) or state.opening_lockout)

    @staticmethod
    def _reported_matches_desired(device: Device | None) -> bool:
        """Compare a device's physical state against its own desired command."""
        if device is None:
            return False
        if device.desired_mode is None:
            return True
        if device.desired_mode == HVAC_MODE_OFF:
            return device.current_mode == HVAC_MODE_OFF
        if device.current_target_temp is None:
            return device.current_mode == device.desired_mode and device.desired_temp is None
        return device.matches_desired(device.current_target_temp, device.current_mode)

    async def queue(self, coordinator: HybridClimateCoordinator) -> None:
        """Apply a pending rearm, then queue this pass's actions for the cycle."""
        self._apply_pending_rearm(coordinator)
        if not self.armed or self.finished:
            return
        manager = coordinator.device_manager
        prefix = self.source.replace("_", "-").capitalize()
        for device_id in sorted(self._candidates - self.done):
            # Existing ownership or a normal request hands control to the normal path.
            if any(device_id in state.active_devices for state in coordinator.zone_states.values()):
                self.done.add(device_id)
                self.outcomes[device_id] = PassOutcome(RESTORE_OUTCOME_OWNED)
                continue
            if manager.has_pending_device(device_id):
                self.done.add(device_id)
                self.outcomes[device_id] = PassOutcome(RESTORE_OUTCOME_PENDING_NORMAL_REQUEST)
                continue
            device = manager.get_device(device_id)
            if device is None:
                _LOGGER.warning("%s takeover: device %s not found", prefix, device_id)
                self.done.add(device_id)
                self.outcomes[device_id] = PassOutcome(RESTORE_OUTCOME_NOT_FOUND)
                continue
            if not device.is_available:
                self.outcomes[device_id] = PassOutcome(RESTORE_OUTCOME_UNAVAILABLE_RETRY)
                continue
            if device.current_mode not in (HVAC_MODE_HEAT, HVAC_MODE_COOL):
                self.done.add(device_id)
                self.outcomes[device_id] = PassOutcome(RESTORE_OUTCOME_NOT_HEAT_OR_COOL)
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
                self.outcomes[device_id] = PassOutcome(RESTORE_OUTCOME_MISSING_TEMPERATURE_RETRY)
                continue
            if not enabled:
                await manager.turn_off_device(device, force_off=True)
            else:
                heating = device.can_heat() and (
                    not device.can_cool() or device.current_mode != HVAC_MODE_COOL
                )
                target, suppliers = idle_target(enabled, device_id, heating)
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
            self._queued_last_command_at[device_id] = device.last_command_at
            self._queued.add(device_id)
            self._queued_devices[device_id] = device
        if self._candidates <= self.done:
            self.finished = True

    def record(self, command_results: dict[str, bool]) -> None:
        """Finish successful requests and leave blocked requests eligible to retry."""
        prefix = self.source.replace("_", "-").capitalize()
        for device_id in self._queued:
            device = self._queued_devices.get(device_id)
            before = self._queued_last_command_at.get(device_id)
            if command_results.get(device_id) is True:
                sent = device is not None and device.last_command_at != before
                if sent or self._reported_matches_desired(device):
                    code = RESTORE_OUTCOME_SENT if sent else RESTORE_OUTCOME_UNCHANGED
                    self.done.add(device_id)
                    if device is not None:
                        self.applied_at[device_id] = device.last_command_at
                        self.applied_source[device_id] = self.source
                    active_device = self._queued_active.get(device_id)
                    if active_device is not None and active_device.current_mode == HVAC_MODE_OFF:
                        _LOGGER.info("%s takeover: %s turned off by device mutex", prefix, device_id)
                    else:
                        _LOGGER.info("%s takeover: applied idle action to %s", prefix, device_id)
                else:
                    # The 60s COMMANDING short-circuit returned True without sending
                    # while the device still differs physically; keep retrying (A3).
                    code = RESTORE_OUTCOME_IN_FLIGHT_RETRY
                    _LOGGER.debug("%s takeover: in-flight retry for %s", prefix, device_id)
            else:
                code = RESTORE_OUTCOME_BLOCKED_RETRY
                _LOGGER.debug("%s takeover: pending retry for %s", prefix, device_id)
            self.outcomes[device_id] = PassOutcome(
                code,
                device.desired_mode if device is not None else None,
                device.desired_temp if device is not None else None,
            )
        self._queued.clear()
        self._queued_active.clear()
        self._queued_devices.clear()
        self._queued_last_command_at.clear()
        if self.armed and self._candidates <= self.done:
            self.finished = True
