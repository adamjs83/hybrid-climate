"""Purpose: Detect devices whose physical state was changed outside Hybrid Climate.

A device is in manual override when it is available and not in failed_commands,
not an allow_command device for any zone (external_sync.py already adopts those
changes into the zone target and resyncs desired_* to the physical values, so a
mismatch there is a propagated sync, not an override), has a settled desired
command (desired_mode is not None), is outside the 60s in-flight command window
(command_sent_at is None or older than COMMAND_TIMEOUT_SECONDS -- never
is_commanding(), which never clears for a non-allow_command device), and its
reported mode/target differs from that desired command by more than tolerance
(spec v0.13.2 §3.1, amendments A5-A7). When a device reports no
`target_temp_step` attribute at all (e.g. a real Nest entity, which reports
whole degrees), the tolerance falls back to HA's own default step for the
configured unit system (review round 1 item 1).

`evaluate()` runs once per successful coordinator cycle, from
control_restore.post_cycle, after StartupTakeover.record() has applied this
cycle's restore outcomes. Inside the in-flight window the tracker changes
nothing for a device -- neither raising nor clearing (A5). An active override
clears only when the reported state matches the desired command again.

Key dependencies: models.Device (desired_mode/desired_temp/command_sent_at/
matches_desired), zone_helpers.get_allow_command_devices_for_zone, Home
Assistant's logbook component.
Used by: coordinator.py (manual_overrides instance), control_restore.post_cycle,
agent_api.device_control, agent_api.entity_view, binary_sensor.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components import logbook
from homeassistant.components.climate.const import ATTR_TARGET_TEMP_STEP
from homeassistant.const import UnitOfTemperature
from homeassistant.util import dt as dt_util

from .const import (
    COMMAND_TIMEOUT_SECONDS,
    DEFAULT_TARGET_TEMP_STEP_C,
    DEFAULT_TARGET_TEMP_STEP_F,
    DOMAIN,
    EXTERNAL_CHANGE_TOLERANCE_F,
    MANUAL_OVERRIDE_LOG_MESSAGE_FORMAT,
)
from .zone_helpers import get_allow_command_devices_for_zone

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator
    from .models import Device

_LOGGER = logging.getLogger(__name__)


@dataclass
class OverrideInfo:
    """One device's currently active manual-override event."""

    commanded_mode: str | None
    commanded_target: float | None
    reported_mode: str | None
    reported_target: float | None
    since: datetime

    def as_dict(self) -> dict[str, Any]:
        """Project into the get_status/binary_sensor override shape."""
        return {
            "commanded": {"mode": self.commanded_mode, "target": self.commanded_target},
            "reported": {"mode": self.reported_mode, "target": self.reported_target},
            "since": self.since.isoformat(),
        }


class ManualOverrideTracker:
    """Track devices whose physical state diverges from Hybrid Climate's command."""

    def __init__(self) -> None:
        """Start with no device flagged."""
        self.active: dict[str, OverrideInfo] = {}

    def get(self, device_id: str) -> OverrideInfo | None:
        """Return the active override for a device, if any."""
        return self.active.get(device_id)

    def evaluate(self, coordinator: HybridClimateCoordinator) -> None:
        """Re-run the override rule for every device after a successful cycle."""
        manager = coordinator.device_manager
        allow_command_devices = _allow_command_device_ids(coordinator)
        now = dt_util.utcnow()
        for device_id, device in manager.devices.items():
            if not _eligible(device, device_id, manager.failed_commands, allow_command_devices):
                # Rules 1-3 fail: this device cannot be an override. Changing
                # nothing here mirrors A5 -- the only way an active entry
                # clears is a reported-matches-desired result below.
                continue
            if _in_flight(device, now):
                # A5: inside the 60s command window, change nothing either way.
                continue
            tolerance = _tolerance(coordinator, device)
            if _differs(device, device.current_mode, device.current_target_temp, tolerance):
                self._raise_or_update(coordinator, device_id, device, now)
            else:
                self._clear(device_id)
        for device_id in list(self.active):
            if device_id not in manager.devices:
                del self.active[device_id]

    def _raise_or_update(
        self, coordinator: HybridClimateCoordinator, device_id: str, device: Device, now: datetime,
    ) -> None:
        """Create a new override event, or update an existing one's reported values."""
        existing = self.active.get(device_id)
        if existing is None:
            info = OverrideInfo(
                commanded_mode=device.desired_mode, commanded_target=device.desired_temp,
                reported_mode=device.current_mode, reported_target=device.current_target_temp,
                since=now,
            )
            self.active[device_id] = info
            self._log_override(coordinator, device_id, device, info)
        else:
            # Still overridden: refresh in place so a 71->72 drift does not
            # open a second event, and a later restore's new command is
            # reflected without resetting `since`.
            existing.commanded_mode = device.desired_mode
            existing.commanded_target = device.desired_temp
            existing.reported_mode = device.current_mode
            existing.reported_target = device.current_target_temp

    def _clear(self, device_id: str) -> None:
        """Clear an active override once reported matches desired again (A5)."""
        if self.active.pop(device_id, None) is not None:
            _LOGGER.info("Manual override cleared for %s", device_id)

    def _log_override(
        self, coordinator: HybridClimateCoordinator, device_id: str, device: Device, info: OverrideInfo,
    ) -> None:
        """Write exactly one logbook entry for this override's transition into active."""
        message = MANUAL_OVERRIDE_LOG_MESSAGE_FORMAT.format(
            commanded=_format_command(info.commanded_mode, info.commanded_target),
            reported=_format_command(info.reported_mode, info.reported_target),
        )
        _LOGGER.warning("Manual override detected on %s: %s", device_id, message)
        try:
            logbook.async_log_entry(
                coordinator.hass, device_id, message, domain=DOMAIN, entity_id=device.entity_id,
            )
        except Exception:
            _LOGGER.exception("Manual override logbook entry failed for %s", device_id)


def _eligible(
    device: Device, device_id: str, failed_commands: set[str], allow_command_devices: set[str],
) -> bool:
    """Rules 1-3: available, not failed, not allow_command, has a desired command."""
    return (
        device.is_available
        and device_id not in failed_commands
        and device_id not in allow_command_devices
        and device.desired_mode is not None
    )


def _in_flight(device: Device, now: datetime) -> bool:
    """Rule 4: inside the 60s in-flight window since the last sent command."""
    return (
        device.command_sent_at is not None
        and (now - device.command_sent_at).total_seconds() < COMMAND_TIMEOUT_SECONDS
    )


def _differs(
    device: Device, reported_mode: str | None, reported_target: float | None, tolerance: float,
) -> bool:
    """Rule 5, guarding a None reported target to compare mode only (A5)."""
    if reported_mode is None:
        return False
    if reported_target is None:
        return reported_mode != device.desired_mode
    return not device.matches_desired(reported_target, reported_mode, tolerance)


def _allow_command_device_ids(coordinator: HybridClimateCoordinator) -> set[str]:
    """Union of every zone's allow_command devices (rule 2 exclusion)."""
    devices: set[str] = set()
    for zone in coordinator.config.zones.values():
        devices.update(get_allow_command_devices_for_zone(zone))
    return devices


def _default_target_temp_step(coordinator: HybridClimateCoordinator) -> float:
    """HA's own default climate step for the configured unit system (review
    round 1 item 1): a real Nest entity reports no target_temp_step at all,
    but still only moves in whole-degree Fahrenheit increments."""
    unit = coordinator.hass.config.units.temperature_unit
    return DEFAULT_TARGET_TEMP_STEP_C if unit == UnitOfTemperature.CELSIUS else DEFAULT_TARGET_TEMP_STEP_F


def _tolerance(coordinator: HybridClimateCoordinator, device: Device) -> float:
    """A7: max(EXTERNAL_CHANGE_TOLERANCE_F, target_temp_step / 2); target_temp_step
    comes from the device's live attributes, or HA's per-unit default when absent."""
    state = coordinator.hass.states.get(device.entity_id)
    step = state.attributes.get(ATTR_TARGET_TEMP_STEP) if state else None
    if step is None:
        step = _default_target_temp_step(coordinator)
    return max(EXTERNAL_CHANGE_TOLERANCE_F, step / 2)


def _format_command(mode: str | None, target: float | None) -> str:
    """Format a mode/target pair for the logbook message, e.g. 'heat 55.0'."""
    return f"{mode} {target}" if target is not None else f"{mode}"
