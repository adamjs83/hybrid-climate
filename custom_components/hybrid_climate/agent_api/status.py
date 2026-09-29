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

from ..const import DATA_ACTIVE_REVISION, DOMAIN
from ..diagnostics import _sensor_snapshot, async_get_config_entry_diagnostics
from .controls import zone_controls
from .reasons import zone_reasons
from .revision import ledger, revision_state


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
        view.update(
            regulation_offset=state.regulation_offset,
            accumulated_error=state.accumulated_error,
            regulated_setpoint=state.regulated_setpoint,
            reasons=zone_reasons(view, state),
            controls=zone_controls(hass, entry, ident, zone),
        )
        zones[ident] = view

    # Ownership includes all configured stage references, regardless of activity.
    devices: dict[str, Any] = {}
    for ident, view in snapshot["devices"].items():
        owners = [zid for zid, zone in config.zones.items() if ident in zone.get_all_device_ids()]
        if zone_id is None or zone_id in owners:
            devices[ident] = {**view, "zones": owners}

    reading = coordinator._last_outdoor_reading
    outdoor = {
        "temperature": coordinator.master_state.outdoor_temperature,
        "reading_age_seconds": max(0.0, (now - reading[1]).total_seconds()) if reading else None,
        "sensor_status": _sensor_snapshot(hass, config.outdoor_sensor, coordinator)["status"]
        if config.outdoor_sensor else "not_configured",
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
    }
