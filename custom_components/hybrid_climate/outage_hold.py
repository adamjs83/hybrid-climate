"""Purpose: Preserve a running stage during a brief loss of its owned device.

Key dependencies: ZoneState, DeviceManager, and the global grace setting.
Used by: Zone staging and Agent API status projection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from .const import HVAC_MODE_HEAT
from .models import ZoneState

if TYPE_CHECKING:
    from .device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)


def unavailable_owned_devices(
    state: ZoneState, wanted_ids: list[str], manager: DeviceManager, mode: str | None = None,
) -> list[str]:
    """Identify wanted, owned devices lost only because they are unavailable."""
    return [ident for ident in wanted_ids if ident in state.active_devices
            and (device := manager.get_device(ident)) is not None
            and not device.is_available
            and (mode is None or (device.can_heat() if mode == HVAC_MODE_HEAT else device.can_cool()))]


def should_hold_outage(
    state: ZoneState, wanted_ids: list[str], manager: DeviceManager,
    grace: int, now: datetime, has_usable_devices: bool, mode: str,
) -> bool:
    """Keep an active stage until its unavailable owned device exceeds grace."""
    missing = unavailable_owned_devices(state, wanted_ids, manager, mode)
    if has_usable_devices or not state.current_stage or not missing or grace <= 0:
        if state.outage_hold_since is not None and has_usable_devices:
            _LOGGER.info("Zone %s: device returned; ending stage outage hold", state.zone_id)
        state.outage_hold_since = None
        return False
    if state.outage_hold_since is None:
        state.outage_hold_since = now
        _LOGGER.info(
            "Zone %s: holding stage %s through unavailable %s for up to %d s",
            state.zone_id, state.current_stage.rsplit("_", 1)[-1], ", ".join(missing), grace,
        )
    if (now - state.outage_hold_since).total_seconds() < grace:
        return True
    state.outage_hold_since = None
    return False


def outage_hold_payload(
    state: ZoneState, manager: DeviceManager, grace: int,
) -> dict[str, Any] | None:
    """Describe the cached outage hold for status consumers."""
    since = state.outage_hold_since
    if since is None:
        return None
    devices = unavailable_owned_devices(state, state.active_devices, manager)
    return {"since": since.isoformat(), "until": (since + timedelta(seconds=grace)).isoformat(),
            "devices": devices}
