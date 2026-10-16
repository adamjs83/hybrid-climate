"""Purpose: The heating and cooling PI steps of one zone's control cycle.

The four heating PI blocks of zone_control._apply_zone_staging (idle/OFF, comfort band,
prospective step, failed-command rollback) live here unchanged and still go through
coordinator._calculate_pi_offset; the cooling PI calls (cool_pi.py) sit beside them.
Cooling PI runs only for zones with a cool-stage device in mode pi, so other zones never
read the cooling gain numbers and keep the cooling fields at their defaults.

Key dependencies: cool_pi (zone_cool_pi_devices, cool_pi_update), regulation_limits,
models.ZoneConfig/ZoneState, const.
Used by: zone_control._apply_zone_staging and device_arbitration.reconcile_dispatch.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import COOL_REGULATION_PI, HVAC_MODE_COOL, HVAC_MODE_HEAT, REGULATION_PI
from .cool_pi import cool_pi_update, zone_cool_pi_devices
from .models import Device, HvacAction, ZoneConfig, ZoneState
from .regulation_limits import limit_regulated_setpoint, reset_regulation_limits

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

CoolFields = tuple[float, datetime | None, float, float | None]


@dataclass
class RegulationSnapshot:
    """PI state captured before a prospective step, for rollback when no regulated command succeeds."""

    heating_regulated: bool
    previous_integral: float
    previous_pi_time: datetime | None
    previous_limit: tuple[float | None, datetime | None, float | None]
    cooling_regulated: bool
    previous_cool: CoolFields


def _cool_fields(state: ZoneState) -> CoolFields:
    """Return the four cooling PI fields (integral, timestamp, offset, regulated setpoint)."""
    return (state.cool_accumulated_error, state.cool_last_pi_update_time,
            state.cool_regulation_offset, state.cool_regulated_setpoint)


def _restore_cool_fields(state: ZoneState, values: CoolFields) -> None:
    """Write back the four cooling PI fields captured by _cool_fields."""
    (state.cool_accumulated_error, state.cool_last_pi_update_time,
     state.cool_regulation_offset, state.cool_regulated_setpoint) = values


def _is_cool_pi(coordinator: HybridClimateCoordinator, device_id: str) -> bool:
    """Return whether a device's cooling regulation mode is pi."""
    device = coordinator.device_manager.get_device(device_id)
    return device is not None and getattr(device, "cool_regulation", None) == COOL_REGULATION_PI


def idle_regulation(
    coordinator: HybridClimateCoordinator,
    zone_config: ZoneConfig,
    zone_state: ZoneState,
    outdoor_temp: float | None,
    needed_mode: str,
) -> None:
    """Refresh heating and cooling PI without accumulating while no stage runs."""
    # Below the entry threshold (or off), PI must still refresh the equilibrium
    # setpoint and timestamp without integrating an inactive demand.
    if zone_config.regulation and zone_config.regulation.type == REGULATION_PI:
        zone_state.regulation_offset = coordinator._calculate_pi_offset(
            zone_config, zone_state, outdoor_temp, is_actively_heating=False
        )
        target_temp = zone_state.target_temperature
        raw = target_temp + zone_state.regulation_offset if target_temp is not None else None
        # The heating limiter applies off and in the heating comfort band, not to cooling.
        if needed_mode != HVAC_MODE_COOL:
            zone_state.regulated_setpoint = limit_regulated_setpoint(
                zone_state, zone_config.regulation, raw, dt_util.utcnow()
            )
        else:
            zone_state.regulated_setpoint = raw
    # No cooling equilibrium hold: a held cool mode blocks the Family Room heat pump through the mutex.
    if zone_cool_pi_devices(coordinator, zone_config):
        cool_pi_update(coordinator, zone_config, zone_state, active=False)


def prepare_regulation(
    coordinator: HybridClimateCoordinator,
    zone_config: ZoneConfig,
    zone_state: ZoneState,
    devices: Sequence[Device],
    needed_mode: str,
    new_action: HvacAction,
    outdoor_temp: float | None,
) -> RegulationSnapshot:
    """Run the prospective heating and cooling PI steps and return the rollback snapshot."""
    # Calculate the command with a prospective integral; commit accumulation
    # only if at least one regulated heating command succeeds below.
    heating_regulated = False
    previous_integral = zone_state.accumulated_error
    previous_pi_time = zone_state.last_pi_update_time
    previous_limit = (
        zone_state.last_sent_regulated_setpoint,
        zone_state.last_regulated_send_time,
        zone_state.last_regulated_heat_target,
    )
    if zone_config.regulation and zone_config.regulation.type == REGULATION_PI:
        if devices and zone_state.last_active_action is not None and zone_state.last_active_action != new_action:
            zone_state.accumulated_error = 0.0
            zone_state.last_pi_update_time = None
            reset_regulation_limits(zone_state)
        previous_integral = zone_state.accumulated_error
        previous_pi_time = zone_state.last_pi_update_time
        regulated_ids = set(zone_config.regulation.devices)
        heating_regulated = needed_mode == HVAC_MODE_HEAT and any(
            device.device_id in regulated_ids for device in devices
        )
        pi_offset = coordinator._calculate_pi_offset(
            zone_config, zone_state, outdoor_temp, is_actively_heating=heating_regulated
        )
        zone_state.regulation_offset = pi_offset
        target_temp = zone_state.target_temperature
        raw = target_temp + pi_offset if target_temp is not None else None
        if heating_regulated:
            zone_state.regulated_setpoint = limit_regulated_setpoint(
                zone_state, zone_config.regulation, raw, dt_util.utcnow()
            )
        else:
            zone_state.regulated_setpoint = raw

    # Cooling mirrors heating: a reversal drops the stale integral, and the step
    # accumulates only while a selected pi device is asked to cool.
    cooling_regulated = False
    has_cool_pi = bool(zone_cool_pi_devices(coordinator, zone_config))
    if has_cool_pi:
        if devices and zone_state.last_active_action is not None and zone_state.last_active_action != new_action:
            zone_state.cool_accumulated_error = 0.0
            zone_state.cool_last_pi_update_time = None
        cooling_regulated = needed_mode == HVAC_MODE_COOL and any(
            getattr(device, "cool_regulation", None) == COOL_REGULATION_PI for device in devices
        )
    previous_cool = _cool_fields(zone_state)
    if has_cool_pi:
        cool_pi_update(coordinator, zone_config, zone_state, active=cooling_regulated)
    return RegulationSnapshot(
        heating_regulated, previous_integral, previous_pi_time, previous_limit,
        cooling_regulated, previous_cool,
    )


def rollback_regulation(
    coordinator: HybridClimateCoordinator,
    zone_config: ZoneConfig,
    zone_state: ZoneState,
    snapshot: RegulationSnapshot,
    activated: list[str],
    outdoor_temp: float | None,
) -> None:
    """Undo the prospective PI accumulation when no regulated command succeeded."""
    if snapshot.heating_regulated and not set(zone_config.regulation.devices).intersection(activated):
        # Failed regulated commands must not wind up PI while backup heat runs.
        zone_state.accumulated_error = snapshot.previous_integral
        zone_state.last_pi_update_time = snapshot.previous_pi_time
        zone_state.regulation_offset = coordinator._calculate_pi_offset(
            zone_config, zone_state, outdoor_temp, is_actively_heating=False
        )
        (zone_state.last_sent_regulated_setpoint,
         zone_state.last_regulated_send_time,
         zone_state.last_regulated_heat_target) = snapshot.previous_limit
        # A prior command is reusable only for the same heat target, and only
        # when a limit is configured (0/0 keeps the recomputed value).
        limits_set = (zone_config.regulation.regulation_threshold > 0
                      or zone_config.regulation.regulation_min_period > 0)
        if (limits_set and zone_state.last_sent_regulated_setpoint is not None
                and zone_state.last_regulated_heat_target == zone_state.target_temperature):
            zone_state.regulated_setpoint = zone_state.last_sent_regulated_setpoint
        else:
            target_temp = zone_state.target_temperature
            zone_state.regulated_setpoint = (
                target_temp + zone_state.regulation_offset if target_temp is not None else None
            )

    if snapshot.cooling_regulated and not any(_is_cool_pi(coordinator, d) for d in activated):
        # A failed pi cool command must not wind up the cooling integral either.
        _restore_cool_fields(zone_state, snapshot.previous_cool)
        cool_pi_update(coordinator, zone_config, zone_state, active=False)


def restore_cool_pi_on_failure(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    state: ZoneState,
    before: ZoneState,
    requested: set[str],
    accepted: set[str],
    results: dict[str, bool],
) -> None:
    """Restore the cooling PI fields when a cooling zone's pi devices all failed to dispatch."""
    if state.hvac_action != HvacAction.COOLING:
        return
    pi_devices = zone_cool_pi_devices(coordinator, coordinator.config.zones[zone_id])
    if not requested.intersection(pi_devices):
        return
    manager = coordinator.device_manager
    # Committed only when a pi device accepted this zone's cool request and runs cool.
    if not any(
        d in accepted and results.get(d) is True
        and zone_id in manager.accepted_zone_requests[d]
        and manager.get_device(d).current_mode == HVAC_MODE_COOL
        for d in pi_devices
    ):
        _restore_cool_fields(state, _cool_fields(before))
