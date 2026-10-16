"""Purpose: Canonical stage form and the edit merge of the zone wizard.

A zone being edited (UI or YAML) is turned into canonical UI stages once: devices become
{"entity_id", "allow_command"} dicts, legacy top-level outdoor limits move into nested
`conditions` (nested values win), every other stored key is kept. That canonical zone is both
the wizard's starting stages and the baseline the save merges the pages' output into, so
stage 3+, unshown stage keys and PI gains/advanced keys survive an edit.

Key dependencies: const.py (PAGE_* ownership constants, LEGACY_STAGE_CONDITION_KEYS, DEFAULT_PI_GAINS).
Used by: options_flow/zone_helpers.py (load), options_flow/stage_fields.py (stage page submit),
options_flow/zone_save.py (save).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..const import (
    DEFAULT_PI_GAINS,
    LEGACY_STAGE_CONDITION_KEYS,
    PAGE_REGULATION_KEYS,
    PAGE_STAGE_NUMBERS,
)

STAGE_LISTS = ("heat_stages", "cool_stages")


def stage_conditions(stage: dict[str, Any]) -> dict[str, Any]:
    """Return a stage's effective conditions: legacy top-level limits, overridden by nested ones."""
    conditions = {key: stage[key] for key in LEGACY_STAGE_CONDITION_KEYS if stage.get(key) is not None}
    nested = stage.get("conditions")
    if isinstance(nested, dict):
        conditions.update(nested)
    # A None limit is no limit (the converter drops it too).
    return {key: value for key, value in conditions.items() if value is not None}


def canonical_device(reference: Any, yaml_devices: dict[str, Any]) -> dict[str, Any]:
    """Return a stage device reference as an entity_id dict, keeping its allow_command flag."""
    if isinstance(reference, dict):
        ref = reference.get("device") or reference.get("device_id") or reference.get("entity_id", "")
        allow_command = bool(reference.get("allow_command", False))
    else:
        ref, allow_command = str(reference), False
    # A YAML device id resolves to its entity; anything else already is one.
    entity_id = yaml_devices[ref].get("entity_id", ref) if ref in yaml_devices else ref
    return {"entity_id": entity_id, "allow_command": allow_command}


def canonical_stage(stage: dict[str, Any], yaml_devices: dict[str, Any]) -> dict[str, Any]:
    """Return one stored stage (UI or YAML spelling) in canonical UI form, extra keys kept."""
    result = {
        key: deepcopy(value) for key, value in stage.items()
        if key not in LEGACY_STAGE_CONDITION_KEYS and key != "conditions"
    }
    # An unnumbered stage is stage 1, as the converter reads it.
    result.setdefault("stage", 1)
    result["devices"] = [canonical_device(d, yaml_devices) for d in stage.get("devices") or []]
    conditions = stage_conditions(stage)
    if conditions:
        result["conditions"] = conditions
    return result


def canonical_stages(stages: list[Any] | None, yaml_devices: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a stored stage list in canonical UI form (non-dict entries are dropped)."""
    return [canonical_stage(stage, yaml_devices) for stage in stages or [] if isinstance(stage, dict)]


def edit_baseline(zone_conf: dict[str, Any], yaml_devices: dict[str, Any]) -> dict[str, Any]:
    """Return the merge baseline of an edited zone: canonical stages and a copy of its regulation."""
    regulation = zone_conf.get("regulation")
    return {
        **{key: canonical_stages(zone_conf.get(key), yaml_devices) for key in STAGE_LISTS},
        "regulation": deepcopy(regulation) if isinstance(regulation, dict) else None,
    }


def is_page_stage(stage: dict[str, Any]) -> bool:
    """Return True for a stage a stage page shows (1, 2, or unnumbered)."""
    return stage.get("stage", PAGE_STAGE_NUMBERS[0]) in PAGE_STAGE_NUMBERS


def retained_stages(stages: list[dict[str, Any]], allow: dict[str, bool]) -> list[dict[str, Any]]:
    """Return copies of the stages no page shows (3+), with allow_command from `allow` where known."""
    result = []
    for stage in stages:
        if is_page_stage(stage):
            continue
        kept = deepcopy(stage)
        for device in kept.get("devices", []):
            if isinstance(device, dict) and device.get("entity_id") in allow:
                device["allow_command"] = allow[device["entity_id"]]
        result.append(kept)
    return result


def merge_stages(
    stored: list[dict], built: list[dict],
    page_conditions: dict[int, tuple[str, ...]] | None = None,
    page_keys: dict[int, tuple[str, ...]] | None = None,
) -> list[dict]:
    """Merge page-built stages into stored stages, keeping keys and stages the pages do not show.

    `page_keys` / `page_conditions` map a stage number to the stage keys / condition keys its
    page writes (PAGE_STAGE_KEYS / PAGE_CONDITION_KEYS[<stage list>]); only those stored values
    may be removed. Stored legacy top-level limits are normalised into `conditions` first.
    """
    owned_keys = page_keys or {}
    owned_conditions = page_conditions or {}
    stored_by_number = {s["stage"]: s for s in stored if isinstance(s, dict) and "stage" in s}
    result: list[dict] = []
    for stage in built:
        number = stage.get("stage")
        base = stored_by_number.get(number, {})
        owned = owned_keys.get(number, ())
        merged = {
            k: v for k, v in base.items()
            if k not in owned and k != "conditions" and k not in LEGACY_STAGE_CONDITION_KEYS
        }
        merged.update({k: v for k, v in stage.items() if k != "conditions"})
        # Keep stored conditions this stage's page does not edit; the page's values win.
        cleared = owned_conditions.get(number, ())
        conditions = {k: v for k, v in stage_conditions(base).items() if k not in cleared}
        conditions.update(stage.get("conditions") or {})
        if conditions:
            merged["conditions"] = conditions
        result.append(merged)
    built_numbers = {stage.get("stage") for stage in built}
    for stage in stored:
        number = stage.get("stage") if isinstance(stage, dict) else None
        # Business rule: stages the pages do not show (3+, or unnumbered) are kept as saved;
        # stage 1 or 2 missing from the page output was cleared by the user.
        if number in built_numbers or number in PAGE_STAGE_NUMBERS:
            continue
        result.append(stage)
    return result


def merge_regulation(stored: dict | None, page: dict) -> dict:
    """Overlay the PI page's keys on the stored regulation block, or seed default gains."""
    page_keys = {k: page[k] for k in PAGE_REGULATION_KEYS if k in page}
    if isinstance(stored, dict):
        return {**stored, **page_keys}
    return {**page_keys, **DEFAULT_PI_GAINS}
