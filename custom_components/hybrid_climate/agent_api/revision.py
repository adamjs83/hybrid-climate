"""Purpose: Hash behavior options and retain active revisions across entry unloads.

Key dependencies: JSON, SHA-256, Home Assistant data storage, Agent API constants.
Used by: Agent API status, config reads, writes, and runtime lifecycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import json
import math
from typing import Any

from homeassistant.core import HomeAssistant

from .const import API_DATA, COMPAT_KEYS, INTEGER_KEYS


def _normalize(value: Any, key: str = "") -> Any:
    """Normalize JSON numbers without conflating bool, null, or missing keys."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("Revision numbers must be finite")
        if key in INTEGER_KEYS:
            if int(value) != value:
                raise ValueError("Integer field has fractional value")
            return int(value)
        return 0.0 if value == 0 else float(value)
    if isinstance(value, Mapping):
        return {k: _normalize(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    raise ValueError(f"Unsupported revision value: {type(value).__name__}")


def canonical_options(options: Mapping[str, Any]) -> str:
    """Serialize behavior options, explicitly preserving zone insertion order."""
    ui = deepcopy(dict(options.get("ui_config", {})))
    ui.pop("number_values", None)
    payload = {"ui_config": ui}
    payload.update({key: options[key] for key in COMPAT_KEYS if key in options})
    envelope = {"options": payload, "zone_order": list(ui.get("zones", {}))}
    return json.dumps(
        _normalize(envelope), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def stored_revision(options: Mapping[str, Any]) -> str:
    """Hash precisely the canonical behavior projection."""
    return sha256(canonical_options(options).encode("utf-8")).hexdigest()


def revision_state(options: Mapping[str, Any], active: str | None) -> dict[str, Any]:
    """Describe stored versus last successfully activated options."""
    stored = stored_revision(options)
    return {"stored": stored, "active": active, "pending": stored != active}


def ledger(hass: HomeAssistant) -> dict[str, Any]:
    """Keep writer locks and last successful hashes independent of entry unload."""
    return hass.data.setdefault(API_DATA, {"active": {}, "locks": {}})
