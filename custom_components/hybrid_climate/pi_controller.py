"""PI controller for HVAC regulation.

Implements proportional-integral control with:
- Feedforward term (outdoor temperature compensation)
- Anti-windup (integral saturation limits)
- Integral deadband (prevent micro-oscillations)
- Integral decay (when idle or saturated)

The maths is the pure `pi_step`; `PIController.calculate_offset` builds its heating inputs
and writes the result back to the zone state.

Key dependencies: models.py (RegulationConfig, ZoneConfig, ZoneState); number_lookup.py
Used by: coordinator.py (zone staging calls calculate_offset each cycle); cool_pi.py (pi_step)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import REGULATION_PI
from .models import (
    HybridClimateConfig,
    ZoneConfig,
    ZoneState,
)
from .number_lookup import HEAT_PI_DEFAULTS, HEAT_PI_NUMBER_KEYS, read_zone_numbers

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PIParams:
    """Gains and limits for one PI step (offset_min is -offset_max for heating, 0 for cooling)."""
    kp: float
    ki: float
    k_ext: float
    offset_max: float
    offset_min: float
    balance_point: float
    stabilization_threshold: float
    accumulated_error_threshold: float
    integral_decay_halflife: float


@dataclass(frozen=True)
class PIState:
    """Integral accumulator (error-minutes) and the time of the last PI step."""
    accumulated_error: float
    last_update: datetime | None


def pi_step(
    error: float,
    state: PIState,
    params: PIParams,
    now: datetime,
    *,
    active: bool,
    outdoor_temp: float | None,
    label: str,
) -> tuple[float, PIState]:
    """Run one PI step and return (offset clamped to [offset_min, offset_max], new state).

    1. Accumulate integral only when active (a stage is running)
    2. Hold integral steady when idle or at setpoint (error within deadband), decaying if configured
    3. Anti-windup: stop accumulating when output is saturated at either limit
    4. dt-scaled integral: accumulated_error uses error * dt (in minutes)
    """
    accumulated = state.accumulated_error

    # dt since the last step in minutes, default 1 on the first call; clamped to
    # 0.1..10 minutes to prevent huge jumps after restarts or long delays
    dt_minutes = 1.0
    if state.last_update is not None:
        dt_minutes = (now - state.last_update).total_seconds() / 60.0
        dt_minutes = max(0.1, min(10.0, dt_minutes))

    # Feedforward term: balance_point is the outdoor temp where no offset is needed
    ext_term = 0.0
    if outdoor_temp is not None and params.k_ext > 0:
        ext_term = params.k_ext * (params.balance_point - outdoor_temp)

    # Offset the current integral would give, to detect saturation
    p_term = params.kp * error
    prospective_offset = p_term + params.ki * accumulated + ext_term
    output_saturated_high = prospective_offset >= params.offset_max
    output_saturated_low = prospective_offset <= params.offset_min

    # Integral deadband: micro-oscillations around the setpoint must not move the integral
    error_in_deadband = abs(error) < params.stabilization_threshold

    should_accumulate = True
    if not active:
        # Zone idle (comfort band): never accumulate or the integral winds up.
        should_accumulate = False
        # Idle at or near the cap decays 4x faster to recover from windup
        integral_at_cap = abs(accumulated) >= params.accumulated_error_threshold * 0.9
        halflife = params.integral_decay_halflife
        if halflife > 0:
            if integral_at_cap:
                halflife = halflife / 4.0
                _LOGGER.info(
                    "Zone %s PI: idle at cap (%.1f), using fast decay halflife %.0fm",
                    label, accumulated, halflife,
                )
            accumulated = _decay(accumulated, dt_minutes, halflife, label)
        else:
            _LOGGER.debug(
                "Zone %s PI: not actively heating, holding integral at %.1f (error=%.2f)",
                label, accumulated, error,
            )
    elif error_in_deadband:
        # At setpoint: gradually "forget" old state (exponential decay, if configured)
        should_accumulate = False
        if params.integral_decay_halflife > 0:
            accumulated = _decay(accumulated, dt_minutes, params.integral_decay_halflife, label)
        else:
            _LOGGER.debug(
                "Zone %s PI: error %.2f in deadband (threshold %.2f), holding integral at %.1f",
                label, error, params.stabilization_threshold, accumulated,
            )
    elif output_saturated_high and error > 0:
        # Anti-windup: output maxed out and the error still pushes it higher
        should_accumulate = False
        _LOGGER.debug("Zone %s PI: anti-windup (saturated high), not accumulating", label)
    elif output_saturated_low and error < 0:
        # Anti-windup: output at its minimum and the error still pushes it lower
        should_accumulate = False
        _LOGGER.debug("Zone %s PI: anti-windup (saturated low), not accumulating", label)

    if should_accumulate:
        accumulated += error * dt_minutes
        # Absolute cap on the integral (secondary anti-windup)
        cap = params.accumulated_error_threshold
        if abs(accumulated) > cap:
            accumulated = cap if accumulated > 0 else -cap

    i_term = params.ki * accumulated
    offset = max(params.offset_min, min(params.offset_max, p_term + i_term + ext_term))
    _LOGGER.debug(
        "Zone %s PI: error=%.1f, dt=%.2fm, accum=%.1f, P=%.2f, I=%.2f, ext=%.2f, offset=%.2f (kp=%.2f, ki=%.3f, k_ext=%.2f)",
        label, error, dt_minutes, accumulated, p_term, i_term, ext_term, offset,
        params.kp, params.ki, params.k_ext,
    )
    return offset, PIState(accumulated, now)


def _decay(accumulated: float, dt_minutes: float, halflife: float, label: str) -> float:
    """Return the integral after exponential decay over dt (0.5^(dt/halflife))."""
    decay_factor = 0.5 ** (dt_minutes / halflife)
    decayed = accumulated * decay_factor
    if abs(accumulated) > 0.1 and abs(accumulated - decayed) > 0.01:
        _LOGGER.debug(
            "Zone %s PI: idle decay %.2f → %.2f (factor %.4f, halflife %.0fm)",
            label, accumulated, decayed, decay_factor, halflife,
        )
    return decayed


class PIController:
    """Heating adapter around `pi_step`; the controller itself is stateless.

    State lives in ZoneState. get_pi_params_from_numbers reads the zone's number
    entities (entity registry lookup), receiving hass as a parameter.
    """

    def __init__(self) -> None:
        """Initialize the PI controller (stateless — state lives in ZoneState)."""

    def calculate_offset(
        self,
        zone_config: ZoneConfig,
        zone_state: ZoneState,
        outdoor_temp: float | None,
        is_actively_heating: bool = True,
        pi_params: dict[str, float] | None = None,
    ) -> float:
        """Run one heating PI step on the zone and return the offset for regulated devices.

        is_actively_heating False (idle in the comfort band) holds or decays the integral.
        pi_params (kp, ki, k_ext, offset_max, balance_point from the number entities)
        fall back to the regulation config. Writes accumulated_error and last_pi_update_time.
        """
        regulation = zone_config.regulation
        if regulation is None or regulation.type != REGULATION_PI:
            return 0.0

        pi_params = pi_params or {}
        offset_max = pi_params.get("offset_max", regulation.offset_max)
        params = PIParams(
            kp=pi_params.get("kp", regulation.kp),
            ki=pi_params.get("ki", regulation.ki),
            k_ext=pi_params.get("k_ext", regulation.k_ext),
            offset_max=offset_max,
            offset_min=-offset_max,  # heating is symmetric
            balance_point=pi_params.get("balance_point", regulation.balance_point),
            stabilization_threshold=regulation.stabilization_threshold,
            accumulated_error_threshold=regulation.accumulated_error_threshold,
            integral_decay_halflife=regulation.integral_decay_halflife,
        )

        # Positive error = need heat
        target = zone_state.target_temperature
        current = zone_state.current_temperature
        if target is None or current is None:
            return 0.0

        offset, new_state = pi_step(
            target - current,
            PIState(zone_state.accumulated_error, zone_state.last_pi_update_time),
            params,
            dt_util.utcnow(),
            active=is_actively_heating,
            outdoor_temp=outdoor_temp,
            label=zone_config.zone_id,
        )
        zone_state.accumulated_error = new_state.accumulated_error
        zone_state.last_pi_update_time = new_state.last_update
        return offset

    def get_pi_params_from_numbers(
        self,
        hass: HomeAssistant,
        config: HybridClimateConfig,
        entry: ConfigEntry | None,
        zone_id: str,
    ) -> dict[str, float]:
        """Get heating PI parameters from the zone's number entities (registry lookup).

        Returns kp, ki, k_ext, offset_max, balance_point; each falls back to its
        default when the number is unregistered, stateless or non-numeric.
        """
        return read_zone_numbers(hass, zone_id, HEAT_PI_NUMBER_KEYS, HEAT_PI_DEFAULTS)
