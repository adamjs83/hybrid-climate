"""Purpose: Constants shared by the options pages (v0.17.0), kept out of the near-full const.py.

Key dependencies: None.
Used by: options_flow/base.py, structural.py, handler.py, zones.py, conflicts.py, presets.py, shared_equipment.py, devices.py,
zone_pages/*, takeover_skip.py, agent_api/revision.py,
agent_api/config_patch.py.
"""
from __future__ import annotations

# ui_config._last_save = {"structural": bool, "at": iso timestamp}, written by every
# options page save and read once by the reload that follows (spec v0.17.0 §3).
CONF_LAST_SAVE = "_last_save"
LAST_SAVE_STRUCTURAL = "structural"
LAST_SAVE_AT = "at"

# Revision-ledger key holding, per entry id, the last save marker's "at" a setup consumed.
LEDGER_CONSUMED_SAVES = "consumed_saves"

# Options menus (v0.17.0 §1): top menu, shared equipment menu and the per-zone menu steps.
STEP_MENU = "menu"
STEP_GLOBAL_SETTINGS = "global_settings"
STEP_ZONES = "zones"
STEP_DEVICES = "devices"
STEP_PRESETS = "presets"
STEP_SHARED_EQUIPMENT = "shared_equipment"
STEP_HEAT_SOURCES = "heat_sources"
STEP_CONFLICTS = "conflicts"
STEP_ZONE_MENU = "zone_menu"
STEP_ZONE_BASICS = "zone_basics"
STEP_ZONE_SETPOINTS = "zone_setpoints"
STEP_ZONE_HEAT_STAGES = "zone_heat_stages"
STEP_ZONE_COOL_STAGES = "zone_cool_stages"
STEP_ZONE_BEHAVIOUR = "zone_behaviour"
STEP_ZONE_REGULATION = "zone_regulation"
STEP_ZONE_TOU = "zone_tou"
STEP_DELETE_CONFIRM = "delete_confirm"

# Zone pages (§1): nav first. An edit page saves alone; the add path (§0.5) is
# Basics → Heating stages → Cooling stages and saves once on the last page.
NAV_FIELD = "nav_action"
NAV_CANCEL = "cancel"
NAV_SAVE = "save"
NAV_NEXT = "next"
NAV_BACK = "back"
_NAV_LABELS = {NAV_CANCEL: "← Cancel", NAV_SAVE: "Save", NAV_NEXT: "Next →", NAV_BACK: "← Back"}
PAGE_NAV_OPTIONS = [{"value": v, "label": _NAV_LABELS[v]} for v in (NAV_CANCEL, NAV_SAVE)]
CREATE_FIRST_NAV_OPTIONS = [{"value": v, "label": _NAV_LABELS[v]} for v in (NAV_CANCEL, NAV_NEXT)]
CREATE_MIDDLE_NAV_OPTIONS = [{"value": v, "label": _NAV_LABELS[v]} for v in (NAV_BACK, NAV_NEXT)]
CREATE_LAST_NAV_OPTIONS = [{"value": v, "label": _NAV_LABELS[v]} for v in (NAV_BACK, NAV_SAVE)]
FIELD_ZONE_ID = "zone_id"
ERROR_BASE = "base"
ERROR_ZONE_ID_REQUIRED = "zone_id_required"
ERROR_ZONE_ID_EXISTS = "zone_id_exists"
ERROR_ZONE_NAME_REQUIRED = "zone_name_required"
ERROR_WEIGHTS_NEEDED = "weights_needed"  # weighted chosen: set each sensor's weight before saving
# Setpoints page: occupancy fields, offset range (°F) and the setpoint number entity note.
FIELD_OCCUPANCY_ENABLED = "occupancy_enabled"
FIELD_OCCUPIED_OFFSET = "occupied_offset"
FIELD_UNOCCUPIED_OFFSET = "unoccupied_offset"
CONF_SETPOINT_DEFAULT = "default"
CONF_SETPOINT_OCCUPIED = "occupied"
CONF_SETPOINT_UNOCCUPIED = "unoccupied"
FALLBACK_DEFAULT_SETPOINT = 72  # the default setpoint a zone without one is stored with (zone_save.py)
OCCUPANCY_OFFSET_RANGE = (-10, 10, 0.5)  # min, max, step
TEMPERATURE_UNIT = "°F"
MINUTES_UNIT = "min"
NUMBER_DOMAIN = "number"
SETPOINT_NUMBERS_NONE_TEXT = "created when the zone is saved"
# Stage pages: the per-kind "enable" toggles.
FIELD_HAS_HEAT_STAGES = "has_heat_stages"
FIELD_HAS_COOL_STAGES = "has_cool_stages"

# Behaviour page (§1, §0.6): settings, door contacts, opportunistic heating, outdoor limits, thermostat sync.
FIELD_OPPORTUNISTIC_ENABLED = "opportunistic_enabled"
FIELD_OPPORTUNISTIC_THRESHOLD = "opportunistic_threshold"
FIELD_HEAT_LIMIT_MODE = "heat_limit_mode"
FIELD_COOL_LIMIT_MODE = "cool_limit_mode"
FIELD_ZONE_NEVER_HEAT_ABOVE = "zone_never_heat_above"
FIELD_ZONE_NEVER_COOL_BELOW = "zone_never_cool_below"
FIELD_ALLOW_COMMAND_DEVICES = "allow_command_devices"
CONF_ENABLED = "enabled"
# settings.outdoor_reset keys besides the two limits (as the v0.16.x wizard stored them).
CONF_OVERRIDE_ENABLED = "override_enabled"
CONF_HEAT_OVERRIDE_SET = "heat_override_set"
CONF_COOL_OVERRIDE_SET = "cool_override_set"
# Outdoor limit mode per direction: the house (global) limit, no limit, or this zone's value.
LIMIT_MODE_INHERIT = "inherit"
LIMIT_MODE_DISABLED = "disabled"
LIMIT_MODE_VALUE = "value"
LIMIT_MODE_OPTIONS = [
    {"value": LIMIT_MODE_INHERIT, "label": "Use house limit"},
    {"value": LIMIT_MODE_DISABLED, "label": "No limit"},
    {"value": LIMIT_MODE_VALUE, "label": "This zone's value (below)"},
]
SECONDS_UNIT = "s"
OPENING_DOMAIN = "binary_sensor"
# (min, max, step) of the Behaviour page's number fields, as the v0.16.x zone_settings step had them.
HYSTERESIS_RANGE = (0.1, 5.0, 0.1)
MIN_RUNTIME_RANGE = (60, 1800, 60)
OPENING_DELAY_RANGE = (0, 3600, 1)
OPPORTUNISTIC_THRESHOLD_RANGE = (0.1, 5.0, 0.1)
NEVER_HEAT_ABOVE_RANGE = (40, 120, 1)
NEVER_COOL_BELOW_RANGE = (-20, 80, 1)

# Regulation page (§2, owner decision 5): a `heating` section and one `cool_device_N` section per cooling device.
FIELD_REGULATION_TYPE = "regulation_type"
FIELD_PI_DEVICES = "pi_devices"
REGULATION_DIRECT_LABEL = "Direct (send the zone target)"
REGULATION_PI_LABEL = "PI (adjust the thermostat setpoint from the room error)"
SECTION_HEATING = "heating"
SECTION_COOL_DEVICE = "cool_device_{index}"
MAX_REGULATION_COOL_DEVICES = 6  # devices beyond it keep their stored settings untouched
# Description notes (placeholders heating_note, cooling_note); "" when the zone has no such section.
REGULATION_NUMBER_VALUE = "{entity_id} = {value}"
REGULATION_NUMBERS_NEW = "created when the zone is saved"
HEAT_NUMBERS_DIRECT = "these appear when PI is chosen and saved"
HEATING_NOTE = (
    "**Heating.** With PI, choose which heating thermostats PI adjusts and how often a new setpoint is sent. "
    "PI gains (number entities; tune them there): {numbers}.\n\n"
)
COOLING_NOTE = (
    "**Cooling.** Each cooling device has its own section; the setting is stored on the device.\n\n"
    "{devices}\n\nCooling PI gains (number entities; tune them there): {numbers}.\n\n"
)
COOL_DEVICE_LINE = "- Cooling device {index}: {name} ({entity_id})."
COOL_SHARED_ONE = " Shared with {zones}; the setting applies to both."
COOL_SHARED_MANY = " Shared with {zones}; the setting applies to all of them."
COOL_BEYOND_CAP_LINE = "- Not shown (only {cap} cooling devices fit this page; their settings stay as saved): {devices}"
LIST_JOIN = ", "
# Device page: the read-only cooling regulation line (placeholder cooling_regulation).
DEVICE_COOLING_LINE = "\n\nCooling regulation: {mode} (set under Zones → {zones} → Regulation)."
DEVICE_COOLING_UNUSED = (
    "\n\nCooling regulation: {mode}. No zone's cooling stages use this device; once one does, set it on "
    "that zone's Regulation page."
)

# Time-of-use page: fields, ranges and the note shown without a global rate sensor.
FIELD_TOU_HEAT_ENABLED = "tou_heat_enabled"
FIELD_TOU_HEAT_PRE = "tou_heat_pre_condition_minutes"
FIELD_TOU_HEAT_RELAX = "tou_heat_relaxation_amount"
FIELD_TOU_COOL_ENABLED = "tou_cool_enabled"
FIELD_TOU_COOL_PRE = "tou_cool_pre_condition_minutes"
FIELD_TOU_COOL_RELAX = "tou_cool_relaxation_amount"
TOU_PRE_CONDITION_RANGE = (0, 240, 1)
TOU_RELAXATION_RANGE = (0, 10, 0.5)
TOU_NO_RATE_SENSOR_NOTE = (
    "No TOU rate sensor is set under Global settings, so these adjustments have no effect until one is. "
)

# Zone list label: "Basement — heat 2 stages, cool 1 — heating PI, cooling: compensation".
ZONE_LABEL_SEPARATOR = " — "
ZONE_LABEL_STAGES = "{kind} {count}"
ZONE_LABEL_STAGE_NOUN = (" stage", " stages")  # singular, plural; appended to the first stage kind
ZONE_LABEL_NO_STAGES = "no stages"
ZONE_LABEL_HEATING = "heating {mode}"
ZONE_LABEL_HEATING_PI = "PI"
ZONE_LABEL_COOLING_JOIN = "/"
ZONE_LABEL_DELETE = "🗑️ Delete {name}"

# Delete confirmation (§0.10): the item line, the reference lines and the two navigation choices.
DELETE_KIND_ZONE = "zone"
DELETE_KIND_HEAT_SOURCE = "heat_source"
DELETE_KIND_RULE = "rule"
DELETE_NAV_CANCEL = "cancel"
DELETE_NAV_DELETE = "delete"
DELETE_NAV_OPTIONS = [
    {"value": DELETE_NAV_CANCEL, "label": "← Cancel"},
    {"value": DELETE_NAV_DELETE, "label": "Delete"},
]
DELETE_ITEM_ZONE = "zone {name}"
DELETE_ITEM_HEAT_SOURCE = "heat source group {name}"
DELETE_ITEM_RULE = "rule for {device} ({mode} in {zone})"
DELETE_NO_REFERENCES = "Nothing else refers to it."
DELETE_REFERENCES_HEADER = "Still referring to it (not changed by the delete):"
DELETE_REFERENCE_LINE = "- {reference}"
REF_RULE = "Rule: {device} ({mode} in {zone})"
REF_ZONE_STAGE1_HEAT = "Zone {name} (stage 1 heat: {devices})"
REF_RULE_DEVICE = "Device: {device}"
REF_RULE_BLOCKS_HEAT = "Blocks heating on: {devices}"
REF_RULE_BLOCKS_COOL = "Blocks cooling on: {devices}"
REF_UNKNOWN = "?"

# Mutex rule device-block keys (shared condenser support), used by conflicts.py and delete_confirm.py.
CONF_BLOCKED_DEVICES_HEAT = "blocked_devices_heat"
CONF_BLOCKED_DEVICES_COOL = "blocked_devices_cool"
YAML_RULE_NOTE = (
    "This rule comes from configuration.yaml. Saving adds a UI rule alongside it; "
    "the YAML rule stays until you remove it from configuration.yaml."
)

# Preset page: which zone setpoints a mode uses ("Away uses the Sleep setpoints.").
PRESET_REMAP_TEXT = "{mode} uses the {setpoint} setpoints."
PRESET_SETPOINT_LABELS = {"default": "Default", "away": "Away", "sleep": "Sleep", "vacation": "Vacation"}
