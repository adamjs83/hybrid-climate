"""Purpose: Edit device capabilities, idle behavior, compressor timing and coil dry-out in integration options;
the device's cooling regulation is shown read-only, naming the zones whose Regulation page sets it (v0.17.0 §1).

Key dependencies: Home Assistant selectors, cached entity HVAC modes, config_parsers.resolve_cool_regulation,
device_cooling.py (dry-out fields, stored settings), device_list.py (the list entries), regulation_devices.py
(zones cooling with a device).
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
    CONF_COOL_OVERDRIVE,
    CONF_COOL_REGULATION,
    CONF_DEVICES,
    CONF_ENTITY_ID,
    CONF_IDLE,
    CONF_IDLE_ACTION,
    CONF_IDLE_SETBACK,
    CONF_UI_VERSION,
    DEFAULT_IDLE_SETBACK,
    DEFAULT_COOL_OVERDRIVE,
    IDLE_ACTION_OFF,
    IDLE_ACTION_SETBACK,
)
from ..config_parsers import resolve_cool_regulation
from .base import OptionsFlowBase
from .capability_defaults import device_form_capabilities, submitted_capabilities
from .device_cooling import (
    cooling_settings_from_yaml, dry_out_fields, dry_out_from_input, dry_out_from_stored, merge_cooling_settings,
    regulation_settings_from_stored,
)
from .device_list import CAP_COOL, CAP_HEAT, device_list_entries
from .page_const import DEVICE_COOLING_LINE, DEVICE_COOLING_UNUSED, LIST_JOIN
from .regulation_devices import all_zones, zones_cooling_with


# Device action constants
DEVICE_ACTION_BACK = "back"


class DeviceFlowMixin(OptionsFlowBase):
    """Mixin providing the device list and device edit options flow steps."""

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

        device_options, device_names = device_list_entries(
            self.hass, self._get_yaml_config().get(CONF_DEVICES, {}), self._get_ui_config())
        device_options.insert(0, {"value": DEVICE_ACTION_BACK, "label": "← Back to Menu"})

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

        # The capabilities that pre-fill Can heat / Can cool also decide whether the
        # cooling block is shown; ticking Can cool shows it on the next open.
        current = self._load_device_config(device_id)
        defaults = device_form_capabilities(
            self.hass, device_id, self._get_ui_config().get(CONF_DEVICES, {}).get(device_id),
            current.get(CONF_CAPABILITIES, [CAP_HEAT]),
        )
        show_cooling = CAP_COOL in defaults

        if user_input is not None:
            # Handle navigation
            nav_action = user_input.get("nav_action", "save")
            if nav_action == "cancel":
                self._device_edit_id = None
                return await self.async_step_devices()
            
            capabilities = submitted_capabilities(user_input)
            # Cooling regulation is set on the zone Regulation page: keep the stored keys as they are.
            # A hidden dry-out block was not submitted: write the stored values back.
            regulation = regulation_settings_from_stored(current)
            dry_out = dry_out_from_input(user_input) if show_cooling else dry_out_from_stored(current)
            return self._save_device_config(
                device_id, capabilities,
                user_input.get(CONF_IDLE_ACTION, IDLE_ACTION_OFF),
                user_input.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK),
                compressor_group=user_input.get("compressor_group", "").strip(),
                min_compressor_runtime=int(user_input.get("min_compressor_runtime", 0)),
                min_compressor_off_time=int(user_input.get("min_compressor_off_time", 0)),
                cool_overdrive=regulation.pop(CONF_COOL_OVERDRIVE),
                **regulation, **dry_out,
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
                **(dry_out_fields(current) if show_cooling else {}),
            }),
            errors=errors,
            description_placeholders={
                "device_id": device_id,
                "cooling_regulation": self._cooling_regulation_line(device_id, current, show_cooling),
            },
        )

    def _cooling_regulation_line(self, device_id: str, current: dict[str, Any], show_cooling: bool) -> str:
        """Return the read-only cooling regulation line: the effective mode and the zones whose page sets it."""
        yaml_config = self._get_yaml_config()
        zones = all_zones(self._get_ui_config(), yaml_config)
        names = [name for _zone_id, name in
                 zones_cooling_with(zones, device_id, yaml_config.get(CONF_DEVICES) or {})]
        if not names and not show_cooling:
            return ""
        mode = resolve_cool_regulation(
            current.get(CONF_COOL_REGULATION), float(current.get(CONF_COOL_OVERDRIVE, DEFAULT_COOL_OVERDRIVE)))
        if not names:
            return DEVICE_COOLING_UNUSED.format(mode=mode)
        return DEVICE_COOLING_LINE.format(mode=mode, zones=LIST_JOIN.join(names))

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
            CONF_COOL_OVERDRIVE: device_conf.get(CONF_COOL_OVERDRIVE, DEFAULT_COOL_OVERDRIVE),
            **cooling_settings_from_yaml(device_conf),
        }

    def _save_device_config(
        self, device_id: str, capabilities: list[str], action: str, setback: float,
        *, compressor_group: str = "", min_compressor_runtime: int = 0,
        min_compressor_off_time: int = 0, cool_overdrive: float = DEFAULT_COOL_OVERDRIVE,
        **cooling_settings: Any,
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
            CONF_COOL_OVERDRIVE: cool_overdrive,
            **merge_cooling_settings(cooling_settings),
        }
        stored_config["devices"] = devices

        # Remove legacy device_idle if it exists (consolidation cleanup)
        if "device_idle" in stored_config:
            del stored_config["device_idle"]

        # Clear edit state
        self._device_edit_id = None

        return self._save_ui_config(stored_config)
