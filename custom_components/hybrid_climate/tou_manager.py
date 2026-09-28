"""TOU (Time-of-Use) rate optimization manager.

Reads an external rate period sensor and adjusts zone setpoints to reduce
electric consumption during peak pricing. Two behaviors:
- Pre-conditioning: shift setpoints aggressively before peak to build thermal buffer
- Peak relaxation: relax setpoints during peak to reduce device runtime

Key dependencies: models.py (TouGlobalConfig, ZoneTouConfig, ZoneConfig)
Used by: zone_control.py (called during each zone update cycle)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import (
    ATTR_NEXT_PEAK_START,
    TOU_PERIOD_PEAK,
    TOU_STATE_NORMAL,
    TOU_STATE_PEAK_RELAXED,
    TOU_STATE_PRE_CONDITIONING,
)
from .models import ZoneConfig, ZoneTouModeConfig

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


class TouManager:
    """Manages TOU-aware setpoint adjustments for zones."""

    def __init__(self, coordinator: HybridClimateCoordinator) -> None:
        """Initialize TOU manager."""
        self._coordinator = coordinator

    def _get_rate_period(self) -> str | None:
        """Read current rate period from the external sensor."""
        rate_sensor_id = self._coordinator.config.tou_global.rate_sensor
        if not rate_sensor_id:
            return None

        state = self._coordinator.hass.states.get(rate_sensor_id)
        if state is None or state.state in ("unavailable", "unknown"):
            _LOGGER.debug("TOU rate sensor %s not available", rate_sensor_id)
            return None

        return state.state

    def _get_next_peak_start(self) -> datetime | None:
        """Read next_peak_start attribute from the rate sensor."""
        rate_sensor_id = self._coordinator.config.tou_global.rate_sensor
        if not rate_sensor_id:
            return None

        state = self._coordinator.hass.states.get(rate_sensor_id)
        if state is None:
            return None

        next_peak_raw = state.attributes.get(ATTR_NEXT_PEAK_START)
        if next_peak_raw is None:
            return None

        # Parse ISO datetime string
        if isinstance(next_peak_raw, datetime):
            return next_peak_raw

        try:
            return dt_util.parse_datetime(str(next_peak_raw))
        except (ValueError, TypeError):
            _LOGGER.warning(
                "TOU: could not parse next_peak_start: %s", next_peak_raw
            )
            return None

    def _is_pre_conditioning(
        self, tou_mode_config: ZoneTouModeConfig, now: datetime
    ) -> bool:
        """Check if we should be pre-conditioning right now."""
        if tou_mode_config.pre_condition_minutes <= 0:
            return False

        next_peak = self._get_next_peak_start()
        if next_peak is None:
            return False

        # Make both aware or both naive for comparison
        if next_peak.tzinfo is None:
            next_peak = dt_util.as_local(next_peak)

        minutes_until_peak = (next_peak - now).total_seconds() / 60.0

        return 0 < minutes_until_peak <= tou_mode_config.pre_condition_minutes

    def get_adjusted_setpoints(
        self,
        zone_id: str,
        zone_config: ZoneConfig,
        base_heat_setpoint: float,
        base_cool_setpoint: float | None,
    ) -> tuple[float, float | None, str]:
        """Return TOU-adjusted setpoints and current TOU state for a zone.

        Applies pre-conditioning or peak relaxation adjustments and clamps
        adjusted targets if they cross. Normal seasonal targets are preserved.

        Returns:
            (effective_heat_setpoint, effective_cool_setpoint, tou_state)
        """
        tou_config = zone_config.tou
        if tou_config is None:
            return base_heat_setpoint, base_cool_setpoint, TOU_STATE_NORMAL

        rate_period = self._get_rate_period()
        if rate_period is None:
            return base_heat_setpoint, base_cool_setpoint, TOU_STATE_NORMAL

        now = dt_util.now()
        heat_sp = base_heat_setpoint
        cool_sp = base_cool_setpoint
        tou_state = TOU_STATE_NORMAL

        if rate_period == TOU_PERIOD_PEAK:
            # Peak: relax setpoints to reduce electric load
            tou_state = TOU_STATE_PEAK_RELAXED
            if tou_config.heat is not None:
                heat_sp -= tou_config.heat.relaxation_amount
            if tou_config.cool is not None and cool_sp is not None:
                cool_sp += tou_config.cool.relaxation_amount

        else:
            # Check if we should be pre-conditioning
            heat_precon = (
                tou_config.heat is not None
                and self._is_pre_conditioning(tou_config.heat, now)
            )
            cool_precon = (
                tou_config.cool is not None
                and cool_sp is not None
                and self._is_pre_conditioning(tou_config.cool, now)
            )

            if heat_precon or cool_precon:
                tou_state = TOU_STATE_PRE_CONDITIONING
                if heat_precon:
                    heat_sp += tou_config.heat.relaxation_amount
                if cool_precon:
                    cool_sp -= tou_config.cool.relaxation_amount

        # Enforce deadband clamping invariant:
        # effective_heat + hysteresis <= effective_cool
        # Clamp whichever side TOU actively adjusted.
        if cool_sp is not None and tou_state != TOU_STATE_NORMAL:
            hysteresis = zone_config.settings.hysteresis
            min_gap = hysteresis

            if heat_sp + min_gap > cool_sp:
                if tou_state == TOU_STATE_PRE_CONDITIONING:
                    # During pre-conditioning, we pushed one or both setpoints
                    # Clamp the one that was actively moved
                    if tou_config.heat is not None and self._is_pre_conditioning(
                        tou_config.heat, now
                    ):
                        # Pre-heating raised heat into cool — clamp heat down
                        heat_sp = cool_sp - min_gap
                    else:
                        # Pre-cooling lowered cool into heat — clamp cool up
                        cool_sp = heat_sp + min_gap
                elif tou_state == TOU_STATE_PEAK_RELAXED:
                    # During peak, relaxation moved setpoints toward each other
                    if tou_config.cool is not None:
                        cool_sp = heat_sp + min_gap
                    else:
                        heat_sp = cool_sp - min_gap
                _LOGGER.debug(
                    "TOU: clamped setpoints for zone %s: heat=%.1f cool=%.1f",
                    zone_id,
                    heat_sp,
                    cool_sp,
                )

        if tou_state != TOU_STATE_NORMAL:
            _LOGGER.debug(
                "TOU zone %s: state=%s, heat %.1f->%.1f, cool %s->%s",
                zone_id,
                tou_state,
                base_heat_setpoint,
                heat_sp,
                base_cool_setpoint,
                cool_sp,
            )

        return heat_sp, cool_sp, tou_state
