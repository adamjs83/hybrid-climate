"""Setpoint management, persistence, and mode application.

Handles:
- Master mode setpoint application (home/away/sleep/vacation/boost/off)
- Zone setpoint get/set with persistence to number entities and helpers
- Immediate device updates after setpoint changes

Key dependencies: models.py (MasterMode, MasterModeConfig, ZoneConfig)
Used by: coordinator.py, number.py (via coordinator delegation)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    DEFAULT_HEAT_COOL_DEADBAND,
    DEFAULT_COOL_SETPOINT,
    DEFAULT_AWAY_COOL_RAISE,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    OCCUPANCY_ON_STATES,
    TEMP_MAX_VALID,
    TEMP_MIN_VALID,
)
from .models import MasterMode, MasterModeConfig, ZoneConfig
from .zone_helpers import resolve_number_entity_id

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


def get_current_mode_config(coordinator: HybridClimateCoordinator) -> MasterModeConfig:
    """Get the configuration for the current master mode."""
    return coordinator.config.master.modes.get(
        coordinator.master_state.mode,
        MasterModeConfig(),
    )


def set_master_mode(coordinator: HybridClimateCoordinator, mode: MasterMode) -> None:
    """Set the master operating mode.

    This resets all zone targets to their YAML-configured setpoints for the new mode.
    User changes made after this will persist until the next mode change.
    """
    # Track last non-OFF mode for restore when switching back from OFF
    if mode != MasterMode.OFF:
        coordinator.master_state.last_active_mode = mode

    coordinator.master_state.mode = mode
    _LOGGER.info("Master mode set to: %s", mode.value)

    # Recalculate all zone targets from YAML for the new mode
    apply_mode_setpoints(coordinator)

    # Log the mode config being applied
    mode_config = get_current_mode_config(coordinator)
    _LOGGER.debug(
        "Mode config: disable_all=%s, skip_time_escalation=%s, "
        "setpoint_offset=%s, use_zone_away_setpoints=%s",
        mode_config.disable_all,
        mode_config.skip_time_escalation,
        mode_config.setpoint_offset,
        mode_config.use_zone_away_setpoints,
    )


def get_zone_occupancy(
    coordinator: HybridClimateCoordinator, zone_config: ZoneConfig
) -> bool | None:
    """Return a zone's known occupancy, or None when its sensor is unavailable."""
    entity_id = zone_config.setpoints.occupancy_entity
    state = coordinator.hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    return state.state in OCCUPANCY_ON_STATES


def _selected_setpoint_name(mode: MasterMode, config: MasterModeConfig,
                            occupied: bool | None) -> str:
    """Choose one preset name for both heat and cool directions."""
    if (mode == MasterMode.HOME and occupied is not None
            and config.use_zone_setpoint in (None, "default")
            and not config.use_zone_away_setpoints):
        return "occupied" if occupied else "unoccupied"
    if config.use_zone_setpoint:
        return config.use_zone_setpoint
    if config.use_zone_away_setpoints:
        return "away"
    if mode in (MasterMode.AWAY, MasterMode.SLEEP, MasterMode.VACATION):
        return mode.value
    if mode == MasterMode.HOME and occupied is not None:
        return "occupied" if occupied else "unoccupied"
    return "default"


def get_effective_setpoints(
    coordinator: HybridClimateCoordinator, zone_id: str,
    override: tuple[str, float] | None = None,
    dependencies: dict[str, set[str]] | None = None,
) -> tuple[float, float | None]:
    """Derive operating heat and cool targets from preset, occupancy, and numbers."""
    zone = coordinator.config.zones[zone_id]
    mode_config = get_current_mode_config(coordinator)
    occupied = get_zone_occupancy(coordinator, zone)
    if occupied is None:
        occupied = coordinator._zone_occupancy.get(zone_id)
    name = _selected_setpoint_name(coordinator.master_state.mode, mode_config, occupied)
    used_keys: set[str] = set()

    def number(key: str) -> float | None:
        """Read a number, including a slider value before HA publishes its state."""
        used_keys.add(key)
        if override is not None and override[0] == key:
            return override[1]
        return _resolve_number_value(coordinator, zone_id, key)

    heat = number(f"{name}_heat_temp")
    if heat is None and name in ("occupied", "unoccupied"):
        default_heat = number("default_heat_temp")
        named_heat = getattr(zone.setpoints, name, None)
        if default_heat is not None:
            heat = default_heat + ((named_heat - zone.setpoints.default) if named_heat is not None else 0)
    if heat is None:
        heat = zone.setpoints.get_effective_setpoint(
            coordinator.master_state.mode, occupied, name
        )

    if dependencies is not None:
        dependencies[HVAC_MODE_HEAT] = used_keys.copy()
    used_keys.clear()

    cool: float | None = None
    if zone.cool_stages:
        default_cool = number("default_cool_temp")
        if default_cool is None:
            default_cool = max(DEFAULT_COOL_SETPOINT,
                               zone.setpoints.default + DEFAULT_HEAT_COOL_DEADBAND)
        # Dedicated occupied cooling is also a baseline for empty-house targets.
        baseline = default_cool
        if name in ("away", "unoccupied", "vacation"):
            occupied_cool = number("occupied_cool_temp")
            if occupied_cool is not None:
                baseline = max(baseline, occupied_cool)
        cool = number(f"{name}_cool_temp") if name != "default" else default_cool
        if cool is None:
            if name in ("away", "unoccupied", "vacation"):
                named_heat = getattr(zone.setpoints, name, None)
                heat_delta = abs(named_heat - zone.setpoints.default) if named_heat is not None else 0
                cool = baseline + max(DEFAULT_AWAY_COOL_RAISE, heat_delta)
            else:
                cool = default_cool
        # An empty home must not demand more cooling than its occupied baseline.
        cool += mode_config.setpoint_offset
        if name in ("away", "unoccupied", "vacation"):
            cool = max(cool, baseline, baseline + mode_config.setpoint_offset)

    if dependencies is not None:
        dependencies[HVAC_MODE_COOL] = used_keys.copy()
    return heat + mode_config.setpoint_offset, cool


def apply_mode_setpoints(
    coordinator: HybridClimateCoordinator, zone_id: str | None = None,
    override: tuple[str, float] | None = None,
) -> None:
    """Apply setpoints for the current master mode to all zones.

    Dual-setpoint: Sets both heat and cool target temperatures.
    Priority:
    1. Number entities (number.hybrid_climate_{zone}_{mode}_{heat|cool}_temp)
    2. YAML configuration

    This is called on startup and when master mode changes.
    """
    zones = (zone_id,) if zone_id is not None else coordinator.config.zones
    for zone_id in zones:
        dependencies: dict[str, set[str]] = {}
        heat_setpoint, cool_setpoint = get_effective_setpoints(
            coordinator, zone_id, override, dependencies
        )
        # Slider edits only change directions that depend on that number.
        # Inactive preset edits must preserve manual operating targets.
        update_heat = override is None or override[0] in dependencies[HVAC_MODE_HEAT]
        update_cool = override is None or override[0] in dependencies[HVAC_MODE_COOL]

        # Store heat setpoint
        if update_heat and heat_setpoint is not None:
            coordinator._zone_target_temps[zone_id] = heat_setpoint
            zone_state = coordinator.zone_states.get(zone_id)
            if zone_state:
                zone_state.target_temperature = heat_setpoint

        # Store cool setpoint
        if update_cool and cool_setpoint is not None:
            coordinator._zone_target_temps_cool[zone_id] = cool_setpoint
            zone_state = coordinator.zone_states.get(zone_id)
            if zone_state:
                zone_state.target_temperature_cool = cool_setpoint

        _LOGGER.debug(
            "Zone %s: mode %s heat=%.1f cool=%s",
            zone_id,
            coordinator.master_state.mode.value,
            heat_setpoint if heat_setpoint else 0,
            f"{cool_setpoint:.1f}" if cool_setpoint else "N/A",
        )


async def recompute_setpoints_from_numbers(
    coordinator: HybridClimateCoordinator, zone_id: str | None = None,
    override: tuple[str, float] | None = None,
) -> None:
    """Recompute zone setpoints from number entities when values change.

    This is called by HybridClimateNumberEntity.async_set_native_value()
    when a user adjusts a number slider. It re-runs the setpoint logic
    to pick up the new values.
    """
    _LOGGER.info("Recomputing zone setpoints from number entities")
    apply_mode_setpoints(coordinator, zone_id, override)
    # Log resulting setpoints
    for zone_id, temp in coordinator._zone_target_temps.items():
        _LOGGER.info("Zone %s target after recompute: %.1f", zone_id, temp)





def _resolve_number_value(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    key: str,
) -> float | None:
    """Look up a number entity value using the 3-step fallback chain.

    Priority:
    1. Number entity state (resolved via entity registry)
    2. Persisted number_values in config_entry.options
    3. Legacy input_number helper (backwards compat)
    """
    # 1. Try number entity via entity registry
    entity_id = resolve_number_entity_id(coordinator.hass, zone_id, key)
    state = coordinator.hass.states.get(entity_id) if entity_id else None

    _LOGGER.debug("Looking for setpoint %s (resolved: %s), found: %s",
                  key, entity_id, state.state if state else "None")

    if state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        try:
            return float(state.state)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid number state for %s: %s", key, state.state)

    # 2. Fallback: persisted number_values in config entry options
    if coordinator.entry:
        entry = coordinator.hass.config_entries.async_get_entry(coordinator.entry.entry_id)
        if entry:
            ui_config = entry.options.get("ui_config", {})
            number_values = ui_config.get("number_values", {})
            zone_values = number_values.get(zone_id, {})
            if key in zone_values:
                _LOGGER.debug("Using persisted value for %s_%s: %s", zone_id, key, zone_values[key])
                return float(zone_values[key])

    # 3. Fallback: legacy input_number helper format
    entity_id = f"input_number.hybrid_{zone_id}_{key}"
    state = coordinator.hass.states.get(entity_id)

    if state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        try:
            return float(state.state)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid legacy number state for %s: %s", key, state.state)

    return None


async def set_zone_target_temp(coordinator: HybridClimateCoordinator, zone_id: str, temperature: float) -> None:
    """Set target temperature for a zone (manual override).

    Immediately updates active heating devices to reflect the new target.
    Big setpoint changes trigger partial integral reset to avoid dragging
    stale PI state into a new operating regime.
    """
    if zone_id not in coordinator.config.zones:
        _LOGGER.warning("Unknown zone: %s", zone_id)
        return

    if not TEMP_MIN_VALID <= temperature <= TEMP_MAX_VALID:
        _LOGGER.warning("Invalid temperature: %s", temperature)
        return

    zone_config = coordinator.config.zones[zone_id]
    zone_state = coordinator.zone_states.get(zone_id)

    # Check for big setpoint change and scale integral if needed
    if zone_state and zone_config.regulation:
        regulation = zone_config.regulation
        old_target = zone_state.target_temperature
        if old_target is not None:
            delta = abs(temperature - old_target)
            if delta > regulation.integral_reset_threshold:
                old_integral = zone_state.accumulated_error
                zone_state.accumulated_error *= regulation.integral_reset_factor
                _LOGGER.info(
                    "Zone %s: big setpoint change (%.1f->%.1f, delta%.1f°F), "
                    "scaling integral %.1f -> %.1f",
                    zone_id,
                    old_target,
                    temperature,
                    delta,
                    old_integral,
                    zone_state.accumulated_error,
                )

    coordinator._zone_target_temps[zone_id] = temperature
    if zone_state:
        zone_state.target_temperature = temperature

    _LOGGER.info("Zone %s target temp set to: %s", zone_id, temperature)

    # Log when heat and cool setpoints are crossed — this is valid by design
    # when outdoor reset gates which side is active (seasonal thresholds)
    cool_sp = coordinator._zone_target_temps_cool.get(zone_id)
    if cool_sp is not None and temperature > cool_sp:
        _LOGGER.info(
            "Zone %s: heat setpoint (%.1f) > cool setpoint (%.1f) — "
            "this is valid when outdoor reset gates heating vs cooling",
            zone_id, temperature, cool_sp,
        )

    await _immediate_device_update(coordinator, zone_id, HVAC_MODE_HEAT, temperature)


async def set_zone_target_temp_cool(coordinator: HybridClimateCoordinator, zone_id: str, temperature: float) -> None:
    """Set cool target temperature for a zone (manual override).

    For dual-setpoint zones, this sets the cooling threshold.
    """
    if zone_id not in coordinator.config.zones:
        _LOGGER.warning("Unknown zone: %s", zone_id)
        return

    if not TEMP_MIN_VALID <= temperature <= TEMP_MAX_VALID:
        _LOGGER.warning("Invalid temperature: %s", temperature)
        return

    zone_state = coordinator.zone_states.get(zone_id)

    coordinator._zone_target_temps_cool[zone_id] = temperature
    if zone_state:
        zone_state.target_temperature_cool = temperature

    _LOGGER.info("Zone %s cool target temp set to: %s", zone_id, temperature)

    # Log when heat and cool setpoints are crossed — valid by design
    heat_sp = coordinator._zone_target_temps.get(zone_id)
    if heat_sp is not None and heat_sp > temperature:
        _LOGGER.info(
            "Zone %s: heat setpoint (%.1f) > cool setpoint (%.1f) — "
            "this is valid when outdoor reset gates heating vs cooling",
            zone_id, heat_sp, temperature,
        )

    await _immediate_device_update(coordinator, zone_id, HVAC_MODE_COOL, temperature)


async def _immediate_device_update(
    coordinator: HybridClimateCoordinator,
    zone_id: str,
    direction: str,
    target_temp: float,
) -> None:
    """Push a changed target only to this zone's active devices in that direction."""
    zone_state = coordinator.zone_states.get(zone_id)
    if not zone_state:
        return

    # Ownership is the same list used by last-one-out release; an idle or
    # shared device owned only by another zone must never receive this change.
    for device_id in zone_state.active_devices:
        device = coordinator.device_manager.get_device(device_id)
        if device is None or not device.is_available or device.current_mode != direction:
            continue
        # Preserve the current PI offset until the next control cycle recalculates it.
        config = coordinator.config.zones[zone_id]
        if (direction == HVAC_MODE_HEAT and config.regulation
                and device_id in config.regulation.devices):
            device_target = target_temp + zone_state.regulation_offset
            zone_state.regulated_setpoint = device_target
        else:
            device_target = target_temp
        await coordinator.device_manager.set_device_mode(device, direction, device_target)
