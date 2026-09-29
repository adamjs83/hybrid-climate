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
READ_ONLY_FIELDS = frozenset({
    ("global", "outdoor_sensor"),
    ("devices", "idle.action"),
    ("devices", "idle.setback"),
    ("devices", "allow_command"),
    ("zones", "regulation"),
})
READ_ONLY_MESSAGE = "Read-only field; change it in the integration options UI"
READ_ONLY_DESCRIPTIONS = {
    "outdoor_sensor": "Outdoor temperature sensor",
    "idle.action": "Device action when idle",
    "idle.setback": "Temperature setback when idle",
    "allow_command": "Allow external device changes to update zones",
    "regulation": "Zone regulation method and devices",
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
UNKNOWN_REASON_DETAIL = "No definitive cause is recorded in cached runtime state"
UNCONTROLLED_MODE_DETAIL = (
    "Device reports {reported_mode}, but no zone owns it and the integration "
    "has not commanded {reported_mode}"
)
SENSOR_OUTLIER_THRESHOLD = 1.5
OUTLIER_COMPARE_EPSILON = 1e-6
WITHIN_TARGET_CODE = "within_target"
WITHIN_TARGET_DETAIL = "Cached temperature is within the zone's heat/cool targets"
