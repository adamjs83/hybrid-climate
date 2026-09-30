"""Purpose: Explain recorded zone restrictions without inferring control decisions.

Key dependencies: Diagnostics reason codes and cached zone state.
Used by: Agent API status projection.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import Stage, ZoneConfig, ZoneState
from .const import (
    ABOVE_COOL_TARGET_BELOW_START_CODE,
    ABOVE_COOL_TARGET_BELOW_START_DETAIL,
    BELOW_HEAT_TARGET_BELOW_START_CODE,
    BELOW_HEAT_TARGET_BELOW_START_DETAIL,
    COOLING_DEMAND_CODE,
    COOLING_DEMAND_DETAIL,
    HEATING_DEMAND_CODE,
    HEATING_DEMAND_DETAIL,
    REASON_DETAILS,
    STAGE_WITHOUT_USABLE_DEVICES_CODE,
    STAGE_WITHOUT_USABLE_DEVICES_DETAIL,
    UNKNOWN_REASON_CODE,
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


def _demand(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    """Explain an actively heating/cooling zone from the cached hvac_action alone.

    The cached action alone proves demand, so the reason is emitted even when
    current/target are missing or non-numeric — only `error` becomes None then.
    """
    action = snapshot.get("hvac_action")
    if action not in ("heating", "cooling"):
        return None
    current = snapshot.get("current_temperature")
    stage = snapshot.get("stage")
    if action == "heating":
        code, detail, target = HEATING_DEMAND_CODE, HEATING_DEMAND_DETAIL, snapshot.get("heat_target")
        error = round(target - current, 2) if _is_usable_number(current) and _is_usable_number(target) else None
    else:
        code, detail, target = COOLING_DEMAND_CODE, COOLING_DEMAND_DETAIL, snapshot.get("cool_target")
        error = round(current - target, 2) if _is_usable_number(current) and _is_usable_number(target) else None
    return {"code": code, "detail": detail, "stage": stage, "error": error}


def _start_threshold(hysteresis: float, stages: list[Stage]) -> float | None:
    """Return the diff a direction needs to start equipment, or None with no stages."""
    if not stages:
        return None
    return max(hysteresis, stages[0].threshold)


def _below_start(snapshot: Mapping[str, Any], zone: ZoneConfig | None) -> dict[str, Any] | None:
    """Explain an idle zone past its target but not yet past that direction's start threshold.

    An idle zone only starts a mode once the diff exceeds hysteresis (`determine_needed_mode`,
    strict `>`), and stage 1 only once `diff >= stage.threshold`; a diff at or below the larger
    of the two cannot have started equipment, so it is not a mystery even though `_within_target`
    does not cover it (current is past the target, not inside it). Like `_within_target`, a
    present-but-non-numeric value on either target invalidates the whole snapshot, not just
    that direction.
    """
    if zone is None or snapshot.get("hvac_action") != "idle":
        return None
    current = snapshot.get("current_temperature")
    if not _is_usable_number(current):
        return None
    heat_target = snapshot.get("heat_target")
    cool_target = snapshot.get("cool_target")
    if heat_target is not None and not _is_usable_number(heat_target):
        return None
    if cool_target is not None and not _is_usable_number(cool_target):
        return None
    hysteresis = zone.settings.hysteresis
    # sign flips the direction's diff so it is always "how far past the target", matching
    # cool (current - cool_target) and heat (heat_target - current).
    directions = (
        (cool_target, zone.cool_stages, ABOVE_COOL_TARGET_BELOW_START_CODE,
         ABOVE_COOL_TARGET_BELOW_START_DETAIL, 1),
        (heat_target, zone.heat_stages, BELOW_HEAT_TARGET_BELOW_START_CODE,
         BELOW_HEAT_TARGET_BELOW_START_DETAIL, -1),
    )
    for target, stages, code, detail, sign in directions:
        if target is None:
            continue
        diff = sign * (current - target)
        start_threshold = _start_threshold(hysteresis, stages)
        if start_threshold is not None and 0 < diff <= start_threshold:
            return {
                "code": code, "detail": detail,
                "margin_to_target": round(diff, 2),
                "margin_to_start": round(start_threshold - diff, 2),
                "start_threshold": round(start_threshold, 2),
                "hysteresis": round(hysteresis, 2),
                "stage_threshold": round(stages[0].threshold, 2),
            }
    return None


def zone_reasons(
    snapshot: Mapping[str, Any], state: ZoneState, zone: ZoneConfig | None = None,
    stage_without_usable_devices: bool = False,
) -> list[dict[str, Any]]:
    """Explain only recorded restrictions; unknown is preferable to a guessed cause."""
    raw_reasons = snapshot.get("blocking_reasons") or []
    result = [
        {"code": code, "detail": REASON_DETAILS[code]}
        for code in raw_reasons if code in REASON_DETAILS
    ]
    for reason in result:
        if reason["code"] == "opening_lockout" and state.opening_changed_at:
            reason["since"] = state.opening_changed_at.isoformat()
    if stage_without_usable_devices:
        result.append({"code": STAGE_WITHOUT_USABLE_DEVICES_CODE,
                       "detail": STAGE_WITHOUT_USABLE_DEVICES_DETAIL})
    if result:
        return result
    # An unrecognized-only recorded list is still a recorded restriction, even though it
    # yields no known-code entries; demand/within_target/below_start must not override it, so
    # only an empty raw list is eligible for either check. Precedence: recorded known
    # reasons -> demand -> within_target -> below_start -> unknown.
    if not raw_reasons:
        demand = _demand(snapshot)
        if demand is not None:
            return [demand]
        within_target = _within_target(snapshot)
        if within_target is not None:
            return [within_target]
        below_start = _below_start(snapshot, zone)
        if below_start is not None:
            return [below_start]
    return [{"code": UNKNOWN_REASON_CODE, "detail": UNKNOWN_REASON_DETAIL}]
