"""Purpose: Build the Devices list: one entry per YAML device, then every UI-only device (stored or referenced by a
UI zone stage), labelled with capabilities, idle action and the effective cooling mode.

Key dependencies: const.py, config_parsers.resolve_cool_regulation, capability_defaults.device_form_capabilities.
Used by: options_flow/devices.py (async_step_devices).
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from ..config_parsers import resolve_cool_regulation
from ..const import (
    CAPABILITY_COOL,
    CAPABILITY_HEAT,
    CONF_CAPABILITIES,
    CONF_COOL_OVERDRIVE,
    CONF_COOL_REGULATION,
    CONF_ENTITY_ID,
    CONF_IDLE,
    CONF_IDLE_ACTION,
    CONF_IDLE_SETBACK,
    DEFAULT_COOL_OVERDRIVE,
    DEFAULT_IDLE_SETBACK,
    DEVICE_LIST_COOLING,
    DEVICE_LIST_IDLE_OFF,
    DEVICE_LIST_IDLE_SETBACK,
    IDLE_ACTION_OFF,
    IDLE_ACTION_SETBACK,
)
from .capability_defaults import device_form_capabilities

CAP_HEAT = CAPABILITY_HEAT
CAP_COOL = CAPABILITY_COOL


def device_list_label(name: str, capabilities: list[str], conf: dict[str, Any]) -> str:
    """Return a device list label: name, capabilities, idle action and effective cooling mode."""
    # Capabilities read "heat", "cool" or "heat+cool" in that order.
    caps = "+".join(cap for cap in (CAP_HEAT, CAP_COOL) if cap in capabilities)
    if conf.get(CONF_IDLE_ACTION, IDLE_ACTION_OFF) == IDLE_ACTION_SETBACK:
        idle = DEVICE_LIST_IDLE_SETBACK.format(
            setback=float(conf.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK)))
    else:
        idle = DEVICE_LIST_IDLE_OFF
    parts = [caps, idle]
    # Heat-only devices have no cooling regulation to show.
    if CAP_COOL in capabilities:
        mode = resolve_cool_regulation(
            conf.get(CONF_COOL_REGULATION),
            float(conf.get(CONF_COOL_OVERDRIVE, DEFAULT_COOL_OVERDRIVE)),
        )
        parts.append(DEVICE_LIST_COOLING.format(mode=mode))
    return f"{name} ({', '.join(parts)})"


def device_list_entries(
    hass: HomeAssistant, yaml_devices: dict[str, Any], ui_config: dict[str, Any],
) -> tuple[list[dict[str, str]], list[str]]:
    """Return the list's edit options ({"value": "edit_<entity_id>", "label": ...}) and the device names."""
    ui_devices = ui_config.get("devices", {})

    # Also collect devices from UI zones (auto-generated)
    ui_zones = ui_config.get("zones", {})
    ui_zone_entity_ids: set[str] = set()
    for zone_conf in ui_zones.values():
        for stage in zone_conf.get("heat_stages", []) + zone_conf.get("cool_stages", []):
            for dev in stage.get("devices", []):
                if isinstance(dev, dict):
                    entity_id = dev.get("entity_id", "")
                    if entity_id:
                        ui_zone_entity_ids.add(entity_id)
                elif isinstance(dev, str):
                    ui_zone_entity_ids.add(dev)

    # Build device list for display
    device_options: list[dict[str, str]] = []
    seen_entity_ids: set[str] = set()

    # First add YAML devices
    for device_id in yaml_devices:
        device_conf = yaml_devices[device_id]
        entity_id = device_conf.get(CONF_ENTITY_ID, device_id)
        seen_entity_ids.add(entity_id)

        # Check UI devices first, then YAML (the same values the edit page loads)
        if entity_id in ui_devices:
            summary_conf = ui_devices[entity_id]
        else:
            idle_conf = device_conf.get(CONF_IDLE, {})
            summary_conf = {
                **device_conf,
                CONF_IDLE_ACTION: idle_conf.get(CONF_IDLE_ACTION, IDLE_ACTION_OFF),
                CONF_IDLE_SETBACK: idle_conf.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK),
            }
        capabilities = device_form_capabilities(
            hass, entity_id, ui_devices.get(entity_id),
            device_conf.get(CONF_CAPABILITIES, [CAP_HEAT]),
        )

        device_options.append({
            "value": f"edit_{entity_id}",  # Use entity_id for consistency
            "label": device_list_label(device_id, capabilities, summary_conf),
        })

    # Then add UI-only devices (from ui_devices or zones, not in YAML)
    all_ui_entity_ids = set(ui_devices.keys()) | ui_zone_entity_ids
    for entity_id in sorted(all_ui_entity_ids - seen_entity_ids):
        dev_conf = ui_devices.get(entity_id, {})
        capabilities = device_form_capabilities(
            hass, entity_id, ui_devices.get(entity_id), [CAP_HEAT],
        )

        # Display name from entity_id (climate.xxx -> xxx)
        display_name = entity_id.replace("climate.", "")
        device_options.append({
            "value": f"edit_{entity_id}",
            "label": device_list_label(display_name, capabilities, dev_conf),
        })

    device_names = list(yaml_devices.keys()) + [
        eid.replace("climate.", "") for eid in (all_ui_entity_ids - seen_entity_ids)
    ]
    return device_options, device_names
