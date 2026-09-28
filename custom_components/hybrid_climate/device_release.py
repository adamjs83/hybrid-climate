"""Purpose: Reconcile zone device ownership and apply capability-safe idle actions.

Key dependencies: models.py, device_manager.py, const.py.
Used by: zone_control.py for staging, shutdown, and PI equilibrium holds.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import HEAT_COOL_REVERSAL_SECONDS, HVAC_MODE_COOL, HVAC_MODE_HEAT, REGULATION_PI
from .models import HvacAction, HvacMode, HybridClimateConfig, MasterMode, ZoneConfig, ZoneState

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


def zone_disabled(coordinator: HybridClimateCoordinator, state: ZoneState) -> bool:
    """Return whether the master or user explicitly disabled this zone."""
    return (
        coordinator.master_state.mode == MasterMode.OFF
        or coordinator.get_current_mode_config().disable_all
        or state.user_mode_override == HvacMode.OFF
    )


def restart_delay_active(state: ZoneState) -> bool:
    """Return whether a released zone must wait before issuing new demand."""
    return (
        state.last_direction_stop_time is not None
        and (dt_util.utcnow() - state.last_direction_stop_time).total_seconds()
        < HEAT_COOL_REVERSAL_SECONDS
    )


async def reconcile_devices(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    config: ZoneConfig,
    state: ZoneState,
    active_devices: list[str],
    *,
    hold_equilibrium: bool = False,
    release_regulated: bool = False,
) -> None:
    """Release dropped devices, retaining ownership until idle or shared handoff succeeds."""
    previously_owned = bool(state.active_devices)
    regulated = set()
    if config.regulation and config.regulation.type == REGULATION_PI:
        regulated = set(config.regulation.devices)
    retained = list(dict.fromkeys(active_devices))
    candidates = set(state.active_devices) - set(retained)
    if hold_equilibrium or release_regulated:
        # Include PI devices held by older cycles even without active ownership.
        candidates.update(regulated - set(retained))

    for device_id in sorted(candidates):
        # Last one out releases shared equipment, including PI-regulated devices.
        if any(
            device_id in other.active_devices
            for other_id, other in coordinator.zone_states.items()
            if other_id != zone_id
        ):
            continue
        device = coordinator.device_manager.get_device(device_id)
        if device is None or not device.is_available:
            retained.append(device_id)
            _LOGGER.warning("Zone %s: retaining unavailable device %s for release", zone_id, device_id)
            continue

        if (
            hold_equilibrium
            and device_id in regulated
            and device.can_heat()
            and state.regulated_setpoint is not None
        ):
            await coordinator.device_manager.set_device_mode(
                device, HVAC_MODE_HEAT, state.regulated_setpoint
            )
            # Equilibrium is still an owned HEAT command and must later be released.
            retained.append(device_id)
            continue

        # Prefer the prior direction only when the physical device supports it.
        was_heating = device.can_heat() and (
            not device.can_cool() or state.last_active_action != HvacAction.COOLING
        )
        target = state.target_temperature if was_heating else state.target_temperature_cool
        if was_heating and target is None:
            target = config.setpoints.default
        if target is None or not (device.can_heat() or device.can_cool()):
            success = await coordinator.device_manager.turn_off_device(device)
        else:
            success = await coordinator.device_manager.set_device_idle(device, target, was_heating)
        if not success:
            retained.append(device_id)
            _LOGGER.warning("Zone %s: retaining device %s after failed idle command", zone_id, device_id)

    state.active_devices = retained
    # Every release path, including empty selections, starts the same off timer.
    if previously_owned and not retained:
        state.last_direction_stop_time = dt_util.utcnow()


async def release_removed_config_devices(
    coordinator: HybridClimateCoordinator, new_config: HybridClimateConfig,
) -> bool:
    """Release removed control directions, returning false if ownership must survive."""
    # Only control references retain ownership; heat sources merely monitor devices.
    retained_entities: set[tuple[str, HvacAction]] = set()
    for zone in new_config.zones.values():
        for stages, action in (
            (zone.heat_stages, HvacAction.HEATING),
            (zone.cool_stages, HvacAction.COOLING),
        ):
            for stage in stages:
                for reference in stage.devices:
                    device = new_config.devices.get(reference.device_id)
                    if device and (
                        device.can_heat() if action == HvacAction.HEATING else device.can_cool()
                    ):
                        retained_entities.add((device.entity_id, action))
        if zone.regulation and zone.regulation.type == REGULATION_PI:
            for device_id in zone.regulation.devices:
                device = new_config.devices.get(device_id)
                if device and device.can_heat():
                    retained_entities.add((device.entity_id, HvacAction.HEATING))

    owned = {
        device_id: state
        for state in coordinator.zone_states.values()
        for device_id in state.active_devices
    }
    coordinator.device_manager.cancel_cycle()
    all_released = True
    released_entities: set[str] = set()
    for device_id, state in owned.items():
        device = coordinator.device_manager.get_device(device_id)
        if device is None:
            _LOGGER.error("Cannot release unknown owned device %s", device_id)
            all_released = False
            continue
        # Physical mode is authoritative when shared owners requested opposing modes.
        was_heating = device.can_heat() and (
            not device.can_cool() or (
                device.current_mode == HVAC_MODE_HEAT
                if device.current_mode in (HVAC_MODE_HEAT, HVAC_MODE_COOL)
                else state.last_active_action != HvacAction.COOLING
            )
        )
        action = HvacAction.HEATING if was_heating else HvacAction.COOLING
        if (device.entity_id, action) in retained_entities:
            continue
        if device.entity_id in released_entities:
            continue
        if not device.is_available:
            _LOGGER.warning("Attempting release of removed unavailable device %s", device_id)
        target = state.target_temperature if was_heating else state.target_temperature_cool
        if target is None:
            released = await coordinator.device_manager.turn_off_device(device)
        else:
            released = await coordinator.device_manager.set_device_idle(device, target, was_heating)
        if released:
            released_entities.add(device.entity_id)
            # Do not repeat successful releases if a later device prevents unloading.
            for owner in coordinator.zone_states.values():
                owner.active_devices = [
                    owned_id for owned_id in owner.active_devices
                    if coordinator.device_manager.get_device(owned_id) is None
                    or coordinator.device_manager.get_device(owned_id).entity_id != device.entity_id
                ]
        else:
            all_released = False
            _LOGGER.warning("Failed to release removed device %s; retaining coordinator", device_id)
    return all_released
