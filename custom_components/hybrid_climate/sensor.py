"""Sensor platform for Hybrid Climate integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hybrid Climate sensor entities."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data is None:
        _LOGGER.error("Failed to set up sensor entities: entry data not found")
        return

    coordinator: HybridClimateCoordinator = data["coordinator"]
    entities: list[SensorEntity] = []

    for zone_id, zone_config in coordinator.config.zones.items():
        # Zone temperature sensor (aggregated from all indoor sensors)
        entities.append(
            ZoneTemperatureSensor(
                coordinator=coordinator,
                zone_id=zone_id,
                zone_name=zone_config.name,
            )
        )

        # Regulated setpoint sensor (only if zone has PI regulation)
        if zone_config.regulation and zone_config.regulation.type == "pi":
            entities.append(
                RegulatedSetpointSensor(
                    coordinator=coordinator,
                    zone_id=zone_id,
                    zone_name=zone_config.name,
                )
            )

        # TOU state sensor (only if zone has TOU config)
        if zone_config.tou is not None:
            entities.append(
                TouStateSensor(
                    coordinator=coordinator,
                    zone_id=zone_id,
                    zone_name=zone_config.name,
                )
            )

    async_add_entities(entities)
    _LOGGER.info("Created %d sensor entities for Hybrid Climate", len(entities))


class ZoneTemperatureSensor(SensorEntity):
    """Sensor showing the calculated zone temperature."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: HybridClimateCoordinator,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the zone temperature sensor."""
        self.coordinator = coordinator
        self.zone_id = zone_id
        self.zone_name = zone_name

        self._attr_unique_id = f"{DOMAIN}_{zone_id}_temperature"
        self._attr_name = "Temperature"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group under the zone device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_{self.zone_id}")},
            name=f"Hybrid Climate - {self.zone_name}",
            manufacturer="Hybrid Climate",
            model="Zone",
        )

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return self.coordinator.hass.config.units.temperature_unit

    @property
    def native_value(self) -> float | None:
        """Return the current zone temperature."""
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state:
            return zone_state.current_temperature
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return sensor attributes with individual sensor readings."""
        attrs: dict[str, Any] = {}
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        
        if zone_state:
            # Individual sensor values
            if zone_state.sensor_values:
                attrs["sensor_values"] = zone_state.sensor_values
            
            # Smoothed sensor values
            if zone_state.sensor_smoothed_values:
                attrs["sensor_smoothed_values"] = zone_state.sensor_smoothed_values
        
        # Aggregation method from config
        zone_config = self.coordinator.config.zones.get(self.zone_id)
        if zone_config and zone_config.sensors:
            attrs["aggregation_method"] = zone_config.sensors.aggregation.value
            attrs["smoothing_samples"] = zone_config.sensors.smoothing_samples
            attrs["source_sensors"] = zone_config.sensors.indoor
        
        return attrs

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class RegulatedSetpointSensor(SensorEntity):
    """Sensor showing the PI-regulated setpoint."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: HybridClimateCoordinator,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the regulated setpoint sensor."""
        self.coordinator = coordinator
        self.zone_id = zone_id
        self.zone_name = zone_name

        self._attr_unique_id = f"{DOMAIN}_{zone_id}_regulated_setpoint"
        self._attr_name = "Regulated Setpoint"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group under the zone device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_{self.zone_id}")},
            name=f"Hybrid Climate - {self.zone_name}",
            manufacturer="Hybrid Climate",
            model="Zone",
        )

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return self.coordinator.hass.config.units.temperature_unit

    @property
    def native_value(self) -> float | None:
        """Return the current regulated setpoint."""
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state:
            return zone_state.regulated_setpoint
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return PI control attributes."""
        attrs: dict[str, Any] = {}
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        
        if zone_state:
            # PI control state
            attrs["target_temperature"] = zone_state.target_temperature
            attrs["regulation_offset"] = round(zone_state.regulation_offset, 2) if zone_state.regulation_offset else 0
            attrs["accumulated_error"] = round(zone_state.accumulated_error, 2) if zone_state.accumulated_error else 0
        
        # PI configuration from zone config
        zone_config = self.coordinator.config.zones.get(self.zone_id)
        if zone_config and zone_config.regulation:
            reg = zone_config.regulation
            attrs["pi_kp"] = reg.kp
            attrs["pi_ki"] = reg.ki
            attrs["pi_k_ext"] = reg.k_ext
            attrs["pi_offset_max"] = reg.offset_max
            attrs["pi_balance_point"] = reg.balance_point
        
        # Current outdoor temperature (used in PI calculation)
        if self.coordinator.master_state.outdoor_temperature is not None:
            attrs["outdoor_temperature"] = self.coordinator.master_state.outdoor_temperature

        return attrs

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class TouStateSensor(SensorEntity):
    """Sensor showing the TOU state for a zone."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HybridClimateCoordinator,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the TOU state sensor."""
        self.coordinator = coordinator
        self.zone_id = zone_id
        self.zone_name = zone_name

        self._attr_unique_id = f"{DOMAIN}_{zone_id}_tou_state"
        self._attr_name = "TOU State"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group under the zone device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_{self.zone_id}")},
            name=f"Hybrid Climate - {self.zone_name}",
            manufacturer="Hybrid Climate",
            model="Zone",
        )

    @property
    def native_value(self) -> str | None:
        """Return the current TOU state."""
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state:
            return zone_state.tou_state
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return TOU configuration attributes."""
        attrs: dict[str, Any] = {}
        zone_config = self.coordinator.config.zones.get(self.zone_id)

        if zone_config and zone_config.tou:
            tou = zone_config.tou
            if tou.heat:
                attrs["heat_pre_condition_minutes"] = tou.heat.pre_condition_minutes
                attrs["heat_relaxation_amount"] = tou.heat.relaxation_amount
            if tou.cool:
                attrs["cool_pre_condition_minutes"] = tou.cool.pre_condition_minutes
                attrs["cool_relaxation_amount"] = tou.cool.relaxation_amount

        # Include the current rate period for context
        rate_sensor_id = self.coordinator.config.tou_global.rate_sensor
        if rate_sensor_id:
            rate_state = self.coordinator.hass.states.get(rate_sensor_id)
            if rate_state:
                attrs["rate_period"] = rate_state.state
                next_peak = rate_state.attributes.get("next_peak_start")
                if next_peak:
                    attrs["next_peak_start"] = str(next_peak)

        return attrs

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
