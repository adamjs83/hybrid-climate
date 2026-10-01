"""Purpose: Debounce master-mode-change restore passes, serve manual restore
requests, and run end-of-cycle bookkeeping.

Key dependencies: startup_takeover.StartupTakeover (request_rearm/record/arm/
is_pending/outcomes), manual_override.ManualOverrideTracker.evaluate (A12's
post_cycle bookkeeping), Home Assistant's async_call_later,
zone_helpers.get_all_zone_devices.
Used by: coordinator.py (control_restore instance + post_cycle),
setpoint_manager.set_master_mode, occupancy.py (home/away auto-switch),
__init__.py (entry.async_on_unload, A8), agent_api.service_handlers
(hybrid_climate.restore_control) and button.py (RestoreControlButton).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_call_later

from .const import (
    DOMAIN,
    MODE_CHANGE_RESTORE_DEBOUNCE_S,
    RESTORE_CONTROL_NOT_READY_MESSAGE,
    RESTORE_CONTROL_REFRESH_FAILED_MESSAGE,
    RESTORE_CONTROL_UNKNOWN_ZONE_MESSAGE,
    RESTORE_OUTCOME_RESULT,
    RESTORE_OUTCOME_SENT,
    RESTORE_OUTCOME_UNCHANGED,
    RESTORE_RESULT_PENDING,
    RESTORE_RESULT_SUPERSEDED,
    RESTORE_SOURCE_MANUAL,
    RESTORE_SOURCE_MODE_CHANGE,
)
from .zone_helpers import get_all_zone_devices

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)


class ControlRestore:
    """Debounce settled master mode changes into one re-armed takeover pass."""

    def __init__(self, coordinator: HybridClimateCoordinator) -> None:
        """Hold the coordinator so a late timer can check it is still current (A8)."""
        self._coordinator = coordinator
        self._cancel_timer: CALLBACK_TYPE | None = None

    def note_mode_change(self) -> None:
        """(Re)start the debounce timer; settles into one mode-change pass (spec §1.2)."""
        if self._cancel_timer is not None:
            self._cancel_timer()
        self._cancel_timer = async_call_later(
            self._coordinator.hass, MODE_CHANGE_RESTORE_DEBOUNCE_S, self._fire,
        )

    async def async_shutdown(self) -> None:
        """Cancel a pending debounce timer on entry unload/reload (A8)."""
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

    def _is_current(self) -> bool:
        """Return False once this entry's coordinator has been replaced (A8)."""
        entry = self._coordinator.entry
        if entry is None:
            return True
        runtime = self._coordinator.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        return runtime is not None and runtime.get("coordinator") is self._coordinator

    @callback
    def _fire(self, _now: Any) -> None:
        """Request a mode-change pass and a follow-up refresh, if still current."""
        self._cancel_timer = None
        if not self._is_current():
            _LOGGER.debug(
                "Control restore: debounce timer fired for a replaced coordinator; skipping"
            )
            return
        self._coordinator.startup_takeover.request_rearm(RESTORE_SOURCE_MODE_CHANGE)
        self._coordinator.hass.async_create_task(
            self._coordinator.async_request_refresh()
        )


def post_cycle(coordinator: HybridClimateCoordinator, command_results: dict[str, bool]) -> None:
    """Record this cycle's takeover/restore outcomes and arm the first successful pass."""
    coordinator.startup_takeover.record(command_results)
    if not coordinator.startup_takeover.armed:
        coordinator.startup_takeover.arm(coordinator)
    # Manual-override detection runs last, after a restore sent this cycle has
    # already updated desired_* (spec §3.1).
    coordinator.manual_overrides.evaluate(coordinator)


async def async_restore(
    coordinator: HybridClimateCoordinator, zone_id: str | None = None,
) -> dict[str, Any]:
    """Run one manual restore pass and report its outcomes (spec §2.1, A2).

    Requests a manual rearm, forces a full refresh so the pass actually runs
    within this call, then reports from the pass's own outcomes. If a newer
    request replaced this one before it was ever applied, every device in
    scope is reported `superseded` instead (A2). A refresh that fails, or
    that never actually ran this request (e.g. HA shutting down mid-call),
    is never reported as superseded — this request is cancelled so it can
    never apply later under a `pass_id` the caller already saw as an error
    (review round 1 items 3/4), and a refresh error is raised instead.
    Cancelling drops only this call's own still-waiting request; any other
    request still waiting (e.g. a mode-change restore that arrived first)
    is untouched and still applies on its own merits (review round 2 item 1).
    """
    takeover = coordinator.startup_takeover
    if zone_id is not None and zone_id not in coordinator.config.zones:
        raise ServiceValidationError(RESTORE_CONTROL_UNKNOWN_ZONE_MESSAGE)
    if not takeover.armed:
        raise HomeAssistantError(RESTORE_CONTROL_NOT_READY_MESSAGE)
    pass_id = takeover.request_rearm(RESTORE_SOURCE_MANUAL, zone_id)
    await coordinator.async_refresh()
    if not coordinator.last_update_success or takeover.is_request_pending(pass_id):
        takeover.cancel_pending_request(pass_id)
        raise HomeAssistantError(RESTORE_CONTROL_REFRESH_FAILED_MESSAGE)
    return _build_restore_response(coordinator, pass_id, zone_id)


def _restore_scope(coordinator: HybridClimateCoordinator, zone_id: str | None) -> list[str]:
    """Return this pass's own device scope: one zone, or every referenced zone."""
    zones = (
        {zone_id: coordinator.config.zones[zone_id]} if zone_id is not None
        else coordinator.config.zones
    )
    devices = set().union(*(get_all_zone_devices(zone) for zone in zones.values())) if zones else set()
    return sorted(devices)


def _build_restore_response(
    coordinator: HybridClimateCoordinator, pass_id: int, zone_id: str | None,
) -> dict[str, Any]:
    """Project this pass's own scope into the manual restore response shape."""
    takeover = coordinator.startup_takeover
    superseded = takeover.pass_id != pass_id
    devices: list[dict[str, Any]] = []
    for device_id in _restore_scope(coordinator, zone_id):
        device = coordinator.device_manager.get_device(device_id)
        entity_id = device.entity_id if device is not None else None
        if superseded:
            devices.append({
                "device_id": device_id, "entity_id": entity_id,
                "result": RESTORE_RESULT_SUPERSEDED, "reason": RESTORE_RESULT_SUPERSEDED,
                "command": None,
            })
            continue
        outcome = takeover.outcomes.get(device_id)
        if outcome is None:
            # Every device in this pass's own scope is a candidate of the
            # current pass (rearm's scope_candidates), so one full refresh
            # always produces an outcome; this only guards a future change.
            _LOGGER.warning("Restore control: no outcome recorded for %s", device_id)
            devices.append({
                "device_id": device_id, "entity_id": entity_id,
                "result": RESTORE_RESULT_PENDING, "reason": None, "command": None,
            })
            continue
        command = (
            {"mode": outcome.mode, "target": outcome.target}
            if outcome.code in (RESTORE_OUTCOME_SENT, RESTORE_OUTCOME_UNCHANGED) else None
        )
        devices.append({
            "device_id": device_id, "entity_id": entity_id,
            "result": RESTORE_OUTCOME_RESULT.get(outcome.code, RESTORE_RESULT_PENDING),
            "reason": outcome.code, "command": command,
        })
    entry_id = coordinator.entry.entry_id if coordinator.entry is not None else None
    return {"entry_id": entry_id, "zone_id": zone_id, "source": RESTORE_SOURCE_MANUAL, "devices": devices}
