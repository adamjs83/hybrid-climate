"""PI controller for HVAC regulation.

Implements proportional-integral control with:
- Feedforward term (outdoor temperature compensation)
- Anti-windup (integral saturation limits)
- Integral deadband (prevent micro-oscillations)
- Integral decay (when idle or saturated)

Key dependencies: models.py (RegulationConfig, ZoneConfig, ZoneState)
Used by: coordinator.py (zone staging calls calculate_offset each cycle)
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_BALANCE_POINT,
    DEFAULT_K_EXT,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_OFFSET_MAX,
    REGULATION_PI,
)
from .models import (
    HybridClimateConfig,
    ZoneConfig,
    ZoneState,
)
from .zone_helpers import resolve_number_entity_id

_LOGGER = logging.getLogger(__name__)


class PIController:
    """Pure calculation engine for PI-based HVAC regulation.

    All inputs are passed as parameters — the controller does not reach
    back into the coordinator or HomeAssistant state for the PI calculation.
    The get_pi_params_* methods DO access hass state (entity registry,
    entity states) to look up number entities, receiving hass as a parameter.
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
        """Calculate PI controller offset for regulated devices.

        Implements proper HVAC PI controller behavior:
        1. Accumulate integral only when actively heating/cooling (stage activated)
        2. Hold integral steady when idle or at setpoint (error within deadband)
        3. Anti-windup: stop accumulating when output is saturated at limits
        4. Integral deadband prevents micro-oscillations from adjusting integral
        5. dt-scaled integral: accumulated_error uses error * dt (in minutes)

        Args:
            zone_config: Zone configuration with regulation settings
            zone_state: Current zone state (includes accumulated_error)
            outdoor_temp: Current outdoor temperature (for k_ext factor)
            is_actively_heating: True if a heating/cooling stage is active.
                When False (zone idle but not at setpoint), the integral is held
                steady instead of accumulating, preventing windup in the
                "comfort band" between hysteresis and stage threshold.
            pi_params: PI tuning parameters from number entities (kp, ki, k_ext,
                offset_max, balance_point). Falls back to regulation config defaults.

        Returns:
            Offset to add to zone target for regulated devices
        """
        regulation = zone_config.regulation
        if regulation is None or regulation.type != REGULATION_PI:
            return 0.0

        # Use provided PI params, falling back to regulation config defaults
        if pi_params is None:
            pi_params = {}
        kp = pi_params.get("kp", regulation.kp)
        ki = pi_params.get("ki", regulation.ki)
        k_ext = pi_params.get("k_ext", regulation.k_ext)
        offset_max = pi_params.get("offset_max", regulation.offset_max)
        balance_point = pi_params.get("balance_point", regulation.balance_point)

        # Get current error (positive = need heat, negative = need cool)
        target = zone_state.target_temperature
        current = zone_state.current_temperature
        if target is None or current is None:
            return 0.0

        error = target - current

        # Calculate dt (time since last PI update) in minutes
        now = dt_util.utcnow()
        dt_minutes = 1.0  # Default to 1 minute if no previous update
        if zone_state.last_pi_update_time is not None:
            dt_seconds = (now - zone_state.last_pi_update_time).total_seconds()
            dt_minutes = dt_seconds / 60.0
            # Clamp dt to reasonable bounds (0.1 to 10 minutes)
            # Prevents huge jumps after restarts or long delays
            dt_minutes = max(0.1, min(10.0, dt_minutes))
        zone_state.last_pi_update_time = now

        # Calculate external temperature contribution first (feedforward term)
        ext_term = 0.0
        if outdoor_temp is not None and k_ext > 0:
            # When outdoor is cold, push setpoint higher
            # When outdoor is warm, push setpoint lower
            # balance_point = outdoor temp where no offset needed
            outdoor_offset = balance_point - outdoor_temp
            ext_term = k_ext * outdoor_offset

        # Calculate what the offset would be with current accumulated_error
        p_term = kp * error
        i_term = ki * zone_state.accumulated_error
        prospective_offset = p_term + i_term + ext_term

        # Check if output would be saturated (at min/max limits)
        output_saturated_high = prospective_offset >= offset_max
        output_saturated_low = prospective_offset <= -offset_max

        # Integral deadband: only accumulate if error is significant
        # This prevents micro-oscillations from constantly adjusting integral
        error_in_deadband = abs(error) < regulation.stabilization_threshold

        # Determine if we should update the integral
        # Don't accumulate if:
        # - Not actively heating/cooling (stage not active, e.g., in comfort band)
        # - Error is within deadband (at setpoint) - HOLD integral steady
        # - Output saturated high and error positive (can't go higher)
        # - Output saturated low and error negative (can't go lower)
        should_accumulate = True

        if not is_actively_heating:
            # Zone is IDLE (no heating/cooling stage active)
            # This happens when temp is in the "comfort band" between hysteresis and threshold
            # Hold the integral steady - don't accumulate or we'll wind up
            should_accumulate = False

            # Apply faster decay when idle AND integral is at or near cap
            # This helps recover faster from windup situations
            integral_at_cap = abs(zone_state.accumulated_error) >= regulation.accumulated_error_threshold * 0.9

            # Apply decay if configured (use faster rate if at cap)
            halflife = regulation.integral_decay_halflife
            if halflife > 0:
                # When at cap and idle, decay 4x faster to recover from windup
                if integral_at_cap:
                    halflife = halflife / 4.0
                    _LOGGER.info(
                        "Zone %s PI: idle at cap (%.1f), using fast decay halflife %.0fm",
                        zone_config.zone_id,
                        zone_state.accumulated_error,
                        halflife,
                    )

                decay_factor = 0.5 ** (dt_minutes / halflife)
                old_integral = zone_state.accumulated_error
                zone_state.accumulated_error *= decay_factor
                if abs(old_integral) > 0.1 and abs(old_integral - zone_state.accumulated_error) > 0.01:
                    _LOGGER.debug(
                        "Zone %s PI: idle decay %.2f → %.2f (factor %.4f, halflife %.0fm)",
                        zone_config.zone_id,
                        old_integral,
                        zone_state.accumulated_error,
                        decay_factor,
                        halflife,
                    )
            else:
                _LOGGER.debug(
                    "Zone %s PI: not actively heating, holding integral at %.1f (error=%.2f)",
                    zone_config.zone_id,
                    zone_state.accumulated_error,
                    error,
                )
        elif error_in_deadband:
            # At setpoint - apply exponential decay to integral (if configured)
            # This gradually "forgets" old state during extended idle periods
            should_accumulate = False
            if regulation.integral_decay_halflife > 0:
                # decay_factor = 0.5^(dt/halflife) gives half-life behavior
                decay_factor = 0.5 ** (dt_minutes / regulation.integral_decay_halflife)
                old_integral = zone_state.accumulated_error
                zone_state.accumulated_error *= decay_factor
                # Only log if there was meaningful decay
                if abs(old_integral) > 0.1 and abs(old_integral - zone_state.accumulated_error) > 0.01:
                    _LOGGER.debug(
                        "Zone %s PI: idle decay %.2f → %.2f (factor %.4f, halflife %.0fm)",
                        zone_config.zone_id,
                        old_integral,
                        zone_state.accumulated_error,
                        decay_factor,
                        regulation.integral_decay_halflife,
                    )
            else:
                _LOGGER.debug(
                    "Zone %s PI: error %.2f in deadband (threshold %.2f), holding integral at %.1f",
                    zone_config.zone_id,
                    error,
                    regulation.stabilization_threshold,
                    zone_state.accumulated_error,
                )
        elif output_saturated_high and error > 0:
            # Anti-windup: output maxed out and still need more heat
            should_accumulate = False
            _LOGGER.debug(
                "Zone %s PI: anti-windup (saturated high), not accumulating",
                zone_config.zone_id,
            )
        elif output_saturated_low and error < 0:
            # Anti-windup: output at minimum and still need more cooling
            should_accumulate = False
            _LOGGER.debug(
                "Zone %s PI: anti-windup (saturated low), not accumulating",
                zone_config.zone_id,
            )

        # Update accumulated error only if appropriate
        # Scale by dt to make integral time-based (error-minutes)
        if should_accumulate:
            zone_state.accumulated_error += error * dt_minutes

            # Apply absolute cap on accumulated error (secondary anti-windup)
            if abs(zone_state.accumulated_error) > regulation.accumulated_error_threshold:
                zone_state.accumulated_error = (
                    regulation.accumulated_error_threshold
                    if zone_state.accumulated_error > 0
                    else -regulation.accumulated_error_threshold
                )

        # Recalculate with potentially updated integral
        i_term = ki * zone_state.accumulated_error
        offset = p_term + i_term + ext_term

        # Clamp to max offset
        offset = max(-offset_max, min(offset_max, offset))

        _LOGGER.debug(
            "Zone %s PI: error=%.1f, dt=%.2fm, accum=%.1f, P=%.2f, I=%.2f, ext=%.2f, offset=%.2f (kp=%.2f, ki=%.3f, k_ext=%.2f)",
            zone_config.zone_id,
            error,
            dt_minutes,
            zone_state.accumulated_error,
            p_term,
            i_term,
            ext_term,
            offset,
            kp,
            ki,
            k_ext,
        )

        return offset

    def get_pi_params_from_numbers(
        self,
        hass: HomeAssistant,
        config: HybridClimateConfig,
        entry: ConfigEntry | None,
        zone_id: str,
    ) -> dict[str, float]:
        """Get PI parameters from number entities for a zone.

        Returns dict with kp, ki, k_ext, offset_max, balance_point.
        Falls back to defaults if number entities don't exist.

        Note: Number entities were created with zone_id from config, but entity_id
        is derived from unique_id which HA slugifies. The entity naming includes
        zone_name, so we try multiple patterns to find the entity.
        """
        params = {
            "kp": DEFAULT_KP,
            "ki": DEFAULT_KI,
            "k_ext": DEFAULT_K_EXT,
            "offset_max": DEFAULT_OFFSET_MAX,
            "balance_point": DEFAULT_BALANCE_POINT,
        }

        param_map = {
            "kp": "pi_kp",
            "ki": "pi_ki",
            "k_ext": "pi_k_ext",
            "offset_max": ["pi_offset_max", "pi_max_offset"],  # Try both naming conventions
            "balance_point": "pi_balance_point",
        }

        for param, suffixes in param_map.items():
            found = False

            # Normalize suffixes to list (some params have alternate names)
            if isinstance(suffixes, str):
                suffixes = [suffixes]

            for suffix in suffixes:
                # Primary: resolve via entity registry (handles all naming patterns)
                entity_id = resolve_number_entity_id(hass, zone_id, suffix)
                if entity_id:
                    state = hass.states.get(entity_id)
                    if state is not None:
                        try:
                            params[param] = float(state.state)
                            found = True
                            break
                        except (ValueError, TypeError):
                            pass

                # Fallback: old input_number format
                entity_id = f"input_number.hybrid_{zone_id}_{suffix}"
                state = hass.states.get(entity_id)
                if state is not None:
                    try:
                        params[param] = float(state.state)
                        found = True
                        break
                    except (ValueError, TypeError):
                        pass

            if not found:
                _LOGGER.debug(
                    "PI param %s not found for zone %s (keys tried: %s)",
                    param, zone_id, suffixes
                )

        return params

