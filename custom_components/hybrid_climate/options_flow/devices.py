"""Purpose: Edit device capabilities and idle behavior in integration options.

Key dependencies: Home Assistant selectors and cached entity HVAC modes.
Used by: Hybrid Climate options flow handler.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from ..const import (
    CONF_CAPABILITIES,
    CONF_DEVICES,
    CONF_ENTITY_ID,
    CONF_IDLE,
    CONF_IDLE_ACTION,
    CONF_IDLE_SETBACK,
    CONF_UI_CONFIG,
    CONF_UI_VERSION,
    DEFAULT_IDLE_SETBACK,
    IDLE_ACTION_OFF,
    IDLE_ACTION_SETBACK,
)
from .base import OptionsFlowBase
from .capability_defaults import device_form_capabilities, submitted_capabilities


# Device action constants
DEVICE_ACTION_BACK = "back"

# Capability constants
CAP_HEAT = "heat"
CAP_COOL = "cool"


class DeviceFlowMixin(OptionsFlowBase):
    """Mixin providing device idle behavior configuration flow steps."""

    # Selected device for editing
    _device_edit_id: str | None = None

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show device list with edit options."""
        if user_input is not None:
            action = user_input.get("action")
            if action == DEVICE_ACTION_BACK:
                return await self.async_step_menu()
            elif action and action.startswith("edit_"):
                device_id = action[5:]  # Remove "edit_" prefix
                self._device_edit_id = device_id
                return await self.async_step_device_edit()

        yaml_devices = self._get_yaml_config().get(CONF_DEVICES, {})
        ui_devices = self._get_ui_config().get("devices", {})
        
        # Also collect devices from UI zones (auto-generated)
        ui_zones = self._get_ui_config().get("zones", {})
        ui_zone_entity_ids: set[str] = set()
        for zone_conf in ui_zones.values():
            for stage in zone_conf.get("heat_stages", []) + zone_conf.get("cool_stages", []):
                for dev in stage.get("devices", []):
                    if isinstance(dev, dict):
                        entity_id = dev.get("entity_id", "")
                        if entity_id:
                            ui_zone_entity_ids.add(entity_id)
                    elif isinstance(dev, str):
                        ui_zone_entity_ids.add(dev)

        # Build device list for display
        device_options = [{"value": DEVICE_ACTION_BACK, "label": "← Back to Menu"}]
        seen_entity_ids: set[str] = set()

        # First add YAML devices
        for device_id in yaml_devices:
            device_conf = yaml_devices[device_id]
            entity_id = device_conf.get(CONF_ENTITY_ID, device_id)
            seen_entity_ids.add(entity_id)
            
            # Check UI devices first, then YAML
            if entity_id in ui_devices:
                dev_conf = ui_devices[entity_id]
                action = dev_conf.get(CONF_IDLE_ACTION, IDLE_ACTION_OFF)
                setback = dev_conf.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK)
            else:
                idle_conf = device_conf.get(CONF_IDLE, {})
                action = idle_conf.get(CONF_IDLE_ACTION, IDLE_ACTION_OFF)
                setback = idle_conf.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK)

            if action == IDLE_ACTION_SETBACK:
                status = f"setback {setback}°F"
            else:
                status = "off when idle"

            device_options.append({
                "value": f"edit_{entity_id}",  # Use entity_id for consistency
                "label": f"{device_id} ({status})",
            })

        # Then add UI-only devices (from ui_devices or zones, not in YAML)
        all_ui_entity_ids = set(ui_devices.keys()) | ui_zone_entity_ids
        for entity_id in sorted(all_ui_entity_ids - seen_entity_ids):
            dev_conf = ui_devices.get(entity_id, {})
            action = dev_conf.get(CONF_IDLE_ACTION, IDLE_ACTION_OFF)
            setback = dev_conf.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK)

            if action == IDLE_ACTION_SETBACK:
                status = f"setback {setback}°F"
            else:
                status = "off when idle"

            # Display name from entity_id (climate.xxx -> xxx)
            display_name = entity_id.replace("climate.", "")
            device_options.append({
                "value": f"edit_{entity_id}",
                "label": f"{display_name} ({status})",
            })

        device_names = list(yaml_devices.keys()) + [
            eid.replace("climate.", "") for eid in (all_ui_entity_ids - seen_entity_ids)
        ]

        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema({
                vol.Required("action"): SelectSelector(
                    SelectSelectorConfig(
                        options=device_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={
                "device_list": ", ".join(device_names) if device_names else "(none)",
                "device_count": str(len(device_names)),
            },
        )

    async def async_step_device_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure capabilities and idle behavior for a specific device."""
        errors: dict[str, str] = {}
        device_id = self._device_edit_id

        if not device_id:
            return await self.async_step_devices()

        if user_input is not None:
            # Handle navigation
            nav_action = user_input.get("nav_action", "save")
            if nav_action == "cancel":
                self._device_edit_id = None
                return await self.async_step_devices()
            
            capabilities = submitted_capabilities(user_input)
            # Extract idle config
            action = user_input.get(CONF_IDLE_ACTION, IDLE_ACTION_OFF)
            setback = user_input.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK)

            # Save device config
            return self._save_device_config(
                device_id, capabilities, action, setback,
                compressor_group=user_input.get("compressor_group", "").strip(),
                min_compressor_runtime=int(user_input.get("min_compressor_runtime", 0)),
                min_compressor_off_time=int(user_input.get("min_compressor_off_time", 0)),
            )

        current = self._load_device_config(device_id)
        defaults = device_form_capabilities(
            self.hass, device_id, self._get_ui_config().get(CONF_DEVICES, {}).get(device_id),
            current.get(CONF_CAPABILITIES, [CAP_HEAT]),
        )

        return self.async_show_form(
            step_id="device_edit",
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
                vol.Required(
                    "can_heat",
                    default=CAP_HEAT in defaults,
                ): BooleanSelector(),
                vol.Required(
                    "can_cool",
                    default=CAP_COOL in defaults,
                ): BooleanSelector(),
                vol.Required(
                    CONF_IDLE_ACTION,
                    default=current.get(CONF_IDLE_ACTION, IDLE_ACTION_OFF),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": IDLE_ACTION_OFF, "label": "Turn Off"},
                            {"value": IDLE_ACTION_SETBACK, "label": "Setback from target"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_IDLE_SETBACK,
                    default=current.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=20,
                        step=1,
                        unit_of_measurement="°F",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(
                    "compressor_group",
                    default=current.get("compressor_group", ""),
                ): TextSelector(TextSelectorConfig()),
                vol.Required(
                    "min_compressor_runtime",
                    default=current.get("min_compressor_runtime", 0),
                ): NumberSelector(NumberSelectorConfig(
                    min=0, max=3600, step=30, unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )),
                vol.Required(
                    "min_compressor_off_time",
                    default=current.get("min_compressor_off_time", 0),
                ): NumberSelector(NumberSelectorConfig(
                    min=0, max=3600, step=30, unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )),
            }),
            errors=errors,
            description_placeholders={
                "device_id": device_id,
            },
        )

    # Keep old method name for backwards compatibility
    async def async_step_device_idle(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Redirect to device_edit for backwards compatibility."""
        return await self.async_step_device_edit(user_input)

    def _load_device_config(self, device_id: str) -> dict[str, Any]:
        """Load existing device config (capabilities + idle)."""
        yaml_devices = self._get_yaml_config().get(CONF_DEVICES, {})
        ui_config = self._get_ui_config()
        ui_devices = ui_config.get("devices", {})

        # UI config takes precedence
        if device_id in ui_devices:
            return ui_devices[device_id]

        # Fall back to YAML
        device_conf = yaml_devices.get(device_id, {})
        idle_conf = device_conf.get(CONF_IDLE, {})

        return {
            CONF_CAPABILITIES: device_conf.get(CONF_CAPABILITIES, [CAP_HEAT]),
            CONF_IDLE_ACTION: idle_conf.get(CONF_IDLE_ACTION, IDLE_ACTION_OFF),
            CONF_IDLE_SETBACK: idle_conf.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK),
            "compressor_group": device_conf.get("compressor_group", ""),
            "min_compressor_runtime": device_conf.get("min_compressor_runtime", 0),
            "min_compressor_off_time": device_conf.get("min_compressor_off_time", 0),
        }

    # Backwards compat alias
    def _load_device_idle_config(self, device_id: str) -> dict[str, Any]:
        """Load existing device idle config (backwards compat)."""
        return self._load_device_config(device_id)

    def _save_device_config(
        self, device_id: str, capabilities: list[str], action: str, setback: float,
        *, compressor_group: str = "", min_compressor_runtime: int = 0,
        min_compressor_off_time: int = 0,
    ) -> FlowResult:
        """Save device configuration to options storage."""
        stored_config = dict(self._get_ui_config())
        stored_config[CONF_UI_VERSION] = 1

        # Store in devices dict (full device config)
        devices = stored_config.get("devices", {})
        if not isinstance(devices, dict):
            devices = {}

        devices[device_id] = {
            CONF_ENTITY_ID: device_id if device_id.startswith("climate.") else f"climate.{device_id}",
            CONF_CAPABILITIES: capabilities,
            CONF_IDLE_ACTION: action,
            CONF_IDLE_SETBACK: setback,
            "compressor_group": compressor_group,
            "min_compressor_runtime": min_compressor_runtime,
            "min_compressor_off_time": min_compressor_off_time,
        }
        stored_config["devices"] = devices

        # Remove legacy device_idle if it exists (consolidation cleanup)
        if "device_idle" in stored_config:
            del stored_config["device_idle"]

        # Clear edit state
        self._device_edit_id = None

        return self._save_ui_config(stored_config)

    # Backwards compat alias
    def _save_device_idle_config(
        self, device_id: str, action: str, setback: float
    ) -> FlowResult:
        """Save device idle configuration (backwards compat)."""
        current = self._load_device_config(device_id)
        capabilities = current.get(CONF_CAPABILITIES, [CAP_HEAT])
        return self._save_device_config(device_id, capabilities, action, setback)
