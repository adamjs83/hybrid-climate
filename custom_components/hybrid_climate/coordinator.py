"""Purpose: Orchestrate sensor updates, zone demand, and physical dispatch.

Key dependencies: zone control, device manager, conflict resolver.
Used by: integration setup and climate entities.
"""
from __future__ import annotations

import logging
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .conflict_resolver import ConflictResolver
from .const import (
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    HVAC_MODE_OFF,
)
from . import setpoint_manager
from .control_restore import ControlRestore, post_cycle
from .device_manager import DeviceManager
from .external_sync import check_external_device_changes
from .device_arbitration import queue_mutex_releases, queue_retained_demand, reconcile_dispatch
from .hvac_action_tracking import stamp_hvac_action_transitions
from .manual_override import ManualOverrideTracker
from .occupancy import check_master_occupancy, check_zone_occupancy
from .pi_controller import PIController
from .startup_takeover import StartupTakeover
from .tou_manager import TouManager
from .sensor_manager import init_sensor_sample_buffers
from .outdoor_sensors import OutdoorReading, update_outdoor_reading
from .zone_control import (
    apply_opportunistic_heating,
    update_zone,
)
from .zone_helpers import update_master_summaries
from .models import (
    HybridClimateConfig,
    MasterMode,
    MasterModeConfig,
    MasterState,
    ZoneConfig,
    ZoneState,
)

_LOGGER = logging.getLogger(__name__)


class HybridClimateCoordinator(DataUpdateCoordinator):
    """Central coordinator for Hybrid Climate integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: HybridClimateConfig,
        entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )
        self.config = config
        self.entry = entry  # For reading persisted number values
        
        self.pi_controller = PIController()
        self.device_manager = DeviceManager(hass, config.devices)
        self.startup_takeover = StartupTakeover()
        self.control_restore = ControlRestore(self)
        self.manual_overrides = ManualOverrideTracker()
        self.conflict_resolver = ConflictResolver(
            config.conflicts,
            self.device_manager,
            config.zones,
        )
        self.tou_manager = TouManager(self)

        # State tracking
        self.master_state = MasterState()
        self.zone_states: dict[str, ZoneState] = {}
        self._zone_target_temps: dict[str, float] = {}  # Heat setpoints
        self._zone_target_temps_cool: dict[str, float] = {}  # Cool setpoints
        self._zone_occupancy: dict[str, bool | None] = {}
        self._sensor_fail_notified: set[str] = set()  # Zones with active sensor failure notifications
        self._sensor_restore_start_times: dict[str, datetime] = {}  # Grace period tracking

        # Initialize zone states
        for zone_id in config.zones:
            self.zone_states[zone_id] = ZoneState(zone_id=zone_id)

        # Initialize zone target temps from YAML for current mode
        # These are the "overlay" temps that drive device setpoints
        # Only recalculated on master mode change, otherwise user changes persist
        setpoint_manager.apply_mode_setpoints(self)
        self._zone_occupancy = {
            zone_id: setpoint_manager.get_zone_occupancy(self, zone)
            for zone_id, zone in config.zones.items()
        }

        # Last known good sensor values (for stale sensor handling)
        self._last_sensor_values: dict[str, tuple[float, datetime]] = {}
        self._last_outdoor_reading: tuple[float, datetime, str | None] | None = None
        self.outdoor_reading = OutdoorReading(None, None, [])
        self._outdoor_using_fallback = False

        # Sensor sample buffers for smoothing (moving average)
        # Key: sensor entity_id, Value: deque of float values
        # Note: Keyed by globally unique entity_id, so if the same sensor is used
        # by multiple zones with different smoothing_samples settings, the first
        # zone's config wins. This is acceptable since sharing sensors across zones
        # with different smoothing needs is rare. If this becomes an issue, key by
        # (zone_id, sensor_id) instead, or rebuild buffers on config reload.
        self._sensor_samples: dict[str, deque[float]] = {}
        init_sensor_sample_buffers(self.config, self._sensor_samples)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data and orchestrate climate control."""
        try:
            # 1. Update device states
            await self.device_manager.update_device_states()

            # Detect each physical edit before collecting this cycle's demand.
            await check_external_device_changes(self)
            previous_states = deepcopy(self.zone_states)
            self.device_manager.begin_cycle()

            # 4. Check master occupancy entity for auto home/away switching
            self._check_master_occupancy()
            self._check_zone_occupancy()

            # 5. Get outdoor temperature
            outdoor_temp = update_outdoor_reading(self)
            self.master_state.outdoor_temperature = outdoor_temp

            # 6. Update each zone
            for zone_id, zone_config in self.config.zones.items():
                await update_zone(self, zone_id, zone_config, outdoor_temp)

            # 7. Apply opportunistic heating (after normal zone updates)
            await apply_opportunistic_heating(self, outdoor_temp)

            # A failed partial command cannot leave external sync suppressed forever.
            # If no zone still owns or requests the device, return it to OFF.
            for device_id in self.device_manager.failed_commands.copy():
                if (not self.device_manager.has_pending_device(device_id)
                        and not any(device_id in state.active_devices for state in self.zone_states.values())):
                    device = self.device_manager.get_device(device_id)
                    if device and device.is_available:
                        await self.device_manager.set_device_mode(device, HVAC_MODE_OFF)

            # Mutex releases share the batch, avoiding an OFF/ON pair in one cycle.
            await queue_retained_demand(self)
            # queue() applies any pending rearm request itself (A1/A2) and is a
            # no-op before the first startup pass has armed.
            await self.startup_takeover.queue(self)
            await queue_mutex_releases(self)
            command_results = await self.device_manager.dispatch_cycle(
                self.config.conflicts.device_mutex
            )
            reconcile_dispatch(self, previous_states, command_results)

            # Agent API observability only (spec 0.13.0 §7.3); never read by control.
            # Stamped last, after reconcile_dispatch, so a reversed/failed command's
            # rollback of hvac_action is reflected before comparing against the
            # pre-cycle snapshot, and an opportunistic-heating transition is included.
            stamp_hvac_action_transitions(self.zone_states, previous_states)

            post_cycle(self, command_results)

            # 9. Update master state summaries
            update_master_summaries(self.master_state, self.zone_states, self.conflict_resolver, self.master_state.outdoor_temperature, self.config)

            return {
                "master_state": self.master_state,
                "zone_states": self.zone_states,
            }

        except Exception as e:
            self.device_manager.cancel_cycle()
            _LOGGER.error("Error updating hybrid climate: %s", e, exc_info=True)
            raise UpdateFailed(f"Update failed: {e}") from e

    def _check_master_occupancy(self) -> None:
        """Delegate master home/away auto-switching to occupancy.py (A12)."""
        check_master_occupancy(self)

    def _check_zone_occupancy(self) -> None:
        """Delegate per-zone occupancy setpoint reapplication to occupancy.py (A12)."""
        check_zone_occupancy(self)

    def _calculate_pi_offset(
        self,
        zone_config: ZoneConfig,
        zone_state: ZoneState,
        outdoor_temp: float | None,
        is_actively_heating: bool = True,
    ) -> float:
        """Calculate PI controller offset for regulated devices.

        Delegates to PIController.calculate_offset with PI params fetched
        from number entities.
        """
        pi_params = self.get_pi_params_from_numbers(zone_config.zone_id)
        return self.pi_controller.calculate_offset(
            zone_config, zone_state, outdoor_temp,
            is_actively_heating=is_actively_heating,
            pi_params=pi_params,
        )

    # Public methods for external control — delegated to setpoint_manager

    def get_current_mode_config(self) -> MasterModeConfig:
        """Get the configuration for the current master mode."""
        return setpoint_manager.get_current_mode_config(self)

    def set_master_mode(self, mode: MasterMode) -> None:
        """Set the master operating mode."""
        setpoint_manager.set_master_mode(self, mode)

    async def recompute_setpoints_from_numbers(
        self, zone_id: str | None = None, override: tuple[str, float] | None = None
    ) -> None:
        """Recompute zone setpoints from number entities when values change."""
        await setpoint_manager.recompute_setpoints_from_numbers(self, zone_id, override)

    async def set_zone_target_temp(self, zone_id: str, temperature: float) -> None:
        """Set target temperature for a zone (manual override)."""
        await setpoint_manager.set_zone_target_temp(self, zone_id, temperature)

    async def set_zone_target_temp_cool(self, zone_id: str, temperature: float) -> None:
        """Set cool target temperature for a zone (manual override)."""
        await setpoint_manager.set_zone_target_temp_cool(self, zone_id, temperature)

    def get_pi_params_from_numbers(self, zone_id: str) -> dict[str, float]:
        """Get PI parameters from number entities for a zone (delegates to PIController)."""
        return self.pi_controller.get_pi_params_from_numbers(
            self.hass, self.config, self.entry, zone_id
        )

    def get_zone_state(self, zone_id: str) -> ZoneState | None:
        """Get state for a specific zone."""
        return self.zone_states.get(zone_id)

    def get_master_state(self) -> MasterState:
        """Get master state."""
        return self.master_state
