"""Purpose: Validate Agent API edits against complete disposable runtime candidates.

Key dependencies: Stored accessors, setup preparation, and revision hashing.
Used by: Agent API set_config service and validation tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

import voluptuous as vol

from ..config_prepare import prepare_runtime_config
from ..const import OUTDOOR_LOCKOUT_HYSTERESIS
from ..models import HybridClimateConfig
from .accessors import Edit, read_effective, read_stored, target_id, write_field
from .const import DRY_RUN_KEY, PATCH_SCOPES, STAGE_ADDRESS_KEYS, STAGE_PATCH_KEY
from .revision import revision_state


def edit_key(edit: Edit) -> str:
    """Give stage leaves stable response names including their stored position."""
    if edit.direction is not None:
        return f"stages.{edit.direction}.{edit.index}.{edit.field}"
    return edit.field


def parse_edits(data: Mapping[str, Any]) -> list[Edit]:
    """Expand only documented patch envelopes into individually checked edits."""
    edits: list[Edit] = []
    for scope in PATCH_SCOPES:
        groups = data.get(scope, {})
        if not isinstance(groups, Mapping):
            raise ValueError(f"{scope} must be an object")
        if scope == "global":
            edits.extend(Edit(scope, None, key, value) for key, value in groups.items())
            continue
        for ident, fields in groups.items():
            if not isinstance(ident, str) or not isinstance(fields, Mapping):
                raise ValueError(f"{scope} entries need an ID and field object")
            for key, value in fields.items():
                if scope == "zones" and key == STAGE_PATCH_KEY:
                    if not isinstance(value, list):
                        raise ValueError("Stages must be a list")
                    for stage in value:
                        if not isinstance(stage, Mapping) or not STAGE_ADDRESS_KEYS <= stage.keys():
                            raise ValueError("Each stage needs direction and index")
                        if stage["direction"] not in ("heat", "cool") or type(stage["index"]) is not int or stage["index"] < 0:
                            raise ValueError("Invalid stage address")
                        leaves = stage.keys() - STAGE_ADDRESS_KEYS
                        if not leaves:
                            raise ValueError("Stage patch has no tuning fields")
                        for leaf in sorted(leaves):
                            edits.append(Edit(scope, ident, leaf, stage[leaf],
                                              stage["direction"], stage["index"]))
                else:
                    edits.append(Edit(scope, ident, key, value))
    # Repeated stage objects may address the same leaf even though mapping keys are unique.
    seen: set[tuple[Any, ...]] = set()
    for edit in edits:
        token = (edit.scope, edit.id, edit.direction, edit.index, edit.field)
        try:
            duplicate = token in seen
            seen.add(token)
        except TypeError as error:
            raise ValueError("Stage address must be scalar") from error
        if duplicate:
            raise ValueError("Duplicate stage field")
    return edits


def issue(edit: Edit | None, code: str, message: str) -> dict[str, Any]:
    """Create a structured issue without exporting configuration."""
    return {"scope": edit.scope if edit else "global", "id": edit.id if edit else None,
            "field": edit_key(edit) if edit else None, "code": code, "message": message}


def empty_result(options: Mapping[str, Any], dry_run: bool) -> dict[str, Any]:
    """Provide a stable response shape for validation and transaction outcomes."""
    revision = revision_state(options, None)
    return {"dry_run": dry_run, "valid": True, "errors": [], "warnings": [], "diff": [],
            "revision_before": revision, "revision_proposed": revision,
            "applied": False, "saved": False, "reloaded": False,
            "revision_after": revision, "pending": revision["pending"]}


def assert_took_effect(model: HybridClimateConfig, edit: Edit) -> None:
    """Reject edits silently neutralized by conversion or option overrides."""
    actual = read_effective(model, edit)
    if actual != edit.value:
        raise ValueError("Requested value was overridden or discarded during preparation")


def validate_patch(
    options: Mapping[str, Any], data: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Prepare a disposable candidate and compare stored and effective values."""
    candidate = deepcopy(dict(options))
    result = empty_result(options, data.get(DRY_RUN_KEY, True))
    try:
        edits = parse_edits(data)
        before = prepare_runtime_config(options)
    except (ValueError, TypeError, KeyError, vol.Invalid) as error:
        result["errors"].append(issue(None, "preparation", str(error)))
        result["valid"] = False
        return candidate, result
    # Apply only checked leaves; any failure prevents the candidate being saved.
    for edit in edits:
        try:
            write_field(candidate, before, edit)
        except (ValueError, TypeError) as error:
            result["errors"].append(issue(edit, "invalid_value", str(error)))
    if result["errors"]:
        result["valid"] = False
        return candidate, result
    try:
        after = prepare_runtime_config(candidate)
    except (ValueError, TypeError, KeyError, vol.Invalid) as error:
        result["errors"].append(issue(None, "preparation", str(error)))
        result["valid"] = False
        return candidate, result
    # Compare presence as well as JSON values, then check loaded behavior.
    for edit in edits:
        try:
            assert_took_effect(after, edit)
            old_present, old = read_stored(options, before, edit)
            new_present, new = read_stored(candidate, after, edit)
            old_effective = read_effective(before, edit)
            new_effective = read_effective(after, edit)
            if (old_present, old, old_effective) != (new_present, new, new_effective):
                delta = {"scope": edit.scope, "id": edit.id, "field": edit_key(edit),
                         "old": old, "new": new, "old_effective": old_effective,
                         "new_effective": new_effective}
                if old_present != new_present:
                    delta.update(old_present=old_present, new_present=new_present)
                result["diff"].append(delta)
        except (ValueError, IndexError, AttributeError) as error:
            result["errors"].append(issue(edit, "not_effective", str(error)))
    # Effective global limits must preserve an ordered heating/cooling interval.
    reset = after.conflicts.outdoor_reset
    heat, cool = reset.never_heat_above, reset.never_cool_below
    if heat is not None and cool is not None:
        if heat >= cool:
            result["errors"].append(issue(None, "cross_field", "never_heat_above must be less than never_cool_below"))
        else:
            gap = f"{OUTDOOR_LOCKOUT_HYSTERESIS:g}°F"
            result["warnings"].append(issue(None, "outdoor_gap", f"Outdoor limits create a no-operation gap; lockout release also uses {gap} hysteresis"))
    for zone_id in dict.fromkeys(target_id(edit) for edit in edits if edit.scope == "zones"):
        zone = after.zones[zone_id]
        if zone.heat_stages and zone.cool_stages:
            result["warnings"].append(issue(Edit("zones", zone_id, "stages", None),
                                            "dual_mode", "This zone has both heating and cooling stages"))
    result["valid"] = not result["errors"]
    result["revision_proposed"] = revision_state(candidate, None)
    return candidate, result
