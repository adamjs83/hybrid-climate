"""External device synchronization and mutex enforcement.

Handles:
- Device mutex rule enforcement (priority devices block others)
- External device change detection (COMMANDING/LISTENING state machine)
- Bidirectional setpoint sync for allow_command devices

Key dependencies: device_manager.py, conflict_resolver.py, models.py
Used by: coordinator.py (_async_update_data calls these each cycle)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import (
    COMMAND_TIMEOUT_SECONDS,
    EXTERNAL_CHANGE_TOLERANCE_F,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
)
from .models import Device, HvacAction, ZoneState
from .zone_helpers import get_allow_command_devices_for_zone

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)

def _sync_zone_setpoint_from_device(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    zone_state: ZoneState | None,
    current_temp: float,
    current_mode: str,
) -> None:
    """Sync zone setpoint from device, writing to heat or cool target based on mode.

    Only syncs when the device is unambiguously in heat or cool mode.
    For ambiguous modes (off, heat_cool, fan_only, transient), skips sync
    because we can't determine which setpoint the user intended to change.
    """
    if current_mode == HVAC_MODE_COOL:
        coordinator._zone_target_temps_cool[zone_id] = current_temp
        if zone_state:
            zone_state.target_temperature_cool = current_temp
    elif current_mode == HVAC_MODE_HEAT:
        coordinator._zone_target_temps[zone_id] = current_temp
        if zone_state:
            zone_state.target_temperature = current_temp
    else:
        _LOGGER.debug(
            "Device sync skipped for zone %s: ambiguous mode '%s'",
            zone_id, current_mode,
        )


async def enforce_device_mutex_rules(coordinator: HybridClimateCoordinator) -> None:
    """Enforce device mutex rules - priority devices always win.

    This runs every update cycle and ensures:
    1. When a priority device (from 'when' clause) is in a certain mode,
       blocked devices are immediately forced to compatible mode or OFF
    2. External changes that violate mutex are overridden
    3. Zone commands that would violate mutex are corrected

    The rule is: if priority device is heating, blocked devices cannot cool.
                 if priority device is cooling, blocked devices cannot heat.
    """
    mutex_rules = coordinator.config.conflicts.device_mutex
    if not mutex_rules:
        _LOGGER.debug("No mutex rules configured")
        return

    _LOGGER.debug("Enforcing %d mutex rules", len(mutex_rules))
    for rule in mutex_rules:
        _LOGGER.debug(
            "Checking mutex rule: device=%s, mode=%s, for_zone=%s, blocked_heat=%s, blocked_cool=%s",
            rule.device_id, rule.mode, rule.for_zone,
            rule.blocked_devices_heat, rule.blocked_devices_cool
        )
        if not coordinator.conflict_resolver.mutex_rule_active(rule):
            continue

        # Rule is active - enforce on blocked devices
        _LOGGER.debug(
            "Mutex rule active: %s is %s in %s",
            rule.device_id, rule.mode, rule.for_zone
        )

        # Enforce blocked_devices_heat - these devices cannot heat
        for blocked_id in rule.blocked_devices_heat:
            blocked_device = coordinator.device_manager.get_device(blocked_id)
            if blocked_device is None or not blocked_device.is_available:
                continue

            blocked_mode = blocked_device.current_mode
            is_blocked_heating = blocked_mode in (HVAC_MODE_HEAT, "heat", "heating")

            if is_blocked_heating:
                # Blocked device is heating but shouldn't be - turn it off
                _LOGGER.warning(
                    "Mutex enforcement: %s is heating but blocked by %s (%s) - turning OFF",
                    blocked_id, rule.device_id, rule.mode
                )
                if await coordinator.device_manager.set_device_mode(blocked_device, HVAC_MODE_OFF):
                    _remove_blocked_ownership(coordinator, blocked_id)

        # Enforce blocked_devices_cool - these devices cannot cool
        for blocked_id in rule.blocked_devices_cool:
            blocked_device = coordinator.device_manager.get_device(blocked_id)
            if blocked_device is None or not blocked_device.is_available:
                continue

            blocked_mode = blocked_device.current_mode
            is_blocked_cooling = blocked_mode in (HVAC_MODE_COOL, "cool", "cooling")

            if is_blocked_cooling:
                # Blocked device is cooling but shouldn't be - turn it off
                _LOGGER.warning(
                    "Mutex enforcement: %s is cooling but blocked by %s (%s) - turning OFF",
                    blocked_id, rule.device_id, rule.mode
                )
                if await coordinator.device_manager.set_device_mode(blocked_device, HVAC_MODE_OFF):
                    _remove_blocked_ownership(coordinator, blocked_id)


def _remove_blocked_ownership(coordinator: HybridClimateCoordinator, device_id: str) -> None:
    """Remove mutex-released equipment from every zone's active ownership."""
    for state in coordinator.zone_states.values():
        if device_id in state.active_devices:
            state.active_devices.remove(device_id)
            if not state.active_devices:
                state.hvac_action = HvacAction.IDLE
                state.current_stage = None


async def check_external_device_changes(coordinator: HybridClimateCoordinator) -> None:
    """Check for external changes on allow_command devices using state machine.

    State Machine:
    - LISTENING: Device matches our desired state. Any change = external -> sync to overlay.
    - COMMANDING: We sent a command, waiting for device to match. Ignore mismatches.

    Only checks devices that have allow_command=True for at least one zone.
    """
    eligible: dict[str, list[str]] = {}
    for zone_id, zone_config in coordinator.config.zones.items():
        for device_id in get_allow_command_devices_for_zone(zone_config):
            eligible.setdefault(device_id, []).append(zone_id)

    for device_id, zone_ids in eligible.items():
        device = coordinator.device_manager.get_device(device_id)
        if device is None or not device.is_available:
            continue
        # A rejected service can leave the physical mode partially changed.
        # Keep retrying the command without treating that change as a user edit.
        if device_id in coordinator.device_manager.failed_commands:
            continue

        # Get current state from HA
        state = coordinator.hass.states.get(device.entity_id)
        if state is None:
            continue

        current_temp = state.attributes.get("temperature")
        current_mode = state.state  # heat, cool, off
        if current_temp is None:
            continue

        try:
            current_temp = float(current_temp)
        except (ValueError, TypeError):
            _LOGGER.warning("Device %s has invalid target temperature %r", device_id, current_temp)
            continue

        # Initialize desired state on first run
        if device.desired_mode is None:
            device.desired_temp = current_temp
            device.desired_mode = current_mode
            _LOGGER.debug(
                "Device %s: initializing desired state to %.1f/%s",
                device_id,
                current_temp,
                current_mode,
            )
            continue

        # Handle based on current state
        if device.is_commanding():
            # COMMANDING state: waiting for device to match desired
            await _handle_commanding_state(
                coordinator, device, device_id, current_temp, current_mode, zone_ids
            )
        else:
            # LISTENING state: check for external changes
            await _handle_listening_state(
                device, device_id, current_temp, current_mode,
                zone_ids, coordinator
            )

def _sync_eligible_zones(
    coordinator: HybridClimateCoordinator, zone_ids: list[str],
    current_temp: float, current_mode: str,
) -> None:
    """Distribute one physical change before the device acknowledges it."""
    for zone_id in zone_ids:
        _sync_zone_setpoint_from_device(
            coordinator, zone_id, coordinator.zone_states.get(zone_id),
            current_temp, current_mode,
        )


async def _handle_commanding_state(
    coordinator: HybridClimateCoordinator,
    device: Device,
    device_id: str,
    current_temp: float,
    current_mode: str,
    zone_ids: list[str],
) -> None:
    """Handle device in COMMANDING state - waiting for ack or timeout."""
    # Check if device now matches desired state (acknowledged)
    if device.matches_desired(current_temp, current_mode, EXTERNAL_CHANGE_TOLERANCE_F):
        device.command_acknowledged()
        _LOGGER.debug(
            "Device %s acknowledged command (temp=%.1f, mode=%s) -> LISTENING",
            device_id,
            current_temp,
            current_mode,
        )
        return

    # Check for timeout
    if device.command_sent_at:
        elapsed = (dt_util.utcnow() - device.command_sent_at).total_seconds()
        if elapsed > COMMAND_TIMEOUT_SECONDS:
            _LOGGER.warning(
                "Device %s command timeout after %ds (desired=%s, current=%.1f) -> LISTENING",
                device_id,
                int(elapsed),
                device.desired_temp,
                current_temp,
            )
            # A lagging or rejected physical target must not replace zone targets.
            device.command_timeout(current_temp, current_mode)
            return

    # Still waiting for ack
    _LOGGER.debug(
        "Device %s COMMANDING: waiting for ack (desired=%s, current=%.1f)",
        device_id,
        device.desired_temp,
        current_temp,
    )


async def _handle_listening_state(
    device: Device,
    device_id: str,
    current_temp: float,
    current_mode: str,
    zone_ids: list[str],
    coordinator: HybridClimateCoordinator,
) -> None:
    """Handle device in LISTENING state - detect external changes."""
    # Check if device still matches desired state
    if device.matches_desired(current_temp, current_mode, EXTERNAL_CHANGE_TOLERANCE_F):
        # No change - still in sync
        return

    # Device differs from desired - this is an external change!
    _LOGGER.info(
        "External change detected on %s: %.1f/%s (was %s/%s) -> syncing to zones %s",
        device_id,
        current_temp,
        current_mode,
        device.desired_temp,
        device.desired_mode,
        zone_ids,
    )

    # Sync overlay to match underlay
    _sync_eligible_zones(coordinator, zone_ids, current_temp, current_mode)

    # Update desired state to match current (we're now in sync again)
    device.desired_temp = current_temp
    device.desired_mode = current_mode
