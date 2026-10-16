"""Purpose: Resolve, rate-limit and record the per-device cooling regulation offset.

The signed offset (°F) is added to the resolved zone cool target of an owned
cooling command: off 0, overdrive -cool_overdrive, compensation unit - room
(clamped), pi inert (0) in this release. Compensation and pi pass a per-device
limiter that mirrors regulation_limits for heating.

Key dependencies: Device and ZoneState runtime fields in models.py, const.py modes.
Used by: device_arbitration.dispatch_requests (dispatch and bookkeeping) and
device_manager.update_device_states (unit reading).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
import logging
import math
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    ATTR_CURRENT_TEMPERATURE,
    COOL_REGULATION_COMPENSATION,
    COOL_REGULATION_OVERDRIVE,
    COOL_REGULATION_PI,
    HVAC_MODE_COOL,
    REGULATION_THRESHOLD_FLOAT_TOLERANCE,
)
from .models import Device, ZoneState

_LOGGER = logging.getLogger(__name__)

CoolRequest = tuple[str, float | None, str | None]


def read_unit_temperature(device: Device, climate_state: Any, sensor_state: Any) -> float | None:
    """Return the unit's own reading from its compensation sensor or climate entity, never raising."""
    if device.cool_compensation_sensor:
        if sensor_state is None or sensor_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        raw = sensor_state.state
    else:
        if climate_state is None:
            return None
        raw = climate_state.attributes.get(ATTR_CURRENT_TEMPERATURE)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    # NaN or inf would clamp to a limit instead of falling back; treat as missing.
    return value if math.isfinite(value) else None


def _set_fallback(device: Device, fallback: bool) -> None:
    """Record the compensation fallback flag, logging only on transitions."""
    if fallback and not device.cool_regulation_fallback:
        _LOGGER.warning(
            "Device %s: cooling compensation reading unavailable; raw offset falls back to 0 "
            "(still subject to the limiter) until it returns",
            device.device_id,
        )
    elif not fallback and device.cool_regulation_fallback:
        _LOGGER.info("Device %s: cooling compensation reading recovered", device.device_id)
    device.cool_regulation_fallback = fallback


def resolve_cool_offset(device: Device, zone_state: ZoneState | None, now: datetime) -> float:
    """Return the raw signed offset for the device's cooling regulation mode (before the limiter)."""
    mode = device.cool_regulation
    if mode == COOL_REGULATION_OVERDRIVE:
        return -device.cool_overdrive
    if mode == COOL_REGULATION_COMPENSATION:
        unit = device.current_temperature
        room = zone_state.current_temperature if zone_state is not None else None
        if unit is None or room is None:
            _set_fallback(device, True)
            return 0.0
        _set_fallback(device, False)
        limit = device.cool_compensation_max
        # Plus sign: the unit stops when its own sensor reads what it reads
        # while the room sits at target; never push harder than the maximum.
        return max(-limit, min(limit, unit - room))
    # Off, and pi until the cooling PI release, send the zone target unchanged.
    return 0.0


def limit_cool_offset(device: Device, raw: float, target: float | None, now: datetime) -> float:
    """Return the last sent offset until the threshold and minimum period both pass."""
    previous = device.last_sent_cool_offset
    last_time = device.last_cool_offset_time
    # A first owned send, a changed zone target or a cleared limiter sends at once.
    if previous is None or last_time is None or target != device.last_cool_offset_target:
        send = True
    else:
        send = (
            abs(raw - previous) >= device.cool_regulation_threshold - REGULATION_THRESHOLD_FLOAT_TOLERANCE
            and now - last_time >= timedelta(minutes=device.cool_regulation_min_period)
        )
    if send:
        device.last_sent_cool_offset = raw
        device.last_cool_offset_time = now
        device.last_cool_offset_target = target
        return raw
    return previous if previous is not None else raw


def clear_cool_limiter(device: Device) -> None:
    """Forget the last sent offset so the next owned cooling command sends immediately."""
    device.last_sent_cool_offset = None
    device.last_cool_offset_time = None
    device.last_cool_offset_target = None


def record_cool_dispatch(device: Device, owned_cool: bool, offset: float, success: bool) -> None:
    """Commit the sent offset after a dispatch; clear the limiter when nothing owned was sent."""
    if not success:
        # A failed or blocked send leaves the old physical target and its
        # recorded offset in place; the next owned send starts fresh.
        clear_cool_limiter(device)
    elif owned_cool:
        device.cool_offset_sent = offset
    else:
        device.cool_offset_sent = 0.0
        clear_cool_limiter(device)


def select_owner_state(
    zone_states: Mapping[str, ZoneState] | None, requests: Iterable[CoolRequest],
    target: float | None, owners: set[str],
) -> ZoneState | None:
    """Return the first owner zone, in config order, whose cool request supplied the target."""
    if not zone_states:
        return None
    supplying = {zone_id for mode, temp, zone_id in requests if mode == HVAC_MODE_COOL and temp == target}
    for zone_id, state in zone_states.items():
        if zone_id in supplying and zone_id in owners:
            return state
    return None


def cool_dispatch_target(
    device: Device, zone_state: ZoneState | None, target: float, now: datetime,
) -> tuple[float, float]:
    """Return the physical target and the limited offset for an owned cooling command."""
    offset = resolve_cool_offset(device, zone_state, now)
    # Overdrive and off are constants; only regulated modes pass the limiter.
    if device.cool_regulation in (COOL_REGULATION_COMPENSATION, COOL_REGULATION_PI):
        offset = limit_cool_offset(device, offset, target, now)
    return target + offset, offset


def warn_pi_inert(device: Device, warned: set[str]) -> None:
    """Warn once per device (per manager) that cooling PI is not active yet."""
    if device.cool_regulation == COOL_REGULATION_PI and device.device_id not in warned:
        warned.add(device.device_id)
        _LOGGER.warning(
            "Device %s: cool_regulation pi sends offset 0; cooling PI arrives in a later release",
            device.device_id,
        )
