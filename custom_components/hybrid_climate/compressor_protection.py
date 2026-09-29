"""Protect a shared compressor using observed HVAC mode transitions.

The climate entity's mode is a proxy for compressor operation; integrations
without a separate running signal cannot distinguish thermostat cycling.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.util import dt as dt_util

from .const import HVAC_MODE_COOL, HVAC_MODE_HEAT, HVAC_MODE_OFF
from .models import Device


@dataclass
class CompressorState:
    active_devices: set[str]
    changed_at: datetime


class CompressorProtection:
    """Gate only transitions that stop or restart an entire group.

    On startup, the last transition is unknown, so the first observed state
    starts a full interval. This may delay a start, but avoids a rapid restart.
    """

    def __init__(self, devices: dict[str, Device]) -> None:
        self.devices = devices
        self.groups: dict[str, set[str]] = {}
        self.states: dict[str, CompressorState] = {}
        self.blocked_reasons: dict[str, str] = {}
        for device_id, device in devices.items():
            if device.compressor_group:
                self.groups.setdefault(device.compressor_group, set()).add(device_id)

    def observe(self) -> None:
        """Refresh group state after all HA entity states have been read."""
        now = dt_util.utcnow()
        for group_id, members in self.groups.items():
            active = {
                device_id for device_id in members
                if self.devices[device_id].current_mode in (HVAC_MODE_HEAT, HVAC_MODE_COOL)
            }
            previous = self.states.get(group_id)
            if previous is None:
                self.states[group_id] = CompressorState(active, now)
            elif bool(previous.active_devices) != bool(active):
                self.states[group_id] = CompressorState(active, now)
            else:
                previous.active_devices = active

    def allow(self, device: Device, mode: str, *, force_off: bool = False) -> bool:
        """Return whether a command respects group run and off intervals."""
        group_id = device.compressor_group
        if not group_id:
            return True
        state = self.states.get(group_id)
        if state is None:
            self.observe()
            state = self.states[group_id]
        elapsed = (dt_util.utcnow() - state.changed_at).total_seconds()
        active = device.device_id in state.active_devices
        min_run = max(
            self.devices[member_id].min_compressor_runtime
            for member_id in self.groups[group_id]
        )
        min_off = max(
            self.devices[member_id].min_compressor_off_time
            for member_id in self.groups[group_id]
        )
        if mode == HVAC_MODE_OFF and active and len(state.active_devices) == 1:
            if not force_off and elapsed < min_run:
                self.blocked_reasons[device.device_id] = "minimum compressor runtime"
                return False
        elif mode in (HVAC_MODE_HEAT, HVAC_MODE_COOL) and not active and not state.active_devices:
            if elapsed < min_off:
                self.blocked_reasons[device.device_id] = "minimum compressor off time"
                return False
        self.blocked_reasons.pop(device.device_id, None)
        return True

    def command_succeeded(self, device: Device, mode: str) -> None:
        """Record a successful transition before dispatching another device."""
        group_id = device.compressor_group
        if not group_id:
            return
        state = self.states[group_id]
        was_active = bool(state.active_devices)
        if mode == HVAC_MODE_OFF:
            state.active_devices.discard(device.device_id)
        elif mode in (HVAC_MODE_HEAT, HVAC_MODE_COOL):
            state.active_devices.add(device.device_id)
        if was_active != bool(state.active_devices):
            state.changed_at = dt_util.utcnow()
