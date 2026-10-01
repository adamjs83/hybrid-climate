"""Purpose: Describe cached device ownership, unexplained active modes, and control reason.

Key dependencies: Loaded device/zone state models, the startup takeover tracker,
and the manual-override tracker.
Used by: Agent API get_status device projection and entity_view device snapshots.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from ..const import HVAC_MODE_COOL, HVAC_MODE_HEAT, RESTORE_SOURCE_STARTUP
from ..capability_check import CapabilityMismatch
from ..models import Device, ZoneState
from .const import (
    CONTROL_REASON_AWAITING_CONTROL_RESTORE,
    CONTROL_REASON_AWAITING_STARTUP_TAKEOVER,
    CONTROL_REASON_CONTROL_RESTORED,
    CONTROL_REASON_MANUAL_OVERRIDE,
    CONTROL_REASON_NEVER_OWNED_SINCE_START,
    CONTROL_REASON_MISSING_STAGE_CAPABILITY,
    CONTROL_REASON_NOT_REFERENCED,
    CONTROL_REASON_OWNED_ACTIVE,
    CONTROL_REASON_RELEASED_IDLE,
    CONTROL_REASON_TAKEN_OVER_AT_STARTUP,
    UNCONTROLLED_MODE_DETAIL,
)

if TYPE_CHECKING:
    from ..manual_override import ManualOverrideTracker, OverrideInfo
    from ..startup_takeover import StartupTakeover


def _control_reason(
    device: Device,
    owners: Sequence[str],
    referenced_zones: Sequence[str],
    pi_regulated: bool,
    takeover: StartupTakeover,
    missing_capabilities: Sequence[CapabilityMismatch] = (),
    override: OverrideInfo | None = None,
) -> str:
    """Pick the first matching cached-state explanation per spec §7.6 precedence."""
    if not referenced_zones:
        return CONTROL_REASON_NOT_REFERENCED
    if override is not None:
        return CONTROL_REASON_MANUAL_OVERRIDE
    if owners:
        return CONTROL_REASON_OWNED_ACTIVE
    # The candidate set is only materialized at arm()/rearm(); before arming,
    # mirror what arm() would compute: every control-referenced device is a
    # candidate unless it belongs to a PI-regulated zone (PI devices are
    # excluded from every pass). Once armed, use the pass's own pending set
    # (A4) rather than just "not in done".
    is_candidate = (
        takeover.is_pending(device.device_id) if takeover.armed else not pi_regulated
    )
    if not takeover.finished and is_candidate:
        return (
            CONTROL_REASON_AWAITING_STARTUP_TAKEOVER if takeover.source == RESTORE_SOURCE_STARTUP
            else CONTROL_REASON_AWAITING_CONTROL_RESTORE
        )
    if (device.device_id in takeover.applied_at
            and takeover.applied_at[device.device_id] == device.last_command_at):
        applied_source = takeover.applied_source.get(device.device_id, RESTORE_SOURCE_STARTUP)
        return (
            CONTROL_REASON_TAKEN_OVER_AT_STARTUP if applied_source == RESTORE_SOURCE_STARTUP
            else CONTROL_REASON_CONTROL_RESTORED
        )
    if device.desired_mode is not None:
        return CONTROL_REASON_RELEASED_IDLE
    if missing_capabilities:
        return CONTROL_REASON_MISSING_STAGE_CAPABILITY
    return CONTROL_REASON_NEVER_OWNED_SINCE_START


def device_control(
    device_view: Mapping[str, Any],
    device: Device,
    zone_states: Mapping[str, ZoneState],
    zone_order: Sequence[str],
    referenced_zones: Sequence[str],
    pi_regulated: bool,
    takeover: StartupTakeover,
    missing_capabilities: Sequence[CapabilityMismatch] = (),
    overrides: ManualOverrideTracker | None = None,
) -> dict[str, Any]:
    """Describe cached owners, desired control, an unexplained active mode, and reason."""
    owners = [zone_id for zone_id in zone_order
              if device.device_id in zone_states[zone_id].active_devices]
    reported_mode = device_view["reported_mode"]
    # A pending command can leave the physical mode stale after ownership ends.
    uncontrolled = (
        reported_mode in (HVAC_MODE_HEAT, HVAC_MODE_COOL)
        and not owners
        and device.desired_mode != reported_mode
        and not device.is_commanding()
    )
    override = overrides.get(device.device_id) if overrides is not None else None
    return {
        "owner_zones": owners,
        "commanded": device.desired_mode is not None,
        "idle_setpoint_basis": device.idle_setpoint_basis,
        "uncontrolled_active_mode": uncontrolled,
        "detail": UNCONTROLLED_MODE_DETAIL.format(reported_mode=reported_mode)
        if uncontrolled else None,
        "reason": _control_reason(device, owners, referenced_zones, pi_regulated, takeover,
                                  missing_capabilities, override),
        "override": override.as_dict() if override is not None else None,
        "missing_capabilities": [
            {"zone": item.zone, "stage": item.stage, "capability": item.capability}
            for item in missing_capabilities
        ],
    }
