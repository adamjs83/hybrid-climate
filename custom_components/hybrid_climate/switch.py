"""Purpose: Expose a per-zone "Hold" switch (spec v0.18.0 §1) that starts and ends zone holds.

On means the zone is held; off resumes the saved temperatures. The switch restores its on state
and attributes into `ZoneState.hold` before the startup seed applies them.

Key dependencies: hold.py (start_hold, end_hold, is_held), the zone device identity shared with
button.py/number_entities.py.
Used by: Home Assistant switch platform setup.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DIAG_DEVICE_NAME_PREFIX, DIAG_MANUFACTURER, DIAG_ZONE_MODEL, DOMAIN
from .coordinator import HybridClimateCoordinator
from .hold import (
    ATTR_HELD_COOL, ATTR_HELD_HEAT, ATTR_HOLD_SINCE, ATTR_HOLD_UNTIL, HOLD_KEY, HoldState, end_hold,
    is_held, start_hold,
)

_LOGGER = logging.getLogger(__name__)


def _optional_float(value: Any) -> float | None:
    """Return a restored temperature as a float, None when absent; raise on garbage."""
    return None if value is None else float(value)


def _restored_hold(attributes: dict[str, Any]) -> HoldState:
    """Build a HoldState from restored switch attributes; raise ValueError when malformed."""
    since = dt_util.parse_datetime(str(attributes.get(ATTR_HOLD_SINCE)))
    if since is None:
        raise ValueError(f"bad {ATTR_HOLD_SINCE}")
    until_value = attributes.get(ATTR_HOLD_UNTIL)
    until = None if until_value is None else dt_util.parse_datetime(str(until_value))
    # A naive end time cannot be compared with the aware cycle clock in expire_holds.
    if until_value is not None and (until is None or until.tzinfo is None):
        raise ValueError(f"bad {ATTR_HOLD_UNTIL}")
    return HoldState(since=since, until=until,
                     heat=_optional_float(attributes.get(ATTR_HELD_HEAT)),
                     cool=_optional_float(attributes.get(ATTR_HELD_COOL)))


class HoldSwitch(SwitchEntity, RestoreEntity):
    """Hold this zone at its current targets (on) or resume saved temperatures (off)."""

    _attr_has_entity_name = True
    _attr_translation_key = HOLD_KEY
    _attr_should_poll = False

    def __init__(
        self, hass: HomeAssistant, coordinator: HybridClimateCoordinator, zone_id: str,
    ) -> None:
        """Keep the zone identity this switch holds."""
        self.hass = hass
        self.coordinator = coordinator
        self.zone_id = zone_id
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_{HOLD_KEY}"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the same zone device as the zone's other entities."""
        zone = self.coordinator.config.zones[self.zone_id]
        return DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_{self.zone_id}")},
            name=f"{DIAG_DEVICE_NAME_PREFIX}{zone.name}",
            manufacturer=DIAG_MANUFACTURER, model=DIAG_ZONE_MODEL,
        )

    @property
    def is_on(self) -> bool:
        """Return whether the zone is held."""
        return is_held(self.coordinator, self.zone_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the hold's start, end (ISO or None) and held targets."""
        zone_state = self.coordinator.zone_states.get(self.zone_id)
        hold = zone_state.hold if zone_state is not None else None
        return {
            ATTR_HOLD_SINCE: hold.since.isoformat() if hold else None,
            ATTR_HOLD_UNTIL: hold.until.isoformat() if hold and hold.until else None,
            ATTR_HELD_HEAT: hold.heat if hold else None,
            ATTR_HELD_COOL: hold.cool if hold else None,
        }

    async def async_added_to_hass(self) -> None:
        """Follow coordinator updates and restore an active hold before the startup seed."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))
        last_state = await self.async_get_last_state()
        zone_state = self.coordinator.zone_states.get(self.zone_id)
        if last_state is None or last_state.state != STATE_ON or zone_state is None:
            return
        try:
            zone_state.hold = _restored_hold(dict(last_state.attributes))
        except (TypeError, ValueError) as err:
            _LOGGER.warning("Zone %s: restored hold ignored (%s): %s",
                            self.zone_id, err, dict(last_state.attributes))
            return
        _LOGGER.info("Zone %s: restored hold %s", self.zone_id, zone_state.hold)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Publish the hold state on every coordinator update."""
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start an untimed hold at the zone's current targets."""
        start_hold(self.coordinator, self.zone_id)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """End the hold and resume the saved temperatures."""
        await end_hold(self.coordinator, self.zone_id)
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one hold switch per configured zone."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data is None:
        _LOGGER.error("Failed to set up hold switches: entry data not found")
        return
    coordinator: HybridClimateCoordinator = data["coordinator"]
    async_add_entities(HoldSwitch(hass, coordinator, zone_id) for zone_id in coordinator.config.zones)
