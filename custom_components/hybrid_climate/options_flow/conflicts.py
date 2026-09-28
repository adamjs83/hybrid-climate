"""Device mutex conflict configuration flow for Hybrid Climate options."""
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
    CONF_BLOCK_COOL,
    CONF_BLOCK_HEAT,
    CONF_CONFLICTS,
    CONF_DEVICE_MUTEX,
    CONF_DEVICES,
    CONF_UI_CONFIG,
    CONF_UI_VERSION,
    CONF_ZONES,
)
from .base import OptionsFlowBase

# New fields for blocking other devices (shared condenser support)
CONF_BLOCKED_DEVICES_HEAT = "blocked_devices_heat"
CONF_BLOCKED_DEVICES_COOL = "blocked_devices_cool"


# Action constants
CONFLICT_ACTION_BACK = "back"
CONFLICT_ACTION_ADD = "add"


class ConflictFlowMixin(OptionsFlowBase):
    """Mixin providing device mutex conflict configuration flow steps."""

    _conflict_edit_index: int | None = None
    _conflict_wip: dict[str, Any] | None = None

    async def async_step_conflicts(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show conflict rules list with add/edit/delete options."""
        if user_input is not None:
            action = user_input.get("action")
            if action == CONFLICT_ACTION_BACK:
                return await self.async_step_menu()
            elif action == CONFLICT_ACTION_ADD:
                self._conflict_wip = {}
                self._conflict_edit_index = None
                return await self.async_step_conflict_edit()
            elif action and action.startswith("edit_"):
                idx = int(action[5:])
                self._conflict_edit_index = idx
                self._conflict_wip = self._load_conflict_for_edit(idx)
                return await self.async_step_conflict_edit()
            elif action and action.startswith("delete_"):
                idx = int(action[7:])
                return self._delete_conflict(idx)

        # Get existing rules from YAML and UI
        yaml_rules = self._get_yaml_config().get(CONF_CONFLICTS, {}).get(CONF_DEVICE_MUTEX, [])
        ui_rules = self._get_ui_config().get(CONF_DEVICE_MUTEX, [])
        
        # Combine rules (UI rules override/extend YAML)
        all_rules = yaml_rules + ui_rules

        # Build options list
        rule_options = [
            {"value": CONFLICT_ACTION_BACK, "label": "← Back to Menu"},
            {"value": CONFLICT_ACTION_ADD, "label": "+ Add Mutex Rule"},
        ]

        for idx, rule in enumerate(all_rules):
            device_id = rule.get("device") or rule.get("device_id", "?")
            mode = rule.get("mode", "?")
            for_zone = rule.get("for_zone", "?")
            block_heat = rule.get(CONF_BLOCK_HEAT, [])
            block_cool = rule.get(CONF_BLOCK_COOL, [])
            blocked_devices_heat = rule.get(CONF_BLOCKED_DEVICES_HEAT, [])
            blocked_devices_cool = rule.get(CONF_BLOCKED_DEVICES_COOL, [])
            
            blocks = []
            if block_heat:
                blocks.append(f"zones no heat: {', '.join(block_heat)}")
            if block_cool:
                blocks.append(f"zones no cool: {', '.join(block_cool)}")
            if blocked_devices_heat:
                blocks.append(f"devices no heat: {', '.join(blocked_devices_heat)}")
            if blocked_devices_cool:
                blocks.append(f"devices no cool: {', '.join(blocked_devices_cool)}")
            block_summary = "; ".join(blocks) if blocks else "no blocks"
            
            rule_options.append({
                "value": f"edit_{idx}",
                "label": f"✏️ {device_id} ({mode} in {for_zone}) → {block_summary}",
            })
            rule_options.append({
                "value": f"delete_{idx}",
                "label": f"🗑️ Delete rule for {device_id}",
            })

        return self.async_show_form(
            step_id="conflicts",
            data_schema=vol.Schema({
                vol.Required("action"): SelectSelector(
                    SelectSelectorConfig(
                        options=rule_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={
                "rule_count": str(len(all_rules)),
            },
        )

    async def async_step_conflict_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit a device mutex rule."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Handle navigation
            nav_action = user_input.get("nav_action", "save")
            if nav_action == "cancel":
                self._conflict_edit_index = None
                self._conflict_wip = None
                return await self.async_step_conflicts()
            
            device = user_input.get("device", "")
            mode = user_input.get("mode", "heat")
            for_zone = user_input.get("for_zone", "")
            block_heat = user_input.get(CONF_BLOCK_HEAT, [])
            block_cool = user_input.get(CONF_BLOCK_COOL, [])
            blocked_devices_heat = user_input.get(CONF_BLOCKED_DEVICES_HEAT, [])
            blocked_devices_cool = user_input.get(CONF_BLOCKED_DEVICES_COOL, [])

            if not device:
                errors["device"] = "device_required"
            elif not for_zone:
                errors["for_zone"] = "zone_required"
            elif not block_heat and not block_cool and not blocked_devices_heat and not blocked_devices_cool:
                errors["base"] = "no_blocks_specified"

            if not errors:
                return self._save_conflict_config(
                    device, mode, for_zone, block_heat, block_cool,
                    blocked_devices_heat, blocked_devices_cool
                )

        wip = self._conflict_wip or {}

        # Get available devices and zones from both YAML and UI
        yaml_devices = self._get_yaml_config().get(CONF_DEVICES, {})
        ui_devices = self._get_ui_config().get(CONF_DEVICES, {})
        yaml_zones = self._get_yaml_config().get(CONF_ZONES, {})
        ui_zones = self._get_ui_config().get(CONF_ZONES, {})
        all_zones = set(yaml_zones.keys()) | set(ui_zones.keys())

        # Build device options from both YAML and UI devices (entity_id based)
        device_options = []
        seen_entities = set()

        # Add YAML devices
        for dev_id, dev_conf in yaml_devices.items():
            entity_id = dev_conf.get("entity_id", dev_id)
            if entity_id not in seen_entities:
                device_options.append({
                    "value": entity_id,
                    "label": f"{dev_id} ({entity_id})",
                })
                seen_entities.add(entity_id)

        # Add UI devices (keyed by entity_id)
        for entity_id in ui_devices.keys():
            if entity_id not in seen_entities:
                device_options.append({
                    "value": entity_id,
                    "label": entity_id,
                })
                seen_entities.add(entity_id)

        # Build zone options
        zone_options = [{"value": z, "label": z} for z in sorted(all_zones)]

        return self.async_show_form(
            step_id="conflict_edit",
            data_schema=vol.Schema({
                vol.Required("nav_action", default="save"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "cancel", "label": "← Cancel"},
                            {"value": "save", "label": "Save →"},
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required("device", default=wip.get("device", "")): SelectSelector(
                    SelectSelectorConfig(
                        options=device_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,  # Allow typing entity_id
                    )
                ) if device_options else EntitySelector(
                    EntitySelectorConfig(domain="climate")
                ),
                vol.Required("mode", default=wip.get("mode", "heat")): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "heat", "label": "Heating"},
                            {"value": "cool", "label": "Cooling"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("for_zone", default=wip.get("for_zone", "")): SelectSelector(
                    SelectSelectorConfig(
                        options=zone_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ) if zone_options else str,
                vol.Optional(CONF_BLOCK_HEAT, default=wip.get(CONF_BLOCK_HEAT, [])): SelectSelector(
                    SelectSelectorConfig(
                        options=zone_options if zone_options else [],
                        mode=SelectSelectorMode.DROPDOWN,
                        multiple=True,
                        custom_value=True,  # Allows manual entry even with no zones
                    )
                ),
                vol.Optional(CONF_BLOCK_COOL, default=wip.get(CONF_BLOCK_COOL, [])): SelectSelector(
                    SelectSelectorConfig(
                        options=zone_options if zone_options else [],
                        mode=SelectSelectorMode.DROPDOWN,
                        multiple=True,
                        custom_value=True,  # Allows manual entry even with no zones
                    )
                ),
                # Blocked devices (for shared condenser support)
                vol.Optional(CONF_BLOCKED_DEVICES_HEAT, default=wip.get(CONF_BLOCKED_DEVICES_HEAT, [])): SelectSelector(
                    SelectSelectorConfig(
                        options=device_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        multiple=True,
                        custom_value=True,
                    )
                ) if device_options else EntitySelector(
                    EntitySelectorConfig(domain="climate", multiple=True)
                ),
                vol.Optional(CONF_BLOCKED_DEVICES_COOL, default=wip.get(CONF_BLOCKED_DEVICES_COOL, [])): SelectSelector(
                    SelectSelectorConfig(
                        options=device_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        multiple=True,
                        custom_value=True,
                    )
                ) if device_options else EntitySelector(
                    EntitySelectorConfig(domain="climate", multiple=True)
                ),
            }),
            errors=errors,
            description_placeholders={
                "edit_mode": "Edit" if self._conflict_edit_index is not None else "Add",
            },
        )

    def _load_conflict_for_edit(self, idx: int) -> dict[str, Any]:
        """Load existing conflict rule for editing."""
        yaml_rules = self._get_yaml_config().get(CONF_CONFLICTS, {}).get(CONF_DEVICE_MUTEX, [])
        ui_rules = self._get_ui_config().get(CONF_DEVICE_MUTEX, [])
        all_rules = yaml_rules + ui_rules

        if idx < 0 or idx >= len(all_rules):
            return {}

        rule = all_rules[idx]
        
        # Normalize device field (could be device_id or device)
        device = rule.get("device") or rule.get("device_id", "")
        
        # If it's a device_id, try to resolve to entity_id
        yaml_devices = self._get_yaml_config().get(CONF_DEVICES, {})
        if device in yaml_devices:
            device = yaml_devices[device].get("entity_id", device)

        return {
            "device": device,
            "mode": rule.get("mode", "heat"),
            "for_zone": rule.get("for_zone", ""),
            CONF_BLOCK_HEAT: rule.get(CONF_BLOCK_HEAT, []),
            CONF_BLOCK_COOL: rule.get(CONF_BLOCK_COOL, []),
            CONF_BLOCKED_DEVICES_HEAT: rule.get(CONF_BLOCKED_DEVICES_HEAT, []),
            CONF_BLOCKED_DEVICES_COOL: rule.get(CONF_BLOCKED_DEVICES_COOL, []),
        }

    def _save_conflict_config(
        self,
        device: str,
        mode: str,
        for_zone: str,
        block_heat: list[str],
        block_cool: list[str],
        blocked_devices_heat: list[str] | None = None,
        blocked_devices_cool: list[str] | None = None,
    ) -> FlowResult:
        """Save conflict rule to options storage."""
        stored_config = dict(self._get_ui_config())
        stored_config[CONF_UI_VERSION] = 1

        rules = stored_config.get(CONF_DEVICE_MUTEX, [])
        if not isinstance(rules, list):
            rules = []

        new_rule = {
            "device": device,  # Store entity_id
            "mode": mode,
            "for_zone": for_zone,
            CONF_BLOCK_HEAT: block_heat,
            CONF_BLOCK_COOL: block_cool,
            CONF_BLOCKED_DEVICES_HEAT: blocked_devices_heat or [],
            CONF_BLOCKED_DEVICES_COOL: blocked_devices_cool or [],
        }

        if self._conflict_edit_index is not None:
            # Editing existing rule
            yaml_rules = self._get_yaml_config().get(CONF_CONFLICTS, {}).get(CONF_DEVICE_MUTEX, [])
            yaml_count = len(yaml_rules)
            
            if self._conflict_edit_index < yaml_count:
                # Can't edit YAML rules directly, add as override
                # The UI rule will take effect and YAML rule stays
                rules.append(new_rule)
            else:
                # Edit UI rule
                ui_idx = self._conflict_edit_index - yaml_count
                if ui_idx < len(rules):
                    rules[ui_idx] = new_rule
                else:
                    rules.append(new_rule)
        else:
            # Adding new rule
            rules.append(new_rule)

        stored_config[CONF_DEVICE_MUTEX] = rules

        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.warning("Saving %d mutex rules: %s", len(rules), rules)

        # Clear edit state
        self._conflict_edit_index = None
        self._conflict_wip = None

        return self._save_ui_config(stored_config)

    def _delete_conflict(self, idx: int) -> FlowResult:
        """Delete a conflict rule."""
        yaml_rules = self._get_yaml_config().get(CONF_CONFLICTS, {}).get(CONF_DEVICE_MUTEX, [])
        yaml_count = len(yaml_rules)

        if idx < yaml_count:
            # Can't delete YAML rules from UI
            return self.async_abort(reason="cannot_delete_yaml_rule")

        stored_config = dict(self._get_ui_config())
        rules = stored_config.get(CONF_DEVICE_MUTEX, [])
        
        ui_idx = idx - yaml_count
        if isinstance(rules, list) and 0 <= ui_idx < len(rules):
            del rules[ui_idx]
            stored_config[CONF_DEVICE_MUTEX] = rules
            return self._save_ui_config(stored_config)

        # Index out of range, just go back
        return self.async_abort(reason="rule_not_found")
