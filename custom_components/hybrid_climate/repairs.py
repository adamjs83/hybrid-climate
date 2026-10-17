"""Purpose: Reconcile Home Assistant Repairs issues with the coordinator's state each cycle.

One reconciler computes the issues the current state wants (sensor failure, device
unavailable past its grace, manual override, stage without usable devices, Agent API
apply left pending), creates the missing ones and deletes the ones no longer wanted.
None are fixable; each text names the entity and where to go.

Key dependencies: homeassistant.helpers.issue_registry and entity_registry,
capability_check.active_stage_unusable, agent_api.revision.revision_state.
Used by: coordinator._async_update_data (sync_issues), __init__.async_unload_entry
(clear_all_issues), agent_api.config_patch and __init__.async_setup_entry
(raise_pending_apply / clear_pending_apply).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .agent_api.revision import revision_state
from .capability_check import active_stage_unusable
from .const import DATA_ACTIVE_REVISION, DOMAIN, SENSOR_STATUS_FAILED
from .zone_helpers import get_all_zone_devices

if TYPE_CHECKING:
    from .coordinator import HybridClimateCoordinator

_LOGGER = logging.getLogger(__name__)

# Issue keys; each is also the translation key under "issues" in strings.json.
ISSUE_SENSOR_FAILURE = "sensor_failure"
ISSUE_DEVICE_UNAVAILABLE = "device_unavailable"
ISSUE_MANUAL_OVERRIDE = "manual_override"
ISSUE_STAGE_WITHOUT_USABLE_DEVICES = "stage_without_usable_devices"
ISSUE_PENDING_APPLY = "pending_apply"

# Plain-text places in the UI the issue texts point to.
PAGE_INTEGRATION = "Settings → Devices & services → Hybrid Climate"
PAGE_CONFIGURE = f"{PAGE_INTEGRATION} → Configure"
PAGE_ZONE_BASICS = PAGE_CONFIGURE + " → Zones → {zone} → Basics & sensors"
PAGE_ZONE_STAGES = PAGE_CONFIGURE + " → Zones → {zone} → Heating stages / Cooling stages"
PAGE_GLOBAL_SETTINGS = f"{PAGE_CONFIGURE} → Global settings → Device outage grace period"
PAGE_ZONE_DEVICE = PAGE_INTEGRATION + " → {zone}"

ATTR_FRIENDLY_NAME = "friendly_name"
CLIMATE_DOMAIN = "climate"

# issue_id -> (translation key, placeholders)
Wanted = dict[str, tuple[str, dict[str, str]]]


def _issue_id(key: str, subject: str) -> str:
    """Build the issue id for one key and subject."""
    return f"{key}_{subject}"


def pending_apply_issue_id(entry_id: str) -> str:
    """Build the pending-apply issue id shared by the apply path, setup and the reconciler."""
    return _issue_id(ISSUE_PENDING_APPLY, entry_id)


def _pending_apply_placeholders() -> dict[str, str]:
    """Name the page where the integration is reloaded."""
    return {"page": PAGE_INTEGRATION}


def _zone_placeholders(coordinator: HybridClimateCoordinator, zone_id: str, page: str) -> dict[str, str]:
    """Name the zone, its climate entity and the page to open."""
    zone_config = coordinator.config.zones[zone_id]
    name = zone_config.name or zone_id
    zone_entity = ""
    entry = coordinator.entry
    if entry is not None:
        unique_id = f"{DOMAIN}_{entry.entry_id}_{zone_id}"
        zone_entity = er.async_get(coordinator.hass).async_get_entity_id(
            CLIMATE_DOMAIN, DOMAIN, unique_id) or ""
    return {"zone": name, "zone_entity": zone_entity, "page": page.format(zone=name)}


def _device_placeholders(coordinator: HybridClimateCoordinator, device_id: str, page: str) -> dict[str, str]:
    """Name the physical climate entity, its friendly name and the page to open."""
    device = coordinator.device_manager.get_device(device_id)
    entity_id = device.entity_id if device is not None else device_id
    state = coordinator.hass.states.get(entity_id)
    friendly = state.attributes.get(ATTR_FRIENDLY_NAME) if state is not None else None
    # The zones using it, so the Restore control page names a real zone.
    zones = [
        zone.name or zone_id for zone_id, zone in coordinator.config.zones.items()
        if device_id in get_all_zone_devices(zone)
    ]
    return {
        "device": entity_id, "device_name": friendly or entity_id,
        "page": page.format(zone=" / ".join(zones) or entity_id),
    }


def _stage_devices(coordinator: HybridClimateCoordinator) -> set[str]:
    """Return every device referenced by any zone's heat or cool stages."""
    devices: set[str] = set()
    for zone_config in coordinator.config.zones.values():
        devices |= get_all_zone_devices(zone_config)
    return devices


def _unavailable_past_grace(coordinator: HybridClimateCoordinator, now: datetime) -> list[str]:
    """Track unavailable stage devices and return those past the configured grace."""
    since = coordinator._device_unavailable_since
    grace = coordinator.config.device_unavailable_grace
    expired: list[str] = []
    for device_id in sorted(_stage_devices(coordinator)):
        device = coordinator.device_manager.get_device(device_id)
        if device is None or device.is_available:
            since.pop(device_id, None)
            continue
        first_seen = since.setdefault(device_id, now)
        # Grace 0 means no waiting period (raise on the cycle after the first sighting), matching
        # outage_hold.py, where grace <= 0 disables the outage hold; a negative grace never raises.
        if grace >= 0 and (now - first_seen).total_seconds() > grace:
            expired.append(device_id)
    # Forget devices no longer referenced by any stage.
    for device_id in set(since) - _stage_devices(coordinator):
        since.pop(device_id, None)
    return expired


def _pending_apply(coordinator: HybridClimateCoordinator) -> bool:
    """Report whether saved options are ahead of the active revision."""
    entry = coordinator.entry
    if entry is None:
        return False
    runtime = coordinator.hass.data.get(DOMAIN, {}).get(entry.entry_id)
    # Setup stores the active revision only after the first refresh; until then nothing is
    # pending (a failed setup is covered by the apply path's own raise_pending_apply).
    if runtime is None or DATA_ACTIVE_REVISION not in runtime:
        return False
    return bool(revision_state(entry.options, runtime[DATA_ACTIVE_REVISION])["pending"])


def _wanted_issues(coordinator: HybridClimateCoordinator) -> Wanted:
    """Compute every issue the current state calls for."""
    wanted: Wanted = {}
    for zone_id, state in coordinator.zone_states.items():
        if zone_id not in coordinator.config.zones:
            continue
        if state.sensor_status == SENSOR_STATUS_FAILED:
            wanted[_issue_id(ISSUE_SENSOR_FAILURE, zone_id)] = (
                ISSUE_SENSOR_FAILURE, _zone_placeholders(coordinator, zone_id, PAGE_ZONE_BASICS))
        # An outage hold already explains the gap; raise only once it is not running.
        if state.outage_hold_since is None and active_stage_unusable(coordinator.config, state, zone_id)[1]:
            wanted[_issue_id(ISSUE_STAGE_WITHOUT_USABLE_DEVICES, zone_id)] = (
                ISSUE_STAGE_WITHOUT_USABLE_DEVICES,
                _zone_placeholders(coordinator, zone_id, PAGE_ZONE_STAGES))
    for device_id in _unavailable_past_grace(coordinator, dt_util.utcnow()):
        wanted[_issue_id(ISSUE_DEVICE_UNAVAILABLE, device_id)] = (
            ISSUE_DEVICE_UNAVAILABLE, _device_placeholders(coordinator, device_id, PAGE_GLOBAL_SETTINGS))
    for device_id in sorted(coordinator.manual_overrides.active):
        wanted[_issue_id(ISSUE_MANUAL_OVERRIDE, device_id)] = (
            ISSUE_MANUAL_OVERRIDE, _device_placeholders(coordinator, device_id, PAGE_ZONE_DEVICE))
    if _pending_apply(coordinator):
        wanted[pending_apply_issue_id(coordinator.entry.entry_id)] = (
            ISSUE_PENDING_APPLY, _pending_apply_placeholders())
    return wanted


def _create(hass: HomeAssistant, issue_id: str, key: str, placeholders: dict[str, str]) -> bool:
    """Create one issue; log and report False when the registry refuses."""
    try:
        ir.async_create_issue(
            hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
            translation_key=key, translation_placeholders=placeholders,
        )
    except Exception:
        _LOGGER.exception("Could not create Repairs issue %s", issue_id)
        return False
    return True


def _delete(hass: HomeAssistant, issue_id: str) -> bool:
    """Delete one issue; log and report False when the registry refuses."""
    try:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    except Exception:
        _LOGGER.exception("Could not delete Repairs issue %s", issue_id)
        return False
    return True


def _is_current(coordinator: HybridClimateCoordinator) -> bool:
    """Return False once the coordinator is retired or no longer the entry's runtime one."""
    if getattr(coordinator, "retired", False):
        return False
    entry = coordinator.entry
    if entry is None:
        return True
    runtime = coordinator.hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    return runtime.get("coordinator") is coordinator


def sync_issues(coordinator: HybridClimateCoordinator) -> None:
    """Create wanted issues not yet raised and delete raised ones no longer wanted."""
    # A cycle finishing during or after unload must not raise issues nobody will clear.
    if not _is_current(coordinator):
        return
    try:
        wanted = _wanted_issues(coordinator)
    except Exception:
        # A state the reconciler cannot read must never break the control cycle.
        _LOGGER.exception("Could not compute Repairs issues")
        return
    owned = coordinator._issue_ids
    hass = coordinator.hass
    for issue_id, (key, placeholders) in wanted.items():
        if issue_id not in owned and _create(hass, issue_id, key, placeholders):
            owned.add(issue_id)
    for issue_id in sorted(owned - set(wanted)):
        if _delete(hass, issue_id):
            owned.discard(issue_id)


def clear_all_issues(hass: HomeAssistant, coordinator: HybridClimateCoordinator) -> None:
    """Delete every issue this coordinator raised (entry unload), except pending_apply."""
    owned = coordinator._issue_ids
    # pending_apply belongs to the apply path and setup: an unload inside a reload that
    # is about to fail must leave it, and a successful setup clears it.
    pending_prefix = f"{ISSUE_PENDING_APPLY}_"
    for issue_id in sorted(owned):
        if not issue_id.startswith(pending_prefix):
            _delete(hass, issue_id)
    owned.clear()
    coordinator._device_unavailable_since.clear()


def raise_pending_apply(hass: HomeAssistant, entry_id: str) -> None:
    """Raise the pending-apply issue after an apply whose saved options did not become active."""
    _create(hass, pending_apply_issue_id(entry_id), ISSUE_PENDING_APPLY, _pending_apply_placeholders())


def clear_pending_apply(hass: HomeAssistant, entry_id: str) -> None:
    """Clear the pending-apply issue once the saved options are active."""
    _delete(hass, pending_apply_issue_id(entry_id))

