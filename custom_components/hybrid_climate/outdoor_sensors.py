"""Purpose: Read ordered outdoor sources and retain recent verified readings.

Key dependencies: Home Assistant states and outdoor validation constants.
Used by: Coordinator, sensor manager compatibility helpers, and Agent API.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.const import ATTR_TEMPERATURE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    OUTDOOR_STATUS_INVALID, OUTDOOR_STATUS_MISSING, OUTDOOR_STATUS_OK,
    OUTDOOR_STATUS_UNAVAILABLE, OUTDOOR_TEMP_STALE_SECONDS,
    TEMP_MAX_VALID, TEMP_MIN_VALID,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class OutdoorReading:
    """One cycle's selected value and all candidate observations."""

    temperature: float | None
    source: str | None
    candidates: list[dict[str, Any]]
    retained: bool = False


def _read_entity(hass: HomeAssistant, entity_id: str) -> tuple[str, float | None, Any]:
    """Classify and parse one sensor or weather entity."""
    state = hass.states.get(entity_id)
    if state is None:
        return OUTDOOR_STATUS_MISSING, None, None
    if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return OUTDOOR_STATUS_UNAVAILABLE, None, state.state
    raw = state.attributes.get(ATTR_TEMPERATURE) if entity_id.startswith("weather.") else state.state
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return OUTDOOR_STATUS_INVALID, None, raw
    if not TEMP_MIN_VALID <= value <= TEMP_MAX_VALID:
        return OUTDOOR_STATUS_INVALID, None, raw
    return OUTDOOR_STATUS_OK, value, raw


def read_outdoor_candidates(
    hass: HomeAssistant,
    entities: list[str],
    previous_statuses: dict[str, str] | None = None,
) -> OutdoorReading:
    """Read every configured source and select the first valid temperature."""
    candidates: list[dict[str, Any]] = []
    selected = OutdoorReading(None, None, candidates)
    for entity_id in entities:
        status, value, raw = _read_entity(hass, entity_id)
        if previous_statuses is not None:
            # Report status edges without repeating a warning for a steady fault.
            previous = previous_statuses.get(entity_id)
            if status != previous:
                if status == OUTDOOR_STATUS_INVALID:
                    _LOGGER.warning("Invalid outdoor reading from %s: %r", entity_id, raw)
                elif status == OUTDOOR_STATUS_OK and previous == OUTDOOR_STATUS_INVALID:
                    _LOGGER.info("Outdoor reading recovered for %s", entity_id)
                elif status != OUTDOOR_STATUS_OK:
                    _LOGGER.debug("Outdoor reading for %s changed to %s", entity_id, status)
        candidates.append({"entity_id": entity_id, "status": status, "value": value})
        if selected.source is None and status == OUTDOOR_STATUS_OK:
            selected.temperature, selected.source = value, entity_id
    return selected


def retain_outdoor_reading(
    reading: OutdoorReading,
    last: tuple[float, datetime, str | None] | None,
    now: datetime,
) -> tuple[OutdoorReading, tuple[float, datetime, str | None] | None]:
    """Retain the last verified value and source for the stale window."""
    if reading.temperature is not None:
        return reading, (reading.temperature, now, reading.source)
    if last and (now - last[1]).total_seconds() < OUTDOOR_TEMP_STALE_SECONDS:
        reading.temperature, reading.source, reading.retained = last[0], last[2], True
    return reading, last


def update_outdoor_reading(coordinator: Any) -> float | None:
    """Refresh cached outdoor status and log each fallback transition once."""
    # The prior cycle belongs to this coordinator, keeping entries independent.
    previous_reading = coordinator.outdoor_reading
    previous_source = previous_reading.source
    if previous_source is None and coordinator._last_outdoor_reading is not None:
        previous_source = coordinator._last_outdoor_reading[2]
    previous_statuses = {
        candidate["entity_id"]: candidate["status"]
        for candidate in previous_reading.candidates
    }
    reading = read_outdoor_candidates(
        coordinator.hass, coordinator.config.outdoor_sensors, previous_statuses,
    )
    reading, coordinator._last_outdoor_reading = retain_outdoor_reading(
        reading, coordinator._last_outdoor_reading, dt_util.utcnow(),
    )
    primary = coordinator.config.outdoor_sensor
    using_fallback = reading.source is not None and reading.source != primary
    # Source changes and retention changes are separate operational transitions.
    if reading.source != previous_reading.source and not reading.retained:
        if using_fallback:
            _LOGGER.warning(
                "Outdoor source switched to fallback from %s to %s",
                previous_source, reading.source,
            )
        elif reading.source == primary and previous_source not in (None, primary):
            _LOGGER.info("Outdoor source returned to primary from %s to %s",
                         previous_source, reading.source)
    if reading.retained and not previous_reading.retained:
        _LOGGER.warning("Outdoor sources unavailable; retaining last reading from %s", reading.source)
    elif reading.temperature is None and previous_reading.temperature is not None:
        _LOGGER.warning("Retained outdoor reading expired; temperature is unavailable")
    coordinator._outdoor_using_fallback = using_fallback
    coordinator.outdoor_reading = reading
    return reading.temperature
