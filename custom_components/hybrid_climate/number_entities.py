"""Number entity implementation for tunable parameters.

Handles value persistence, coordinator updates, and active setpoint detection.

Key dependencies: number_definitions.py, coordinator.py, const.py
Used by: number.py (async_setup_entry instantiates this class)
"""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_UI_CONFIG,
    DEFAULT_BALANCE_POINT,
    DEFAULT_AWAY_COOL_RAISE,
    DEFAULT_COOL_SETPOINT,
    DEFAULT_HEAT_COOL_DEADBAND,
    DEFAULT_K_EXT,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_OFFSET_MAX,
    DOMAIN,
)
from .coordinator import HybridClimateCoordinator
from .number_definitions import HybridClimateNumberEntityDescription

_LOGGER = logging.getLogger(__name__)

# Storage key for number values in ui_config
CONF_NUMBER_VALUES = "number_values"


def get_stored_number_values(entry: ConfigEntry) -> dict[str, dict[str, float]]:
    """Get stored number values from config entry options.

    Returns dict of {zone_id: {param_key: value}}
    """
    ui_config = entry.options.get(CONF_UI_CONFIG, {})
    return ui_config.get(CONF_NUMBER_VALUES, {})


class HybridClimateNumberEntity(NumberEntity):
    """Number entity for Hybrid Climate tunable parameters.

    - Loads initial value from config_entry.options (persisted) or zone config (default)
    - On change, persists to config_entry.options AND directly updates coordinator
    """

    entity_description: HybridClimateNumberEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: HybridClimateCoordinator,
        zone_id: str,
        zone_name: str,
        description: HybridClimateNumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.zone_id = zone_id
        self.zone_name = zone_name
        self.entity_description = description

        # Unique ID for entity registry
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_{description.key}"

        # Load initial value: first check persisted options, then fall back to config
        stored_values = get_stored_number_values(entry)
        zone_values = stored_values.get(zone_id, {})

        if description.key in zone_values:
            self._attr_native_value = zone_values[description.key]
            _LOGGER.debug(
                "Loaded %s_%s = %.1f from stored options",
                zone_id, description.key, self._attr_native_value
            )
        else:
            self._attr_native_value = self._get_zone_config_value()
            _LOGGER.debug(
                "Loaded %s_%s = %.1f from zone config",
                zone_id, description.key, self._attr_native_value
            )

    def _get_zone_config_value(self) -> float:
        """Get the initial value from zone config (built from UI config)."""
        zone_config = self.coordinator.config.zones.get(self.zone_id)
        if not zone_config:
            return self._get_default_value()

        desc = self.entity_description

        if desc.param_type == "setpoint":
            setpoints = zone_config.setpoints
            mode = desc.setpoint_mode

            if desc.is_cooling:
                default_cool = max(DEFAULT_COOL_SETPOINT,
                                   setpoints.default + DEFAULT_HEAT_COOL_DEADBAND)
                if mode in ("away", "unoccupied", "vacation"):
                    named_heat = getattr(setpoints, mode, None)
                    heat_delta = abs(named_heat - setpoints.default) if named_heat is not None else 0
                    return default_cool + max(DEFAULT_AWAY_COOL_RAISE, heat_delta)
                return default_cool
            else:
                # Heating setpoints
                value = getattr(setpoints, mode, None) if mode else None
                if value is not None:
                    return value
                return setpoints.default

        elif desc.param_type == "pi":
            if zone_config.regulation:
                value = getattr(zone_config.regulation, desc.pi_param, None)
                if value is not None:
                    return value

        return self._get_default_value()

    def _get_default_value(self) -> float:
        """Get default value for this parameter."""
        desc = self.entity_description

        if desc.param_type == "pi":
            defaults = {
                "kp": DEFAULT_KP,
                "ki": DEFAULT_KI,
                "k_ext": DEFAULT_K_EXT,
                "offset_max": DEFAULT_OFFSET_MAX,
                "balance_point": DEFAULT_BALANCE_POINT,
            }
            return defaults.get(desc.pi_param, 1.0)

        # Setpoint defaults
        if desc.is_cooling:
            return DEFAULT_COOL_SETPOINT
        return DEFAULT_COOL_SETPOINT - DEFAULT_HEAT_COOL_DEADBAND

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group entities under the zone."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_{self.zone_id}")},
            name=f"Hybrid Climate - {self.zone_name}",
            manufacturer="Hybrid Climate",
            model="Zone",
        )

    async def async_added_to_hass(self) -> None:
        """Push current value to coordinator when entity is registered.

        At startup, mode application runs before number entities exist in the
        registry. Recompute once their values are available.
        """
        await super().async_added_to_hass()
        if self._attr_native_value is not None:
            await self._update_coordinator(self._attr_native_value)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.zone_name} {self.entity_description.name}"

    async def async_set_native_value(self, value: float) -> None:
        """Set the value, persist it, and update coordinator."""
        old_value = self._attr_native_value
        self._attr_native_value = value

        _LOGGER.info(
            "Number %s_%s changed: %.1f -> %.1f",
            self.zone_id, self.entity_description.key, old_value or 0, value
        )

        # 1. Persist to config_entry.options so it survives restarts
        await self._persist_value(value)

        # 2. Publish before refreshing: occupancy checks also resolve HA numbers.
        self.async_write_ha_state()

        # 3. Recompute dependent operating targets and refresh device demand.
        await self._update_coordinator(value)

    async def _persist_value(self, value: float) -> None:
        """Persist the value to config_entry.options."""
        try:
            # Get the CURRENT config entry (not the stale reference from init)
            entry = self.hass.config_entries.async_get_entry(self.entry.entry_id)
            if not entry:
                _LOGGER.error("Config entry not found for %s", self.entry.entry_id)
                return

            # Get current options from the live entry
            new_options = dict(entry.options)
            ui_config = dict(new_options.get(CONF_UI_CONFIG, {}))
            number_values = dict(ui_config.get(CONF_NUMBER_VALUES, {}))
            zone_values = dict(number_values.get(self.zone_id, {}))

            # Update the value
            zone_values[self.entity_description.key] = value
            number_values[self.zone_id] = zone_values
            ui_config[CONF_NUMBER_VALUES] = number_values
            new_options[CONF_UI_CONFIG] = ui_config

            # Save to config entry
            self.hass.config_entries.async_update_entry(entry, options=new_options)
            _LOGGER.info("Persisted %s_%s = %.1f to options (options now: %s)",
                         self.zone_id, self.entity_description.key, value,
                         list(entry.options.keys()))
        except Exception as e:
            _LOGGER.error("Failed to persist %s_%s = %.1f: %s",
                         self.zone_id, self.entity_description.key, value, e)

    async def _update_coordinator(self, value: float) -> None:
        """Directly update coordinator with the new value."""
        desc = self.entity_description

        if desc.param_type == "setpoint":
            await self.coordinator.recompute_setpoints_from_numbers(
                self.zone_id, (desc.key, value)
            )
            await self.coordinator.async_request_refresh()

        elif desc.param_type == "pi":
            # PI params are read dynamically, just refresh
            await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.zone_id in self.coordinator.config.zones
