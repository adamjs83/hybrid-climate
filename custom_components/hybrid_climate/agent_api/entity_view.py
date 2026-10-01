"""Purpose: Project cached status fields into diagnostic entity states.

Key dependencies: Diagnostics snapshots, Agent API control and reason projections.
Used by: Diagnostic sensor and binary sensor platforms.
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from ..const import REGULATION_PI, STAGE_COOL_PREFIX, STAGE_HEAT_PREFIX, STAGE_NONE, STAGE_OPPORTUNISTIC
from ..capability_check import active_stage_unusable
from .const import (
    STATUS_AGGREGATION_SPREAD, STATUS_OVERRIDE, STATUS_REASON_CODE, STATUS_REPORTED_MODE,
    STATUS_UNCONTROLLED_ACTIVE_MODE,
)
from ..coordinator import HybridClimateCoordinator
from ..diagnostics import _device_snapshot, _zone_snapshot
from .device_control import device_control
from .reasons import zone_reasons
from .sensor_view import temperature_aggregation


def zone_reason_codes(hass: HomeAssistant, coordinator: HybridClimateCoordinator, zone_id: str) -> list[str]:
    """Return the status reason codes for one cached zone snapshot."""
    zone = coordinator.config.zones[zone_id]
    state = coordinator.zone_states[zone_id]
    snapshot = _zone_snapshot(hass, zone_id, zone, state, coordinator)
    _, no_usable = active_stage_unusable(coordinator.config, state, zone_id)
    return [reason[STATUS_REASON_CODE] for reason in zone_reasons(snapshot, state, zone, no_usable)]


def zone_spread(coordinator: HybridClimateCoordinator, zone_id: str) -> float | None:
    """Return the same smoothed-input spread as get_status."""
    return temperature_aggregation(coordinator.config.zones[zone_id], coordinator.zone_states[zone_id])[STATUS_AGGREGATION_SPREAD]


def zone_stage_options(coordinator: HybridClimateCoordinator, zone_id: str) -> list[str]:
    """Build enum options from the loaded stage numbers."""
    zone = coordinator.config.zones[zone_id]
    options = [STAGE_NONE]
    options.extend(f"{STAGE_HEAT_PREFIX}{stage.stage_number}" for stage in zone.heat_stages)
    options.extend(f"{STAGE_COOL_PREFIX}{stage.stage_number}" for stage in zone.cool_stages)
    if zone.heat_stages:
        options.append(STAGE_OPPORTUNISTIC)
    return options


def zone_stage_value(coordinator: HybridClimateCoordinator, zone_id: str) -> str:
    """Return a known stage option, or the idle enum value."""
    stage = coordinator.zone_states[zone_id].current_stage or STAGE_NONE
    return stage if stage in zone_stage_options(coordinator, zone_id) else STAGE_NONE


def device_reported_mode(hass: HomeAssistant, coordinator: HybridClimateCoordinator, device_id: str) -> str | None:
    """Read the same normalized physical mode as the diagnostics device snapshot."""
    return device_mode_snapshot(hass, coordinator, device_id)[0]


def device_uncontrolled_mode(hass: HomeAssistant, coordinator: HybridClimateCoordinator, device_id: str) -> str | None:
    """Return the reported mode only when get_status marks the device uncontrolled."""
    return device_mode_snapshot(hass, coordinator, device_id)[1]


def device_mode_snapshot(
    hass: HomeAssistant, coordinator: HybridClimateCoordinator, device_id: str,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """Project reported mode, uncontrolled mode, and manual override from one device snapshot."""
    config = coordinator.config
    device = config.devices[device_id]
    snapshot = _device_snapshot(
        hass, device, coordinator.device_manager.failed_commands,
        coordinator.device_manager.compressor_protection,
    )
    owners = [zone_id for zone_id, zone in config.zones.items() if device_id in zone.get_all_device_ids()]
    pi_regulated = any(
        zone.regulation and zone.regulation.type == REGULATION_PI and device_id in zone.regulation.devices
        for zone in config.zones.values()
    )
    control = device_control(
        snapshot, device, coordinator.zone_states, tuple(config.zones), owners,
        pi_regulated, coordinator.startup_takeover, overrides=coordinator.manual_overrides,
    )
    reported = snapshot[STATUS_REPORTED_MODE]
    return (
        reported, reported if control[STATUS_UNCONTROLLED_ACTIVE_MODE] else None,
        control[STATUS_OVERRIDE],
    )


def outdoor_source(coordinator: HybridClimateCoordinator) -> tuple[str | None, bool]:
    """Return selected source and whether it differs from the configured primary."""
    reading = getattr(coordinator, "outdoor_reading", None)
    source = reading.source if reading else None
    return source, source is not None and source != coordinator.config.outdoor_sensor
