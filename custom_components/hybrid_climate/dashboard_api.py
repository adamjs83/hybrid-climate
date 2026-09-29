"""Purpose: Supply safe dashboard discovery data and serve the Lovelace card.

Key dependencies: Home Assistant WebSocket, HTTP, and entity registries.
Used by: Integration setup and the Hybrid Climate Lovelace card.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .diagnostics import _zone_snapshot
from .number_definitions import PI_NUMBERS, SETPOINT_NUMBERS


DASHBOARD_COMMAND = f"{DOMAIN}/dashboard_info"
DASHBOARD_CARD_URL = f"/{DOMAIN}/hybrid-climate-card.js"


def _entity_id(registry: er.EntityRegistry, platform: str, unique_id: str) -> str | None:
    """Resolve the registered entity ID, including user-renamed entities."""
    return registry.async_get_entity_id(platform, DOMAIN, unique_id)


def _number_controls(
    registry: er.EntityRegistry, zone_id: str, zone: Any,
) -> dict[str, Any]:
    """List only registered controls supported by this zone."""
    setpoints: dict[str, dict[str, str]] = {}
    pi: dict[str, str] = {}
    has_heat = bool(zone.heat_stages)
    has_cool = bool(zone.cool_stages)

    for description in SETPOINT_NUMBERS:
        if description.is_cooling and not has_cool:
            continue
        if not description.is_cooling and not has_heat:
            continue
        entity_id = _entity_id(registry, "number", f"{DOMAIN}_{zone_id}_{description.key}")
        if entity_id is not None:
            mode = description.setpoint_mode
            direction = "cool" if description.is_cooling else "heat"
            setpoints.setdefault(mode, {})[direction] = entity_id

    if zone.regulation is not None and zone.regulation.type == "pi":
        for description in PI_NUMBERS:
            entity_id = _entity_id(registry, "number", f"{DOMAIN}_{zone_id}_{description.key}")
            if entity_id is not None:
                pi[description.pi_param] = entity_id

    return {"setpoints": setpoints, "pi": pi}


def _zone_devices(hass: HomeAssistant, zone: Any, config: Any) -> list[dict[str, str]]:
    """Return each configured device once, preserving stage order."""
    devices: list[dict[str, str]] = []
    seen: set[str] = set()
    for stage in zone.heat_stages + zone.cool_stages:
        for stage_device in stage.devices:
            device_id = stage_device.device_id
            if device_id in seen or device_id not in config.devices:
                continue
            seen.add(device_id)
            entity_id = config.devices[device_id].entity_id
            state = hass.states.get(entity_id)
            name = getattr(state, "name", None) or device_id.replace("_", " ").title()
            devices.append({"id": device_id, "entity_id": entity_id, "name": name})
    return devices


async def async_dashboard_info(hass: HomeAssistant) -> dict[str, Any]:
    """Build the read-only dashboard discovery response for loaded entries."""
    registry = er.async_get(hass)
    entries: list[dict[str, Any]] = []
    # hass.data also contains migration data; only loaded entry runtimes belong here.
    for entry_id, runtime in hass.data.get(DOMAIN, {}).items():
        if not isinstance(runtime, dict) or "coordinator" not in runtime:
            continue

        coordinator = runtime["coordinator"]
        config = coordinator.config
        zones: list[dict[str, Any]] = []
        for order, (zone_id, zone) in enumerate(config.zones.items()):
            override = zone.settings.outdoor_reset
            state = coordinator.get_zone_state(zone_id)
            status: dict[str, Any] = {}
            if state is not None:
                # Reuse the diagnostics reason calculation, then whitelist card fields.
                snapshot = _zone_snapshot(hass, zone_id, zone, state, coordinator)
                status = {
                    "action": snapshot["hvac_action"],
                    "stage": snapshot["stage"],
                    "active_devices": snapshot["active_devices"],
                    "blocked_devices": snapshot["blocked_devices"],
                    "blocking_reasons": snapshot["blocking_reasons"],
                    "sensor_status": snapshot["sensor_status"],
                    "opening_status": snapshot["opening_status"],
                    "opening_lockout": snapshot["opening_lockout"],
                    "outdoor_permissions": snapshot["outdoor_permissions"],
                    "regulation_offset": state.regulation_offset,
                    "accumulated_error": state.accumulated_error,
                    "regulated_setpoint": state.regulated_setpoint,
                }

            zones.append({
                "id": zone_id,
                "name": zone.name,
                "entity_id": _entity_id(registry, "climate", f"{DOMAIN}_{entry_id}_{zone_id}"),
                "order": order,
                "outdoor_reset": {
                    "heat_override_set": bool(override and override.heat_override_set),
                    "cool_override_set": bool(override and override.cool_override_set),
                    "never_heat_above": override.never_heat_above if override else None,
                    "never_cool_below": override.never_cool_below if override else None,
                },
                "controls": _number_controls(registry, zone_id, zone),
                "devices": _zone_devices(hass, zone, config),
                "status": status,
            })

        entries.append({
            "entry_id": entry_id,
            "master": {
                "entity_id": _entity_id(registry, "climate", f"{DOMAIN}_{entry_id}_master"),
                "name": config.master.name,
                "outdoor_temperature": coordinator.master_state.outdoor_temperature,
                "settings": {
                    "never_heat_above": config.conflicts.outdoor_reset.never_heat_above,
                    "never_cool_below": config.conflicts.outdoor_reset.never_cool_below,
                    "device_mutex_count": len(config.conflicts.device_mutex),
                },
            },
            "zones": zones,
        })

    return {"entries": entries}


@websocket_api.websocket_command({vol.Required("type"): DASHBOARD_COMMAND})
@websocket_api.async_response
async def _websocket_dashboard_info(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any],
) -> None:
    """Send dashboard metadata to an authenticated Home Assistant client."""
    connection.send_result(msg["id"], await async_dashboard_info(hass))


async def async_setup_dashboard(hass: HomeAssistant) -> None:
    """Register the dashboard command and card asset once per HA startup."""
    websocket_api.async_register_command(hass, _websocket_dashboard_info)
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            DASHBOARD_CARD_URL,
            str(Path(__file__).resolve().parent / "frontend" / "hybrid-climate-card.js"),
            False,
        ),
    ])
