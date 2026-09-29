"""Sensor polling, smoothing, and temperature acquisition.

Key dependencies: models.py (ZoneConfig, ZoneSensors, AggregationMethod)
Used by: coordinator.py
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any, TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .aggregation import aggregate
from .const import (
    DEFAULT_SENSOR_STALE_TIME,
    OUTDOOR_TEMP_STALE_SECONDS,
    REGULATION_PI,
    SENSOR_RESTORE_GRACE_PERIOD_SECONDS,
    TEMP_MAX_VALID,
    TEMP_MIN_VALID,
)
from .outdoor_sensors import read_outdoor_candidates

if TYPE_CHECKING:
    from .device_manager import DeviceManager
    from .models import (
        AggregationMethod,
        HybridClimateConfig,
        ZoneConfig,
        ZoneState,
    )

_LOGGER = logging.getLogger(__name__)


def retain_outdoor_temperature(
    reading: float | None,
    last_reading: tuple[float, datetime] | None,
    now: datetime,
) -> tuple[float | None, tuple[float, datetime] | None]:
    """Use a recent verified outdoor reading until the stale window expires."""
    if reading is not None:
        return reading, (reading, now)
    if last_reading is not None:
        last_temp, last_time = last_reading
        if (now - last_time).total_seconds() < OUTDOOR_TEMP_STALE_SECONDS:
            return last_temp, last_reading
    return None, last_reading


def init_sensor_sample_buffers(
    config: HybridClimateConfig,
    sensor_samples: dict[str, deque[float]],
) -> None:
    """Initialize sample buffers for each sensor based on zone config."""
    for zone_config in config.zones.values():
        smoothing_samples = zone_config.sensors.smoothing_samples
        for sensor_id in zone_config.sensors.indoor:
            if sensor_id not in sensor_samples:
                sensor_samples[sensor_id] = deque(maxlen=smoothing_samples)
                _LOGGER.debug(
                    "Initialized sample buffer for %s with maxlen=%d",
                    sensor_id,
                    smoothing_samples,
                )


def collect_sensor_sample(
    sensor_id: str,
    value: float,
    sensor_samples: dict[str, deque[float]],
) -> None:
    """Add a sample to the sensor's buffer."""
    if sensor_id in sensor_samples:
        sensor_samples[sensor_id].append(value)


def get_smoothed_sensor_value(
    sensor_id: str,
    sensor_samples: dict[str, deque[float]],
) -> float | None:
    """Get the smoothed (moving average) value for a sensor."""
    if sensor_id not in sensor_samples:
        return None
    samples = sensor_samples[sensor_id]
    if not samples:
        return None
    return sum(samples) / len(samples)


async def get_outdoor_temperature(
    hass: HomeAssistant,
    config: HybridClimateConfig,
) -> float | None:
    """Get outdoor temperature from configured sensor.

    Supports both sensor entities (state is temperature) and weather entities
    (temperature is in attributes).
    """
    entities = getattr(config, "outdoor_sensors", None)
    if entities is None:
        entities = [config.outdoor_sensor] if config.outdoor_sensor else []
    return read_outdoor_candidates(hass, entities).temperature


async def get_zone_temperature(
    zone_config: ZoneConfig,
    hass: HomeAssistant,
    sensor_samples: dict[str, deque[float]],
    last_sensor_values: dict[str, tuple[float, datetime]],
    zone_states: dict[str, ZoneState],
    device_manager: DeviceManager,
    restore_start_times: dict[str, datetime] | None = None,
) -> float | None:
    """Get aggregated temperature for a zone with smoothing.

    Applies moving average smoothing to each sensor before aggregation.

    Fallback strategy:
    1. Use live sensor values (smoothed)
    2. Use stale sensor values (< 10 min old) if live unavailable
    3. If no primary sensors available, fall back to underlying climate entity sensors
    4. If all fails, return None
    """
    control_readings: dict[str, float] = {}
    raw_readings: dict[str, float] = {}
    smoothed_readings: dict[str, float] = {}
    stale_sensors: list[str] = []

    # Try primary indoor sensors
    for sensor_id in zone_config.sensors.indoor:
        state = hass.states.get(sensor_id)

        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            # Check for last known good value within stale window
            if sensor_id in last_sensor_values:
                last_value, last_time = last_sensor_values[sensor_id]
                age = (dt_util.utcnow() - last_time).total_seconds()
                if age < DEFAULT_SENSOR_STALE_TIME:
                    _LOGGER.debug(
                        "Using stale value for %s (age: %ss)",
                        sensor_id,
                        int(age),
                    )
                    # Use the smoothed value from buffer if available
                    smoothed = get_smoothed_sensor_value(sensor_id, sensor_samples)
                    if smoothed is not None:
                        control_readings[sensor_id] = smoothed
                        raw_readings[sensor_id] = last_value
                        smoothed_readings[sensor_id] = smoothed
                    else:
                        control_readings[sensor_id] = last_value
                        raw_readings[sensor_id] = last_value
                        smoothed_readings[sensor_id] = last_value
                else:
                    stale_sensors.append(sensor_id)
                    _LOGGER.debug(
                        "Sensor %s stale > %ss, excluding from aggregation",
                        sensor_id,
                        DEFAULT_SENSOR_STALE_TIME,
                    )
            continue

        try:
            temp = float(state.state)
            if TEMP_MIN_VALID <= temp <= TEMP_MAX_VALID:
                # Collect sample for smoothing
                collect_sensor_sample(sensor_id, temp, sensor_samples)
                last_sensor_values[sensor_id] = (temp, dt_util.utcnow())

                # Get smoothed value (moving average of samples)
                smoothed = get_smoothed_sensor_value(sensor_id, sensor_samples)
                if smoothed is not None:
                    control_readings[sensor_id] = smoothed
                    raw_readings[sensor_id] = temp
                    smoothed_readings[sensor_id] = round(smoothed, 2)
                else:
                    # No samples yet, use raw value
                    control_readings[sensor_id] = temp
                    raw_readings[sensor_id] = temp
                    smoothed_readings[sensor_id] = temp
            else:
                _LOGGER.warning(
                    "Sensor %s temp %s out of valid range",
                    sensor_id,
                    temp,
                )
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Could not parse temperature from %s: %s",
                sensor_id,
                state.state,
            )

    # Fallback to underlying climate entity sensors if no primary sensors available
    # BUT: Skip fallback for zones with PI-regulated devices (e.g., radiant floors)
    # because their current_temperature is the floor temp, not room temp
    if not control_readings:
        has_pi_regulation = (
            zone_config.regulation is not None
            and zone_config.regulation.type == REGULATION_PI
        )
        if has_pi_regulation:
            _LOGGER.debug(
                "Zone %s: no primary sensors available, skipping device fallback "
                "(PI-regulated devices have floor sensors, not room sensors)",
                zone_config.zone_id,
            )
        else:
            _LOGGER.debug(
                "Zone %s: no primary sensors, trying climate entity fallback",
                zone_config.zone_id,
            )
            fallback_temp = await get_fallback_temperature_from_devices(
                zone_config, hass, device_manager,
            )
            if fallback_temp is not None:
                control_readings["_fallback_device"] = fallback_temp
                raw_readings["_fallback_device"] = fallback_temp
                smoothed_readings["_fallback_device"] = fallback_temp
                _LOGGER.info(
                    "Zone %s: using fallback temperature from device: %s",
                    zone_config.zone_id,
                    fallback_temp,
                )

    # Final fallback: use restored/last known zone temperature
    # This preserves continuity after restarts when sensors aren't immediately available
    # but only for a grace period (5 min) — after that, return None to trigger fail-safe
    if not control_readings and restore_start_times is not None:
        zone_id = zone_config.zone_id
        zone_state = zone_states.get(zone_id)
        if zone_state and zone_state.current_temperature is not None:
            now = dt_util.utcnow()

            # Track when we first started using the restored value
            if zone_id not in restore_start_times:
                restore_start_times[zone_id] = now
                _LOGGER.info(
                    "Zone %s: using restored/last known temperature: %.1f "
                    "(grace period started, %ds until expiry)",
                    zone_id,
                    zone_state.current_temperature,
                    SENSOR_RESTORE_GRACE_PERIOD_SECONDS,
                )

            elapsed = (now - restore_start_times[zone_id]).total_seconds()
            if elapsed <= SENSOR_RESTORE_GRACE_PERIOD_SECONDS:
                restored_temp = zone_state.current_temperature
                control_readings["_restored"] = restored_temp
                raw_readings["_restored"] = restored_temp
                smoothed_readings["_restored"] = restored_temp
            else:
                _LOGGER.warning(
                    "Zone %s: restored temperature grace period expired after %ds. "
                    "Returning None to trigger sensor-failure safe mode.",
                    zone_id, int(elapsed),
                )
    elif control_readings and restore_start_times is not None:
        # Sensors are working — clear any restore tracking for this zone
        zone_id = zone_config.zone_id
        if zone_id in restore_start_times:
            _LOGGER.info(
                "Zone %s: sensors recovered, clearing restore grace timer",
                zone_id,
            )
            del restore_start_times[zone_id]

    if not control_readings:
        if stale_sensors:
            _LOGGER.warning(
                "Zone %s: all sensors stale or unavailable: %s",
                zone_config.zone_id,
                stale_sensors,
            )
        return None

    # Store individual sensor values in zone state (both raw and smoothed)
    zone_state = zone_states.get(zone_config.zone_id)
    if zone_state:
        zone_state.sensor_values = raw_readings
        zone_state.sensor_smoothed_values = smoothed_readings

    return aggregate(
        zone_config.sensors.aggregation, control_readings, zone_config.sensors.weights,
    )


async def get_fallback_temperature_from_devices(
    zone_config: ZoneConfig,
    hass: HomeAssistant,
    device_manager: DeviceManager,
) -> float | None:
    """Get temperature from underlying climate devices as fallback.

    Tries devices from heat_stages and cool_stages in order.
    """
    # Collect all device IDs from this zone's stages
    device_ids: list[str] = []
    for stage in zone_config.heat_stages:
        device_ids.extend(stage.get_device_ids())
    for stage in zone_config.cool_stages:
        device_ids.extend(stage.get_device_ids())

    # Remove duplicates while preserving order
    seen = set()
    unique_devices = []
    for d in device_ids:
        if d not in seen:
            seen.add(d)
            unique_devices.append(d)

    # Try each device
    for device_id in unique_devices:
        device = device_manager.get_device(device_id)
        if device is None:
            continue

        state = hass.states.get(device.entity_id)
        if state is None:
            continue

        # Try current_temperature attribute
        current_temp = state.attributes.get("current_temperature")
        if current_temp is not None:
            try:
                temp = float(current_temp)
                if TEMP_MIN_VALID <= temp <= TEMP_MAX_VALID:
                    _LOGGER.debug(
                        "Fallback temp from %s: %s",
                        device.entity_id,
                        temp,
                    )
                    return temp
            except (ValueError, TypeError):
                pass

    return None
