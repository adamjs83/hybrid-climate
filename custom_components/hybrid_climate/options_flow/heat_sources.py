"""Heat source group configuration flow for Hybrid Climate options."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ..const import (
    CONF_DEVICES,
    CONF_HEAT_SOURCES,
    CONF_NAME,
    CONF_UI_CONFIG,
    CONF_UI_VERSION,
)
from .base import OptionsFlowBase


# Action constants
HEAT_SOURCE_ACTION_ADD = "add"
HEAT_SOURCE_ACTION_BACK = "back"


class HeatSourceFlowMixin(OptionsFlowBase):
    """Mixin providing heat source group configuration flow steps."""

    _heat_source_edit_id: str | None = None

    async def async_step_heat_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show heat source group list with add/edit/delete options."""
        if user_input is not None:
            action = user_input.get("action")
            if action == HEAT_SOURCE_ACTION_BACK:
                return await self.async_step_menu()
            elif action == HEAT_SOURCE_ACTION_ADD:
                self._heat_source_edit_id = None
                return await self.async_step_heat_source_edit()
            elif action and action.startswith("edit_"):
                source_id = action[5:]
                self._heat_source_edit_id = source_id
                return await self.async_step_heat_source_edit()
            elif action and action.startswith("delete_"):
                source_id = action[7:]
                return self._delete_heat_source(source_id)

        yaml_sources = self._get_yaml_config().get(CONF_HEAT_SOURCES, {})
        ui_sources = self._get_ui_config().get(CONF_HEAT_SOURCES, {})
        
        # Merge sources (UI overrides YAML)
        all_source_ids = set(yaml_sources.keys()) | set(ui_sources.keys())

        # Build source list for display
        source_options = [
            {"value": HEAT_SOURCE_ACTION_BACK, "label": "← Back to Menu"},
            {"value": HEAT_SOURCE_ACTION_ADD, "label": "+ Add Heat Source Group"},
        ]

        for source_id in sorted(all_source_ids):
            source_conf = ui_sources.get(source_id, yaml_sources.get(source_id, {}))
            name = source_conf.get(CONF_NAME, source_id)
            device_count = len(source_conf.get(CONF_DEVICES, []))
            
            source_options.append({
                "value": f"edit_{source_id}",
                "label": f"✏️ {name} ({device_count} devices)",
            })
            source_options.append({
                "value": f"delete_{source_id}",
                "label": f"🗑️ Delete {name}",
            })

        return self.async_show_form(
            step_id="heat_sources",
            data_schema=vol.Schema({
                vol.Required("action"): SelectSelector(
                    SelectSelectorConfig(
                        options=source_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={
                "source_count": str(len(all_source_ids)),
            },
        )

    async def async_step_heat_source_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a heat source group."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Handle navigation
            action = user_input.get("nav_action", "save")
            if action == "cancel":
                self._heat_source_edit_id = None
                return await self.async_step_heat_sources()
            
            source_id = user_input.get("source_id", "").strip().lower().replace(" ", "_")
            name = user_input.get(CONF_NAME, "").strip()
            devices = user_input.get(CONF_DEVICES, [])

            # Use existing source_id if editing
            if self._heat_source_edit_id:
                source_id = self._heat_source_edit_id

            if not source_id:
                errors["source_id"] = "source_id_required"
            elif not name:
                errors[CONF_NAME] = "source_name_required"
            elif not devices:
                errors[CONF_DEVICES] = "source_devices_required"
            elif not self._heat_source_edit_id:
                # Check for duplicate only when adding new
                yaml_sources = self._get_yaml_config().get(CONF_HEAT_SOURCES, {})
                ui_sources = self._get_ui_config().get(CONF_HEAT_SOURCES, {})
                if source_id in yaml_sources or source_id in ui_sources:
                    errors["source_id"] = "source_id_exists"

            if not errors:
                return self._save_heat_source(source_id, name, devices)

        # Load current values for editing
        current = self._load_heat_source_for_edit()

        schema_dict = {}
        
        # Only show source_id field when adding new
        if not self._heat_source_edit_id:
            schema_dict[vol.Required("source_id", default=current.get("source_id", ""))] = str

        schema_dict.update({
            vol.Required(CONF_NAME, default=current.get(CONF_NAME, "")): str,
            vol.Required(CONF_DEVICES, default=current.get(CONF_DEVICES, [])): EntitySelector(
                EntitySelectorConfig(domain="climate", multiple=True)
            ),
            vol.Required("nav_action", default="save"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "cancel", "label": "← Cancel"},
                        {"value": "save", "label": "Save →"},
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            ),
        })

        return self.async_show_form(
            step_id="heat_source_edit",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "source_id": self._heat_source_edit_id or "(new)",
            },
        )

    def _load_heat_source_for_edit(self) -> dict[str, Any]:
        """Load existing heat source config for editing."""
        if not self._heat_source_edit_id:
            return {}

        yaml_sources = self._get_yaml_config().get(CONF_HEAT_SOURCES, {})
        ui_sources = self._get_ui_config().get(CONF_HEAT_SOURCES, {})

        # UI takes precedence
        source_conf = ui_sources.get(
            self._heat_source_edit_id,
            yaml_sources.get(self._heat_source_edit_id, {})
        )

        # Convert device IDs to entity IDs if needed
        devices = source_conf.get(CONF_DEVICES, [])
        yaml_devices = self._get_yaml_config().get(CONF_DEVICES, {})
        
        entity_ids = []
        for device in devices:
            if device.startswith("climate."):
                entity_ids.append(device)
            elif device in yaml_devices:
                entity_ids.append(yaml_devices[device].get("entity_id", device))
            else:
                entity_ids.append(f"climate.{device}")

        return {
            "source_id": self._heat_source_edit_id,
            CONF_NAME: source_conf.get(CONF_NAME, self._heat_source_edit_id),
            CONF_DEVICES: entity_ids,
        }

    def _save_heat_source(
        self, source_id: str, name: str, devices: list[str]
    ) -> FlowResult:
        """Save heat source group configuration."""
        stored_config = dict(self._get_ui_config())
        stored_config[CONF_UI_VERSION] = 1
        
        sources = stored_config.get(CONF_HEAT_SOURCES, {})
        if not isinstance(sources, dict):
            sources = {}
        
        sources[source_id] = {
            CONF_NAME: name,
            CONF_DEVICES: devices,  # Store as entity_ids
        }
        stored_config[CONF_HEAT_SOURCES] = sources

        self._heat_source_edit_id = None
        return self._save_ui_config(stored_config)

    def _delete_heat_source(self, source_id: str) -> FlowResult:
        """Delete a heat source group from UI config."""
        stored_config = dict(self._get_ui_config())
        sources = stored_config.get(CONF_HEAT_SOURCES, {})
        
        if isinstance(sources, dict) and source_id in sources:
            del sources[source_id]
            stored_config[CONF_HEAT_SOURCES] = sources
            return self._save_ui_config(stored_config)
        
        return self.async_abort(reason="cannot_delete_yaml_source")
