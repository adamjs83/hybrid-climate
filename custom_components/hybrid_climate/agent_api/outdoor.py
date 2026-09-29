"""Purpose: Read and write atomic per-zone outdoor reset overrides.

Key dependencies: Override model, field bounds, and value validation.
Used by: Agent API stored accessors.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ZoneOutdoorResetConfig
from .const import OUTDOOR_KEYS
from .fields import OUTDOOR_VALUE_FIELDS
from .value_validation import validate_value


def read_override(block: Mapping[str, Any], direction: str) -> dict[str, Any]:
    """Interpret explicit flags and legacy key presence without losing null."""
    key = OUTDOOR_KEYS[direction]
    enabled = block.get("override_enabled", True)
    active = enabled and block.get(direction + "_override_set", key in block)
    if not active:
        return {"mode": "inherit"}
    value = block.get(key)
    return {"mode": "disabled"} if value is None else {"mode": "value", "value": value}


def model_override(reset: ZoneOutdoorResetConfig | None, direction: str) -> dict[str, Any]:
    """Project parsed flag/value semantics as one atomic operation."""
    if reset is None or not getattr(reset, direction + "_override_set"):
        return {"mode": "inherit"}
    value = getattr(reset, OUTDOOR_KEYS[direction])
    return {"mode": "disabled"} if value is None else {"mode": "value", "value": value}


def write_override(block: dict[str, Any], direction: str, operation: Any) -> None:
    """Change one direction while preserving the other direction's effective mode."""
    if direction not in OUTDOOR_KEYS:
        raise ValueError("Invalid outdoor direction")
    if not isinstance(operation, dict) or operation.get("mode") not in ("inherit", "disabled", "value"):
        raise ValueError("Expected inherit, disabled, or value operation")
    mode = operation["mode"]
    expected_keys = {"mode", "value"} if mode == "value" else {"mode"}
    if set(operation) != expected_keys:
        raise ValueError("Contradictory outdoor override operation")
    value = None
    if mode == "value":
        value = validate_value(OUTDOOR_VALUE_FIELDS[direction], operation["value"])
    # Snapshot both effective modes before enabling the shared legacy switch.
    prior = {side: read_override(block, side) for side in OUTDOOR_KEYS}
    block["override_enabled"] = True
    for side, previous in prior.items():
        block[side + "_override_set"] = previous["mode"] != "inherit"
    block[direction + "_override_set"] = mode != "inherit"
    block[OUTDOOR_KEYS[direction]] = value
