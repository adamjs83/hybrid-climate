"""Purpose: Resolve outdoor and physical-device mutex restrictions.

Key dependencies: device manager, conflict configuration, zone state.
Used by: coordinator and zone control when selecting equipment.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .const import HVAC_MODE_COOL, HVAC_MODE_HEAT, OUTDOOR_LOCKOUT_HYSTERESIS
from .models import ConflictConfig, DeviceMutexRule, ZoneConfig, ZoneState

if TYPE_CHECKING:
    from .device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)


@dataclass
class ConflictResult:
    """Result of conflict resolution for a zone."""

    zone_id: str
    can_heat: bool = True
    can_cool: bool = True
    blocked_devices_heat: list[str] = field(default_factory=list)
    blocked_devices_cool: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def get_blocked_devices(self, mode: str) -> list[str]:
        """Get blocked devices for a specific mode."""
        if mode == HVAC_MODE_HEAT:
            return self.blocked_devices_heat
        elif mode == HVAC_MODE_COOL:
            return self.blocked_devices_cool
        return []


class ConflictResolver:
    """Resolves conflicts between zones and devices.

    Physical trigger mode is shared by staging and post-command enforcement.
    """

    def __init__(
        self,
        config: ConflictConfig,
        device_manager: DeviceManager,
    ) -> None:
        """Initialize the conflict resolver."""
        self.config = config
        self.device_manager = device_manager
        self._active_conflicts: list[str] = []
        self._outdoor_permissions: dict[str, tuple[bool, bool]] = {}
        self._warned_gaps: set[str] = set()

    def resolve_for_zone(
        self,
        zone_id: str,
        outdoor_temp: float | None,
        target_temp: float | None,
        zone_states: dict[str, ZoneState],
        zone_config: ZoneConfig | None = None,
    ) -> ConflictResult:
        """Resolve conflicts for a specific zone.

        Args:
            zone_id: The zone to resolve for
            outdoor_temp: Current outdoor temperature
            target_temp: Zone's target temperature
            zone_states: Current state of all zones
            zone_config: Zone configuration (for per-zone outdoor reset override)

        Returns:
            ConflictResult with blocked devices and reasons
        """
        result = ConflictResult(zone_id=zone_id)

        # Check outdoor reset (with zone-specific override support)
        self._check_outdoor_reset(result, outdoor_temp, target_temp, zone_config)

        # Check device mutex rules
        self._check_device_mutex(result, zone_id, zone_states)

        return result

    def _check_outdoor_reset(
        self,
        result: ConflictResult,
        outdoor_temp: float | None,
        target_temp: float | None,
        zone_config: ZoneConfig | None = None,
    ) -> None:
        """Check outdoor reset rules with zone-specific override support.
        
        Zone overrides work as follows:
        - If zone has outdoor_reset.heat_override_set=True:
          - Use zone's never_heat_above (None = disabled, float = zone limit)
        - Otherwise use global never_heat_above
        - Same logic for cooling
        """
        global_reset = self.config.outdoor_reset
        zone_reset = zone_config.settings.outdoor_reset if zone_config and zone_config.settings else None

        # Determine effective never_heat_above
        if zone_reset and zone_reset.heat_override_set:
            # Zone explicitly overrides (None = disabled, float = zone limit)
            never_heat_above = zone_reset.never_heat_above
            heat_source = "zone"
        else:
            never_heat_above = global_reset.never_heat_above
            heat_source = "global"

        # Determine effective never_cool_below
        if zone_reset and zone_reset.cool_override_set:
            # Zone explicitly overrides (None = disabled, float = zone limit)
            never_cool_below = zone_reset.never_cool_below
            cool_source = "zone"
        else:
            never_cool_below = global_reset.never_cool_below
            cool_source = "global"

        if (never_heat_above is not None and never_cool_below is not None
                and never_heat_above < never_cool_below
                and result.zone_id not in self._warned_gaps):
            _LOGGER.warning(
                "Zone %s: outdoor reset leaves a no-heat/no-cool gap from %s to %s",
                result.zone_id, never_heat_above, never_cool_below,
            )
            self._warned_gaps.add(result.zone_id)

        previous_heat, previous_cool = self._outdoor_permissions.get(result.zone_id, (True, True))
        if outdoor_temp is None:
            # No verified outdoor reading: preserve the last known permission.
            result.can_heat, result.can_cool = self._outdoor_permissions.get(
                result.zone_id, (never_heat_above is None, never_cool_below is None)
            )
            return

        _LOGGER.debug(
            "Outdoor reset check for %s: outdoor_temp=%s, never_heat_above=%s (%s), never_cool_below=%s (%s)",
            result.zone_id,
            outdoor_temp,
            never_heat_above,
            heat_source,
            never_cool_below,
            cool_source,
        )

        # Never heat above threshold
        if never_heat_above is not None:
            heat_limit = never_heat_above - (OUTDOOR_LOCKOUT_HYSTERESIS if not previous_heat else 0)
            if outdoor_temp > heat_limit:
                result.can_heat = False
                result.reasons.append(
                    f"Outdoor reset ({heat_source}): outdoor temp {outdoor_temp}° > "
                    f"heating release limit {heat_limit}°"
                )
                _LOGGER.debug(
                    "Zone %s: heating blocked by %s outdoor reset (outdoor: %s > %s)",
                    result.zone_id,
                    heat_source,
                    outdoor_temp,
                    never_heat_above,
                )

        # Never cool below threshold
        if never_cool_below is not None:
            cool_limit = never_cool_below + (OUTDOOR_LOCKOUT_HYSTERESIS if not previous_cool else 0)
            if outdoor_temp < cool_limit:
                result.can_cool = False
                result.reasons.append(
                    f"Outdoor reset ({cool_source}): outdoor temp {outdoor_temp}° < "
                    f"cooling release limit {cool_limit}°"
                )
                _LOGGER.debug(
                    "Zone %s: cooling blocked by %s outdoor reset (outdoor: %s < %s)",
                    result.zone_id,
                    cool_source,
                    outdoor_temp,
                    never_cool_below,
                )

        self._outdoor_permissions[result.zone_id] = (result.can_heat, result.can_cool)

    def _check_device_mutex(
        self,
        result: ConflictResult,
        zone_id: str,
        zone_states: dict[str, ZoneState],
    ) -> None:
        """Check device mutex rules."""
        for rule in self.config.device_mutex:
            self._evaluate_mutex_rule(result, zone_id, rule, zone_states)

    def mutex_rule_active(self, rule: DeviceMutexRule) -> bool:
        """Return whether the priority device physically runs in the trigger mode."""
        device = self.device_manager.get_device(rule.device_id)
        return bool(device and device.is_available and device.current_mode == rule.mode)

    def _evaluate_mutex_rule(
        self,
        result: ConflictResult,
        zone_id: str,
        rule: DeviceMutexRule,
        zone_states: dict[str, ZoneState],
    ) -> None:
        """Evaluate a single mutex rule against the current zone."""
        if not self.mutex_rule_active(rule):
            return

        # Rule is triggered - apply blocks
        # Block the triggering device itself for the specified zones
        if zone_id in rule.block_heat:
            if rule.device_id not in result.blocked_devices_heat:
                result.blocked_devices_heat.append(rule.device_id)
                result.reasons.append(
                    f"Device mutex: {rule.device_id} blocked for heat "
                    f"(used by {rule.for_zone} for {rule.mode})"
                )
                _LOGGER.debug(
                    "Zone %s: device %s blocked for heat due to mutex "
                    "(used by %s for %s)",
                    zone_id,
                    rule.device_id,
                    rule.for_zone,
                    rule.mode,
                )

        if zone_id in rule.block_cool:
            if rule.device_id not in result.blocked_devices_cool:
                result.blocked_devices_cool.append(rule.device_id)
                result.reasons.append(
                    f"Device mutex: {rule.device_id} blocked for cool "
                    f"(used by {rule.for_zone} for {rule.mode})"
                )
                _LOGGER.debug(
                    "Zone %s: device %s blocked for cool due to mutex "
                    "(used by %s for %s)",
                    zone_id,
                    rule.device_id,
                    rule.for_zone,
                    rule.mode,
                )

        # Block OTHER related devices (e.g., shared condenser units)
        # These apply to ALL zones, not just block_heat/block_cool zones
        for blocked_device in rule.blocked_devices_heat:
            if blocked_device not in result.blocked_devices_heat:
                result.blocked_devices_heat.append(blocked_device)
                result.reasons.append(
                    f"Device mutex: {blocked_device} blocked for heat "
                    f"(shares condenser with {rule.device_id} cooling in {rule.for_zone})"
                )
                _LOGGER.debug(
                    "Zone %s: device %s blocked for heat due to shared condenser "
                    "(%s cooling in %s)",
                    zone_id,
                    blocked_device,
                    rule.device_id,
                    rule.for_zone,
                )

        for blocked_device in rule.blocked_devices_cool:
            if blocked_device not in result.blocked_devices_cool:
                result.blocked_devices_cool.append(blocked_device)
                result.reasons.append(
                    f"Device mutex: {blocked_device} blocked for cool "
                    f"(shares condenser with {rule.device_id} heating in {rule.for_zone})"
                )
                _LOGGER.debug(
                    "Zone %s: device %s blocked for cool due to shared condenser "
                    "(%s heating in %s)",
                    zone_id,
                    blocked_device,
                    rule.device_id,
                    rule.for_zone,
                )

    def get_all_conflicts(
        self,
        outdoor_temp: float | None,
        zone_states: dict[str, ZoneState],
        zone_target_temps: dict[str, float | None],
        zone_configs: dict[str, ZoneConfig] | None = None,
    ) -> dict[str, ConflictResult]:
        """Resolve conflicts for all zones.

        Args:
            outdoor_temp: Current outdoor temperature
            zone_states: Current state of all zones
            zone_target_temps: Target temperatures for all zones
            zone_configs: Zone configurations (for per-zone outdoor reset overrides)

        Returns:
            Dict mapping zone_id to ConflictResult
        """
        results: dict[str, ConflictResult] = {}
        zone_configs = zone_configs or {}
        # Accumulate reasons then dedupe: global conditions (outdoor reset,
        # shared-condenser mutex) get reported once per affected zone, which
        # balloons the master's active_conflicts list into N copies of the
        # same string. Keep insertion order for readability.
        accumulated: list[str] = []

        for zone_id in zone_states:
            target_temp = zone_target_temps.get(zone_id)
            zone_config = zone_configs.get(zone_id)
            result = self.resolve_for_zone(
                zone_id,
                outdoor_temp,
                target_temp,
                zone_states,
                zone_config,
            )
            results[zone_id] = result
            accumulated.extend(result.reasons)

        self._active_conflicts = list(dict.fromkeys(accumulated))

        return results

    @property
    def active_conflicts(self) -> list[str]:
        """Get list of currently active conflict descriptions."""
        return self._active_conflicts.copy()

    def would_create_conflict(
        self,
        zone_id: str,
        device_id: str,
        mode: str,
        zone_states: dict[str, ZoneState],
    ) -> tuple[bool, list[str]]:
        """Check if activating a device would create new conflicts.

        This is a forward-looking check - what would happen if we
        activated this device?

        Args:
            zone_id: Zone that would activate the device
            device_id: Device to check
            mode: Mode to check (heat or cool)
            zone_states: Current state of all zones

        Returns:
            Tuple of (would_conflict, affected_zones)
        """
        affected_zones: list[str] = []

        for rule in self.config.device_mutex:
            if rule.device_id != device_id:
                continue
            if rule.mode != mode:
                continue
            if rule.for_zone != zone_id:
                continue

            # This rule would trigger if we activate this device
            if mode == HVAC_MODE_HEAT:
                affected_zones.extend(rule.block_heat)
            elif mode == HVAC_MODE_COOL:
                affected_zones.extend(rule.block_cool)

        # Check if any affected zones are currently needing the opposite mode
        conflicting_zones = []
        for affected_zone_id in affected_zones:
            state = zone_states.get(affected_zone_id)
            if state is None:
                continue

            # Check if affected zone is actively heating/cooling
            if mode == HVAC_MODE_COOL and state.hvac_action.value == "heating":
                conflicting_zones.append(affected_zone_id)
            elif mode == HVAC_MODE_HEAT and state.hvac_action.value == "cooling":
                conflicting_zones.append(affected_zone_id)

        return len(conflicting_zones) > 0, conflicting_zones
