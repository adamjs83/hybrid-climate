"""Zone configuration flow entry point.

Key dependencies: zone_steps.py, zone_helpers.py
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
    CONF_NAME,
    CONF_ZONES,
)
from .base import OptionsFlowBase
from .sensor_weights import SensorWeightsMixin
from .zone_helpers import ZoneHelpersMixin
from .zone_steps import ZoneStepsMixin


# Zone wizard step constants
ZONE_ACTION_ADD = "add"
ZONE_ACTION_BACK = "back"


class ZoneFlowMixin(ZoneStepsMixin, SensorWeightsMixin, ZoneHelpersMixin, OptionsFlowBase):
    """Zone configuration flow combining steps and helpers."""

    # Work-in-progress storage for multi-step zone wizard
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
                self._zone_wip = {}
                self._zone_edit_id = None
                return await self.async_step_zone_basics()
            elif action and action.startswith("edit_"):
                zone_id = action[5:]
                self._zone_edit_id = zone_id
                self._zone_wip = self._load_zone_for_edit(zone_id)
                return await self.async_step_zone_basics()
            elif action and action.startswith("delete_"):
                zone_id = action[7:]
                return self._delete_zone(zone_id)

        yaml_zones = self._get_yaml_config().get(CONF_ZONES, {})
        ui_zones = self._get_ui_config().get(CONF_ZONES, {})

        # Merge zone lists (UI overrides YAML)
        all_zone_ids = set(yaml_zones.keys()) | set(ui_zones.keys())

        # Build zone list for display
        zone_options = [
            {"value": ZONE_ACTION_BACK, "label": "← Back to Menu"},
            {"value": ZONE_ACTION_ADD, "label": "+ Add New Zone"},
        ]

        for zone_id in sorted(all_zone_ids):
            zone_conf = ui_zones.get(zone_id, yaml_zones.get(zone_id, {}))
            name = zone_conf.get(CONF_NAME, zone_id)

            # Build status summary
            heat_stages = len(zone_conf.get("heat_stages", []))
            cool_stages = len(zone_conf.get("cool_stages", []))
            status_parts = []
            if heat_stages:
                status_parts.append(f"{heat_stages} heat")
            if cool_stages:
                status_parts.append(f"{cool_stages} cool")
            status = " · ".join(status_parts) if status_parts else "no stages"

            zone_options.append({
                "value": f"edit_{zone_id}",
                "label": f"✏️ {name} ({status})",
            })
            zone_options.append({
                "value": f"delete_{zone_id}",
                "label": f"🗑️ Delete {name}",
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
