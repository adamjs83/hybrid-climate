"""Purpose: Resolve Agent API edits to existing UI nodes and loaded model values.

Key dependencies: Field catalog, runtime config model, and outdoor helpers.
Used by: Candidate validation and Agent API service handlers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..const import CONF_DEVICES, CONF_UI_CONFIG, CONF_ZONES
from ..models import HybridClimateConfig
from .const import OUTDOOR_FIELDS
from .fields import FIELDS, Field
from .outdoor import model_override, read_override, write_override
from .value_validation import validate_value


@dataclass(frozen=True)
class Edit:
    """Address one tuning change independently of its stored container layout."""

    scope: str
    id: str | None
    field: str
    value: Any
    direction: str | None = None
    index: int | None = None


class MissingStoredTarget(ValueError):
    """Signal that a writable field has no existing storage parent."""


def field_for(edit: Edit) -> Field:
    """Look up only explicitly writable API fields."""
    scope = "stage" if edit.direction is not None else edit.scope
    if scope == "stage" and edit.scope != "zones":
        raise ValueError("Stages require a zone")
    if scope != "stage" and edit.index is not None:
        raise ValueError("Invalid stage address")
    try:
        return FIELDS[(scope, edit.field)]
    except KeyError as error:
        raise ValueError("Unknown or structural field") from error


def target_id(edit: Edit) -> str:
    """Narrow the required ID of a non-global field."""
    if edit.id is None:
        raise ValueError("Field requires an ID")
    return edit.id


def stage_index(edit: Edit) -> int:
    """Narrow a validated non-negative stage-list position."""
    if type(edit.index) is not int or edit.index < 0:
        raise ValueError("Invalid stage address")
    return edit.index


def stored_parent(
    options: Mapping[str, Any], model: HybridClimateConfig, edit: Edit,
) -> tuple[dict[str, Any], str]:
    """Locate an existing parent container without implicitly creating a block."""
    field_for(edit)
    try:
        ui = options[CONF_UI_CONFIG]
        if edit.scope == "global":
            if edit.id is not None:
                raise ValueError("Global field must not have an ID")
            node = ui["global"]
        elif edit.scope == "devices":
            node = ui[CONF_DEVICES][model.devices[target_id(edit)].entity_id]
        else:
            node = ui[CONF_ZONES][target_id(edit)]
        if edit.direction is not None:
            if edit.direction not in ("heat", "cool"):
                raise ValueError("Invalid stage address")
            stages = node[edit.direction + "_stages"]
            index = stage_index(edit)
            if index >= len(stages):
                raise ValueError("Stage does not exist")
            # Converter drops device-less stages; duplicate numbers also make identity ambiguous.
            if any(not item.get("devices") for item in stages) or len({item.get("stage") for item in stages}) != len(stages):
                raise ValueError("Stored stages do not map one-to-one to loaded stages")
            loaded = getattr(model.zones[target_id(edit)], edit.direction + "_stages")
            if len(loaded) != len(stages):
                raise ValueError("Stored stages do not map one-to-one to loaded stages")
            node = stages[index]
            if edit.field == "outdoor_temp_min":
                if edit.direction != "heat" or node.get("stage") != 2:
                    raise ValueError("Outdoor minimum is exposed only for heating stage 2")
                if "conditions" in node:
                    if not isinstance(node["conditions"], dict):
                        raise MissingStoredTarget("Existing stage conditions block required")
                    return node["conditions"], edit.field
                if edit.field in node:
                    return node, edit.field
                raise MissingStoredTarget("Existing stage conditions block required")
        for part in edit.field.split(".")[:-1]:
            node = node[part]
        if not isinstance(node, dict):
            raise MissingStoredTarget("Existing configuration block required")
        return node, edit.field.rsplit(".", 1)[-1]
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise MissingStoredTarget("Existing configuration block required") from error


def read_stored(
    options: Mapping[str, Any], model: HybridClimateConfig, edit: Edit,
) -> tuple[bool, Any]:
    """Return key presence separately from its possibly-null stored value."""
    field_for(edit)
    try:
        if edit.field in OUTDOOR_FIELDS:
            block = options[CONF_UI_CONFIG][CONF_ZONES][target_id(edit)]["settings"]["outdoor_reset"]
            return True, read_override(block, edit.field.rsplit(".", 1)[1])
        node, key = stored_parent(options, model, edit)
        return key in node, node.get(key)
    except MissingStoredTarget:
        return False, None
    except (KeyError, TypeError):
        return False, None


def read_effective(model: HybridClimateConfig, edit: Edit) -> Any:
    """Read the exact loaded model field corresponding to a patch."""
    field_for(edit)
    try:
        if edit.scope == "global":
            return getattr(model.conflicts.outdoor_reset, edit.field)
        node = model.devices[target_id(edit)] if edit.scope == "devices" else model.zones[target_id(edit)]
        if edit.field in OUTDOOR_FIELDS:
            return model_override(node.settings.outdoor_reset, edit.field.rsplit(".", 1)[1])
        if edit.direction is not None:
            node = getattr(node, edit.direction + "_stages")[stage_index(edit)]
            if edit.field == "outdoor_temp_min":
                return node.conditions.outdoor_temp_min
        for key in edit.field.split("."):
            if node is None:
                return None
            node = getattr(node, key)
        return node.value if isinstance(node, Enum) else node
    except (KeyError, IndexError, AttributeError, TypeError) as error:
        raise ValueError("Target does not exist in loaded configuration") from error


def write_field(options: dict[str, Any], model: HybridClimateConfig, edit: Edit) -> None:
    """Write a validated leaf or atomic override to an existing configuration node."""
    definition = field_for(edit)
    if edit.field in OUTDOOR_FIELDS:
        try:
            block = options[CONF_UI_CONFIG][CONF_ZONES][target_id(edit)]["settings"]["outdoor_reset"]
        except (KeyError, TypeError) as error:
            raise ValueError("Existing configuration block required") from error
        if not isinstance(block, dict):
            raise ValueError("Existing configuration block required")
        write_override(block, edit.field.rsplit(".", 1)[1], edit.value)
        return
    value = validate_value(definition, edit.value)
    node, key = stored_parent(options, model, edit)
    if edit.field == "time_escalation" and value is None:
        node.pop(key, None)
    else:
        node[key] = value
    if edit.scope == "global":
        options[key] = value
    if edit.direction is not None and edit.field == "outdoor_temp_min":
        # Keep an existing legacy leaf in sync with the canonical conditions leaf.
        stage = options[CONF_UI_CONFIG][CONF_ZONES][target_id(edit)][edit.direction + "_stages"][stage_index(edit)]
        if key in stage:
            stage[key] = value
