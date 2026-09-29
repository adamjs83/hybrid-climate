"""Purpose: Project active tunables, provenance, and owned entity controls.

Key dependencies: Field catalog, stored accessors, revision state, structure view.
Used by: Agent API get_config service.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import (
    CONF_UI_CONFIG, CONF_ZONES, DATA_ACTIVE_REVISION, DATA_PREPARED_OPTIONS, DOMAIN,
)
from ..models import HybridClimateConfig
from .accessors import Edit, field_for, read_effective, read_stored, stored_parent, target_id
from .const import (
    OUTDOOR_FIELDS, PRESET_SERVICE, SOURCE_DEFAULT, SOURCE_OPTIONS_OVERRIDE, SOURCE_UI_CONFIG,
)
from .config_readonly import compressor_groups, readonly_device, readonly_global, readonly_zone
from .controls import entity_values, zone_controls
from .fields import FIELDS
from .patch_validation import edit_key
from .revision import revision_state
from .structure import get_structure


def iter_fields(model: HybridClimateConfig, zone_id: str | None) -> list[Edit]:
    """Enumerate explicit fields over configured IDs and stage positions."""
    edits: list[Edit] = []
    selected = {zone_id: model.zones[zone_id]} if zone_id else model.zones
    allowed_devices = {device_id for zone in selected.values()
                       for device_id in zone.get_all_device_ids()}
    # The field catalog fixes response ordering; stage edits follow loaded list order.
    for (scope, key), _definition in FIELDS.items():
        if scope == "global":
            edits.append(Edit(scope, None, key, None))
        elif scope == "devices":
            edits.extend(Edit(scope, ident, key, None) for ident in model.devices
                         if zone_id is None or ident in allowed_devices)
        elif scope == "zones":
            edits.extend(Edit(scope, ident, key, None) for ident in selected)
        elif scope == "stage":
            for ident, zone in selected.items():
                for direction in ("heat", "cool"):
                    for index, stage in enumerate(getattr(zone, direction + "_stages")):
                        if key == "outdoor_temp_min" and (direction != "heat" or stage.stage_number != 2):
                            continue
                        edits.append(Edit("zones", ident, key, None, direction, index))
    return edits


def field_view(
    options: Mapping[str, Any], model: HybridClimateConfig, edit: Edit,
) -> dict[str, Any]:
    """Describe an active value using prepared storage and field metadata."""
    definition = field_for(edit)
    result = {"value": read_effective(model, edit),
              "type": definition.kind, "description": definition.description}
    for key, value in (("min", definition.minimum), ("max", definition.maximum),
                       ("unit", definition.unit)):
        if value is not None:
            result[key] = value
    if definition.enum:
        result["enum"] = list(definition.enum)
    # A loaded default remains readable even when its optional storage parent is absent.
    try:
        present, _stored = read_stored(options, model, edit)
        result["source"] = SOURCE_UI_CONFIG if present else SOURCE_DEFAULT
        if edit.scope == "global" and options.get(edit.field) is not None:
            result["source"] = SOURCE_OPTIONS_OVERRIDE
        if edit.field in OUTDOOR_FIELDS:
            block = options[CONF_UI_CONFIG][CONF_ZONES][target_id(edit)]["settings"]["outdoor_reset"]
            result["writable"] = isinstance(block, dict)
        else:
            stored_parent(options, model, edit)
            result["writable"] = True
    except (KeyError, TypeError, ValueError):
        # Ambiguous stage storage has no trustworthy stored provenance.
        result["writable"] = False
    return result


def get_config(
    hass: HomeAssistant, entry: ConfigEntry, zone_id: str | None = None,
    include_structure: bool = False,
) -> dict[str, Any]:
    """Project active tunables and entity controls without exporting options."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    model = runtime["config"]
    options = runtime[DATA_PREPARED_OPTIONS]
    result: dict[str, Any] = {
        "revision": revision_state(entry.options, runtime[DATA_ACTIVE_REVISION]),
        "global": readonly_global(model, options), "zones": {}, "devices": {},
        "entity_controlled": {}, "compressor_groups": compressor_groups(model, zone_id),
    }
    # Provenance comes from the snapshot that produced this loaded model.
    for edit in iter_fields(model, zone_id):
        destination = result[edit.scope]
        if edit.id is not None:
            destination = destination.setdefault(edit.id, {})
        destination[edit_key(edit)] = field_view(options, model, edit)
    selected = {zone_id: model.zones[zone_id]} if zone_id else model.zones
    for ident in selected:
        result["zones"].setdefault(ident, {}).update(readonly_zone(model, options, ident))
    for ident in result["devices"]:
        result["devices"][ident].update(readonly_device(model, options, ident))
    for ident, zone in selected.items():
        controls = zone_controls(hass, entry, ident, zone)
        result["entity_controlled"][ident] = {
            **controls, "values": entity_values(hass, entry, ident, controls),
            "presets": {"entity_id": controls["climate"], "service": PRESET_SERVICE},
        }
    if include_structure:
        result["structure"] = get_structure(model, zone_id)
    return result
