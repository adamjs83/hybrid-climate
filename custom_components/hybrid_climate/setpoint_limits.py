"""Purpose: Clamp device targets and learn rounded Home Assistant limits.

Key dependencies: Home Assistant climate services and device state attributes.
Used by: DeviceManager when dispatching a target temperature.
"""
from __future__ import annotations

import logging

from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .const import (
    OUT_OF_RANGE_ERROR_FRAGMENT, OUT_OF_RANGE_TRANSLATION_KEY,
    SERVICE_CLIMATE, SERVICE_SET_TEMPERATURE,
)
from .models import Device
from .target_step import quantize_target, resolve_step

_LOGGER = logging.getLogger(__name__)


def clamp_target(
    hass: HomeAssistant, device: Device, target: float,
    learned: dict[str, dict[str, float]],
) -> float:
    """Clamp a target to reported limits and any learned effective limits."""
    state = hass.states.get(device.entity_id)
    attributes = state.attributes if state else {}
    minimum = attributes.get("min_temp")
    maximum = attributes.get("max_temp")
    learned_limits = learned.get(device.device_id, {})
    if "min_temp" in learned_limits:
        minimum = max(minimum, learned_limits["min_temp"]) if minimum is not None else learned_limits["min_temp"]
    if "max_temp" in learned_limits:
        maximum = min(maximum, learned_limits["max_temp"]) if maximum is not None else learned_limits["max_temp"]
    if minimum is not None:
        target = max(target, minimum)
    if maximum is not None:
        target = min(target, maximum)
    return target


def plan_target(
    hass: HomeAssistant, device: Device, mode: str, target: float | None,
    learned: dict[str, dict[str, float]],
) -> tuple[float | None, float | None, float]:
    """Return (raw clamped target, step-rounded clamped target, step) for a dispatch."""
    step = resolve_step(hass, device)
    if target is None:
        return None, None, step
    raw = clamp_target(hass, device, target, learned)
    # Clamp, quantize, clamp: a step may overshoot a limit that is not on the step grid.
    return raw, clamp_target(hass, device, quantize_target(raw, step, mode), learned), step


async def send_temperature(
    hass: HomeAssistant, device: Device, target: float,
    learned: dict[str, dict[str, float]],
) -> float:
    """Retry one rejected reported boundary a step inward and return the sent target."""
    payload = {"entity_id": device.entity_id, ATTR_TEMPERATURE: target}
    try:
        await hass.services.async_call(SERVICE_CLIMATE, SERVICE_SET_TEMPERATURE, payload, blocking=True)
        return target
    except ServiceValidationError as error:
        # A rounded HA boundary may exceed the device's native limit after unit
        # conversion. Retry only a first failure exactly at that reported edge.
        state = hass.states.get(device.entity_id)
        attributes = state.attributes if state else {}
        boundary = ("max_temp" if attributes.get("max_temp") == target else
                    "min_temp" if attributes.get("min_temp") == target else None)
        if (boundary is None or boundary in learned.get(device.device_id, {})
                or (getattr(error, "translation_key", None) != OUT_OF_RANGE_TRANSLATION_KEY
                    and OUT_OF_RANGE_ERROR_FRAGMENT not in str(error).lower())):
            raise
        step = resolve_step(hass, device)
        retry = target - step if boundary == "max_temp" else target + step
        payload[ATTR_TEMPERATURE] = retry
        await hass.services.async_call(SERVICE_CLIMATE, SERVICE_SET_TEMPERATURE, payload, blocking=True)
        # Learn only after HA accepts the retry, so an unrelated rejection never
        # narrows future targets or changes the recorded command.
        learned.setdefault(device.device_id, {})[boundary] = retry
        _LOGGER.warning("Device %s reported %s %s but accepted %s; using learned limit",
                        device.device_id, boundary, target, retry)
        return retry
