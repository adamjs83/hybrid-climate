"""Purpose: Describe cached device ownership and unexplained active modes.

Key dependencies: Loaded device and zone states plus the diagnostics device view.
Used by: Agent API get_status device projection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..const import HVAC_MODE_COOL, HVAC_MODE_HEAT
from ..models import Device, ZoneState
from .const import UNCONTROLLED_MODE_DETAIL


def device_control(
    device_view: Mapping[str, Any], device: Device,
    zone_states: Mapping[str, ZoneState], zone_order: Sequence[str],
) -> dict[str, Any]:
    """Describe cached owners, desired control, and an unexplained active mode."""
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
    return {
        "owner_zones": owners,
        "commanded": device.desired_mode is not None,
        "uncontrolled_active_mode": uncontrolled,
        "detail": UNCONTROLLED_MODE_DETAIL.format(reported_mode=reported_mode)
        if uncontrolled else None,
    }
