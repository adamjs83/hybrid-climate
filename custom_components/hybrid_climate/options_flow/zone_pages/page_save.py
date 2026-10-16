"""Purpose: The shared per-page zone block writer every zone page saves through (v0.17.0 §1).

Key dependencies: options_flow/base.py (_get_ui_config, _save_ui_config), const.py; for YAML-only zones
config_converter.import_yaml_to_ui_config (every zone block) and zone_merge.canonical_stages (stage keys kept).
Used by: zone_pages page steps (the composed options flow handler inherits ZonePageSaveMixin).
"""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from homeassistant.data_entry_flow import FlowResult

from ...config_converter import import_yaml_to_ui_config
from ...const import CONF_COOL_STAGES, CONF_DEVICES, CONF_HEAT_STAGES, CONF_UI_VERSION, CONF_ZONES
from ..base import OptionsFlowBase
from ..zone_merge import canonical_stages

ABORT_ZONE_NOT_FOUND = "zone_not_found"


def materialize_yaml_zone(yaml_config: dict[str, Any], zone_id: str) -> dict[str, Any]:
    """Return a YAML zone in UI form with every block the UI format holds (Ruling 9).

    The YAML import converter carries every zone block (settings, openings, regulation with all its keys,
    opportunistic, tou, cool_regulation); stage lists then use the canonical edit form, which also keeps
    stage keys the converter does not copy.
    """
    yaml_zone = (yaml_config.get(CONF_ZONES) or {})[zone_id]
    yaml_devices = yaml_config.get(CONF_DEVICES) or {}
    imported = import_yaml_to_ui_config({CONF_DEVICES: yaml_devices, CONF_ZONES: {zone_id: yaml_zone}})
    zone = copy.deepcopy(imported[CONF_ZONES][zone_id])
    for key in (CONF_HEAT_STAGES, CONF_COOL_STAGES):
        stages = canonical_stages(yaml_zone.get(key), yaml_devices)
        if stages:
            zone[key] = stages
    return zone


class ZonePageSaveMixin(OptionsFlowBase):
    """Mixin providing the one-block zone writer for page saves."""

    def _save_zone_block(
        self, zone_id: str, apply: Callable[[dict[str, Any], dict[str, Any]], None],
    ) -> FlowResult:
        """Apply one page's edit to a copy of the stored zone and save it through the snapshot merge.

        A zone only in configuration.yaml is materialised into UI storage first.
        apply(zone, ui_config) mutates the zone copy (and may edit other ui_config blocks,
        such as devices); the zone copy is stored back after it runs, so apply must edit the
        zone through its first argument, not through ui_config["zones"].
        """
        # A zone only in YAML is first copied whole into UI storage (every block it has), then edited.
        yaml_config = self._get_yaml_config()
        yaml_zone: dict[str, Any] | None = None
        if zone_id in (yaml_config.get(CONF_ZONES) or {}):
            yaml_zone = materialize_yaml_zone(yaml_config, zone_id)
        ui_config = self._get_ui_config()
        zones = ui_config.get(CONF_ZONES)
        if not isinstance(zones, dict):
            zones = {}
        stored = zones.get(zone_id)
        if isinstance(stored, dict):
            zone = copy.deepcopy(stored)
        elif yaml_zone is not None:
            zone = yaml_zone
            ui_config[CONF_UI_VERSION] = 1
        else:
            # Neither in UI storage nor in YAML (deleted meanwhile): abort unsaved.
            return self.async_abort(reason=ABORT_ZONE_NOT_FOUND)
        apply(zone, ui_config)
        zones[zone_id] = zone
        ui_config[CONF_ZONES] = zones
        return self._save_ui_config(ui_config)
