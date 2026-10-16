"""Purpose: Stage 1 / stage 2 fields of the zone wizard's heat and cool stage pages, and the stages a submit stores.

Key dependencies: const.py (time escalation minute range, page stage defaults), options_flow/base.py
(minute conversions), options_flow/zone_merge.py (stage_conditions, retained_stages).
Used by: options_flow/zone_pages/stage_page.py (the Heating and Cooling stages pages).
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from ..const import (
    DEFAULT_TIME_ESCALATION,
    MAX_TIME_ESCALATION_MINUTES,
    MIN_TIME_ESCALATION_MINUTES,
    PAGE_STAGE_DEFAULT_THRESHOLDS,
    PAGE_STAGE_NUMBERS,
    TIME_ESCALATION_MINUTES_STEP,
)
from .base import minutes_to_seconds, seconds_to_minutes
from .zone_merge import retained_stages, stage_conditions


def _threshold_selector() -> NumberSelector:
    """Return the stage threshold selector (°F above or below target)."""
    return NumberSelector(
        NumberSelectorConfig(
            min=0.5,
            max=10,
            step=0.5,
            unit_of_measurement="°F",
            mode=NumberSelectorMode.BOX,
        )
    )


def _climate_devices_selector() -> EntitySelector:
    """Return the multi-select climate device picker for a stage."""
    return EntitySelector(EntitySelectorConfig(domain="climate", multiple=True))


def stage_form_fields(
    stage1: dict[str, Any],
    stage2: dict[str, Any],
    stage1_device_ids: list[str],
    stage2_device_ids: list[str],
    *,
    include_outdoor_min: bool,
) -> dict[Any, Any]:
    """Return the stage 1 and stage 2 schema entries for a heat or cool stage page."""
    # Escalation is stored in seconds and shown in minutes. A stored stage 2 shows its own
    # timer (blank when it has none); only a page with no stage 2 yet suggests 30 minutes.
    escalation_seconds = (stage2.get("time_escalation") or None) if stage2 else DEFAULT_TIME_ESCALATION
    fields: dict[Any, Any] = {
        vol.Optional("stage1_devices", default=stage1_device_ids): _climate_devices_selector(),
        vol.Optional("stage1_threshold", default=stage1.get("threshold", 1.0)): _threshold_selector(),
        vol.Optional(
            "stage2_devices",
            description={"suggested_value": stage2_device_ids if stage2_device_ids else None},
        ): _climate_devices_selector(),
        vol.Optional(
            "stage2_threshold", description={"suggested_value": stage2.get("threshold")},
        ): _threshold_selector(),
        vol.Optional(
            "stage2_time_escalation",
            description={"suggested_value": seconds_to_minutes(escalation_seconds)},
        ): NumberSelector(
            NumberSelectorConfig(
                min=MIN_TIME_ESCALATION_MINUTES,
                max=MAX_TIME_ESCALATION_MINUTES,
                step=TIME_ESCALATION_MINUTES_STEP,
                unit_of_measurement="min",
                mode=NumberSelectorMode.BOX,
            )
        ),
    }
    # Only heating uses an outdoor floor for stage 2 (heat pump efficiency).
    if include_outdoor_min:
        fields[vol.Optional(
            "stage2_outdoor_min",
            description={"suggested_value": stage_conditions(stage2).get("outdoor_temp_min")},
        )] = NumberSelector(
            NumberSelectorConfig(
                min=-20,
                max=80,
                step=1,
                unit_of_measurement="°F",
                mode=NumberSelectorMode.BOX,
            )
        )
    return fields


def submitted_stages(
    user_input: dict[str, Any],
    current: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
    *,
    enabled: bool,
    include_outdoor_min: bool,
) -> list[dict[str, Any]]:
    """Return the wizard's stage list after a stage page submit.

    Stages 1-2 come from the form (canonical UI form); stages 3+ the page does not show
    follow from `baseline` so later pages (settings, PI) still see their devices.
    A disabled mode keeps no stage at all.
    """
    if not enabled:
        return []
    # allow_command is managed on the Behaviour page; keep each device's current flag.
    allow = {
        d.get("entity_id", ""): d.get("allow_command", False)
        for s in current for d in s.get("devices", []) if isinstance(d, dict)
    }
    stages: list[dict[str, Any]] = []
    for number in PAGE_STAGE_NUMBERS:
        device_ids = [eid for eid in user_input.get(f"stage{number}_devices") or [] if eid]
        if not device_ids:
            continue
        stage: dict[str, Any] = {
            "stage": number,
            "devices": [{"entity_id": eid, "allow_command": allow.get(eid, False)} for eid in device_ids],
            "threshold": user_input.get(f"stage{number}_threshold", PAGE_STAGE_DEFAULT_THRESHOLDS[number]),
        }
        if number == PAGE_STAGE_NUMBERS[-1]:
            # A blank timer stores none (no timed escalation), never the 30-minute suggestion.
            minutes = user_input.get("stage2_time_escalation")
            if minutes is not None:
                stage["time_escalation"] = minutes_to_seconds(minutes, DEFAULT_TIME_ESCALATION)
            outdoor_min = user_input.get("stage2_outdoor_min") if include_outdoor_min else None
            if outdoor_min is not None:
                stage["conditions"] = {"outdoor_temp_min": outdoor_min}
        stages.append(stage)
    return stages + retained_stages(baseline, allow)
