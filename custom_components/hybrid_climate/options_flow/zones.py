"""Purpose: Zone list step (name, stages and regulation summary; add, edit → zone menu, delete → confirm).

Key dependencies: zone_save.py, zone_helpers.py, page_const.py, models.resolve_cool_regulation;
zone_pages/menu.py, zone_pages/basics.py (add path) and zone_pages/delete_confirm.py via the composed flow.
Used by: options_flow/handler.py
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ..const import (
    CONF_COOL_OVERDRIVE,
    CONF_COOL_REGULATION,
    CONF_COOL_STAGES,
    CONF_DEVICES,
    CONF_ENTITY_ID,
    CONF_HEAT_STAGES,
    CONF_NAME,
    CONF_REGULATION,
    CONF_REGULATION_TYPE,
    CONF_ZONES,
    DEFAULT_COOL_OVERDRIVE,
    DEVICE_LIST_COOLING,
    REGULATION_DIRECT,
    REGULATION_PI,
)
from ..models import resolve_cool_regulation
from .base import OptionsFlowBase
from .page_const import (
    ZONE_LABEL_COOLING_JOIN,
    ZONE_LABEL_DELETE,
    ZONE_LABEL_HEATING,
    ZONE_LABEL_HEATING_PI,
    ZONE_LABEL_NO_STAGES,
    ZONE_LABEL_SEPARATOR,
    ZONE_LABEL_STAGE_NOUN,
    ZONE_LABEL_STAGES,
)
from .zone_helpers import ZoneHelpersMixin
from .zone_save import ZoneSaveMixin


# Zone list action constants
ZONE_ACTION_ADD = "add"
ZONE_ACTION_BACK = "back"
STAGE_KIND_HEAT = "heat"
STAGE_KIND_COOL = "cool"


def _device_conf(ref: str, ui_devices: dict[str, Any], yaml_devices: dict[str, Any]) -> dict[str, Any]:
    """Return a stage device's settings: the UI entry by entity id, else the YAML device by id or entity id."""
    if ref in ui_devices:
        return ui_devices[ref]
    for device_id, conf in yaml_devices.items():
        if ref == device_id or ref == conf.get(CONF_ENTITY_ID):
            entity_id = conf.get(CONF_ENTITY_ID, device_id)
            return ui_devices.get(entity_id, conf)
    return {}


def zone_list_label(
    zone_id: str, zone: dict[str, Any], ui_devices: dict[str, Any], yaml_devices: dict[str, Any],
) -> str:
    """Return "Basement — heat 2 stages, cool 1 — heating PI, cooling: compensation" for the zone list."""
    heat = zone.get(CONF_HEAT_STAGES) or []
    cool = zone.get(CONF_COOL_STAGES) or []
    stages = [ZONE_LABEL_STAGES.format(kind=kind, count=len(found))
              for kind, found in ((STAGE_KIND_HEAT, heat), (STAGE_KIND_COOL, cool)) if found]
    if not stages:
        return ZONE_LABEL_SEPARATOR.join([zone.get(CONF_NAME, zone_id), ZONE_LABEL_NO_STAGES])
    # Only the first stage kind carries the noun: "heat 2 stages, cool 1".
    first_count = len(heat) if heat else len(cool)
    stages[0] += ZONE_LABEL_STAGE_NOUN[0 if first_count == 1 else 1]
    regulation: list[str] = []
    if heat:
        reg_type = (zone.get(CONF_REGULATION) or {}).get(CONF_REGULATION_TYPE, REGULATION_DIRECT)
        regulation.append(ZONE_LABEL_HEATING.format(
            mode=ZONE_LABEL_HEATING_PI if reg_type == REGULATION_PI else reg_type))
    if cool:
        # Cooling regulation is per device: list each cool-stage device's effective mode once.
        modes: list[str] = []
        for stage in cool:
            for device in stage.get(CONF_DEVICES, []):
                ref = device.get(CONF_ENTITY_ID, "") if isinstance(device, dict) else str(device)
                conf = _device_conf(ref, ui_devices, yaml_devices)
                mode = resolve_cool_regulation(
                    conf.get(CONF_COOL_REGULATION),
                    float(conf.get(CONF_COOL_OVERDRIVE, DEFAULT_COOL_OVERDRIVE)))
                if mode not in modes:
                    modes.append(mode)
        if modes:
            regulation.append(DEVICE_LIST_COOLING.format(mode=ZONE_LABEL_COOLING_JOIN.join(modes)))
    parts = [zone.get(CONF_NAME, zone_id), ", ".join(stages)]
    if regulation:
        parts.append(", ".join(regulation))
    return ZONE_LABEL_SEPARATOR.join(parts)


class ZoneFlowMixin(ZoneSaveMixin, ZoneHelpersMixin, OptionsFlowBase):
    """Zone list step combining the save and load helpers."""

    # Work-in-progress storage for the add-zone path
    _zone_wip: dict[str, Any] | None = None
    _zone_edit_id: str | None = None

    async def async_step_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show zone list with add/edit/delete options."""
        if user_input is not None:
            action = user_input.get("action")
            if action == ZONE_ACTION_BACK:
                return await self.async_step_menu()
            elif action == ZONE_ACTION_ADD:
                # The add path (zone_pages: basics → heat → cool) collects the zone, then saves it.
                self._zone_wip = {}
                self._zone_edit_id = None
                return await self.async_step_zone_basics()
            elif action and action.startswith("edit_"):
                # The zone menu loads the zone (zone_pages/menu.py).
                self._zone_edit_id = action[5:]
                return await self.async_step_zone_menu()
            elif action and action.startswith("delete_"):
                # Confirm first; YAML-only zones abort there as before (zone_pages/delete_confirm.py).
                return await self._confirm_zone_delete(action[7:])

        yaml_config = self._get_yaml_config()
        ui_config = self._get_ui_config()
        yaml_zones = yaml_config.get(CONF_ZONES, {})
        ui_zones = ui_config.get(CONF_ZONES, {})
        ui_devices = ui_config.get(CONF_DEVICES, {}) or {}
        yaml_devices = yaml_config.get(CONF_DEVICES, {}) or {}

        # Merge zone lists (UI overrides YAML)
        all_zone_ids = set(yaml_zones.keys()) | set(ui_zones.keys())

        # Build zone list for display
        zone_options = [
            {"value": ZONE_ACTION_BACK, "label": "← Back to Menu"},
            {"value": ZONE_ACTION_ADD, "label": "+ Add New Zone"},
        ]

        for zone_id in sorted(all_zone_ids):
            zone_conf = ui_zones.get(zone_id, yaml_zones.get(zone_id, {}))
            zone_options.append({
                "value": f"edit_{zone_id}",
                "label": zone_list_label(zone_id, zone_conf, ui_devices, yaml_devices),
            })
            zone_options.append({
                "value": f"delete_{zone_id}",
                "label": ZONE_LABEL_DELETE.format(name=zone_conf.get(CONF_NAME, zone_id)),
            })

        return self.async_show_form(
            step_id="zones",
            data_schema=vol.Schema({
                vol.Required("action"): SelectSelector(
                    SelectSelectorConfig(
                        options=zone_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={
                "zone_count": str(len(all_zone_ids)),
            },
        )
