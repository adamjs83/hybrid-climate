"""Purpose: The seven zone configuration wizard steps (basics, occupancy, heat stages, cool stages, settings, PI settings, TOU).

Key dependencies: const.py, entity registry (PI number ids), regulation_devices.py, sensor_weights.py (aggregation_selector), zone_helpers.py methods via the composed flow.
Used by: options_flow/zones.py (ZoneFlowMixin inherits ZoneStepsMixin).
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ..const import (
    AGGREGATION_AVERAGE,
    CONF_AGGREGATION,
    CONF_DEVICES,
    CONF_HYSTERESIS,
    CONF_MIN_RUNTIME,
    CONF_OPENING_ENTITIES,
    CONF_OPEN_DELAY,
    CONF_CLOSE_DELAY,
    CONF_NAME,
    CONF_OCCUPANCY_ENTITY,
    CONF_OCCUPANCY_OFF_DELAY,
    DEFAULT_OCCUPANCY_OFF_DELAY,
    MAX_OCCUPANCY_OFF_DELAY,
    OCCUPANCY_OFF_DELAY_MINUTES_STEP,
    SECONDS_PER_MINUTE,
    CONF_SENSORS,
    CONF_SMOOTHING_SAMPLES,
    CONF_TOU,
    CONF_TOU_COOL,
    CONF_TOU_HEAT,
    CONF_TOU_PRE_CONDITION_MINUTES,
    CONF_TOU_RELAXATION_AMOUNT,
    CONF_ZONES,
    DEFAULT_HYSTERESIS,
    DEFAULT_MIN_RUNTIME,
    DEFAULT_OPEN_DELAY,
    DEFAULT_CLOSE_DELAY,
    DEFAULT_REGULATION_MIN_PERIOD,
    DEFAULT_REGULATION_THRESHOLD,
    MAX_REGULATION_MIN_PERIOD,
    MAX_REGULATION_THRESHOLD,
    MIN_REGULATION_MIN_PERIOD,
    MIN_REGULATION_THRESHOLD,
    DEFAULT_SMOOTHING_SAMPLES,
    DEFAULT_TOU_PRE_CONDITION_MINUTES,
    DEFAULT_TOU_RELAXATION_AMOUNT,
    DOMAIN,
    MAX_SMOOTHING_SAMPLES,
    MIN_SMOOTHING_SAMPLES, NEW_ZONE_TITLE,
    PI_NUMBER_KEYS,
    PI_NUMBERS_NEW_ZONE_TEXT,
    REGULATION_DIRECT,
    REGULATION_PI,
    STAGES_DISABLED_KEYS,
)
from .base import minutes_to_seconds, seconds_to_minutes
from .regulation_devices import heat_capable_stage_devices, selected_pi_devices
from .sensor_weights import aggregation_selector
from .stage_fields import stage_form_fields, submitted_stages


class ZoneStepsMixin:
    """Mixin providing zone wizard step methods."""

    # Zone being edited; None while adding a zone (ZoneFlowMixin sets it).
    _zone_edit_id: str | None = None

    async def async_step_zone_basics(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zone wizard step 1: Basic info and sensors."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Handle navigation
            nav_action = user_input.get("nav_action", "next")
            if nav_action == "cancel":
                self._zone_wip = None
                self._zone_edit_id = None
                return await self.async_step_zones()

            zone_id = user_input.get("zone_id", "").strip().lower().replace(" ", "_")
            name = user_input.get(CONF_NAME, "").strip()

            # Use existing zone_id if editing
            if self._zone_edit_id:
                zone_id = self._zone_edit_id

            if not zone_id:
                errors["zone_id"] = "zone_id_required"
            elif not name:
                errors[CONF_NAME] = "zone_name_required"
            elif not self._zone_edit_id:
                # Check for duplicate only when adding new
                yaml_zones = self._get_yaml_config().get(CONF_ZONES, {})
                ui_zones = self._get_ui_config().get(CONF_ZONES, {})
                if zone_id in yaml_zones or zone_id in ui_zones:
                    errors["zone_id"] = "zone_id_exists"

            if not errors:
                self._zone_wip = self._zone_wip or {}
                self._zone_wip["zone_id"] = zone_id
                self._zone_wip[CONF_NAME] = name
                self._zone_wip[CONF_SENSORS] = user_input.get(CONF_SENSORS, [])
                self._zone_wip[CONF_AGGREGATION] = user_input.get(
                    CONF_AGGREGATION, AGGREGATION_AVERAGE
                )
                self._zone_wip[CONF_SMOOTHING_SAMPLES] = int(user_input.get(
                    CONF_SMOOTHING_SAMPLES, DEFAULT_SMOOTHING_SAMPLES
                ))
                if self._needs_weights_step():
                    return await self.async_step_zone_sensor_weights()
                return await self.async_step_zone_occupancy()

        wip = self._zone_wip or {}
        zone_id_default = wip.get("zone_id", self._zone_edit_id or "")
        name_default = wip.get(CONF_NAME, "")
        sensors_default = wip.get(CONF_SENSORS, [])
        aggregation_default = wip.get(CONF_AGGREGATION, AGGREGATION_AVERAGE)
        smoothing_default = wip.get(CONF_SMOOTHING_SAMPLES, DEFAULT_SMOOTHING_SAMPLES)

        schema_dict = {
            vol.Required("nav_action", default="next"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "cancel", "label": "← Cancel"},
                        {"value": "next", "label": "Next →"},
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            ),
        }

        # Only show zone_id field when adding new zone
        if not self._zone_edit_id:
            schema_dict[vol.Required("zone_id", default=zone_id_default)] = str

        schema_dict.update({
            vol.Required(CONF_NAME, default=name_default): str,
            vol.Optional(CONF_SENSORS, default=sensors_default): EntitySelector(
                EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            vol.Required(CONF_AGGREGATION, default=aggregation_default): aggregation_selector(),
            vol.Required(CONF_SMOOTHING_SAMPLES, default=smoothing_default): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SMOOTHING_SAMPLES,
                    max=MAX_SMOOTHING_SAMPLES,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
        })

        return self.async_show_form(
            step_id="zone_basics",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "zone_name": name_default if self._zone_edit_id and name_default else NEW_ZONE_TITLE,
            },
        )

    async def async_step_zone_occupancy(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zone wizard step 2: Occupancy settings (optional)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            action = user_input.get("nav_action", "next")

            # Handle navigation
            if action == "back":
                if self._needs_weights_step():
                    return await self.async_step_zone_sensor_weights()
                return await self.async_step_zone_basics()
            elif action == "skip":
                # Skip occupancy, clear any existing settings
                self._zone_wip = self._zone_wip or {}
                self._zone_wip["occupancy_enabled"] = False
                self._zone_wip[CONF_OCCUPANCY_ENTITY] = None
                return await self.async_step_zone_heat_stages()

            # Process occupancy settings
            self._zone_wip = self._zone_wip or {}
            self._zone_wip["occupancy_enabled"] = user_input.get("occupancy_enabled", False)
            if self._zone_wip["occupancy_enabled"]:
                entity = user_input.get(CONF_OCCUPANCY_ENTITY)
                # Only set entity if it's a valid non-empty string
                if entity and isinstance(entity, str) and entity.strip():
                    self._zone_wip[CONF_OCCUPANCY_ENTITY] = entity.strip()
                else:
                    self._zone_wip[CONF_OCCUPANCY_ENTITY] = None
                self._zone_wip["occupied_offset"] = user_input.get("occupied_offset", 2)
                # The form shows minutes; storage stays in seconds.
                self._zone_wip[CONF_OCCUPANCY_OFF_DELAY] = minutes_to_seconds(
                    user_input.get(CONF_OCCUPANCY_OFF_DELAY), DEFAULT_OCCUPANCY_OFF_DELAY,
                )
                self._zone_wip["unoccupied_offset"] = user_input.get("unoccupied_offset", -2)
            else:
                self._zone_wip[CONF_OCCUPANCY_ENTITY] = None
            return await self.async_step_zone_heat_stages()

        wip = self._zone_wip or {}
        occupancy_enabled = wip.get("occupancy_enabled", False)
        occupancy_entity = wip.get(CONF_OCCUPANCY_ENTITY) or ""
        occupancy_off_delay = seconds_to_minutes(wip.get(CONF_OCCUPANCY_OFF_DELAY) or DEFAULT_OCCUPANCY_OFF_DELAY)
        occupied_offset = wip.get("occupied_offset", 2)
        unoccupied_offset = wip.get("unoccupied_offset", -2)

        # Build schema - entity selector only shown if occupancy enabled
        schema_dict: dict[Any, Any] = {
            vol.Required("nav_action", default="next"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "back", "label": "← Back"},
                        {"value": "skip", "label": "Disable occupancy for this zone"},
                        {"value": "next", "label": "Next →"},
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Required("occupancy_enabled", default=occupancy_enabled): BooleanSelector(),
        }

        # Only add entity selector and offsets - they're optional
        schema_dict[vol.Optional(CONF_OCCUPANCY_ENTITY, description={"suggested_value": occupancy_entity})] = EntitySelector(
            EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
        )
        schema_dict[vol.Optional(CONF_OCCUPANCY_OFF_DELAY, default=occupancy_off_delay)] = NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=MAX_OCCUPANCY_OFF_DELAY / SECONDS_PER_MINUTE,
                step=OCCUPANCY_OFF_DELAY_MINUTES_STEP,
                unit_of_measurement="min",
                mode=NumberSelectorMode.BOX,
            )
        )
        schema_dict[vol.Optional("occupied_offset", default=occupied_offset)] = NumberSelector(
            NumberSelectorConfig(
                min=-10,
                max=10,
                step=0.5,
                unit_of_measurement="°F",
                mode=NumberSelectorMode.BOX,
            )
        )
        schema_dict[vol.Optional("unoccupied_offset", default=unoccupied_offset)] = NumberSelector(
            NumberSelectorConfig(
                min=-10,
                max=10,
                step=0.5,
                unit_of_measurement="°F",
                mode=NumberSelectorMode.BOX,
            )
        )

        return self.async_show_form(
            step_id="zone_occupancy",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "zone_name": wip.get(CONF_NAME, "Zone"),
            },
        )

    async def async_step_zone_heat_stages(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zone wizard step 3: Heat stages configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Handle navigation
            action = user_input.get("nav_action", "next")
            if action == "back":
                return await self.async_step_zone_occupancy()

            self._zone_wip = self._zone_wip or {}

            key = "heat_stages"
            enabled = bool(user_input.get("has_heat_stages", True))
            # Stages 1-2 from the form, then the stored stages 3+ (canonical) for later pages.
            baseline = (self._zone_wip.get("_edit_baseline") or {}) if self._zone_edit_id else {}
            self._zone_wip[key] = submitted_stages(
                user_input, self._zone_wip.get(key, []), baseline.get(key, []),
                enabled=enabled, include_outdoor_min=True,
            )
            # Unticking the toggle disables the mode: the save drops stored stages 3+ too.
            self._zone_wip[STAGES_DISABLED_KEYS[key]] = not enabled
            return await self.async_step_zone_cool_stages()

        wip = self._zone_wip or {}
        heat_stages = wip.get("heat_stages", [])

        # Extract existing stage data
        stage1 = next((s for s in heat_stages if s.get("stage") == 1), {})
        stage2 = next((s for s in heat_stages if s.get("stage") == 2), {})

        # Extract entity_ids from device list (devices are dicts with entity_id key)
        stage1_device_ids = self._extract_entity_ids(stage1.get("devices", []))
        stage2_device_ids = self._extract_entity_ids(stage2.get("devices", []))

        return self.async_show_form(
            step_id="zone_heat_stages",
            data_schema=vol.Schema({
                vol.Required("nav_action", default="next"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "back", "label": "← Back"},
                            {"value": "next", "label": "Next →"},
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required("has_heat_stages", default=len(heat_stages) > 0 or not self._zone_edit_id): BooleanSelector(),
                **stage_form_fields(
                    stage1, stage2, stage1_device_ids, stage2_device_ids, include_outdoor_min=True,
                ),
            }),
            errors=errors,
            description_placeholders={
                "zone_name": wip.get(CONF_NAME, "Zone"),
            },
        )

    async def async_step_zone_cool_stages(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zone wizard step 4: Cool stages configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Handle navigation
            action = user_input.get("nav_action", "next")
            if action == "back":
                return await self.async_step_zone_heat_stages()

            self._zone_wip = self._zone_wip or {}

            key = "cool_stages"
            enabled = bool(user_input.get("has_cool_stages", False))
            # Stages 1-2 from the form, then the stored stages 3+ (canonical) for later pages.
            baseline = (self._zone_wip.get("_edit_baseline") or {}) if self._zone_edit_id else {}
            self._zone_wip[key] = submitted_stages(
                user_input, self._zone_wip.get(key, []), baseline.get(key, []),
                enabled=enabled, include_outdoor_min=False,
            )
            # Unticking the toggle disables the mode: the save drops stored stages 3+ too.
            self._zone_wip[STAGES_DISABLED_KEYS[key]] = not enabled
            return await self.async_step_zone_settings()

        wip = self._zone_wip or {}
        cool_stages = wip.get("cool_stages", [])

        # Extract existing stage data
        stage1 = next((s for s in cool_stages if s.get("stage") == 1), {})
        stage2 = next((s for s in cool_stages if s.get("stage") == 2), {})

        # Extract entity_ids from device list
        stage1_device_ids = self._extract_entity_ids(stage1.get("devices", []))
        stage2_device_ids = self._extract_entity_ids(stage2.get("devices", []))

        return self.async_show_form(
            step_id="zone_cool_stages",
            data_schema=vol.Schema({
                vol.Required("nav_action", default="next"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "back", "label": "← Back"},
                            {"value": "next", "label": "Next →"},
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required("has_cool_stages", default=len(cool_stages) > 0): BooleanSelector(),
                **stage_form_fields(
                    stage1, stage2, stage1_device_ids, stage2_device_ids, include_outdoor_min=False,
                ),
            }),
            errors=errors,
            description_placeholders={
                "zone_name": wip.get(CONF_NAME, "Zone"),
            },
        )

    async def async_step_zone_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zone wizard step 5: Zone settings, opportunistic heating, outdoor reset, and regulation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Handle navigation
            action = user_input.get("nav_action", "next")
            if action == "back":
                return await self.async_step_zone_cool_stages()

            self._zone_wip = self._zone_wip or {}
            self._zone_wip[CONF_HYSTERESIS] = user_input.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)
            self._zone_wip[CONF_MIN_RUNTIME] = int(user_input.get(CONF_MIN_RUNTIME, DEFAULT_MIN_RUNTIME))
            self._zone_wip[CONF_OPENING_ENTITIES] = user_input.get(CONF_OPENING_ENTITIES, [])
            self._zone_wip[CONF_OPEN_DELAY] = int(user_input.get(CONF_OPEN_DELAY, DEFAULT_OPEN_DELAY))
            self._zone_wip[CONF_CLOSE_DELAY] = int(user_input.get(CONF_CLOSE_DELAY, DEFAULT_CLOSE_DELAY))
            self._zone_wip["regulation_type"] = user_input.get("regulation_type", REGULATION_DIRECT)

            # Opportunistic heating settings
            self._zone_wip["opportunistic"] = {
                "enabled": user_input.get("opportunistic_enabled", False),
                "threshold": user_input.get("opportunistic_threshold", 0.5),
            }

            # Zone-specific outdoor reset override
            # Check if any override option is set (implicit override_outdoor_reset)
            has_heat_override = (
                user_input.get("disable_heat_limit", False) or
                user_input.get("zone_never_heat_above") is not None
            )
            has_cool_override = (
                user_input.get("disable_cool_limit", False) or
                user_input.get("zone_never_cool_below") is not None
            )
            # Enable override if checkbox is checked OR any specific override is set
            override_enabled = (
                user_input.get("override_outdoor_reset", False) or
                has_heat_override or
                has_cool_override
            )

            outdoor_reset = {}
            if override_enabled:
                # Mark that override is enabled
                outdoor_reset["override_enabled"] = True

                # Process heat limit override
                if user_input.get("disable_heat_limit", False):
                    outdoor_reset["never_heat_above"] = None  # Disabled
                    outdoor_reset["heat_override_set"] = True
                elif user_input.get("zone_never_heat_above") is not None:
                    outdoor_reset["never_heat_above"] = user_input["zone_never_heat_above"]
                    outdoor_reset["heat_override_set"] = True

                # Process cool limit override
                if user_input.get("disable_cool_limit", False):
                    outdoor_reset["never_cool_below"] = None  # Disabled
                    outdoor_reset["cool_override_set"] = True
                elif user_input.get("zone_never_cool_below") is not None:
                    outdoor_reset["never_cool_below"] = user_input["zone_never_cool_below"]
                    outdoor_reset["cool_override_set"] = True

            # Always save outdoor_reset if override was enabled (even if empty limits)
            if outdoor_reset:
                self._zone_wip["outdoor_reset"] = outdoor_reset
            else:
                # Clear any existing outdoor_reset if override is disabled
                self._zone_wip.pop("outdoor_reset", None)

            # Propagate allow_command to all stage device instances
            allow_cmd_entities = set(user_input.get("allow_command_devices", []))
            self._propagate_allow_command(allow_cmd_entities)

            if self._zone_wip["regulation_type"] == REGULATION_PI:
                return await self.async_step_zone_pi_settings()
            else:
                return await self.async_step_zone_tou()

        wip = self._zone_wip or {}
        hysteresis = wip.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)
        min_runtime = wip.get(CONF_MIN_RUNTIME, DEFAULT_MIN_RUNTIME)
        opening_entities = wip.get(CONF_OPENING_ENTITIES, [])
        open_delay = wip.get(CONF_OPEN_DELAY, DEFAULT_OPEN_DELAY)
        close_delay = wip.get(CONF_CLOSE_DELAY, DEFAULT_CLOSE_DELAY)
        regulation_type = wip.get("regulation_type", REGULATION_DIRECT)

        # Opportunistic defaults
        opportunistic = wip.get("opportunistic", {})
        opportunistic_enabled = opportunistic.get("enabled", False)
        opportunistic_threshold = opportunistic.get("threshold", 0.5)

        # Outdoor reset defaults
        outdoor_reset = wip.get("outdoor_reset", {})
        has_override = outdoor_reset.get("override_enabled", False) or bool(outdoor_reset)
        disable_heat_limit = outdoor_reset.get("heat_override_set", False) and outdoor_reset.get("never_heat_above") is None
        disable_cool_limit = outdoor_reset.get("cool_override_set", False) and outdoor_reset.get("never_cool_below") is None
        zone_never_heat_above = outdoor_reset.get("never_heat_above") if not disable_heat_limit else None
        zone_never_cool_below = outdoor_reset.get("never_cool_below") if not disable_cool_limit else None

        # allow_command defaults
        all_stage_devices = self._get_all_stage_device_ids()
        existing_allow_cmd_ids = self._get_existing_allow_command_ids()

        schema_dict = {
            vol.Required("nav_action", default="next"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "back", "label": "← Back"},
                        {"value": "next", "label": "Next →"},
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Required(CONF_HYSTERESIS, default=hysteresis): NumberSelector(
                NumberSelectorConfig(
                    min=0.1,
                    max=5.0,
                    step=0.1,
                    unit_of_measurement="°F",
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(CONF_MIN_RUNTIME, default=min_runtime): NumberSelector(
                NumberSelectorConfig(
                    min=60,
                    max=1800,
                    step=60,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_OPENING_ENTITIES, default=opening_entities): EntitySelector(
                EntitySelectorConfig(domain="binary_sensor", multiple=True)
            ),
            vol.Required(CONF_OPEN_DELAY, default=open_delay): NumberSelector(
                NumberSelectorConfig(min=0, max=3600, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_CLOSE_DELAY, default=close_delay): NumberSelector(
                NumberSelectorConfig(min=0, max=3600, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX)
            ),
            # Opportunistic heating settings
            vol.Required("opportunistic_enabled", default=opportunistic_enabled): BooleanSelector(),
            vol.Optional("opportunistic_threshold", default=opportunistic_threshold): NumberSelector(
                NumberSelectorConfig(
                    min=0.1,
                    max=5.0,
                    step=0.1,
                    unit_of_measurement="°F",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            # Zone-specific outdoor reset override
            vol.Required("override_outdoor_reset", default=has_override): BooleanSelector(),
            vol.Required("disable_cool_limit", default=disable_cool_limit): BooleanSelector(),
            vol.Optional("zone_never_cool_below", description={"suggested_value": zone_never_cool_below}): NumberSelector(
                NumberSelectorConfig(
                    min=-20,
                    max=80,
                    step=1,
                    unit_of_measurement="°F",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required("disable_heat_limit", default=disable_heat_limit): BooleanSelector(),
            vol.Optional("zone_never_heat_above", description={"suggested_value": zone_never_heat_above}): NumberSelector(
                NumberSelectorConfig(
                    min=40,
                    max=120,
                    step=1,
                    unit_of_measurement="°F",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            # Regulation type
            vol.Required("regulation_type", default=regulation_type): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": REGULATION_DIRECT, "label": "Direct (send the zone target)"},
                        {"value": REGULATION_PI, "label": "PI (adjust the thermostat setpoint from the room error)"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }

        # Only show allow_command selector if zone has stage devices
        if all_stage_devices:
            schema_dict[vol.Optional("allow_command_devices", default=existing_allow_cmd_ids)] = SelectSelector(
                SelectSelectorConfig(
                    options=[{"value": eid, "label": eid} for eid in all_stage_devices],
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )

        return self.async_show_form(
            step_id="zone_settings",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "zone_name": wip.get(CONF_NAME, "Zone"),
            },
        )

    async def async_step_zone_pi_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zone wizard step 6: PI regulation settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Handle navigation
            action = user_input.get("nav_action", "next")
            if action == "back":
                return await self.async_step_zone_settings()

            self._zone_wip = self._zone_wip or {}
            self._zone_wip["pi_config"] = {
                "devices": user_input.get("pi_devices", []),
                "regulation_threshold": user_input.get("regulation_threshold", DEFAULT_REGULATION_THRESHOLD),
                "regulation_min_period": int(user_input.get("regulation_min_period", DEFAULT_REGULATION_MIN_PERIOD)),
            }
            return await self.async_step_zone_tou()

        wip = self._zone_wip or {}
        pi_config = wip.get("pi_config") or {}
        yaml_devices = self._get_yaml_config().get(CONF_DEVICES, {})
        choices = heat_capable_stage_devices(
            wip, self._get_ui_config().get(CONF_DEVICES, {}), yaml_devices,
        )
        pi_devices_default = selected_pi_devices(pi_config.get("devices"), choices, yaml_devices)

        return self.async_show_form(
            step_id="zone_pi_settings",
            data_schema=vol.Schema({
                vol.Required("nav_action", default="next"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "back", "label": "← Back"},
                            {"value": "next", "label": "Next →"},
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required("pi_devices", default=pi_devices_default): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": entity_id, "label": entity_id} for entity_id in choices],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required("regulation_threshold", default=pi_config.get("regulation_threshold", DEFAULT_REGULATION_THRESHOLD)): NumberSelector(
                    NumberSelectorConfig(min=MIN_REGULATION_THRESHOLD, max=MAX_REGULATION_THRESHOLD,
                                         step=0.1, unit_of_measurement="°F", mode=NumberSelectorMode.BOX)
                ),
                vol.Required("regulation_min_period", default=pi_config.get("regulation_min_period", DEFAULT_REGULATION_MIN_PERIOD)): NumberSelector(
                    NumberSelectorConfig(min=MIN_REGULATION_MIN_PERIOD, max=MAX_REGULATION_MIN_PERIOD,
                                         step=1, unit_of_measurement="min", mode=NumberSelectorMode.BOX)
                ),
            }),
            errors=errors,
            description_placeholders={
                "zone_name": wip.get(CONF_NAME, "Zone"),
                "pi_numbers": self._pi_number_entity_ids(),
            },
        )

    def _pi_number_entity_ids(self) -> str:
        """Name the edited zone's PI gain number entities, resolved from the entity registry."""
        if not self._zone_edit_id:
            return PI_NUMBERS_NEW_ZONE_TEXT
        registry = er.async_get(self.hass)
        # Resolve by unique id (as number_entities.py sets it); a missing entity shows its key.
        return ", ".join(
            registry.async_get_entity_id("number", DOMAIN, f"{DOMAIN}_{self._zone_edit_id}_{key}") or key
            for key in PI_NUMBER_KEYS
        )

    async def async_step_zone_tou(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zone wizard step 7: TOU (Time-of-Use) optimization settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Handle navigation
            action = user_input.get("nav_action", "next")
            if action == "back":
                # Back destination depends on whether PI is configured
                wip = self._zone_wip or {}
                if wip.get("regulation_type") == REGULATION_PI:
                    return await self.async_step_zone_pi_settings()
                return await self.async_step_zone_settings()

            self._zone_wip = self._zone_wip or {}
            tou_heat_enabled = user_input.get("tou_heat_enabled", False)
            tou_cool_enabled = user_input.get("tou_cool_enabled", False)

            if tou_heat_enabled or tou_cool_enabled:
                tou_block: dict[str, Any] = {"enabled": True}

                if tou_heat_enabled:
                    heat_pre = user_input.get("tou_heat_pre_condition_minutes", DEFAULT_TOU_PRE_CONDITION_MINUTES)
                    heat_relax = user_input.get("tou_heat_relaxation_amount", DEFAULT_TOU_RELAXATION_AMOUNT)
                    tou_block[CONF_TOU_HEAT] = {
                        CONF_TOU_PRE_CONDITION_MINUTES: int(heat_pre),
                        CONF_TOU_RELAXATION_AMOUNT: float(heat_relax),
                    }

                if tou_cool_enabled:
                    cool_pre = user_input.get("tou_cool_pre_condition_minutes", DEFAULT_TOU_PRE_CONDITION_MINUTES)
                    cool_relax = user_input.get("tou_cool_relaxation_amount", DEFAULT_TOU_RELAXATION_AMOUNT)
                    tou_block[CONF_TOU_COOL] = {
                        CONF_TOU_PRE_CONDITION_MINUTES: int(cool_pre),
                        CONF_TOU_RELAXATION_AMOUNT: float(cool_relax),
                    }

                self._zone_wip[CONF_TOU] = tou_block
            else:
                # Clear TOU config if both disabled
                self._zone_wip.pop(CONF_TOU, None)

            return self._save_zone_config()

        wip = self._zone_wip or {}
        # Load existing TOU config for this zone
        tou_config = wip.get(CONF_TOU, {})
        heat_config = tou_config.get(CONF_TOU_HEAT, {})
        cool_config = tou_config.get(CONF_TOU_COOL, {})
        tou_heat_enabled_default = CONF_TOU_HEAT in tou_config
        tou_cool_enabled_default = CONF_TOU_COOL in tou_config

        heat_pre_default = heat_config.get(CONF_TOU_PRE_CONDITION_MINUTES, DEFAULT_TOU_PRE_CONDITION_MINUTES)
        heat_relax_default = heat_config.get(CONF_TOU_RELAXATION_AMOUNT, DEFAULT_TOU_RELAXATION_AMOUNT)
        cool_pre_default = cool_config.get(CONF_TOU_PRE_CONDITION_MINUTES, DEFAULT_TOU_PRE_CONDITION_MINUTES)
        cool_relax_default = cool_config.get(CONF_TOU_RELAXATION_AMOUNT, DEFAULT_TOU_RELAXATION_AMOUNT)

        return self.async_show_form(
            step_id="zone_tou",
            data_schema=vol.Schema({
                vol.Required("nav_action", default="next"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "back", "label": "← Back"},
                            {"value": "next", "label": "Save & Finish →"},
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                # Heat TOU settings
                vol.Required("tou_heat_enabled", default=tou_heat_enabled_default): BooleanSelector(),
                vol.Optional(
                    "tou_heat_pre_condition_minutes",
                    default=heat_pre_default,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=240,
                        step=1,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "tou_heat_relaxation_amount",
                    default=heat_relax_default,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=10,
                        step=0.5,
                        unit_of_measurement="°F",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                # Cool TOU settings
                vol.Required("tou_cool_enabled", default=tou_cool_enabled_default): BooleanSelector(),
                vol.Optional(
                    "tou_cool_pre_condition_minutes",
                    default=cool_pre_default,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=240,
                        step=1,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    "tou_cool_relaxation_amount",
                    default=cool_relax_default,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=10,
                        step=0.5,
                        unit_of_measurement="°F",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }),
            errors=errors,
            description_placeholders={
                "zone_name": wip.get(CONF_NAME, "Zone"),
            },
        )

    def _get_climate_entities(self) -> list[str]:
        """Get list of available climate entities."""
        states = self._hass.states.async_all("climate")
        return [state.entity_id for state in states]
