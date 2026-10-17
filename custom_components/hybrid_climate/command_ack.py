"""Purpose: Acknowledge or time out device commands on every update cycle.

Key dependencies: models.Device, const.py (COMMAND_TIMEOUT_SECONDS,
EXTERNAL_CHANGE_TOLERANCE_F).
Used by: device_manager.DeviceManager.update_device_states.
"""
from __future__ import annotations

import logging
from collections.abc import Collection, Iterable
from datetime import datetime

from .const import COMMAND_TIMEOUT_SECONDS, EXTERNAL_CHANGE_TOLERANCE_F, HVAC_MODE_OFF
from .models import Device, DeviceCommandState

_LOGGER = logging.getLogger(__name__)


def _target_matches(device: Device) -> bool:
    """Return whether the reported target satisfies the commanded one."""
    # OFF or a mode-only command has no target to compare; some units report
    # no temperature attribute once off.
    if device.desired_mode == HVAC_MODE_OFF or device.desired_temp is None:
        return True
    reported = device.current_target_temp
    if isinstance(reported, bool) or not isinstance(reported, (int, float)):
        return False
    return abs(reported - device.desired_temp) <= EXTERNAL_CHANGE_TOLERANCE_F


def settle_commands(
    devices: Iterable[Device], now: datetime, skip: Collection[str] = (),
    sync_managed: Collection[str] = (),
) -> None:
    """Acknowledge or time out each available commanding device (display only).

    Unavailable devices keep their command state and are judged on their first
    available observation. Devices in skip (failed commands, still retrying)
    are left alone. A timeout only returns the state to LISTENING: desired_*
    and command_sent_at stay, because manual_override.py detects a physical
    edit from exactly that mismatch (it skips allow_command devices, which
    external_sync adopts). Devices in sync_managed (allow_command) that report
    a target leave the timeout to external_sync, which syncs desired to the
    report; those without a reported target are timed out here, desired_mode
    following the report and desired_temp kept.
    """
    for device in devices:
        if not device.is_commanding() or not device.is_available:
            continue
        if device.device_id in skip:
            continue
        if device.current_mode == device.desired_mode and _target_matches(device):
            device.command_acknowledged()
            _LOGGER.debug(
                "Device %s acknowledged command (mode=%s) -> LISTENING",
                device.device_id, device.current_mode,
            )
        elif device.command_sent_at is not None:
            elapsed = (now - device.command_sent_at).total_seconds()
            if elapsed <= COMMAND_TIMEOUT_SECONDS:
                continue
            if device.device_id in sync_managed:
                # external_sync times out sync devices that report a target; it skips
                # the rest, so settle those here with desired_mode following the report.
                if isinstance(device.current_target_temp, (int, float)):
                    continue
                _LOGGER.warning(
                    "Device %s command timeout after %ds (desired=%s, no reported target) -> LISTENING",
                    device.device_id, int(elapsed), device.desired_temp,
                )
                device.command_timeout(device.desired_temp, device.current_mode)
                continue
            _LOGGER.warning(
                "Device %s command timeout after %ds (desired=%s, current=%s) -> LISTENING",
                device.device_id, int(elapsed), device.desired_temp,
                device.current_target_temp,
            )
            device.command_state = DeviceCommandState.LISTENING
