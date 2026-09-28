"""Zone climate entity for Hybrid Climate integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    ATTR_ACCUMULATED_ERROR,
    ATTR_ACTIVE_DEVICES,
    ATTR_BLOCKED_DEVICES,
    ATTR_CURRENT_STAGE,
    ATTR_MASTER_MODE,
    ATTR_REGULATED_SETPOINT,
    ATTR_REGULATION_OFFSET,
    ATTR_SENSOR_SMOOTHED_VALUES,
    ATTR_SENSOR_STATUS,
    ATTR_SENSOR_VALUES,
    ATTR_TIME_IN_STAGE,
    DOMAIN,
    MAX_TEMP_CELSIUS,
    MIN_TEMP_CELSIUS,
    TEMP_MAX_VALID,
    TEMP_MIN_VALID,
)
from .coordinator import HybridClimateCoordinator
from .models import HvacAction as ModelHvacAction, HvacMode as ModelHvacMode, ZoneConfig

_LOGGER = logging.getLogger(__name__)


class ZoneClimateEntity(ClimateEntity, RestoreEntity):
    """Climate entity for a single zone in Hybrid Climate."""

    _attr_has_entity_name = True
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF, HVACMode.AUTO]

    def __init__(
        self,
        coordinator: HybridClimateCoordinator,
        zone_config: ZoneConfig,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the zone climate entity."""
        self.coordinator = coordinator
        self.zone_config = zone_config
        self.zone_id = zone_config.zone_id
        self._entry = entry
        self._hass = coordinator.hass

        # Entity attributes
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{self.zone_id}"
        self._attr_name = zone_config.name

        # Determine supported HVAC modes based on configured stages
        modes = [HVACMode.OFF]
        has_heat = bool(zone_config.heat_stages)
        has_cool = bool(zone_config.cool_stages)

        if has_heat:
            modes.append(HVACMode.HEAT)
        if has_cool:
            modes.append(HVACMode.COOL)
        if has_heat and has_cool:
            modes.append(HVACMode.AUTO)
        self._attr_hvac_modes = modes

        # Dual-setpoint (range) only if zone has both heat and cool
        # Otherwise single setpoint
        if has_heat and has_cool:
            self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        else:
            self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

        self._attr_target_temperature_step = 0.5
        self._attr_precision = 0.1  # Show temperature with 1 decimal place

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group this entity under the zone device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_{self.zone_id}")},
            name=f"Hybrid Climate - {self.zone_config.name}",
            manufacturer="Hybrid Climate",
            model="Zone",
        )

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return self._hass.config.units.temperature_unit

    def _celsius_to_display(self, value: float) -> float:
        """Convert a Celsius value to the user's configured temperature unit."""
        if self._hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return TemperatureConverter.convert(
                value, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT
            )
        return value

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self._celsius_to_display(MIN_TEMP_CELSIUS)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self._celsius_to_display(MAX_TEMP_CELSIUS)

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        # Listen to coordinator updates
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

        # Restore previous state
        if last_state := await self.async_get_last_state():
            # NOTE: We intentionally do NOT restore target temperature as a manual override.
            # The zone should use the mode's configured setpoint (home/away/etc).
            # Manual overrides are transient and should be cleared on restart.

            # Restore PI accumulated error (critical for smooth PI behavior)
            if last_state.attributes.get(ATTR_ACCUMULATED_ERROR) is not None:
                try:
                    restored_accum = float(last_state.attributes[ATTR_ACCUMULATED_ERROR])
                    zone_state = self.coordinator.get_zone_state(self.zone_id)
                    if zone_state:
                        zone_state.accumulated_error = restored_accum
                        _LOGGER.debug(
                            "Zone %s: restored accumulated_error %s",
                            self.zone_id,
                            restored_accum,
                        )
                except (ValueError, TypeError):
                    pass

            # Restore last known current temperature (prevents graph spikes)
            if last_state.attributes.get("current_temperature") is not None:
                try:
                    restored_current = float(last_state.attributes["current_temperature"])
                    if TEMP_MIN_VALID <= restored_current <= TEMP_MAX_VALID:
                        zone_state = self.coordinator.get_zone_state(self.zone_id)
                        if zone_state and zone_state.current_temperature is None:
                            zone_state.current_temperature = restored_current
                            _LOGGER.debug(
                                "Zone %s: restored current_temperature %s",
                                self.zone_id,
                                restored_current,
                            )
                except (ValueError, TypeError):
                    pass

            # Restore regulation offset
            if last_state.attributes.get(ATTR_REGULATION_OFFSET) is not None:
                try:
                    restored_offset = float(last_state.attributes[ATTR_REGULATION_OFFSET])
                    zone_state = self.coordinator.get_zone_state(self.zone_id)
                    if zone_state:
                        zone_state.regulation_offset = restored_offset
                        # Also restore regulated setpoint based on target + offset
                        target = zone_state.target_temperature
                        if target is not None:
                            zone_state.regulated_setpoint = target + restored_offset
                        _LOGGER.debug(
                            "Zone %s: restored regulation_offset %s",
                            self.zone_id,
                            restored_offset,
                        )
                except (ValueError, TypeError):
                    pass

            # Restore user mode override
            if last_state.state in (HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF):
                zone_state = self.coordinator.get_zone_state(self.zone_id)
                if zone_state:
                    mode_map = {
                        HVACMode.HEAT: ModelHvacMode.HEAT,
                        HVACMode.COOL: ModelHvacMode.COOL,
                        HVACMode.OFF: ModelHvacMode.OFF,
                    }
                    zone_state.user_mode_override = mode_map.get(HVACMode(last_state.state))
                    _LOGGER.debug(
                        "Zone %s: restored user_mode_override %s",
                        self.zone_id,
                        zone_state.user_mode_override,
                    )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available.
        
        During startup, we stay available if we have restored state,
        to prevent graphs from showing unavailable gaps.
        """
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state is None:
            return False
        # If we have a current temperature (either from sensors or restored),
        # consider the entity available even if coordinator hasn't updated yet
        if zone_state.current_temperature is not None:
            return zone_state.is_available
        return zone_state.is_available and self.coordinator.last_update_success

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state is None:
            return None
        return zone_state.current_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature (single setpoint mode only).

        For zones with only heat OR only cool, returns the single setpoint.
        For dual-setpoint zones, this returns None (use target_temperature_low/high).
        """
        # Only return single target if not in range mode
        if self._attr_supported_features == ClimateEntityFeature.TARGET_TEMPERATURE_RANGE:
            return None
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state is None:
            return None
        # For heat-only, return heat setpoint; for cool-only, return cool setpoint
        if self.zone_config.heat_stages and not self.zone_config.cool_stages:
            return zone_state.target_temperature
        elif self.zone_config.cool_stages and not self.zone_config.heat_stages:
            return zone_state.target_temperature_cool
        return zone_state.target_temperature

    @property
    def target_temperature_low(self) -> float | None:
        """Return the low target temperature (heat setpoint) for range mode."""
        if self._attr_supported_features != ClimateEntityFeature.TARGET_TEMPERATURE_RANGE:
            return None
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state is None:
            return None
        return zone_state.target_temperature

    @property
    def target_temperature_high(self) -> float | None:
        """Return the high target temperature (cool setpoint) for range mode."""
        if self._attr_supported_features != ClimateEntityFeature.TARGET_TEMPERATURE_RANGE:
            return None
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state is None:
            return None
        return zone_state.target_temperature_cool

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode.
        
        Returns the user's mode override if set, otherwise AUTO.
        """
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state is None:
            return HVACMode.OFF

        # If user has set a mode override, show that
        if zone_state.user_mode_override is not None:
            mode_map = {
                ModelHvacMode.HEAT: HVACMode.HEAT,
                ModelHvacMode.COOL: HVACMode.COOL,
                ModelHvacMode.OFF: HVACMode.OFF,
            }
            return mode_map.get(zone_state.user_mode_override, HVACMode.AUTO)
        
        # No override = AUTO (coordinator decides based on temp)
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action."""
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state is None:
            return HVACAction.OFF

        # Map internal action to HA HVACAction
        action_map = {
            ModelHvacAction.HEATING: HVACAction.HEATING,
            ModelHvacAction.COOLING: HVACAction.COOLING,
            ModelHvacAction.IDLE: HVACAction.IDLE,
            ModelHvacAction.OFF: HVACAction.OFF,
        }
        return action_map.get(zone_state.hvac_action, HVACAction.OFF)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        zone_state = self.coordinator.get_zone_state(self.zone_id)
        master_state = self.coordinator.get_master_state()

        attrs: dict[str, Any] = {
            ATTR_MASTER_MODE: master_state.mode.value if master_state else None,
        }

        if zone_state:
            attrs.update({
                ATTR_CURRENT_STAGE: zone_state.current_stage,
                ATTR_ACTIVE_DEVICES: zone_state.active_devices,
                ATTR_BLOCKED_DEVICES: zone_state.blocked_devices,
                ATTR_TIME_IN_STAGE: zone_state.time_in_current_stage(),
                ATTR_SENSOR_VALUES: zone_state.sensor_values,
                ATTR_SENSOR_SMOOTHED_VALUES: zone_state.sensor_smoothed_values,
                ATTR_SENSOR_STATUS: zone_state.sensor_status,
                ATTR_REGULATION_OFFSET: round(zone_state.regulation_offset, 2),
                ATTR_ACCUMULATED_ERROR: round(zone_state.accumulated_error, 2),
                ATTR_REGULATED_SETPOINT: round(zone_state.regulated_setpoint, 1) if zone_state.regulated_setpoint is not None else None,
            })

        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature(s).

        Handles both single setpoint (ATTR_TEMPERATURE) and range mode
        (ATTR_TARGET_TEMP_LOW / ATTR_TARGET_TEMP_HIGH).
        """
        # Range mode: handle low (heat) and high (cool) separately
        temp_low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        temp_high = kwargs.get(ATTR_TARGET_TEMP_HIGH)

        if temp_low is not None or temp_high is not None:
            # Range mode - set heat and/or cool setpoints
            if temp_low is not None:
                try:
                    temp_low = float(temp_low)
                    if TEMP_MIN_VALID <= temp_low <= TEMP_MAX_VALID:
                        _LOGGER.debug("Zone %s: setting heat setpoint to %s", self.zone_id, temp_low)
                        await self.coordinator.set_zone_target_temp(self.zone_id, temp_low)
                    else:
                        _LOGGER.error("Heat setpoint out of range: %s", temp_low)
                except (ValueError, TypeError):
                    _LOGGER.error("Invalid heat setpoint value: %s", temp_low)

            if temp_high is not None:
                try:
                    temp_high = float(temp_high)
                    if TEMP_MIN_VALID <= temp_high <= TEMP_MAX_VALID:
                        _LOGGER.debug("Zone %s: setting cool setpoint to %s", self.zone_id, temp_high)
                        await self.coordinator.set_zone_target_temp_cool(self.zone_id, temp_high)
                    else:
                        _LOGGER.error("Cool setpoint out of range: %s", temp_high)
                except (ValueError, TypeError):
                    _LOGGER.error("Invalid cool setpoint value: %s", temp_high)

            await self.coordinator.async_request_refresh()
            return

        # Single setpoint mode
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        try:
            temperature = float(temperature)
        except (ValueError, TypeError):
            _LOGGER.error("Invalid temperature value: %s", temperature)
            return

        if not TEMP_MIN_VALID <= temperature <= TEMP_MAX_VALID:
            _LOGGER.error("Temperature out of range: %s", temperature)
            return

        _LOGGER.debug("Zone %s: setting target temp to %s", self.zone_id, temperature)

        # For single-mode zones, set the appropriate setpoint
        if self.zone_config.cool_stages and not self.zone_config.heat_stages:
            # Cool-only zone
            await self.coordinator.set_zone_target_temp_cool(self.zone_id, temperature)
        else:
            # Heat-only or default
            await self.coordinator.set_zone_target_temp(self.zone_id, temperature)

        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode.

        Sets user mode override:
        - AUTO: No restriction, coordinator decides heat vs cool based on temp
        - HEAT: Only allow heating, block cooling
        - COOL: Only allow cooling, block heating  
        - OFF: Disable zone entirely
        """
        from .models import HvacMode as ModelHvacMode
        
        _LOGGER.info("Zone %s: setting hvac_mode to %s", self.zone_id, hvac_mode)

        zone_state = self.coordinator.get_zone_state(self.zone_id)
        if zone_state is None:
            _LOGGER.warning("Zone %s: state not found", self.zone_id)
            return

        # Map HA HVACMode to our override
        if hvac_mode == HVACMode.AUTO:
            zone_state.user_mode_override = None  # No restriction
        elif hvac_mode == HVACMode.HEAT:
            zone_state.user_mode_override = ModelHvacMode.HEAT
        elif hvac_mode == HVACMode.COOL:
            zone_state.user_mode_override = ModelHvacMode.COOL
        elif hvac_mode == HVACMode.OFF:
            zone_state.user_mode_override = ModelHvacMode.OFF
        else:
            _LOGGER.warning("Zone %s: unsupported hvac_mode %s", self.zone_id, hvac_mode)
            return

        _LOGGER.debug(
            "Zone %s: user_mode_override set to %s",
            self.zone_id,
            zone_state.user_mode_override,
        )

        # Trigger update to apply the new mode
        await self.coordinator.async_request_refresh()


async def async_setup_zone_entities(
    hass: HomeAssistant,
    coordinator: HybridClimateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up zone climate entities."""
    entities = []

    for zone_id, zone_config in coordinator.config.zones.items():
        entity = ZoneClimateEntity(coordinator, zone_config, entry)
        entities.append(entity)
        _LOGGER.debug("Created zone entity: %s", zone_config.name)

    async_add_entities(entities)
