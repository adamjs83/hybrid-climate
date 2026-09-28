"""Zone and device lookup helpers for the coordinator.

Key dependencies: models.py (ZoneConfig, HybridClimateConfig, ZoneState, MasterState)
Used by: coordinator.py, zone_control.py, external_sync.py, setpoint_manager.py, pi_controller.py
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

if TYPE_CHECKING:
    from .conflict_resolver import ConflictResolver
    from .models import HybridClimateConfig, MasterState, ZoneConfig, ZoneState

_LOGGER = logging.getLogger(__name__)


def resolve_number_entity_id(
    hass: HomeAssistant, zone_id: str, key: str
) -> str | None:
    """Resolve the actual HA entity_id for a number entity by unique_id.

    Number entities have unique_id = hybrid_climate_{zone_id}_{key},
    but HA-generated entity_ids don't match the simple construction
    (they include the device name slug + entity name slug).
    Use the entity registry to find the correct entity_id.
    """
    unique_id = f"{DOMAIN}_{zone_id}_{key}"
    registry = er.async_get(hass)
    return registry.async_get_entity_id("number", DOMAIN, unique_id)


def get_all_zone_devices(zone_config: ZoneConfig) -> set[str]:
    """Get all device IDs configured for a zone (from all stages)."""
    devices: set[str] = set()
    for stage in zone_config.heat_stages:
        devices.update(stage.get_device_ids())
    for stage in zone_config.cool_stages:
        devices.update(stage.get_device_ids())
    return devices


def get_allow_command_devices_for_zone(zone_config: ZoneConfig) -> set[str]:
    """Get device IDs that have allow_command=True for this zone."""
    return set(zone_config.get_allow_command_device_ids())


def get_zones_for_device(config: HybridClimateConfig, device_id: str) -> list[str]:
    """Find which zone(s) a device belongs to."""
    zones = []
    for zone_id, zone_config in config.zones.items():
        if device_id in get_all_zone_devices(zone_config):
            zones.append(zone_id)
    return zones


def get_heat_source_for_device(config: HybridClimateConfig, device_id: str) -> str | None:
    """Find which heat source group a device belongs to."""
    for source_id, source_config in config.heat_sources.items():
        if device_id in source_config.devices:
            return source_id
    return None


def is_heat_source_active(
    config: HybridClimateConfig,
    zone_states: dict[str, ZoneState],
    source_id: str,
) -> bool:
    """Check if any device in the heat source group is actively heating."""
    from .models import HvacAction

    source_config = config.heat_sources.get(source_id)
    if not source_config:
        return False

    for device_id in source_config.devices:
        # Check if this device is in any zone's active_devices and that zone is heating
        for zone_state in zone_states.values():
            if device_id in zone_state.active_devices and zone_state.hvac_action == HvacAction.HEATING:
                return True
    return False


def get_active_heat_sources(
    config: HybridClimateConfig,
    zone_states: dict[str, ZoneState],
) -> set[str]:
    """Get all heat source groups that have active heating devices."""
    active_sources: set[str] = set()
    for source_id, source_config in config.heat_sources.items():
        if is_heat_source_active(config, zone_states, source_id):
            active_sources.add(source_id)
    return active_sources


def zone_has_device_in_heat_source(
    config: HybridClimateConfig,
    zone_config: ZoneConfig,
    source_id: str,
) -> bool:
    """Check if a zone has any heating devices in the given heat source."""
    source_config = config.heat_sources.get(source_id)
    if not source_config:
        return False

    # Check zone's stage 1 heat devices (opportunistic only activates stage 1)
    for stage in zone_config.heat_stages:
        if stage.stage_number == 1:
            for device_id in stage.get_device_ids():
                if device_id in source_config.devices:
                     return True
    return False


def update_master_summaries(
    master_state: MasterState,
    zone_states: dict[str, ZoneState],
    conflict_resolver: ConflictResolver,
    outdoor_temperature: float | None,
    config: HybridClimateConfig,
) -> None:
    """Update master state with zone summaries."""
    from .models import HvacAction

    heating = []
    cooling = []
    idle = []

    for zone_id, zone_state in zone_states.items():
        if zone_state.hvac_action == HvacAction.HEATING:
            heating.append(zone_id)
        elif zone_state.hvac_action == HvacAction.COOLING:
            cooling.append(zone_id)
        else:
            idle.append(zone_id)

    master_state.zones_heating = heating
    master_state.zones_cooling = cooling
    master_state.zones_idle = idle

    # Resolve all conflicts to populate active_conflicts list
    zone_target_temps = {
        zone_id: state.target_temperature
        for zone_id, state in zone_states.items()
    }
    conflict_resolver.get_all_conflicts(
        outdoor_temperature,
        zone_states,
        zone_target_temps,
        config.zones,  # Pass zone configs for per-zone outdoor reset
    )
    master_state.active_conflicts = conflict_resolver.active_conflicts
