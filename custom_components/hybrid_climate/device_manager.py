"""Purpose: Track physical climate devices and dispatch resolved commands.

Key dependencies: Home Assistant services and Device models.
Used by: coordinator and zone control during each update cycle.
"""
from __future__ import annotations

import logging

from homeassistant.const import ATTR_TEMPERATURE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    COMMAND_TIMEOUT_SECONDS,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    IDLE_ACTION_OFF,
    IDLE_ACTION_SETBACK,
    SERVICE_CLIMATE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from .models import Device, DeviceMutexRule
from .device_arbitration import DeviceRequest, dispatch_requests, resolve_requests
from .compressor_protection import CompressorProtection

_LOGGER = logging.getLogger(__name__)


class DeviceManager:
    """Manages the pool of climate devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        devices: dict[str, Device],
    ) -> None:
        """Initialize the device manager."""
        self.hass = hass
        self.devices = devices
        self.compressor_protection = CompressorProtection(devices)
        self._pending_commands: dict[str, list[DeviceRequest]] = {}
        self.failed_commands: set[str] = set()
        self.accepted_zone_requests: dict[str, set[str]] = {}
        self._collecting = False
        self._forced_off_devices: set[str] = set()
        # Secondary index: entity_id → Device for O(1) fallback lookups
        self._entity_id_index: dict[str, Device] = {
            dev.entity_id: dev for dev in devices.values() if dev.entity_id
        }

    def get_device(self, device_id: str) -> Device | None:
        """Get a device by ID or entity_id."""
        device = self.devices.get(device_id)
        if device is not None:
            return device
        return self._entity_id_index.get(device_id)

    def get_devices_for_zone_stage(
        self,
        device_ids: list[str],
        mode: str,
        blocked_devices: list[str] | None = None,
    ) -> list[Device]:
        """Get available devices for a zone's stage.

        Args:
            device_ids: List of device IDs configured for this stage
            mode: 'heat' or 'cool'
            blocked_devices: Devices blocked due to conflicts

        Returns:
            List of devices that are available and capable
        """
        blocked = blocked_devices or []
        available = []

        for device_id in device_ids:
            if device_id in blocked:
                _LOGGER.debug(
                    "Device %s blocked due to conflict",
                    device_id,
                )
                continue

            device = self.devices.get(device_id)
            if device is None:
                _LOGGER.warning("Device %s not found in pool", device_id)
                continue

            if not device.is_available:
                _LOGGER.debug("Device %s unavailable", device_id)
                continue

            # Check capability
            if mode == HVAC_MODE_HEAT and not device.can_heat():
                _LOGGER.debug("Device %s cannot heat", device_id)
                continue
            if mode == HVAC_MODE_COOL and not device.can_cool():
                _LOGGER.debug("Device %s cannot cool", device_id)
                continue

            available.append(device)

        return available

    async def update_device_states(self) -> None:
        """Update device states from Home Assistant."""
        for device_id, device in self.devices.items():
            state = self.hass.states.get(device.entity_id)

            if state is None:
                _LOGGER.warning(
                    "Device %s entity %s not found",
                    device_id,
                    device.entity_id,
                )
                device.is_available = False
                continue

            if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                device.is_available = False
                continue

            device.is_available = True
            device.current_mode = state.state
            device.current_target_temp = state.attributes.get(ATTR_TEMPERATURE)
        self.compressor_protection.observe()

    async def set_device_mode(
        self,
        device: Device,
        mode: str,
        target_temp: float | None = None,
        *,
        zone_id: str | None = None,
        force_off: bool = False,
    ) -> bool:
        """Set a device's HVAC mode and optionally target temperature.

        Args:
            device: The device to control
            mode: 'heat', 'cool', or 'off'
            target_temp: Optional target temperature
            zone_id: Requesting zone when collecting a coordinator cycle

        Returns:
            True if command was sent successfully
        """
        if self._collecting:
            self._pending_commands.setdefault(device.device_id, []).append((mode, target_temp, zone_id))
            if mode == HVAC_MODE_OFF and force_off:
                self._forced_off_devices.add(device.device_id)
            return True
        return await self._dispatch_device_mode(device, mode, target_temp, force_off=force_off)

    def begin_cycle(self) -> None:
        """Collect zone requests until every zone has been evaluated."""
        self._pending_commands.clear()
        self.accepted_zone_requests.clear()
        self._forced_off_devices.clear()
        self._collecting = True

    def has_pending_mode(self, device_id: str, mode: str) -> bool:
        """Report whether a queued request would activate a trigger device."""
        pending = self._pending_commands.get(device_id)
        return bool(pending and resolve_requests(pending)[0] == mode)

    def has_pending_zone_request(self, device_id: str, zone_id: str) -> bool:
        """Return whether a zone already supplied this device's demand."""
        return any(
            owner == zone_id for _, _, owner in self._pending_commands.get(device_id, [])
        )

    def has_pending_device(self, device_id: str) -> bool:
        """Return whether any zone or release requested this device this cycle."""
        return device_id in self._pending_commands

    def block_pending_mode(
        self, device_id: str, mode: str, zone_id: str | None = None,
    ) -> None:
        """Remove mutex-blocked demand before physical dispatch."""
        pending = self._pending_commands.get(device_id)
        if pending is None:
            return
        self._pending_commands[device_id] = [
            request for request in pending
            if request[0] != mode or (zone_id is not None and request[2] != zone_id)
        ]

    def cancel_cycle(self) -> None:
        """Discard unfinished demand after an interrupted update."""
        self._collecting = False
        self._pending_commands.clear()
        self._forced_off_devices.clear()

    async def dispatch_cycle(self, rules: list[DeviceMutexRule] | None = None) -> dict[str, bool]:
        """Resolve one command per device, releasing mutex conflicts before starts."""
        self._collecting = False
        return await dispatch_requests(self, rules or [])

    async def _dispatch_device_mode(
        self, device: Device, mode: str, target_temp: float | None,
        *, force_off: bool = False,
    ) -> bool:
        """Send only changed fields, recording desired state after success."""
        if not self.compressor_protection.allow(device, mode, force_off=force_off):
            _LOGGER.debug("Device %s blocked: %s", device.device_id,
                          self.compressor_protection.blocked_reasons[device.device_id])
            return False
        try:
            if target_temp is not None:
                state = self.hass.states.get(device.entity_id)
                if state:
                    minimum = state.attributes.get("min_temp")
                    maximum = state.attributes.get("max_temp")
                    if minimum is not None:
                        target_temp = max(target_temp, minimum)
                    if maximum is not None:
                        target_temp = min(target_temp, maximum)
            if (device.device_id not in self.failed_commands
                    and device.is_commanding() and device.desired_mode == mode
                    and device.desired_temp == target_temp
                    and device.command_sent_at is not None
                    and (dt_util.utcnow() - device.command_sent_at).total_seconds()
                    < COMMAND_TIMEOUT_SECONDS):
                return True
            mode_changed = device.current_mode != mode
            temp_changed = target_temp is not None and (
                mode_changed or device.current_target_temp != target_temp
            )
            if not mode_changed and not temp_changed:
                device.desired_mode = mode
                device.desired_temp = target_temp
                device.command_acknowledged()
                self.failed_commands.discard(device.device_id)
                self.compressor_protection.command_succeeded(device, mode)
                return True
            if mode_changed:
                await self.hass.services.async_call(
                    SERVICE_CLIMATE, SERVICE_SET_HVAC_MODE,
                    {"entity_id": device.entity_id, "hvac_mode": mode}, blocking=True,
                )
            if temp_changed:
                await self.hass.services.async_call(
                    SERVICE_CLIMATE, SERVICE_SET_TEMPERATURE,
                    {"entity_id": device.entity_id, ATTR_TEMPERATURE: target_temp},
                    blocking=True,
                )
            device.current_mode = mode
            if target_temp is not None:
                device.current_target_temp = target_temp
            device.start_command(mode, target_temp)
            self.failed_commands.discard(device.device_id)
            self.compressor_protection.command_succeeded(device, mode)
            return True
        except Exception:
            self.failed_commands.add(device.device_id)
            _LOGGER.exception("Failed to command device %s to %s at %s", device.device_id, mode, target_temp)
            return False

    async def turn_off_device(self, device: Device, *, force_off: bool = False) -> bool:
        """Turn off a device."""
        return await self.set_device_mode(device, HVAC_MODE_OFF, force_off=force_off)

    async def set_device_idle(
        self,
        device: Device,
        zone_target_temp: float,
        was_heating: bool,
        *, force_off: bool = False,
    ) -> bool:
        """Set a device to its configured idle state.

        Args:
            device: The device to set idle
            zone_target_temp: The zone's target temperature (for calculating setback)
            was_heating: True if device was heating, False if cooling

        Returns:
            True if command was sent successfully
        """
        idle_config = device.idle_config

        if idle_config.action == IDLE_ACTION_OFF:
            _LOGGER.debug(
                "Device %s idle action: off",
                device.device_id,
            )
            return await self.turn_off_device(device, force_off=force_off)

        elif idle_config.action == IDLE_ACTION_SETBACK:
            # Calculate setback temperature
            if was_heating:
                # For heating: set to target - setback (maintain minimum)
                setback_temp = zone_target_temp - idle_config.setback
                mode = HVAC_MODE_HEAT
            else:
                # For cooling: set to target + setback (or could turn off)
                setback_temp = zone_target_temp + idle_config.setback
                mode = HVAC_MODE_COOL

            _LOGGER.debug(
                "Device %s idle action: setback to %s in %s mode",
                device.device_id,
                setback_temp,
                mode,
            )
            # Note: set_device_mode updates last_commanded_setpoint, which prevents
            # the external change detection from treating this setback as an external
            # change and propagating it back to the zone target
            return await self.set_device_mode(device, mode, setback_temp)

        # Default to off
        return await self.turn_off_device(device, force_off=force_off)
