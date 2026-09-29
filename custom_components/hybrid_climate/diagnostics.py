"""Purpose: Export a safe, live snapshot for Home Assistant diagnostics.

Key dependencies: Coordinator runtime state and Home Assistant entity states.
Used by: Home Assistant's config entry diagnostics endpoint.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


def _value(value: Any) -> Any:
    """Convert an enum to its stable string value."""
    return getattr(value, "value", value)


def _temperature(value: Any) -> float | None:
    """Export only numeric temperatures from external HA state attributes."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _sensor_snapshot(hass: HomeAssistant, sensor_id: str, coordinator: Any) -> dict[str, Any]:
    """Describe sensor availability without exporting arbitrary state attributes."""
    state = hass.states.get(sensor_id)
    if state is None:
        status = "missing"
    elif state.state in ("unknown", "unavailable"):
        status = state.state
    else:
        status = "available"

    cached = coordinator._last_sensor_values.get(sensor_id)
    return {
        "status": status,
        "using_cached_value": status != "available" and cached is not None,
    }


def _device_snapshot(
    hass: HomeAssistant, device: Any, failed: set[str], compressor: Any,
) -> dict[str, Any]:
    """Compare the last requested command with the live HA entity state."""
    state = hass.states.get(device.entity_id)
    reported_mode = state.state if state else None
    reported_target = _temperature(state.attributes.get("temperature")) if state else None
    if reported_mode not in ("heat", "cool", "off", "auto", "unavailable", "unknown", None):
        reported_mode = "unexpected"

    return {
        "entity_id": device.entity_id,
        "available": device.is_available,
        "command_failed": device.device_id in failed,
        "compressor_group": device.compressor_group,
        "compressor_hold_reason": compressor.blocked_reasons.get(device.device_id),
        "command_state": _value(device.command_state),
        "desired_mode": device.desired_mode,
        "desired_target_temperature": device.desired_temp,
        "command_sent_at": device.command_sent_at.isoformat() if device.command_sent_at else None,
        "reported_mode": reported_mode,
        "reported_target_temperature": reported_target,
        "mode_matches": device.desired_mode == reported_mode if device.desired_mode is not None else None,
    }


def _zone_snapshot(hass: HomeAssistant, zone: Any, state: Any, coordinator: Any) -> dict[str, Any]:
    """Describe demand, restrictions, and the sensors used by a zone."""
    reasons: list[str] = []
    if state.sensor_status == "failed":
        reasons.append("sensor_failure")
    if _value(coordinator.master_state.mode) == "off":
        reasons.append("master_off")
    if _value(state.user_mode_override) == "off":
        reasons.append("zone_off")
    if state.blocked_devices:
        reasons.append("device_conflict")
    if state.opening_lockout:
        reasons.append("opening_lockout")
    compressor = coordinator.device_manager.compressor_protection
    if any(device_id in compressor.blocked_reasons for device_id in zone.get_all_device_ids()):
        reasons.append("compressor_hold")
    if any(device_id in coordinator.device_manager.failed_commands for device_id in state.active_devices):
        reasons.append("device_command_failed")

    return {
        "current_temperature": state.current_temperature,
        "heat_target": state.target_temperature,
        "cool_target": state.target_temperature_cool,
        "hvac_mode": _value(state.hvac_mode),
        "hvac_action": _value(state.hvac_action),
        "stage": state.current_stage,
        "active_devices": list(state.active_devices),
        "blocked_devices": list(state.blocked_devices),
        "blocking_reasons": reasons,
        "sensor_status": state.sensor_status or "normal",
        "opening_status": state.opening_status,
        "opening_lockout": state.opening_lockout,
        "opening_changed_at": state.opening_changed_at.isoformat() if state.opening_changed_at else None,
        "opening_contacts": {
            entity_id: _opening_contact_status(hass, entity_id)
            for entity_id in zone.openings.entities
        } if zone.openings else {},
        "sensors": {
            sensor_id: _sensor_snapshot(hass, sensor_id, coordinator)
            for sensor_id in zone.sensors.indoor
        },
    }


def _opening_contact_status(hass: HomeAssistant, entity_id: str) -> str:
    """Report only a contact's recognized on/off/unknown state."""
    state = hass.states.get(entity_id)
    if state is None:
        return "missing"
    return state.state if state.state in ("on", "off") else "unknown"


def _compressor_snapshot(compressor: Any) -> dict[str, Any]:
    """Summarize observed shared-compressor group state."""
    return {
        group_id: {
            "active_devices": sorted(state.active_devices),
            "changed_at": state.changed_at.isoformat(),
        }
        for group_id, state in compressor.states.items()
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry,
) -> dict[str, Any]:
    """Return live diagnostics without exporting entry data, options, or HA attributes."""
    runtime = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    if runtime is None:
        return {"error": "Integration not loaded"}

    coordinator = runtime["coordinator"]
    config = coordinator.config
    return {
        "last_update_success": coordinator.last_update_success,
        "master": {
            "mode": _value(coordinator.master_state.mode),
            "outdoor_temperature": coordinator.master_state.outdoor_temperature,
            "active_conflict_count": len(coordinator.master_state.active_conflicts),
        },
        "zones": {
            zone_id: _zone_snapshot(hass, zone, coordinator.zone_states[zone_id], coordinator)
            for zone_id, zone in config.zones.items()
            if zone_id in coordinator.zone_states
        },
        "devices": {
            device_id: _device_snapshot(
                hass, device, coordinator.device_manager.failed_commands,
                coordinator.device_manager.compressor_protection,
            )
            for device_id, device in config.devices.items()
        },
        "compressor_groups": _compressor_snapshot(
            coordinator.device_manager.compressor_protection
        ),
    }
