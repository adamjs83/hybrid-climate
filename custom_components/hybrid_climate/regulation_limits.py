"""Purpose: Limit changes to heating PI device setpoints.

Key dependencies: Runtime zone state and per-zone regulation settings.
Used by: Zone control and immediate heat target updates.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .const import REGULATION_THRESHOLD_FLOAT_TOLERANCE
from .models import RegulationConfig, ZoneState


def reset_regulation_limits(zone_state: ZoneState) -> None:
    """Forget the last regulated command after release or direction change."""
    zone_state.last_sent_regulated_setpoint = None
    zone_state.last_regulated_send_time = None
    zone_state.last_regulated_heat_target = None


def limit_regulated_setpoint(
    zone_state: ZoneState, regulation: RegulationConfig,
    raw: float | None, now: datetime,
) -> float | None:
    """Return the last sent setpoint until both configured change limits pass."""
    if raw is None:
        return None

    previous = zone_state.last_sent_regulated_setpoint
    last_time = zone_state.last_regulated_send_time
    target = zone_state.target_temperature
    # A new target or a fresh activation must reach devices immediately.
    if (previous is None or last_time is None
            or target != zone_state.last_regulated_heat_target):
        send = True
    else:
        difference = abs(raw - previous)
        elapsed = now - last_time
        send = (
            difference > 0
            and difference >= regulation.regulation_threshold - REGULATION_THRESHOLD_FLOAT_TOLERANCE
            and elapsed >= timedelta(minutes=regulation.regulation_min_period)
        )
    if send:
        zone_state.last_sent_regulated_setpoint = raw
        zone_state.last_regulated_send_time = now
        zone_state.last_regulated_heat_target = target
        return raw
    return previous
