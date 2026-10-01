"""Purpose: Project cached diagnostics into Agent API status responses.

Key dependencies: Diagnostics, revision ledger, owned controls, runtime state.
Used by: Agent API get_status service.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..const import DATA_ACTIVE_REVISION, DOMAIN, REGULATION_PI
from ..capability_check import active_stage_unusable, find_capability_mismatches
from ..diagnostics import _sensor_snapshot, async_get_config_entry_diagnostics
from .controls import zone_controls
from .device_control import device_control
from .entity_view import outdoor_source
from .reasons import zone_reasons
from .revision import ledger, revision_state
from .sensor_view import sensor_values, temperature_aggregation
from .tou_view import zone_tou


async def async_get_status(
    hass: HomeAssistant, entry: ConfigEntry, zone_id: str | None = None,
) -> dict[str, Any]:
    """Enrich the existing diagnostics snapshot without running control decisions."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    config = coordinator.config
    options = deepcopy(dict(entry.options))
    active_revision = runtime[DATA_ACTIVE_REVISION]
    version = ledger(hass).get("version")

    # The diagnostics coroutine currently does not yield; all following reads use
    # the captured coordinator and options to avoid mixing entry generations.
    snapshot = await async_get_config_entry_diagnostics(hass, entry)
    selected = {zone_id: config.zones[zone_id]} if zone_id else config.zones
    now = dt_util.utcnow()
    zones: dict[str, Any] = {}
    for ident, zone in selected.items():
        state = coordinator.zone_states[ident]
        view = deepcopy(snapshot["zones"][ident])
        unusable, no_usable = active_stage_unusable(config, state, ident)
        view.update(
            regulation_offset=state.regulation_offset,
            accumulated_error=state.accumulated_error,
            regulated_setpoint=state.regulated_setpoint,
            reasons=zone_reasons(view, state, zone, no_usable),
            stage_devices_unusable=unusable,
            controls=zone_controls(hass, entry, ident, zone),
            temperature_aggregation=temperature_aggregation(zone, state),
            tou=zone_tou(hass, coordinator.tou_manager, config.tou_global.rate_sensor, zone),
            stage_since=state.stage_start_time.isoformat() if state.stage_start_time else None,
            hvac_action_since=state.hvac_action_since.isoformat() if state.hvac_action_since else None,
        )
        view["sensors"] = {
            entity_id: sensor_values(sensor_view, state, entity_id)
            for entity_id, sensor_view in view["sensors"].items()
        }
        zones[ident] = view

    # Ownership includes all configured stage references, regardless of activity.
    # A device is PI-regulated (and so excluded from startup takeover, spec §7.6)
    # when it appears in a PI zone's regulation.devices; mirrors StartupTakeover.arm().
    pi_regulated_device_ids = {
        device_id
        for zone in config.zones.values()
        if zone.regulation and zone.regulation.type == REGULATION_PI
        for device_id in zone.regulation.devices
    }
    devices: dict[str, Any] = {}
    mismatches = find_capability_mismatches(config)
    for ident, view in snapshot["devices"].items():
        owners = [zid for zid, zone in config.zones.items() if ident in zone.get_all_device_ids()]
        if zone_id is None or zone_id in owners:
            device = config.devices[ident]
            devices[ident] = {
                **view, "zones": owners,
                "last_command_at": device.last_command_at.isoformat() if device.last_command_at else None,
                "control": device_control(
                    view, device, coordinator.zone_states, tuple(config.zones),
                    owners, ident in pi_regulated_device_ids, coordinator.startup_takeover,
                    [item for item in mismatches if item.device == ident],
                    coordinator.manual_overrides,
                ),
            }

    reading = coordinator._last_outdoor_reading
    current = getattr(coordinator, "outdoor_reading", None)
    source, using_fallback = outdoor_source(coordinator)
    outdoor = {
        "temperature": coordinator.master_state.outdoor_temperature,
        "reading_age_seconds": max(0.0, (now - reading[1]).total_seconds()) if reading else None,
        "sensor_status": _sensor_snapshot(hass, config.outdoor_sensor, coordinator)["status"]
        if config.outdoor_sensor else "not_configured",
        "source": source,
        "using_fallback": using_fallback,
        "retained": current.retained if current else False,
        "candidates": [dict(item) for item in current.candidates] if current else [],
        "lockout_latches": {
            ident: {"heat_allowed": values[0], "cool_allowed": values[1]}
            for ident, values in coordinator.conflict_resolver._outdoor_permissions.items()
            if ident in selected
        },
    }
    return {
        "generated_at": now.isoformat(), "version": version,
        "revision": revision_state(options, active_revision),
        "master": snapshot["master"], "outdoor": outdoor,
        "zones": zones, "devices": devices,
        "conflicts": list(coordinator.master_state.active_conflicts),
    }
