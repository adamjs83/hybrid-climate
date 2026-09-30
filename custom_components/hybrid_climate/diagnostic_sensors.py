"""Purpose: Expose cached zone and outdoor diagnostics as history-friendly sensors.

Key dependencies: Coordinator state and Agent API entity projections.
Used by: Hybrid Climate sensor platform.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .agent_api.const import ZONE_REASON_CODES
from .agent_api.entity_view import outdoor_source, zone_reason_codes, zone_spread, zone_stage_options, zone_stage_value
from .const import (
    ATTR_CODES, ATTR_METHOD, ATTR_PRIMARY, DIAG_DEVICE_NAME_PREFIX, DIAG_MANUFACTURER, DIAG_MASTER_MODEL, DIAG_ZONE_MODEL, DIAG_OUTDOOR_SOURCE_SUFFIX, DIAG_REASON_SUFFIX,
    DIAG_SPREAD_SUFFIX, DIAG_STAGE_SUFFIX, DOMAIN, STAGE_NONE, TRANSLATION_OUTDOOR_SOURCE,
    TRANSLATION_REASON, TRANSLATION_SPREAD, TRANSLATION_STAGE,
)
from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


class DiagnosticSensor(SensorEntity):
    """Base for read-only coordinator-backed diagnostic sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, coordinator: HybridClimateCoordinator) -> None:
        """Keep the loaded runtime and Home Assistant state store."""
        self.hass = hass
        self.coordinator = coordinator

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator refreshes."""
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))

    @callback
    def _handle_coordinator_update(self) -> None:
        """Publish the latest cached projection."""
        self.async_write_ha_state()


class ZoneDiagnosticSensor(DiagnosticSensor):
    """Attach one sensor to its configured zone device."""

    def __init__(self, hass: HomeAssistant, coordinator: HybridClimateCoordinator, zone_id: str) -> None:
        """Keep the zone identity."""
        super().__init__(hass, coordinator)
        self.zone_id = zone_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the same zone device identity as the existing temperature sensor."""
        zone = self.coordinator.config.zones[self.zone_id]
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_{self.zone_id}")},
            name=f"{DIAG_DEVICE_NAME_PREFIX}{zone.name}", manufacturer=DIAG_MANUFACTURER, model=DIAG_ZONE_MODEL,
        )


class ZoneReasonSensor(ZoneDiagnosticSensor):
    """Record the first Agent API reason code."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = TRANSLATION_REASON
    _attr_options = list(ZONE_REASON_CODES)

    def __init__(self, hass: HomeAssistant, coordinator: HybridClimateCoordinator, zone_id: str) -> None:
        """Set the stable reason identity."""
        super().__init__(hass, coordinator, zone_id)
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_{DIAG_REASON_SUFFIX}"
        self._codes = zone_reason_codes(hass, coordinator, zone_id)

    async def async_added_to_hass(self) -> None:
        """Refresh the initial codes when HA adds the entity."""
        await super().async_added_to_hass()
        self._codes = zone_reason_codes(self.hass, self.coordinator, self.zone_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh reason codes once before publishing state and attributes."""
        self._codes = zone_reason_codes(self.hass, self.coordinator, self.zone_id)
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        """Return the primary reason code."""
        return self._codes[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose all reason codes without their changing detail payloads."""
        return {ATTR_CODES: self._codes}


class ZoneSpreadSensor(ZoneDiagnosticSensor):
    """Record the spread of smoothed temperature inputs.

    No SensorDeviceClass.TEMPERATURE: this value is a temperature *difference*
    (max - min across sensor inputs), and HA's temperature device class treats a
    state as an absolute reading, converting it between units accordingly. The
    native unit is still the HA temperature unit; only the device class is omitted.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = TRANSLATION_SPREAD

    def __init__(self, hass: HomeAssistant, coordinator: HybridClimateCoordinator, zone_id: str) -> None:
        """Set the stable spread identity."""
        super().__init__(hass, coordinator, zone_id)
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_{DIAG_SPREAD_SUFFIX}"

    @property
    def native_unit_of_measurement(self) -> str:
        """Use the Home Assistant temperature unit."""
        return self.hass.config.units.temperature_unit

    @property
    def native_value(self) -> float | None:
        """Return the cached spread or unknown for fewer than two inputs."""
        return zone_spread(self.coordinator, self.zone_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the loaded aggregation method."""
        return {ATTR_METHOD: self.coordinator.config.zones[self.zone_id].sensors.aggregation.value}


class ZoneStageSensor(ZoneDiagnosticSensor):
    """Record the configured or opportunistic stage."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = TRANSLATION_STAGE

    def __init__(self, hass: HomeAssistant, coordinator: HybridClimateCoordinator, zone_id: str) -> None:
        """Set stable identity and options for the loaded configuration."""
        super().__init__(hass, coordinator, zone_id)
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_{DIAG_STAGE_SUFFIX}"
        self._attr_options = zone_stage_options(coordinator, zone_id)
        self._unexpected_stage: str | None = None

    @property
    def native_value(self) -> str:
        """Return the stage, warning once for each unexpected cached value."""
        actual = self.coordinator.zone_states[self.zone_id].current_stage
        value = zone_stage_value(self.coordinator, self.zone_id)
        if actual is not None and value == STAGE_NONE and actual != self._unexpected_stage:
            _LOGGER.warning("Zone %s has unconfigured stage %s", self.zone_id, actual)
            self._unexpected_stage = actual
        return value


class OutdoorSourceSensor(DiagnosticSensor):
    """Record the selected outdoor reading source."""

    _attr_translation_key = TRANSLATION_OUTDOOR_SOURCE
    _attr_unique_id = f"{DOMAIN}_{DIAG_OUTDOOR_SOURCE_SUFFIX}"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the existing master device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_master")},
            name=f"{DIAG_DEVICE_NAME_PREFIX}{self.coordinator.config.master.name}",
            manufacturer=DIAG_MANUFACTURER, model=DIAG_MASTER_MODEL,
        )

    @property
    def native_value(self) -> str | None:
        """Return the current selected source."""
        return outdoor_source(self.coordinator)[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the configured primary source."""
        return {ATTR_PRIMARY: self.coordinator.config.outdoor_sensor}


def diagnostic_sensors(hass: HomeAssistant, coordinator: HybridClimateCoordinator) -> list[SensorEntity]:
    """Create the new diagnostic sensors for the loaded entry."""
    entities: list[SensorEntity] = []
    for zone_id in coordinator.config.zones:
        entities.extend((
            ZoneReasonSensor(hass, coordinator, zone_id),
            ZoneSpreadSensor(hass, coordinator, zone_id),
            ZoneStageSensor(hass, coordinator, zone_id),
        ))
    entities.append(OutdoorSourceSensor(hass, coordinator))
    return entities
