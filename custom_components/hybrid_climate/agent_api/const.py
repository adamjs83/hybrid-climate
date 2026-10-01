"""Purpose: Define canonical revision fields and ledger storage keys.

Key dependencies: Python built-in immutable collections.
Used by: Agent API revision serialization and later services.
"""

from __future__ import annotations

INTEGER_KEYS = frozenset({
    "_version", "stage", "min_runtime", "smoothing_samples", "time_escalation",
    "open_delay", "close_delay", "min_compressor_runtime",
    "min_compressor_off_time", "pre_condition_minutes",
})
COMPAT_KEYS = ("never_heat_above", "never_cool_below")
API_DATA = "hybrid_climate_agent_api"
SERVICE_GET_STATUS = "get_status"
SERVICE_GET_CONFIG = "get_config"
SERVICE_SET_CONFIG = "set_config"
SERVICE_RESTORE_CONTROL = "restore_control"
ENTRY_ID_KEY = "entry_id"
ZONE_ID_KEY = "zone_id"
INCLUDE_STRUCTURE_KEY = "include_structure"
GLOBAL_KEY = "global"
ZONES_KEY = "zones"
DEVICES_KEY = "devices"
OUTDOOR_FIELDS = frozenset({"settings.outdoor_reset.heat", "settings.outdoor_reset.cool"})
OUTDOOR_KEYS = {"heat": "never_heat_above", "cool": "never_cool_below"}
PATCH_SCOPES = ("global", "zones", "devices")
STAGE_ADDRESS_KEYS = frozenset({"direction", "index"})
STAGE_PATCH_KEY = "stages"
SOURCE_UI_CONFIG = "ui_config"
SOURCE_OPTIONS_OVERRIDE = "options_override"
SOURCE_NUMBER_ENTITY = "number_entity"
SOURCE_DEFAULT = "default"
SOURCE_AUTO_CREATED = "auto_created"
SOURCE_YAML = "yaml"
SOURCE_UI = "ui"
READ_ONLY_FIELDS = frozenset({
    ("global", "outdoor_sensor"),
    ("global", "outdoor_sensors"),
    ("devices", "idle.action"),
    ("devices", "idle.setback"),
    ("devices", "allow_command"),
    ("devices", "capabilities"),
    ("devices", "capabilities_source"),
    ("zones", "regulation"),
})
READ_ONLY_MESSAGE = "Read-only field; change it in the integration options UI"
# sensors.weights is deliberately absent from READ_ONLY_FIELDS: it has no FIELDS row at
# all, so set_config already rejects it as an unknown field (accessors.field_for), the
# same path a genuinely nonexistent field takes. It only needs a read-only get_config entry.
SENSORS_WEIGHTS_FIELD = "sensors.weights"
# outdoor_thresholds is likewise absent from READ_ONLY_FIELDS: it has no FIELDS
# row (never_heat_above/never_cool_below remain independently settable), so
# set_config already rejects it as an unknown field. It only needs a read-only
# get_config entry, at both global and per-zone (effective) scope.
OUTDOOR_THRESHOLDS_FIELD = "outdoor_thresholds"
READ_ONLY_DESCRIPTIONS = {
    "outdoor_sensor": "Outdoor temperature sensor",
    "outdoor_sensors": "Outdoor temperature sources in priority order",
    "idle.action": "Device action when idle",
    "idle.setback": "Temperature setback when idle",
    "allow_command": "Allow external device changes to update zones",
    "capabilities": "Loaded heat and cool capabilities",
    "capabilities_source": "Origin of loaded device capabilities",
    "regulation": "Zone regulation method and devices",
    SENSORS_WEIGHTS_FIELD: "Effective per-sensor weight used for weighted aggregation",
    OUTDOOR_THRESHOLDS_FIELD: "Effective outdoor lockout limits, release points, and hysteresis",
}
READ_ONLY_TEMPERATURE_UNIT = "°F"
MALFORMED_STAGE_STORAGE_WARNING = (
    "Malformed zone stage storage for device %s; using default command-permission source"
)
PRESET_SERVICE = "climate.set_preset_mode"
DRY_RUN_KEY = "dry_run"
REASON_KEY = "reason"
REASON_REQUIRED_MESSAGE = "reason is required"
EXPECTED_HASH_KEY = "expected_hash"
ERROR_PENDING = "pending"
ERROR_STALE_REVISION = "stale_revision"
ERROR_RELOAD_FAILED = "reload_failed"
ERROR_ENTRY_REMOVED = "entry_removed"
ERROR_AUDIT_FAILED = "audit_failed"
PENDING_MESSAGE = "Stored configuration is not active; inspect get_status and retry reload"
STALE_MESSAGE = "Configuration changed; get_config and dry-run again"
RELOAD_FAILED_MESSAGE = "Saved options did not become active"
FAILED_UNLOAD_STATE = "FAILED_UNLOAD"
PENDING_SETUP_RECOVERY_MESSAGE = (
    "Fix the setup failure, then reload this integration from Settings → Devices & services. "
    "Saved options were not rolled back."
)
PENDING_UNLOAD_RECOVERY_MESSAGE = (
    "Fix the device-release failure, then restart Home Assistant. "
    "Saved options were not rolled back."
)
AUDIT_NOTIFICATION_TITLE = "Hybrid Climate configuration change"
AUDIT_LOGBOOK_NAME = "Hybrid Climate Agent API"

REASON_DETAILS = {
    "outdoor_heat_lockout": "Cached outdoor permission blocks heating demand",
    "outdoor_cool_lockout": "Cached outdoor permission blocks cooling demand",
    "master_off": "Master is off",
    "zone_off": "User selected off for this zone",
    "sensor_failure": "Zone temperature sensors failed",
    "opening_lockout": "Opening contact lockout is active",
    "compressor_hold": "A device is held by compressor timing protection",
    "device_conflict": "Cached device conflict blocks a configured device",
    "device_command_failed": "A requested device command failed",
}
UNKNOWN_REASON_CODE = "unknown"
UNKNOWN_REASON_DETAIL = "No definitive cause is recorded in cached runtime state"
UNCONTROLLED_MODE_DETAIL = (
    "Device reports {reported_mode}, but no zone owns it and the integration "
    "has not commanded {reported_mode}"
)
SENSOR_OUTLIER_THRESHOLD = 1.5
OUTLIER_COMPARE_EPSILON = 1e-6
OUTLIER_ACTION_FLAGGED_ONLY = "flagged_only"
WITHIN_TARGET_CODE = "within_target"
WITHIN_TARGET_DETAIL = "Cached temperature is within the zone's heat/cool targets"
HEATING_DEMAND_CODE = "heating_demand"
HEATING_DEMAND_DETAIL = "Cached hvac_action reports active heating demand"
COOLING_DEMAND_CODE = "cooling_demand"
COOLING_DEMAND_DETAIL = "Cached hvac_action reports active cooling demand"
ABOVE_COOL_TARGET_BELOW_START_CODE = "above_cool_target_below_start"
ABOVE_COOL_TARGET_BELOW_START_DETAIL = (
    "Cached temperature is above the cool target but not yet past the cooling start threshold"
)
BELOW_HEAT_TARGET_BELOW_START_CODE = "below_heat_target_below_start"
BELOW_HEAT_TARGET_BELOW_START_DETAIL = (
    "Cached temperature is below the heat target but not yet past the heating start threshold"
)
STAGE_WITHOUT_USABLE_DEVICES_CODE = "stage_without_usable_devices"
STAGE_WITHOUT_USABLE_DEVICES_DETAIL = "No device in the selected stage can serve its direction"

# All codes zone_reasons() can return: every REASON_DETAILS key, the demand/within_target/
# below-start codes, and unknown. This is the enum `options` for the reason sensor (spec §3).
ZONE_REASON_CODES: tuple[str, ...] = (
    *REASON_DETAILS.keys(),
    HEATING_DEMAND_CODE,
    COOLING_DEMAND_CODE,
    WITHIN_TARGET_CODE,
    ABOVE_COOL_TARGET_BELOW_START_CODE,
    BELOW_HEAT_TARGET_BELOW_START_CODE,
    STAGE_WITHOUT_USABLE_DEVICES_CODE,
    UNKNOWN_REASON_CODE,
)

# Public get_status.zones.<id>.tou.mode values. The internal TOU state machine
# (tou_manager.py / const.py TOU_STATE_*) spells peak relaxation "peak_relaxed";
# the Agent API publishes the more descriptive "peak_relaxation" instead.
TOU_MODE_PEAK_RELAXATION = "peak_relaxation"
TOU_MODE_PRE_CONDITIONING = "pre_conditioning"

# get_status.devices.<id>.control.reason values (spec §7.6, v0.13.2 §1 amendments
# A4/A16, §3 amendment A10). First match wins, in this order: not_referenced ->
# manual_override -> owned_active -> awaiting_startup_takeover |
# awaiting_control_restore -> taken_over_at_startup -> control_restored ->
# released_idle -> referenced_without_capability -> never_owned_since_start.
# The awaiting_* reason depends on the current pass's source (StartupTakeover.source);
# the applied_* reason depends on which pass last applied the command
# (StartupTakeover.applied_source), not the current pass's source. manual_override
# comes from ManualOverrideTracker, independent of the takeover/restore pass state.
CONTROL_REASON_NOT_REFERENCED = "not_referenced"
CONTROL_REASON_MANUAL_OVERRIDE = "manual_override"
CONTROL_REASON_OWNED_ACTIVE = "owned_active"
CONTROL_REASON_AWAITING_STARTUP_TAKEOVER = "awaiting_startup_takeover"
CONTROL_REASON_AWAITING_CONTROL_RESTORE = "awaiting_control_restore"
CONTROL_REASON_TAKEN_OVER_AT_STARTUP = "taken_over_at_startup"
CONTROL_REASON_CONTROL_RESTORED = "control_restored"
CONTROL_REASON_RELEASED_IDLE = "released_idle"
CONTROL_REASON_NEVER_OWNED_SINCE_START = "never_owned_since_start"
CONTROL_REASON_MISSING_STAGE_CAPABILITY = "referenced_without_capability"
CONTROL_REASON_CODES = frozenset({
    CONTROL_REASON_NOT_REFERENCED, CONTROL_REASON_MANUAL_OVERRIDE, CONTROL_REASON_OWNED_ACTIVE,
    CONTROL_REASON_AWAITING_STARTUP_TAKEOVER, CONTROL_REASON_AWAITING_CONTROL_RESTORE,
    CONTROL_REASON_TAKEN_OVER_AT_STARTUP, CONTROL_REASON_CONTROL_RESTORED,
    CONTROL_REASON_RELEASED_IDLE, CONTROL_REASON_MISSING_STAGE_CAPABILITY,
    CONTROL_REASON_NEVER_OWNED_SINCE_START,
})

# Cached status projection keys shared with history-friendly entities
STATUS_REASON_CODE = "code"
STATUS_AGGREGATION_SPREAD = "spread"
STATUS_REPORTED_MODE = "reported_mode"
STATUS_UNCONTROLLED_ACTIVE_MODE = "uncontrolled_active_mode"
STATUS_OVERRIDE = "override"
