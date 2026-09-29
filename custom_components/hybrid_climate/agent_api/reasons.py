"""Purpose: Explain recorded zone restrictions without inferring control decisions.

Key dependencies: Diagnostics reason codes and cached zone state.
Used by: Agent API status projection.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ZoneState
from .const import (
    REASON_DETAILS,
    UNKNOWN_REASON_DETAIL,
    WITHIN_TARGET_CODE,
    WITHIN_TARGET_DETAIL,
)


def _is_usable_number(value: Any) -> bool:
    """Return True only for a real, non-boolean int/float; bool is an int subclass."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _within_target(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    """Explain an idle zone sitting inside its cached heat/cool targets, if provable."""
    # Every key is read with .get() because callers (including existing tests) may pass
    # a partial snapshot containing only blocking_reasons; a missing key must never be
    # treated as satisfying a bound. A present-but-non-numeric value (bool or string) is
    # never treated as usable, since it cannot be safely compared or subtracted.
    if snapshot.get("hvac_action") != "idle":
        return None
    current = snapshot.get("current_temperature")
    if current is None or not _is_usable_number(current):
        return None
    heat_target = snapshot.get("heat_target")
    cool_target = snapshot.get("cool_target")
    if heat_target is not None and not _is_usable_number(heat_target):
        return None
    if cool_target is not None and not _is_usable_number(cool_target):
        return None
    if heat_target is None and cool_target is None:
        return None
    if heat_target is not None and current < heat_target:
        return None
    if cool_target is not None and current > cool_target:
        return None
    margins: dict[str, float] = {}
    if heat_target is not None:
        margins["heat"] = round(current - heat_target, 2)
    if cool_target is not None:
        margins["cool"] = round(cool_target - current, 2)
    return {"code": WITHIN_TARGET_CODE, "detail": WITHIN_TARGET_DETAIL, "margins": margins}


def zone_reasons(snapshot: Mapping[str, Any], state: ZoneState) -> list[dict[str, Any]]:
    """Explain only recorded restrictions; unknown is preferable to a guessed cause."""
    raw_reasons = snapshot.get("blocking_reasons") or []
    result = [
        {"code": code, "detail": REASON_DETAILS[code]}
        for code in raw_reasons if code in REASON_DETAILS
    ]
    for reason in result:
        if reason["code"] == "opening_lockout" and state.opening_changed_at:
            reason["since"] = state.opening_changed_at.isoformat()
    if result:
        return result
    # An unrecognized-only recorded list is still a recorded restriction, even though it
    # yields no known-code entries; within_target must not override it, so only an empty
    # raw list is eligible for the within_target check.
    if not raw_reasons:
        within_target = _within_target(snapshot)
        if within_target is not None:
            return [within_target]
    return [{"code": "unknown", "detail": UNKNOWN_REASON_DETAIL}]
