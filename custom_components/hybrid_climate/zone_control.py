"""Zone-level control logic: staging, mode determination, device activation.

Handles:
- Determining if a zone needs HEAT/COOL/OFF based on temperature and setpoints
- Stage calculation (which stage to activate based on thresholds and time)
- Device activation/deactivation for zones
- Opportunistic heating (piggybacking on active heat sources)

Key dependencies: models.py, device_manager.py, pi_controller.py, zone_helpers.py, sensor_manager.py
Used by: coordinator.py (_async_update_data calls update_zone each cycle)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import (
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    MIN_HEAT_COOL_GAP,
    REGULATION_PI,
    SENSOR_RESTORE_GRACE_PERIOD_SECONDS,
    SENSOR_STATUS_FAILED,
)
from .device_release import reconcile_devices, restart_delay_active, zone_disabled
from .models import (
    HvacAction,
    HvacMode,
    MasterMode,
    Stage,
    ZoneConfig,
    ZoneState,
)
from .sensor_manager import get_zone_temperature
from .zone_helpers import (
    get_active_heat_sources,
    get_all_zone_devices,
    zone_has_device_in_heat_source,
)

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


async def _set_idle_zone_devices(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    zone_config: ZoneConfig,
    zone_state: ZoneState,
) -> None:
    """Set inactive devices for a zone to idle state."""
    zone_target = zone_state.target_temperature
    if zone_target is None:
        zone_target = zone_config.setpoints.default

    all_devices = get_all_zone_devices(zone_config)
    active_device_ids = set(zone_state.active_devices)

    for device_id in all_devices:
        device = coordinator.device_manager.get_device(device_id)
        if device is None or not device.is_available:
            continue

        if device_id not in active_device_ids:
            is_heating_device = device.can_heat()
            await coordinator.device_manager.set_device_idle(
                device,
                zone_target,
                is_heating_device,
            )


async def apply_opportunistic_heating(
    coordinator: HybridClimateCoordinator,
    outdoor_temp: float | None,
) -> None:
    """Apply opportunistic heating for zones that can piggyback on active boiler.

    When a heat source (e.g., boiler) is already running for one zone,
    other zones in the same heat source group can turn on early to
    piggyback on the same heating cycle.
    """
    if coordinator.master_state.mode == MasterMode.OFF or coordinator.get_current_mode_config().disable_all:
        return

    # Find which heat sources are currently active
    active_sources = get_active_heat_sources(coordinator.config, coordinator.zone_states)
    if not active_sources:
        return

    _LOGGER.debug("Opportunistic heating: active heat sources: %s", active_sources)

    for zone_id, zone_config in coordinator.config.zones.items():
        zone_state = coordinator.zone_states[zone_id]

        # Opportunistic heat cannot replace cooling or bypass user/sensor restrictions.
        if (
            zone_state.hvac_action in (HvacAction.HEATING, HvacAction.COOLING)
            or zone_state.user_mode_override in (HvacMode.OFF, HvacMode.COOL)
            or not zone_state.is_available
        ):
            continue

        # Skip zones without opportunistic enabled
        if not zone_config.opportunistic or not zone_config.opportunistic.enabled:
            continue

        # Skip zones with PI regulation (PI is in control)
        if zone_config.regulation and zone_config.regulation.type == REGULATION_PI:
            continue

        # Check if this zone has devices in any active heat source
        zone_in_active_source = False
        for source_id in active_sources:
            if zone_has_device_in_heat_source(coordinator.config, zone_config, source_id):
                zone_in_active_source = True
                break

        if not zone_in_active_source:
            continue

        # Check if zone error exceeds opportunistic threshold
        target = zone_state.target_temperature
        current = zone_state.current_temperature
        if target is None or current is None:
            continue

        error = target - current  # positive = needs heat
        threshold = zone_config.opportunistic.threshold

        if error >= threshold:
            _LOGGER.info(
                "Opportunistic heating: zone %s piggybacking (error=%.1f >= threshold=%.1f)",
                zone_id,
                error,
                threshold,
            )

            # Activate stage 1 heating for this zone
            await _activate_opportunistic_stage(
                coordinator,
                zone_id,
                zone_config,
                zone_state,
                outdoor_temp,
            )


async def _activate_opportunistic_stage(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    zone_config: ZoneConfig,
    zone_state: ZoneState,
    outdoor_temp: float | None,
) -> None:
    """Activate stage 1 heating for opportunistic piggybacking."""
    # --- Check qualification: find stage 1 devices ---
    stage_1_devices: list[str] = []
    for stage in zone_config.heat_stages:
        if stage.stage_number == 1 and stage.conditions.evaluate(outdoor_temp):
            stage_1_devices = stage.get_device_ids()
            break

    if not stage_1_devices:
        return

    # Get conflict blocking (with zone config for per-zone outdoor reset)
    conflict_result = coordinator.conflict_resolver.resolve_for_zone(
        zone_id,
        outdoor_temp,
        zone_state.target_temperature,
        coordinator.zone_states,
        zone_config,
    )

    # Piggyback heat must obey the same settling delay and directional latch.
    if (
        not conflict_result.can_heat
        or zone_state.current_temperature is None
        or zone_state.target_temperature is None
        or determine_needed_mode(
            zone_state.current_temperature, zone_state.target_temperature,
            zone_state.target_temperature_cool, 0.0, zone_state,
            conflict_result.can_heat,
            conflict_result.can_cool and bool(zone_config.cool_stages)
            and zone_state.user_mode_override != HvacMode.HEAT,
        ) != HVAC_MODE_HEAT
        or (zone_state.active_devices and zone_state.last_active_action == HvacAction.COOLING)
    ):
        _LOGGER.debug(
            "Opportunistic heating blocked for zone %s by conflict",
            zone_id,
        )
        return

    # --- Find devices from active heat sources, excluding blocked ---
    blocked_devices = conflict_result.get_blocked_devices(HVAC_MODE_HEAT)
    available_devices = [d for d in stage_1_devices if d not in blocked_devices]

    devices = coordinator.device_manager.get_devices_for_zone_stage(
        available_devices,
        HVAC_MODE_HEAT,
        blocked_devices,
    )

    if not devices:
        return

    # --- Activate devices with zone target setpoint ---
    target_temp = zone_state.target_temperature
    activated = []
    for device in devices:
        success = await coordinator.device_manager.set_device_mode(
            device, HVAC_MODE_HEAT, target_temp, zone_id=zone_id
        )
        if success:
            activated.append(device.device_id)

    await reconcile_devices(coordinator, zone_id, zone_config, zone_state, activated)
    if activated:
        zone_state.last_active_action = HvacAction.HEATING
        zone_state.hvac_mode = HvacMode.HEAT
        zone_state.hvac_action = HvacAction.HEATING
        zone_state.current_stage = "heating_stage_1_opportunistic"
        zone_state.stage_start_time = dt_util.utcnow()

        _LOGGER.info(
            "Opportunistic heating: zone %s activated devices: %s",
            zone_id,
            activated,
        )


async def update_zone(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    zone_config: ZoneConfig,
    outdoor_temp: float | None,
) -> None:
    """Update a single zone's state and control its devices."""
    zone_state = coordinator.zone_states[zone_id]

    # Get aggregated indoor temperature
    current_temp = await get_zone_temperature(
        zone_config,
        coordinator.hass,
        coordinator._sensor_samples,
        coordinator._last_sensor_values,
        coordinator.zone_states,
        coordinator.device_manager,
        restore_start_times=coordinator._sensor_restore_start_times,
    )
    zone_state.current_temperature = current_temp

    if current_temp is None:
        _LOGGER.warning("Zone %s: no temperature available", zone_id)
        # Retain ownership and action while devices hold their last setpoints.
        # Explicit shutdown and direction lockouts still apply without sensor data.
        conflict = coordinator.conflict_resolver.resolve_for_zone(
            zone_id, outdoor_temp, zone_state.target_temperature,
            coordinator.zone_states, zone_config,
        )
        if (
            zone_disabled(coordinator, zone_state)
            or (zone_state.last_active_action != HvacAction.COOLING and (
                not conflict.can_heat or zone_state.user_mode_override == HvacMode.COOL
            ))
            or (zone_state.last_active_action == HvacAction.COOLING and (
                not conflict.can_cool or zone_state.user_mode_override == HvacMode.HEAT
            ))
        ):
            await _deactivate_zone(
                coordinator, zone_id, zone_config, zone_state, forced_off=True
            )
        zone_state.is_available = False
        zone_state.sensor_status = SENSOR_STATUS_FAILED

        # Edge-triggered notification: only fire once per failure event
        if zone_id not in coordinator._sensor_fail_notified:
            coordinator._sensor_fail_notified.add(zone_id)
            zone_name = zone_config.name or zone_id
            grace_minutes = SENSOR_RESTORE_GRACE_PERIOD_SECONDS // 60
            await coordinator.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Hybrid Climate: Sensor Failure",
                    "message": (
                        f"Zone '{zone_name}' has no sensor data for over "
                        f"{grace_minutes} minutes. "
                        f"Zone control is suspended. Devices remain tracked and "
                        f"shutdown restrictions still apply. Check sensor connectivity."
                    ),
                    "notification_id": f"hybrid_climate_sensor_fail_{zone_id}",
                },
            )
        return

    zone_state.is_available = True

    # Sensor recovery: clear failed state and dismiss notification
    if zone_state.sensor_status == SENSOR_STATUS_FAILED:
        zone_state.sensor_status = None
        _LOGGER.info("Zone %s: sensors recovered, resuming control", zone_id)
    if zone_id in coordinator._sensor_fail_notified:
        coordinator._sensor_fail_notified.discard(zone_id)
        await coordinator.hass.services.async_call(
            "persistent_notification",
            "dismiss",
            {"notification_id": f"hybrid_climate_sensor_fail_{zone_id}"},
        )

    # Get target temperatures (dual-setpoint: heat and cool)
    heat_setpoint = get_zone_target_temp(coordinator, zone_id, zone_config)
    cool_setpoint = coordinator._zone_target_temps_cool.get(zone_id)

    # Preserve base overlay setpoints (not overwritten by TOU)
    if heat_setpoint is not None:
        coordinator._zone_target_temps[zone_id] = heat_setpoint

    # Apply TOU setpoint adjustments (pre-conditioning or peak relaxation)
    # These adjusted values feed into mode determination, staging, and PI —
    # the rest of the control loop is unaware of TOU.
    if heat_setpoint is not None:
        heat_setpoint, cool_setpoint, tou_state = (
            coordinator.tou_manager.get_adjusted_setpoints(
                zone_id, zone_config, heat_setpoint, cool_setpoint
            )
        )
        zone_state.tou_state = tou_state
    else:
        zone_state.tou_state = "normal"

    # Store effective (TOU-adjusted) setpoints in zone state
    zone_state.target_temperature = heat_setpoint
    zone_state.target_temperature_cool = cool_setpoint

    if heat_setpoint is None:
        await _deactivate_zone(coordinator, zone_id, zone_config, zone_state, forced_off=True)
        zone_state.hvac_mode = HvacMode.OFF
        zone_state.hvac_action = HvacAction.OFF
        return

    # Check for conflicts (with zone config for per-zone outdoor reset)
    # This determines what's ALLOWED based on outdoor temp, device mutex, etc.
    conflict_result = coordinator.conflict_resolver.resolve_for_zone(
        zone_id,
        outdoor_temp,
        heat_setpoint,
        coordinator.zone_states,
        zone_config,
    )

    # Determine what the zone needs based on outdoor reset (season logic)
    needed_mode = determine_needed_mode(
        current_temp,
        heat_setpoint,
        cool_setpoint,
        zone_config.settings.hysteresis,
        zone_state,
        conflict_result.can_heat and bool(zone_config.heat_stages)
        and zone_state.user_mode_override not in (HvacMode.COOL, HvacMode.OFF),
        conflict_result.can_cool and bool(zone_config.cool_stages)
        and zone_state.user_mode_override not in (HvacMode.HEAT, HvacMode.OFF),
    )

    # Master mode override - check both OFF mode and disable_all config
    mode_config = coordinator.get_current_mode_config()
    if coordinator.master_state.mode == MasterMode.OFF or mode_config.disable_all:
        if mode_config.disable_all:
            _LOGGER.debug(
                "Zone %s: disable_all is set, forcing OFF",
                zone_id,
            )
        needed_mode = HVAC_MODE_OFF

    # PI equilibrium may keep heating hardware owned while the zone reports idle.
    # Release it before an opposite-direction request and start the off timer.
    if (
        needed_mode in (HVAC_MODE_HEAT, HVAC_MODE_COOL)
        and zone_state.active_devices
        and zone_state.last_active_action is not None
        and needed_mode != zone_state.last_active_action.value.removesuffix("ing")
    ):
        await _deactivate_zone(coordinator, zone_id, zone_config, zone_state, forced_off=True)
        zone_state.last_update = dt_util.utcnow()
        return

    # Calculate temp_diff for staging (based on which mode is needed)
    if needed_mode == HVAC_MODE_HEAT:
        temp_diff = heat_setpoint - current_temp  # Positive = needs heat
    elif needed_mode == HVAC_MODE_COOL and cool_setpoint:
        temp_diff = current_temp - cool_setpoint  # Positive = needs cool
    else:
        temp_diff = 0.0

    # Calculate staging and activate devices
    await _apply_zone_staging(
        coordinator,
        zone_id,
        zone_config,
        zone_state,
        needed_mode,
        temp_diff,
        outdoor_temp,
        conflict_result.get_blocked_devices(needed_mode),
        forced_off=(
            zone_disabled(coordinator, zone_state)
            or (zone_state.last_active_action != HvacAction.COOLING and (
                not conflict_result.can_heat or zone_state.user_mode_override == HvacMode.COOL
            ))
            or (zone_state.last_active_action == HvacAction.COOLING and (
                not conflict_result.can_cool or zone_state.user_mode_override == HvacMode.HEAT
            ))
        ),
    )

    zone_state.last_update = dt_util.utcnow()


def get_zone_target_temp(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    zone_config: ZoneConfig,
) -> float | None:
    """Get the target temperature for a zone.

    Zone targets are stored in _zone_target_temps and are:
    - Initialized from YAML on startup
    - Reset to YAML values on master mode change
    - Updated by user changes via GUI
    - Updated once by external device changes (allow_command)

    This just returns the stored value; YAML is not recalculated here.
    """
    return coordinator._zone_target_temps.get(zone_id)


def determine_needed_mode(
    current_temp: float,
    heat_setpoint: float,
    cool_setpoint: float | None,
    hysteresis: float,
    zone_state: ZoneState,
    can_heat: bool,
    can_cool: bool,
) -> str:
    """Determine what mode the zone needs based on outdoor reset constraints.

    OUTDOOR RESET IS THE PRIMARY DRIVER (season logic):
    - If only heat allowed (can_heat=True, can_cool=False):
      -> HEAT SEASON: only compare to heat_setpoint, ignore cool_setpoint
      -> Overshoot above cool_setpoint does NOT trigger cooling
      -> PI backs off, room naturally cools
    - If only cool allowed (can_heat=False, can_cool=True):
      -> COOL SEASON: only compare to cool_setpoint, ignore heat_setpoint
      -> Undershoot below heat_setpoint does NOT trigger heating
      -> PI backs off, room naturally warms
    - If both allowed (transition weather):
      -> Use both setpoints with deadband between them
    - If neither allowed:
      -> IDLE (extreme weather or weird config)

    Uses hysteresis to prevent rapid cycling at setpoint boundaries.
    """
    # Seasonal/user restrictions take precedence over the dual-direction latch.
    dual_direction = can_heat and can_cool
    # An active direction must release before the other direction may start.
    if zone_state.hvac_action == HvacAction.HEATING:
        can_cool = False
    elif zone_state.hvac_action == HvacAction.COOLING:
        can_heat = False
    elif restart_delay_active(zone_state):
        return HVAC_MODE_OFF

    # Crossed targets are independent seasonal settings. Keep the prior season
    # until the room has traveled clear of its prior target by a safe margin.
    if (dual_direction and cool_setpoint is not None
            and cool_setpoint - heat_setpoint < MIN_HEAT_COOL_GAP):
        if zone_state.last_active_action == HvacAction.HEATING:
            can_cool = can_cool and current_temp >= heat_setpoint + MIN_HEAT_COOL_GAP
        elif zone_state.last_active_action == HvacAction.COOLING:
            can_heat = can_heat and current_temp <= cool_setpoint - MIN_HEAT_COOL_GAP

    # Neither allowed (extreme weather blocking both)
    if not can_heat and not can_cool:
        return HVAC_MODE_OFF

    # HEAT SEASON: outdoor reset blocks cooling
    # Only look at heat_setpoint, ignore cool_setpoint entirely
    # Room overshoot does NOT trigger cooling - PI will back off
    if can_heat and not can_cool:
        heat_diff = heat_setpoint - current_temp  # Positive = needs heat

        if zone_state.hvac_action == HvacAction.HEATING:
            if heat_diff > 0:
                return HVAC_MODE_HEAT  # Still below setpoint, keep heating
            return HVAC_MODE_OFF  # At/above setpoint, PI will back off

        if heat_diff > hysteresis:
            return HVAC_MODE_HEAT  # Cold enough to start heating

        return HVAC_MODE_OFF  # Above setpoint, stay off (natural cooling)

    # COOL SEASON: outdoor reset blocks heating
    # Only look at cool_setpoint, ignore heat_setpoint entirely
    # Room undershoot does NOT trigger heating - PI will back off
    if can_cool and not can_heat:
        if not cool_setpoint:
            return HVAC_MODE_OFF

        cool_diff = current_temp - cool_setpoint  # Positive = needs cool

        if zone_state.hvac_action == HvacAction.COOLING:
            if cool_diff > 0:
                return HVAC_MODE_COOL  # Still above setpoint, keep cooling
            return HVAC_MODE_OFF  # At/below setpoint, PI will back off

        if cool_diff > hysteresis:
            return HVAC_MODE_COOL  # Hot enough to start cooling

        return HVAC_MODE_OFF  # Below setpoint, stay off (natural warming)

    # TRANSITION WEATHER: both heat and cool allowed
    # Use dual setpoints with deadband - this is the only case where
    # we might switch between heat and cool based on temperature
    heat_diff = heat_setpoint - current_temp
    cool_diff = (current_temp - cool_setpoint) if cool_setpoint else 0

    if zone_state.hvac_action == HvacAction.HEATING:
        if heat_diff > 0:
            return HVAC_MODE_HEAT
        return HVAC_MODE_OFF

    if zone_state.hvac_action == HvacAction.COOLING:
        if cool_setpoint and cool_diff > 0:
            return HVAC_MODE_COOL
        return HVAC_MODE_OFF

    # Currently idle - use hysteresis to decide when to start
    if heat_diff > hysteresis:
        return HVAC_MODE_HEAT
    elif cool_setpoint and cool_diff > hysteresis:
        return HVAC_MODE_COOL

    return HVAC_MODE_OFF  # Within comfort deadband


async def _apply_zone_staging(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    zone_config: ZoneConfig,
    zone_state: ZoneState,
    needed_mode: str,
    temp_diff: float,
    outdoor_temp: float | None,
    blocked_devices: list[str],
    *,
    forced_off: bool = False,
) -> None:
    """Calculate and apply staging for a zone."""
    if restart_delay_active(zone_state) and not zone_state.active_devices:
        # Do not let an idle PI hold reacquire heating during a reversal delay.
        needed_mode = HVAC_MODE_OFF
        forced_off = True
    if needed_mode == HVAC_MODE_OFF:
        # Run PI in idle mode (no integral accumulation) before deactivating
        if not forced_off and zone_config.regulation and zone_config.regulation.type == REGULATION_PI:
            pi_offset = coordinator._calculate_pi_offset(
                zone_config, zone_state, outdoor_temp, is_actively_heating=False
            )
            zone_state.regulation_offset = pi_offset
            target_temp = zone_state.target_temperature
            zone_state.regulated_setpoint = target_temp + pi_offset if target_temp else None
        await _deactivate_zone(
            coordinator, zone_id, zone_config, zone_state,
            forced_off=forced_off,
        )
        return

    new_action = HvacAction.HEATING if needed_mode == HVAC_MODE_HEAT else HvacAction.COOLING
    if zone_state.last_active_action is not None and zone_state.last_active_action != new_action:
        zone_state.escalated_at = None

    # Get stages for the needed mode
    stages = (
        zone_config.heat_stages
        if needed_mode == HVAC_MODE_HEAT
        else zone_config.cool_stages
    )

    if not stages:
        _LOGGER.warning(
            "Zone %s has no %s stages configured",
            zone_id,
            needed_mode,
        )
        await reconcile_devices(
            coordinator, zone_id, zone_config, zone_state, [], release_regulated=True
        )
        zone_state.hvac_mode = HvacMode(needed_mode)
        zone_state.hvac_action = HvacAction.IDLE
        zone_state.current_stage = None
        zone_state.stage_start_time = None
        zone_state.escalated_at = None
        return

    # Determine which stage to activate FIRST, before PI calculation
    # This lets us know if we're actually heating or just in comfort band
    target_stage = _calculate_target_stage(
        coordinator,
        stages,
        abs(temp_diff),
        outdoor_temp,
        zone_state,
        zone_config.settings.hysteresis,
        needed_mode,
    )

    if target_stage is None:
        # Below the entry threshold, PI must still refresh the equilibrium
        # setpoint and timestamp without integrating an inactive demand.
        if zone_config.regulation and zone_config.regulation.type == REGULATION_PI:
            zone_state.regulation_offset = coordinator._calculate_pi_offset(
                zone_config, zone_state, outdoor_temp, is_actively_heating=False
            )
            target_temp = zone_state.target_temperature
            zone_state.regulated_setpoint = (
                target_temp + zone_state.regulation_offset if target_temp is not None else None
            )
        await _deactivate_zone(
            coordinator, zone_id, zone_config, zone_state,
            forced_off=(
                forced_off or (needed_mode == HVAC_MODE_COOL
                               and zone_state.last_active_action != HvacAction.COOLING)
            ),
        )
        return

    # Collect all devices for this and lower stages (additive)
    all_devices: list[str] = []
    for stage in stages:
        if (stage.stage_number <= target_stage.stage_number
                and stage.conditions.evaluate(outdoor_temp)):
            all_devices.extend(stage.get_device_ids())

    # Remove blocked devices
    available_devices = [d for d in all_devices if d not in blocked_devices]
    zone_state.blocked_devices = [d for d in all_devices if d in blocked_devices]

    # Get device objects
    devices = coordinator.device_manager.get_devices_for_zone_stage(
        available_devices,
        needed_mode,
        blocked_devices,
    )

    # Calculate the command with a prospective integral; commit accumulation
    # only if at least one regulated heating command succeeds below.
    heating_regulated = False
    previous_integral = zone_state.accumulated_error
    previous_pi_time = zone_state.last_pi_update_time
    if zone_config.regulation and zone_config.regulation.type == REGULATION_PI:
        if devices and zone_state.last_active_action is not None and zone_state.last_active_action != new_action:
            zone_state.accumulated_error = 0.0
            zone_state.last_pi_update_time = None
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
        zone_state.regulated_setpoint = target_temp + pi_offset if target_temp is not None else None

    if not devices:
        _LOGGER.warning(
            "Zone %s: no available devices for %s",
            zone_id,
            needed_mode,
        )
        await reconcile_devices(
            coordinator, zone_id, zone_config, zone_state, [], release_regulated=True
        )
        zone_state.hvac_action = HvacAction.IDLE
        zone_state.current_stage = None
        zone_state.stage_start_time = None
        zone_state.escalated_at = None
        return

    # Use appropriate setpoint based on mode
    if needed_mode == HVAC_MODE_COOL:
        target_temp = zone_state.target_temperature_cool
        # PI regulation doesn't apply to cooling (regulated devices are heat-only)
        regulated_setpoint = target_temp
    else:
        target_temp = zone_state.target_temperature
        regulated_setpoint = zone_state.regulated_setpoint

    # Get list of regulated device IDs
    regulated_device_ids = set()
    if zone_config.regulation and zone_config.regulation.type == REGULATION_PI:
        regulated_device_ids = set(zone_config.regulation.devices)

    # Activate devices with appropriate setpoints
    activated = []
    for device in devices:
        # Determine setpoint for this device
        if device.device_id in regulated_device_ids:
            device_setpoint = regulated_setpoint
        else:
            device_setpoint = target_temp

        # Activate device
        if needed_mode == HVAC_MODE_HEAT:
            success = await coordinator.device_manager.set_device_mode(
                device, HVAC_MODE_HEAT, device_setpoint, zone_id=zone_id
            )
        else:
            success = await coordinator.device_manager.set_device_mode(
                device, HVAC_MODE_COOL, device_setpoint, zone_id=zone_id
            )

        if success:
            activated.append(device.device_id)

    if heating_regulated and not regulated_device_ids.intersection(activated):
        # Failed regulated commands must not wind up PI while backup heat runs.
        zone_state.accumulated_error = previous_integral
        zone_state.last_pi_update_time = previous_pi_time
        zone_state.regulation_offset = coordinator._calculate_pi_offset(
            zone_config, zone_state, outdoor_temp, is_actively_heating=False
        )
        zone_state.regulated_setpoint = (
            target_temp + zone_state.regulation_offset if target_temp is not None else None
        )

    # Release using the previous direction before recording the new action.
    await reconcile_devices(
        coordinator, zone_id, zone_config, zone_state, activated,
        release_regulated=needed_mode == HVAC_MODE_COOL,
    )

    if not activated:
        # An unsuccessful activation cannot start a direction or escalation timer.
        zone_state.hvac_action = HvacAction.IDLE
        zone_state.current_stage = None
        zone_state.stage_start_time = None
        zone_state.escalated_at = None
        return

    # Update zone state
    if needed_mode == HVAC_MODE_HEAT:
        zone_state.hvac_mode = HvacMode.HEAT
        zone_state.hvac_action = HvacAction.HEATING
        zone_state.last_active_action = HvacAction.HEATING
    else:
        zone_state.hvac_mode = HvacMode.COOL
        zone_state.hvac_action = HvacAction.COOLING
        zone_state.last_active_action = HvacAction.COOLING

    new_stage_name = f"{needed_mode}ing_stage_{target_stage.stage_number}"
    if zone_state.current_stage != new_stage_name:
        zone_state.current_stage = new_stage_name
        zone_state.stage_start_time = dt_util.utcnow()
    if (target_stage.stage_number > min(stage.stage_number for stage in stages)
            and zone_state.escalated_at is None):
        zone_state.escalated_at = dt_util.utcnow()

    _LOGGER.debug(
        "Zone %s: %s stage %d, devices: %s, PI offset: %.1f",
        zone_id,
        needed_mode,
        target_stage.stage_number,
        activated,
        zone_state.regulation_offset,
    )


def _calculate_target_stage(
    coordinator: HybridClimateCoordinator,
    stages: list[Stage],
    temp_diff_abs: float,
    outdoor_temp: float | None,
    zone_state: ZoneState,
    hysteresis: float = 0.0,
    needed_mode: str | None = None,
) -> Stage | None:
    """Calculate which stage should be active.

    Considers:
    - Temperature differential thresholds
    - Time escalation (skipped if skip_time_escalation config is set)
    - Outdoor temperature conditions
    - Boost mode (uses skip_time_escalation from mode config)
    """
    target_stage: Stage | None = None
    direction = needed_mode or (
        HVAC_MODE_COOL if zone_state.hvac_action == HvacAction.COOLING else HVAC_MODE_HEAT
    )
    same_direction = zone_state.last_active_action == (
        HvacAction.HEATING if direction == HVAC_MODE_HEAT else HvacAction.COOLING
    )
    if not same_direction:
        zone_state.escalated_at = None

    # Check if time escalation should be skipped (from mode config)
    mode_config = coordinator.get_current_mode_config()
    skip_time_escalation = mode_config.skip_time_escalation

    for stage in sorted(stages, key=lambda s: s.stage_number):
        # Check outdoor temp conditions
        if not stage.conditions.evaluate(outdoor_temp):
            _LOGGER.debug(
                "Stage %d conditions not met (outdoor: %s)",
                stage.stage_number,
                outdoor_temp,
            )
            continue

        # Check threshold
        if stage.should_activate_by_threshold(temp_diff_abs):
            target_stage = stage
            continue

        # An upper stage stays engaged for this demand cycle until satisfaction.
        if (same_direction and zone_state.escalated_at is not None
                and zone_state.current_stage
                and zone_state.current_stage.startswith(f"{direction}ing_stage_")
                and stage.stage_number <= int(zone_state.current_stage.split("stage_", 1)[1].split("_", 1)[0])
                and temp_diff_abs > 0):
            target_stage = stage
            continue

        # A stage already running stays on through its configured hysteresis band.
        active_direction = (
            (zone_state.hvac_action == HvacAction.HEATING and zone_state.current_stage.startswith("heating_stage_"))
            or (zone_state.hvac_action == HvacAction.COOLING and zone_state.current_stage.startswith("cooling_stage_"))
        ) if zone_state.current_stage else False
        if (active_direction and zone_state.current_stage.startswith(f"{direction}ing_stage_")
                and temp_diff_abs > max(0.0, stage.threshold - hysteresis)
                and stage.stage_number <= int(zone_state.current_stage.split("stage_", 1)[1].split("_", 1)[0])):
            target_stage = stage
            continue

        # Check time escalation
        if stage.time_escalation:
            if skip_time_escalation:
                # Skip time wait - activate immediately if any heat/cool needed
                if temp_diff_abs > 0:
                    _LOGGER.debug(
                        "Skip time escalation: activating stage %d immediately",
                        stage.stage_number,
                    )
                    target_stage = stage
                continue

            if target_stage and same_direction:
                # Check if previous stage has been active long enough
                time_in_stage = zone_state.time_in_current_stage()
                if time_in_stage >= stage.time_escalation:
                    _LOGGER.info(
                        "Time escalation: stage %d after %ds",
                        stage.stage_number,
                        time_in_stage,
                    )
                    target_stage = stage

    return target_stage


async def _deactivate_zone(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    zone_config: ZoneConfig,
    zone_state: ZoneState,
    *,
    forced_off: bool = False,
) -> None:
    """Release devices, retaining PI equilibrium only during permitted heating idle."""
    # Explicit shutdown and lockouts must not wait for minimum runtime.
    if not forced_off and zone_state.stage_start_time and zone_state.active_devices:
        if zone_state.time_in_current_stage() < zone_config.settings.min_runtime:
            return

    await reconcile_devices(
        coordinator, zone_id, zone_config, zone_state, [],
        hold_equilibrium=(
            not forced_off and zone_state.last_active_action != HvacAction.COOLING
        ),
        release_regulated=True,
    )

    # Keep hvac_mode as heat/cool based on zone capabilities, just set action to idle
    # This shows the zone is still in heating/cooling mode, just not actively calling
    if zone_config.heat_stages and not zone_config.cool_stages:
        zone_state.hvac_mode = HvacMode.HEAT
    elif zone_config.cool_stages and not zone_config.heat_stages:
        zone_state.hvac_mode = HvacMode.COOL
    elif zone_config.heat_stages and zone_config.cool_stages:
        # Has both - keep current mode or default to auto
        if zone_state.hvac_mode not in (HvacMode.HEAT, HvacMode.COOL):
            zone_state.hvac_mode = HvacMode.AUTO
    else:
        zone_state.hvac_mode = HvacMode.OFF

    zone_state.hvac_action = HvacAction.IDLE
    zone_state.current_stage = None
    zone_state.stage_start_time = None
    zone_state.escalated_at = None
