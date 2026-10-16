"""Purpose: Zone-level cooling PI controller (v0.17.0): the push below the cool target for pi devices.

error = room − cool target (positive = needs more cooling), no outdoor term; the push is clamped
to [0, offset_max] and stored as the signed device offset −push. The per-device limiter
(cool_regulation.py) still governs what is sent.

Key dependencies: pi_controller.pi_step (shared PI maths); number_lookup.read_zone_numbers
(cool_pi_* gain numbers by registry unique id); models.ZoneConfig/ZoneState; const.
Used by: the cooling branch of the control cycle (v0.17.0 Task 4), setpoint_manager (target change)
and zone.py (cooling PI attributes and restore).
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from math import isfinite
from typing import Any

from homeassistant.util import dt as dt_util

from .const import (
    COOL_REGULATION_PI,
    DEFAULT_INTEGRAL_RESET_FACTOR,
    DEFAULT_INTEGRAL_RESET_THRESHOLD,
)
from .cool_pi_const import (
    ATTR_COOL_ACCUMULATED_ERROR,
    ATTR_COOL_REGULATED_SETPOINT,
    ATTR_COOL_REGULATION_OFFSET,
    COOL_PI_LOG_LABEL,
)
from .models import ZoneConfig, ZoneState
from .number_lookup import COOL_PI_NUMBER_KEYS, read_zone_numbers
from .pi_controller import PIParams, PIState, pi_step

_LOGGER = logging.getLogger(__name__)


def zone_cool_pi_devices(coordinator: Any, zone_config: ZoneConfig) -> set[str]:
    """Return the zone's cool-stage device ids whose cooling regulation mode is pi."""
    devices: set[str] = set()
    for stage in zone_config.cool_stages:
        for device_id in stage.get_device_ids():
            device = coordinator.device_manager.get_device(device_id)
            # A missing device (or a test Mock) simply does not match.
            if device is not None and getattr(device, "cool_regulation", None) == COOL_REGULATION_PI:
                devices.add(device_id)
    return devices


def _cool_gains(coordinator: Any, zone_config: ZoneConfig) -> dict[str, float]:
    """Read kp, ki and offset_max from the zone's cooling numbers, falling back to the zone block."""
    block = zone_config.cool_regulation
    defaults = {"kp": block.kp, "ki": block.ki, "offset_max": block.offset_max}
    gains = read_zone_numbers(coordinator.hass, zone_config.zone_id, COOL_PI_NUMBER_KEYS, defaults)
    for param, value in gains.items():
        # read_zone_numbers passes nan/inf through (Ruling 5); cooling never uses them.
        if not isfinite(value):
            _LOGGER.warning(
                "Zone %s cooling PI: number %s is %s; using the configured %s",
                zone_config.zone_id, COOL_PI_NUMBER_KEYS[param], value, defaults[param],
            )
            gains[param] = defaults[param]
    return gains


def cool_pi_update(
    coordinator: Any, zone_config: ZoneConfig, zone_state: ZoneState, *, active: bool,
) -> None:
    """Run one cooling PI step and write the cooling integral, offset and regulated setpoint."""
    room = zone_state.current_temperature
    target = zone_state.target_temperature_cool
    if room is None or target is None:
        # No reading or no target: hold every cooling field (no accumulation, offset kept).
        _LOGGER.debug("Zone %s cooling PI: missing room or cool target, holding",
                      zone_config.zone_id)
        return

    block = zone_config.cool_regulation
    gains = _cool_gains(coordinator, zone_config)
    params = PIParams(
        kp=gains["kp"],
        ki=gains["ki"],
        k_ext=0.0,  # no outdoor term for cooling
        offset_max=gains["offset_max"],
        offset_min=0.0,  # the push never warms the device setpoint
        balance_point=0.0,
        stabilization_threshold=block.stabilization_threshold,
        accumulated_error_threshold=block.accumulated_error_threshold,
        integral_decay_halflife=block.integral_decay_halflife,
    )
    offset, new_state = pi_step(
        room - target,
        PIState(zone_state.cool_accumulated_error, zone_state.cool_last_pi_update_time),
        params,
        dt_util.utcnow(),
        active=active,
        outdoor_temp=None,
        label=COOL_PI_LOG_LABEL % zone_config.zone_id,
    )
    push = max(0.0, min(params.offset_max, offset))
    zone_state.cool_accumulated_error = new_state.accumulated_error
    zone_state.cool_last_pi_update_time = new_state.last_update
    zone_state.cool_regulation_offset = -push if push else 0.0  # never -0.0
    zone_state.cool_regulated_setpoint = target - push


def cool_target_changed(
    zone_config: ZoneConfig, zone_state: ZoneState, old: float | None, new: float,
) -> None:
    """Partially reset the cooling integral after a big cool target change (heating's rule)."""
    if old is None:
        return
    regulation = zone_config.regulation
    threshold = (regulation.integral_reset_threshold if regulation is not None
                 else DEFAULT_INTEGRAL_RESET_THRESHOLD)
    factor = (regulation.integral_reset_factor if regulation is not None
              else DEFAULT_INTEGRAL_RESET_FACTOR)
    delta = abs(new - old)
    if delta > threshold:
        old_integral = zone_state.cool_accumulated_error
        zone_state.cool_accumulated_error *= factor
        _LOGGER.info(
            "Zone %s: big cool setpoint change (%.1f->%.1f, delta %.1f°F), "
            "scaling cooling integral %.1f -> %.1f",
            zone_config.zone_id, old, new, delta, old_integral, zone_state.cool_accumulated_error,
        )


def cool_pi_attributes(state: ZoneState) -> dict[str, Any]:
    """Return the zone climate's cooling PI attributes, rounded like the heating ones."""
    setpoint = state.cool_regulated_setpoint
    return {
        ATTR_COOL_REGULATION_OFFSET: round(state.cool_regulation_offset, 2),
        ATTR_COOL_ACCUMULATED_ERROR: round(state.cool_accumulated_error, 2),
        ATTR_COOL_REGULATED_SETPOINT: round(setpoint, 1) if setpoint is not None else None,
    }


def restore_cool_pi_state(state: ZoneState, attributes: Mapping[str, Any]) -> None:
    """Restore the cooling integral from the zone climate's last cool_accumulated_error."""
    raw = attributes.get(ATTR_COOL_ACCUMULATED_ERROR)
    if raw is None:
        return  # pre-0.17.0 state or never cooled: keep the fresh integral
    try:
        restored = float(raw)
    except (ValueError, TypeError):
        restored = None
    if restored is None or not isfinite(restored):
        _LOGGER.debug("Zone %s: ignoring unusable restored %s %r",
                      state.zone_id, ATTR_COOL_ACCUMULATED_ERROR, raw)
        return
    state.cool_accumulated_error = restored
    _LOGGER.debug("Zone %s: restored %s %s", state.zone_id, ATTR_COOL_ACCUMULATED_ERROR, restored)
