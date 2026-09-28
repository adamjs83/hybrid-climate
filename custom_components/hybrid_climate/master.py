"""Master climate entity for Hybrid Climate integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ATTR_ACTIVE_CONFLICTS,
    ATTR_MASTER_MODE,
    ATTR_OUTDOOR_TEMPERATURE,
    ATTR_VERSION,
    ATTR_ZONES_COOLING,
    ATTR_ZONES_HEATING,
    ATTR_ZONES_IDLE,
    DOMAIN,
    MODE_AWAY,
    MODE_BOOST,
    MODE_HOME,
    MODE_SLEEP,
    MODE_VACATION,
    VERSION,
)
from .coordinator import HybridClimateCoordinator
from .models import MasterMode

_LOGGER = logging.getLogger(__name__)

# Map master modes to preset names
PRESET_MODE_MAP = {
    MODE_HOME: "Home",
    MODE_AWAY: "Away",
    MODE_SLEEP: "Sleep",
    MODE_VACATION: "Vacation",
    MODE_BOOST: "Boost",
}

PRESET_TO_MASTER_MODE = {
    "Home": MasterMode.HOME,
    "Away": MasterMode.AWAY,
    "Sleep": MasterMode.SLEEP,
    "Vacation": MasterMode.VACATION,
    "Boost": MasterMode.BOOST,
}


class MasterClimateEntity(ClimateEntity, RestoreEntity):
    """Master climate entity for whole-home HVAC orchestration."""

    _attr_has_entity_name = True
    _attr_supported_features = ClimateEntityFeature.PRESET_MODE
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.OFF]
    _attr_preset_modes = ["Home", "Away", "Sleep", "Vacation", "Boost"]

    def __init__(
        self,
        coordinator: HybridClimateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the master climate entity."""
        self.coordinator = coordinator
        self._entry = entry
        self._hass = coordinator.hass

        # Entity attributes
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_master"
        self._attr_name = coordinator.config.master.name
        self._attr_precision = 0.1  # Show temperature with 1 decimal place

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the master entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_master")},
            name=f"Hybrid Climate - {self.coordinator.config.master.name}",
            manufacturer="Hybrid Climate",
            model="Master Controller",
        )

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return self._hass.config.units.temperature_unit

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        # Listen to coordinator updates
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

        # Restore previous master mode
        if last_state := await self.async_get_last_state():
            if last_state.state == HVACMode.OFF:
                self.coordinator.master_state.mode = MasterMode.OFF
                # Also restore last_active_mode from preset if available
                if last_state.attributes.get("preset_mode"):
                    preset = last_state.attributes["preset_mode"]
                    if preset in PRESET_TO_MASTER_MODE:
                        self.coordinator.master_state.last_active_mode = PRESET_TO_MASTER_MODE[preset]
                _LOGGER.debug("Master: restored mode OFF (last_active: %s)", 
                             self.coordinator.master_state.last_active_mode.value)
            elif last_state.attributes.get("preset_mode"):
                preset = last_state.attributes["preset_mode"]
                if preset in PRESET_TO_MASTER_MODE:
                    restored_mode = PRESET_TO_MASTER_MODE[preset]
                    self.coordinator.master_state.mode = restored_mode
                    self.coordinator.master_state.last_active_mode = restored_mode
                    _LOGGER.debug("Master: restored preset mode %s", preset)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        master_state = self.coordinator.get_master_state()
        if master_state.mode == MasterMode.OFF:
            return HVACMode.OFF
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action (aggregate of all zones)."""
        master_state = self.coordinator.get_master_state()

        if master_state.mode == MasterMode.OFF:
            return HVACAction.OFF

        # Determine aggregate action
        if master_state.zones_heating and master_state.zones_cooling:
            # Both heating and cooling happening (different zones)
            return HVACAction.HEATING  # Could show a custom state
        elif master_state.zones_heating:
            return HVACAction.HEATING
        elif master_state.zones_cooling:
            return HVACAction.COOLING
        else:
            return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        master_state = self.coordinator.get_master_state()
        return PRESET_MODE_MAP.get(master_state.mode.value, "Home")

    @property
    def current_temperature(self) -> float | None:
        """Return the outdoor temperature as the 'current' for master."""
        master_state = self.coordinator.get_master_state()
        return master_state.outdoor_temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        master_state = self.coordinator.get_master_state()

        return {
            ATTR_VERSION: VERSION,
            ATTR_MASTER_MODE: master_state.mode.value,
            ATTR_OUTDOOR_TEMPERATURE: master_state.outdoor_temperature,
            ATTR_ZONES_HEATING: master_state.zones_heating,
            ATTR_ZONES_COOLING: master_state.zones_cooling,
            ATTR_ZONES_IDLE: master_state.zones_idle,
            ATTR_ACTIVE_CONFLICTS: master_state.active_conflicts,
            "zone_count": len(self.coordinator.config.zones),
            "device_count": len(self.coordinator.config.devices),
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        _LOGGER.debug("Master: set_hvac_mode called with %s", hvac_mode)

        if hvac_mode == HVACMode.OFF:
            self.coordinator.set_master_mode(MasterMode.OFF)
        else:
            # AUTO mode - restore to last active mode (not always HOME)
            last_mode = self.coordinator.master_state.last_active_mode
            _LOGGER.debug("Master: restoring to last active mode %s", last_mode.value)
            self.coordinator.set_master_mode(last_mode)

        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        _LOGGER.debug("Master: set_preset_mode called with %s", preset_mode)

        master_mode = PRESET_TO_MASTER_MODE.get(preset_mode)
        if master_mode is None:
            _LOGGER.warning("Unknown preset mode: %s", preset_mode)
            return

        self.coordinator.set_master_mode(master_mode)
        await self.coordinator.async_request_refresh()


async def async_setup_master_entity(
    hass: HomeAssistant,
    coordinator: HybridClimateCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up master climate entity."""
    entity = MasterClimateEntity(coordinator, entry)
    async_add_entities([entity])
    _LOGGER.debug("Created master entity: %s", coordinator.config.master.name)
