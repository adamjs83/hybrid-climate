"""Purpose: Resolve, rate-limit and record the per-device cooling regulation offset.

The signed offset (°F) is added to the resolved zone cool target of an owned
cooling command: off 0, overdrive -cool_overdrive, compensation min(0, unit - room)
(clamped), pi the owner zone's cooling PI offset (cool_pi.py), and pi with
cool_pi_compensation max(-cool_max_total_push, PI offset + clamp(unit - room)).
The unit-minus-room part is 0 for the first minutes of each owned cooling run (the
settle). Compensation and pi pass a per-device limiter that mirrors
regulation_limits for heating.

Key dependencies: Device and ZoneState runtime fields in models.py, const.py modes,
cool_pi_const.py settle length.
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
from .cool_pi_const import COOL_COMPENSATION_SETTLE_MINUTES
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


def uses_sensor_part(device: Device) -> bool:
    """True when the device's mode adds the unit-minus-room sensor part."""
    return device.cool_regulation == COOL_REGULATION_COMPENSATION or (
        device.cool_regulation == COOL_REGULATION_PI and device.cool_pi_compensation)


def _sensor_part(device: Device, zone_state: ZoneState | None, low: float, high: float) -> float:
    """Return clamp(unit - room, low, high), or 0 with the fallback flag when either reading is missing."""
    unit = device.current_temperature
    room = zone_state.current_temperature if zone_state is not None else None
    if unit is None or room is None:
        _set_fallback(device, True)
        return 0.0
    _set_fallback(device, False)
    return max(low, min(high, unit - room))


def resolve_cool_offset(
    device: Device, zone_state: ZoneState | None, now: datetime, *, settling: bool = False,
) -> float:
    """Return the raw signed offset for the device's cooling regulation mode (before the limiter)."""
    mode = device.cool_regulation
    part = 0.0
    if mode == COOL_REGULATION_OVERDRIVE:
        raw = -device.cool_overdrive
    elif mode == COOL_REGULATION_COMPENSATION:
        # Plus sign: the unit stops when its own sensor reads what it reads
        # while the room sits at target; never push harder than the maximum.
        # Push only (v0.17.2 owner ruling, as Versatile Thermostat uses it "to force"):
        # a unit reading above the room already works hard, so the target is never raised.
        # While settling the reading is not used, so the fallback flag is left alone.
        if not settling:
            part = _sensor_part(device, zone_state, -device.cool_compensation_max, 0.0)
        raw = part
    elif mode == COOL_REGULATION_PI:
        # The zone's cooling PI step (cool_pi.py) already holds -push <= 0.
        push = zone_state.cool_regulation_offset if zone_state is not None else 0.0
        if device.cool_pi_compensation:
            # Both ways (spec §1): translate the PI target onto the unit's own scale,
            # never lowering it by more than the maximum total push.
            if not settling:
                limit = device.cool_compensation_max
                part = _sensor_part(device, zone_state, -limit, limit)
            raw = max(-device.cool_max_total_push, push + part)
        else:
            raw = push
    else:
        # Off sends the zone target unchanged.
        raw = 0.0
    device.cool_compensation_part = part
    return raw


def limit_cool_offset(
    device: Device, raw: float, target: float | None, now: datetime, *, force: bool = False,
) -> float:
    """Return the last sent offset until the threshold and minimum period both pass, unless forced."""
    previous = device.last_sent_cool_offset
    last_time = device.last_cool_offset_time
    # A forced send (settle end), a first owned send, a changed zone target or a
    # cleared limiter sends at once.
    if force or previous is None or last_time is None or target != device.last_cool_offset_target:
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
    """Forget the last sent offset and the cooling run so the next owned command sends and settles anew."""
    device.last_sent_cool_offset = None
    device.last_cool_offset_time = None
    device.last_cool_offset_target = None
    device.cool_run_started_at = None
    device.cool_settle_pending = False
    device.cool_compensation_settling = False


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
    settling = False
    force = False
    if uses_sensor_part(device):
        if device.cool_run_started_at is None:
            # A new owned cooling run: ignore the unit reading until it settles (spec §2).
            device.cool_run_started_at = now
            device.cool_settle_pending = True
        settling = now - device.cool_run_started_at < timedelta(minutes=COOL_COMPENSATION_SETTLE_MINUTES)
        # The first evaluation after the settle sends at once, like a first owned send.
        force = device.cool_settle_pending and not settling
        if force:
            device.cool_settle_pending = False
    device.cool_compensation_settling = settling
    offset = resolve_cool_offset(device, zone_state, now, settling=settling)
    # Overdrive and off are constants; only regulated modes pass the limiter.
    if device.cool_regulation in (COOL_REGULATION_COMPENSATION, COOL_REGULATION_PI):
        offset = limit_cool_offset(device, offset, target, now, force=force)
    return target + offset, offset

