"""Purpose: Detect stage capability mismatches and explain unusable stage devices.

Key dependencies: Loaded configuration, cached zone/device state, shared constants.
Used by: Setup warnings, device dispatch warnings, Agent API status, smoke checks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .const import (
    CAPABILITY_COOL, CAPABILITY_HEAT, CAPABILITY_UI_COOL_LABEL, CAPABILITY_UI_HEAT_LABEL,
    FIRST_STAGE_NUMBER,
    STAGE_COOL_PREFIX, STAGE_HEAT_PREFIX, STAGE_OPPORTUNISTIC,
    STAGE_UNUSABLE_BLOCKED, STAGE_UNUSABLE_MISSING_CAPABILITY,
    STAGE_UNUSABLE_NOT_FOUND, STAGE_UNUSABLE_UNAVAILABLE,
)
from .models import Device, DeviceCapability, HybridClimateConfig, ZoneState

_LOGGER = logging.getLogger(__name__)
# Entry IDs survive reloads, so reloading an unchanged entry intentionally does not re-warn.
_load_warned: set[tuple[str, str, int, str, str]] = set()
# Dispatch receives devices without an entry ID; keep its process-wide warning memo.
_runtime_warned: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class CapabilityMismatch:
    """Identify a stage reference that its device cannot serve."""

    zone: str
    stage: int
    device: str
    capability: str


def find_capability_mismatches(config: HybridClimateConfig) -> list[CapabilityMismatch]:
    """Return every incapable stage reference in loaded config order."""
    mismatches: list[CapabilityMismatch] = []
    for zone_id, zone in config.zones.items():
        for direction, stages in ((CAPABILITY_HEAT, zone.heat_stages), (CAPABILITY_COOL, zone.cool_stages)):
            needed = DeviceCapability(direction)
            for stage in stages:
                for reference in stage.devices:
                    device = config.devices.get(reference.device_id)
                    if device is not None and needed not in device.capabilities:
                        mismatches.append(CapabilityMismatch(zone_id, stage.stage_number, reference.device_id, direction))
    return mismatches


def warn_load_mismatches(config: HybridClimateConfig, entry_id: str) -> None:
    """Log each loaded stage mismatch once across setup and reloads."""
    for item in find_capability_mismatches(config):
        key = (entry_id, item.zone, item.stage, item.device, item.capability)
        if key not in _load_warned:
            _load_warned.add(key)
            _LOGGER.warning(
                "Zone %s stage %s %s device %s lacks %s capability; fix in Options → Devices → %s → %s",
                item.zone, item.stage, item.capability, item.device, item.capability,
                item.device, CAPABILITY_UI_HEAT_LABEL if item.capability == CAPABILITY_HEAT else CAPABILITY_UI_COOL_LABEL,
            )


def warn_runtime_capability_skip(device: Device, direction: str) -> None:
    """Warn once when dispatch skips an incapable device."""
    key = (device.device_id, direction)
    if key not in _runtime_warned:
        _runtime_warned.add(key)
        _LOGGER.warning("Device %s lacks %s capability; stage dispatch skipped it", device.device_id, direction)


def active_stage_unusable(
    config: HybridClimateConfig, state: ZoneState, zone_id: str,
) -> tuple[list[dict[str, str]], bool]:
    """List unusable devices in the current stage and whether none can serve it."""
    stage_name = state.current_stage
    if stage_name == STAGE_OPPORTUNISTIC:
        direction, number = CAPABILITY_HEAT, FIRST_STAGE_NUMBER
    elif stage_name and stage_name.startswith(STAGE_HEAT_PREFIX):
        direction, suffix = CAPABILITY_HEAT, stage_name.removeprefix(STAGE_HEAT_PREFIX)
        number = int(suffix) if suffix.isdigit() else None
    elif stage_name and stage_name.startswith(STAGE_COOL_PREFIX):
        direction, suffix = CAPABILITY_COOL, stage_name.removeprefix(STAGE_COOL_PREFIX)
        number = int(suffix) if suffix.isdigit() else None
    else:
        return [], False
    stages = config.zones[zone_id].heat_stages if direction == CAPABILITY_HEAT else config.zones[zone_id].cool_stages
    stage = next((item for item in stages if item.stage_number == number), None)
    if stage is None or not stage.devices:
        return [], False
    unusable: list[dict[str, str]] = []
    for reference in stage.devices:
        device = config.devices.get(reference.device_id)
        if device is None:
            why = STAGE_UNUSABLE_NOT_FOUND
        elif DeviceCapability(direction) not in device.capabilities:
            why = STAGE_UNUSABLE_MISSING_CAPABILITY
        elif not device.is_available:
            why = STAGE_UNUSABLE_UNAVAILABLE
        elif reference.device_id in state.blocked_devices:
            why = STAGE_UNUSABLE_BLOCKED
        else:
            continue
        unusable.append({"device": reference.device_id, "why": why})
    return unusable, len(unusable) == len(stage.devices)
