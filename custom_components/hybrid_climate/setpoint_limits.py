"""Purpose: Clamp device targets and learn rounded Home Assistant limits.

Key dependencies: Home Assistant climate services and device state attributes.
Used by: DeviceManager when dispatching a target temperature.
"""
from __future__ import annotations

import logging

from homeassistant.components.climate.const import ATTR_TARGET_TEMP_STEP
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .const import (
    DEFAULT_TARGET_TEMP_STEP_C, DEFAULT_TARGET_TEMP_STEP_F,
    OUT_OF_RANGE_ERROR_FRAGMENT, OUT_OF_RANGE_TRANSLATION_KEY,
    SERVICE_CLIMATE, SERVICE_SET_TEMPERATURE,
)
from .models import Device

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
        step = attributes.get(ATTR_TARGET_TEMP_STEP)
        if step is None:
            unit = hass.config.units.temperature_unit
            step = DEFAULT_TARGET_TEMP_STEP_C if unit == UnitOfTemperature.CELSIUS else DEFAULT_TARGET_TEMP_STEP_F
        if not isinstance(step, (int, float)) or step <= 0:
            raise
        retry = target - step if boundary == "max_temp" else target + step
        payload[ATTR_TEMPERATURE] = retry
        await hass.services.async_call(SERVICE_CLIMATE, SERVICE_SET_TEMPERATURE, payload, blocking=True)
        # Learn only after HA accepts the retry, so an unrelated rejection never
        # narrows future targets or changes the recorded command.
        learned.setdefault(device.device_id, {})[boundary] = retry
        _LOGGER.warning("Device %s reported %s %s but accepted %s; using learned limit",
                        device.device_id, boundary, target, retry)
        return retry
