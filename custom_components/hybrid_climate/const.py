"""Purpose: Define shared configuration keys and runtime constants.

Key dependencies: None.
Used by: Hybrid Climate runtime and configuration modules.
"""

DOMAIN = "hybrid_climate"
VERSION = "0.7.0"  # UI config as source of truth, YAML import on first boot

# Master modes
MODE_HOME = "home"
MODE_AWAY = "away"
MODE_SLEEP = "sleep"
MODE_VACATION = "vacation"
MODE_BOOST = "boost"
MODE_OFF = "off"

MASTER_MODES = [MODE_HOME, MODE_AWAY, MODE_SLEEP, MODE_VACATION, MODE_BOOST, MODE_OFF]

# HVAC modes for zones
HVAC_MODE_HEAT = "heat"
HVAC_MODE_COOL = "cool"
HVAC_MODE_OFF = "off"
HVAC_MODE_AUTO = "auto"
HVAC_MODE_HEAT_COOL = "heat_cool"
ATTR_HVAC_MODES = "hvac_modes"

# HVAC actions
HVAC_ACTION_HEATING = "heating"
HVAC_ACTION_COOLING = "cooling"
HVAC_ACTION_IDLE = "idle"
HVAC_ACTION_OFF = "off"

# Device capabilities
CAPABILITY_HEAT = "heat"
CAPABILITY_COOL = "cool"
FIRST_STAGE_NUMBER = 1
STAGE_UNUSABLE_MISSING_CAPABILITY = "missing_capability"
STAGE_UNUSABLE_UNAVAILABLE = "unavailable"
STAGE_UNUSABLE_BLOCKED = "blocked"
STAGE_UNUSABLE_NOT_FOUND = "not_found"
CLIMATE_ENTITY_PREFIX = "climate."
REGULATION_IGNORED_DEVICE_WARNING = "Zone %s: ignoring PI regulation device %s (not heat-capable)"

# Device idle behavior (what to do when not actively heating/cooling)
IDLE_ACTION_OFF = "off"  # Turn device off
IDLE_ACTION_SETBACK = "setback"  # Set to target +/- setback degrees
IDLE_ACTIONS = [IDLE_ACTION_OFF, IDLE_ACTION_SETBACK]
IDLE_SETPOINT_BASIS_LOCKOUT_FLOOR = "lockout_floor"
IDLE_SETPOINT_BASIS_SETBACK = "setback"
DEFAULT_IDLE_ACTION = IDLE_ACTION_OFF
DEFAULT_IDLE_SETBACK = 5.0  # degrees

# Sensor aggregation methods
AGGREGATION_AVERAGE = "average"
AGGREGATION_MIN = "min"
AGGREGATION_MAX = "max"
AGGREGATION_MEDIAN = "median"
AGGREGATION_WEIGHTED = "weighted"
DEFAULT_SENSOR_WEIGHT = 1.0
MIN_SENSOR_WEIGHT = 0.1  # UI selector only; schema accepts any positive weight.
MAX_SENSOR_WEIGHT = 10.0
SENSOR_WEIGHT_STEP = 0.1

# Defaults
DEFAULT_HYSTERESIS = 0.5
DEFAULT_MIN_RUNTIME = 300  # 5 minutes
DEFAULT_UPDATE_INTERVAL = 60  # 1 minute
DEFAULT_HEAT_THRESHOLD = 1.0
DEFAULT_COOL_THRESHOLD = 1.0
DEFAULT_COOL_STAGE_1_THRESHOLD = -1.0
DEFAULT_HEAT_COOL_DEADBAND = 4.0  # °F offset from heat setpoint when no cool setpoint configured
DEFAULT_COOL_SETPOINT = 76.0  # Safe floor for cooling when no dedicated cool value exists
DEFAULT_AWAY_COOL_RAISE = 4.0  # Cooling setback when an away cool value is absent
COOL_SLIDER_MIN = 60.0
COOL_SLIDER_MAX = 95.0
COOL_SLIDER_STEP = 0.5
DEFAULT_TIME_ESCALATION = 1800  # 30 minutes
DEFAULT_SENSOR_STALE_TIME = 600  # 10 minutes - use last known value
OUTDOOR_TEMP_STALE_SECONDS = 600  # Last outdoor reading remains valid for 10 minutes
OUTDOOR_LOCKOUT_HYSTERESIS = 1.0  # Degrees between lockout entry and release
CONF_LOCKOUT_HEAT_FLOOR = "lockout_heat_floor"
DEFAULT_LOCKOUT_HEAT_FLOOR = 55.0
MIN_LOCKOUT_HEAT_FLOOR = 40
MAX_LOCKOUT_HEAT_FLOOR = 60
LOCKOUT_HEAT_FLOOR_STEP = 0.5
HEAT_COOL_REVERSAL_SECONDS = 300  # Minimum time off before restarting or reversing
MIN_HEAT_COOL_GAP = 1.0  # Room-temperature travel required before reversing crossed targets
SENSOR_RESTORE_GRACE_PERIOD_SECONDS = 300  # 5 min grace for restored temps after restart
SENSOR_STATUS_FAILED = "failed"  # sensor_status value when sensors offline past grace period
DEFAULT_SMOOTHING_SAMPLES = 1  # no smoothing by default (1 = use raw value)
MIN_SMOOTHING_SAMPLES = 1
MAX_SMOOTHING_SAMPLES = 100

# Temperature validation bounds
TEMP_MIN_VALID = -50
TEMP_MAX_VALID = 150

# Config keys
CONF_OUTDOOR_SENSOR = "outdoor_sensor"
CONF_OUTDOOR_SENSORS = "outdoor_sensors"
OUTDOOR_ENTITY_DOMAINS = ("sensor", "weather")
OUTDOOR_STATUS_OK = "ok"
OUTDOOR_STATUS_MISSING = "missing"
OUTDOOR_STATUS_UNAVAILABLE = "unavailable"
OUTDOOR_STATUS_INVALID = "invalid"
CONF_MASTER = "master"
CONF_MASTER_NAME = "master_name"
CONF_CONFLICTS = "conflicts"
CONF_DEVICES = "devices"
CONF_ZONES = "zones"

# UI config storage keys
CONF_UI_CONFIG = "ui_config"
CONF_NUMBER_VALUES = "number_values"
CONF_UI_GLOBAL = "global"
CONF_UI_VERSION = "_version"

# Runtime setup bookkeeping
DATA_ACTIVE_REVISION = "active_revision"
DATA_PREPARED_OPTIONS = "prepared_options"

# Master config
CONF_OCCUPANCY_ENTITY = "occupancy_entity"
CONF_MODES = "modes"
CONF_USE_ZONE_DEFAULTS = "use_zone_defaults"
CONF_USE_ZONE_AWAY_SETPOINTS = "use_zone_away_setpoints"  # Deprecated
CONF_USE_ZONE_SETPOINT = "use_zone_setpoint"
CONF_SETPOINT_OFFSET = "setpoint_offset"
CONF_SKIP_TIME_ESCALATION = "skip_time_escalation"
CONF_DISABLE_ALL = "disable_all"

# Setpoint names
CONF_SLEEP = "sleep"
CONF_VACATION = "vacation"

# Conflict config
CONF_OUTDOOR_RESET = "outdoor_reset"
CONF_NEVER_HEAT_ABOVE = "never_heat_above"
CONF_NEVER_COOL_BELOW = "never_cool_below"
CONF_DEVICE_MUTEX = "device_mutex"
CONF_WHEN = "when"
CONF_THEN = "then"
CONF_DEVICE = "device"
CONF_MODE = "mode"
CONF_FOR_ZONE = "for_zone"
CONF_BLOCK_HEAT = "block_heat"
CONF_BLOCK_COOL = "block_cool"

# Device config
CONF_ENTITY_ID = "entity_id"
CONF_CAPABILITIES = "capabilities"
CONF_IDLE = "idle"
CONF_IDLE_ACTION = "action"
CONF_IDLE_SETBACK = "setback"
CONF_ALLOW_COMMAND = "allow_command"
CONF_COMPRESSOR_GROUP = "compressor_group"
CONF_MIN_COMPRESSOR_RUNTIME = "min_compressor_runtime"
CONF_MIN_COMPRESSOR_OFF_TIME = "min_compressor_off_time"
DEFAULT_ALLOW_COMMAND = False  # Device changes don't propagate to zone by default

# Zone config
CONF_NAME = "name"
CONF_SENSORS = "sensors"
CONF_INDOOR = "indoor"
CONF_AGGREGATION = "aggregation"
CONF_WEIGHTS = "weights"
CONF_SMOOTHING_SAMPLES = "smoothing_samples"
CONF_SETPOINTS = "setpoints"
CONF_DEFAULT = "default"
CONF_AWAY = "away"
CONF_OCCUPIED = "occupied"
CONF_UNOCCUPIED = "unoccupied"
CONF_HEAT_STAGES = "heat_stages"
CONF_COOL_STAGES = "cool_stages"
CONF_SETTINGS = "settings"
CONF_OPENINGS = "openings"
CONF_OPENING_ENTITIES = "entities"
CONF_OPEN_DELAY = "open_delay"
CONF_CLOSE_DELAY = "close_delay"
DEFAULT_OPEN_DELAY = 60
DEFAULT_CLOSE_DELAY = 60

# Stage config
CONF_STAGE = "stage"
CONF_THRESHOLD = "threshold"
CONF_TIME_ESCALATION = "time_escalation"
CONF_CONDITIONS = "conditions"
CONF_OUTDOOR_TEMP_MIN = "outdoor_temp_min"
CONF_OUTDOOR_TEMP_MAX = "outdoor_temp_max"

# Settings config
CONF_HYSTERESIS = "hysteresis"
CONF_MIN_RUNTIME = "min_runtime"
CONF_UPDATE_INTERVAL = "update_interval"

# Regulation config (PI controller for underlying devices)
CONF_REGULATION = "regulation"
CONF_REGULATION_TYPE = "type"
CONF_KP = "kp"
CONF_KI = "ki"
CONF_K_EXT = "k_ext"
CONF_BALANCE_POINT = "balance_point"
CONF_OFFSET_MAX = "offset_max"
CONF_STABILIZATION_THRESHOLD = "stabilization_threshold"
CONF_ACCUMULATED_ERROR_THRESHOLD = "accumulated_error_threshold"
CONF_INTEGRAL_RESET_THRESHOLD = "integral_reset_threshold"
CONF_INTEGRAL_RESET_FACTOR = "integral_reset_factor"
CONF_INTEGRAL_DECAY_HALFLIFE = "integral_decay_halflife"

# Regulation types
REGULATION_DIRECT = "direct"
REGULATION_PI = "pi"

# Regulation defaults
DEFAULT_KP = 1.0
DEFAULT_KI = 0.01
DEFAULT_K_EXT = 0.0  # Disabled by default
DEFAULT_BALANCE_POINT = 65.0  # Outdoor temp where no heating/cooling offset needed
DEFAULT_OFFSET_MAX = 10.0
DEFAULT_STABILIZATION_THRESHOLD = 0.1
DEFAULT_ACCUMULATED_ERROR_THRESHOLD = 240.0
DEFAULT_INTEGRAL_RESET_THRESHOLD = 2.5  # °F change triggers partial reset
DEFAULT_INTEGRAL_RESET_FACTOR = 0.3  # Fraction of integral to keep on reset
DEFAULT_INTEGRAL_DECAY_HALFLIFE = 120.0  # Minutes for idle decay (0 = disabled)

# Heat source config (for opportunistic heating)
CONF_HEAT_SOURCES = "heat_sources"
CONF_OPPORTUNISTIC = "opportunistic"
CONF_OPPORTUNISTIC_THRESHOLD = "opportunistic_threshold"

# Opportunistic heating defaults
DEFAULT_OPPORTUNISTIC_THRESHOLD = 0.5  # Piggyback if error > 0.5°

# TOU (Time-of-Use) rate optimization
CONF_TOU = "tou"
CONF_TOU_RATE_SENSOR = "tou_rate_sensor"
CONF_LEGACY_RATE_SENSOR = "rate_sensor"
CONF_TOU_HEAT = "heat"
CONF_TOU_COOL = "cool"
CONF_TOU_PRE_CONDITION_MINUTES = "pre_condition_minutes"
CONF_TOU_RELAXATION_AMOUNT = "relaxation_amount"

# TOU defaults
DEFAULT_TOU_PRE_CONDITION_MINUTES = 60
DEFAULT_TOU_RELAXATION_AMOUNT = 2.0  # °F

# TOU rate period states (expected from external sensor)
TOU_PERIOD_SUPER_OFF_PEAK = "super_off_peak"
TOU_PERIOD_OFF_PEAK = "off_peak"
TOU_PERIOD_PEAK = "peak"

# TOU zone states (exposed via sensor entities)
TOU_STATE_NORMAL = "normal"
TOU_STATE_PRE_CONDITIONING = "pre_conditioning"
TOU_STATE_PEAK_RELAXED = "peak_relaxed"

# TOU sensor attributes
ATTR_NEXT_PEAK_START = "next_peak_start"

# Attributes
ATTR_CURRENT_STAGE = "current_stage"
ATTR_ACTIVE_DEVICES = "active_devices"
ATTR_REGULATION_OFFSET = "regulation_offset"
ATTR_ACCUMULATED_ERROR = "accumulated_error"
ATTR_REGULATED_SETPOINT = "regulated_setpoint"
ATTR_BLOCKED_DEVICES = "blocked_devices"
ATTR_SENSOR_STATUS = "sensor_status"
ATTR_OPENING_LOCKOUT = "opening_lockout"
ATTR_OPENING_STATUS = "opening_status"
ATTR_TIME_IN_STAGE = "time_in_stage"
ATTR_SENSOR_VALUES = "sensor_values"
ATTR_SENSOR_SMOOTHED_VALUES = "sensor_smoothed_values"
ATTR_OUTDOOR_TEMPERATURE = "outdoor_temperature"
ATTR_ZONES_HEATING = "zones_heating"
ATTR_ZONES_COOLING = "zones_cooling"
ATTR_ZONES_IDLE = "zones_idle"
ATTR_ACTIVE_CONFLICTS = "active_conflicts"
ATTR_MASTER_MODE = "master_mode"
ATTR_VERSION = "version"

# Occupancy sensor truthy states
OCCUPANCY_ON_STATES = ("on", "home", "true", "1")

# HA service constants
SERVICE_CLIMATE = "climate"
SERVICE_SET_HVAC_MODE = "set_hvac_mode"
SERVICE_SET_TEMPERATURE = "set_temperature"

# Zone temperature limits (Celsius)
MIN_TEMP_CELSIUS = 10.0  # ~50°F
MAX_TEMP_CELSIUS = 32.0  # ~90°F

# External device change detection
COMMAND_GRACE_PERIOD_SECONDS = 10
COMMAND_TIMEOUT_SECONDS = 60
EXTERNAL_CHANGE_TOLERANCE_F = 0.1
EXTERNAL_OVERRIDE_THRESHOLD_F = 3.0

# Control restore: re-armable takeover passes (v0.13.2 §1)
RESTORE_SOURCE_STARTUP = "startup"
RESTORE_SOURCE_MODE_CHANGE = "mode_change"
RESTORE_SOURCE_MANUAL = "manual"
MODE_CHANGE_RESTORE_DEBOUNCE_S = 10

# Per-pass device outcome codes (spec §1.1, amendment A3/A9)
RESTORE_OUTCOME_OWNED = "owned"
RESTORE_OUTCOME_PENDING_NORMAL_REQUEST = "pending_normal_request"
RESTORE_OUTCOME_NOT_FOUND = "not_found"
RESTORE_OUTCOME_NOT_HEAT_OR_COOL = "not_heat_or_cool"
RESTORE_OUTCOME_PI_REGULATED = "pi_regulated"
RESTORE_OUTCOME_UNAVAILABLE_RETRY = "unavailable_retry"
RESTORE_OUTCOME_MISSING_TEMPERATURE_RETRY = "missing_temperature_retry"
RESTORE_OUTCOME_BLOCKED_RETRY = "blocked_retry"
RESTORE_OUTCOME_SENT = "sent"
RESTORE_OUTCOME_UNCHANGED = "unchanged"
RESTORE_OUTCOME_IN_FLIGHT_RETRY = "in_flight_retry"

# Manual restore service/button response (spec §2.1): outcome codes group into
# a coarser `result`; `superseded` has no outcome code (the pass never ran).
RESTORE_RESULT_SENT = "sent"
RESTORE_RESULT_UNCHANGED = "unchanged"
RESTORE_RESULT_SKIPPED = "skipped"
RESTORE_RESULT_PENDING = "pending"
RESTORE_RESULT_SUPERSEDED = "superseded"
RESTORE_OUTCOME_RESULT: dict[str, str] = {
    RESTORE_OUTCOME_SENT: RESTORE_RESULT_SENT,
    RESTORE_OUTCOME_UNCHANGED: RESTORE_RESULT_UNCHANGED,
    RESTORE_OUTCOME_OWNED: RESTORE_RESULT_SKIPPED,
    RESTORE_OUTCOME_PENDING_NORMAL_REQUEST: RESTORE_RESULT_SKIPPED,
    RESTORE_OUTCOME_NOT_FOUND: RESTORE_RESULT_SKIPPED,
    RESTORE_OUTCOME_NOT_HEAT_OR_COOL: RESTORE_RESULT_SKIPPED,
    RESTORE_OUTCOME_PI_REGULATED: RESTORE_RESULT_SKIPPED,
    RESTORE_OUTCOME_UNAVAILABLE_RETRY: RESTORE_RESULT_PENDING,
    RESTORE_OUTCOME_MISSING_TEMPERATURE_RETRY: RESTORE_RESULT_PENDING,
    RESTORE_OUTCOME_BLOCKED_RETRY: RESTORE_RESULT_PENDING,
    RESTORE_OUTCOME_IN_FLIGHT_RETRY: RESTORE_RESULT_PENDING,
}
RESTORE_CONTROL_KEY = "restore_control"
RESTORE_CONTROL_NOT_READY_MESSAGE = (
    "Restore control is not ready: the startup takeover pass has not armed yet"
)
RESTORE_CONTROL_REFRESH_FAILED_MESSAGE = (
    "Restore control refresh failed; the coordinator update did not succeed"
)
RESTORE_CONTROL_UNKNOWN_ZONE_MESSAGE = "Unknown zone ID"

# Manual-override detection (spec v0.13.2 §3, amendments A5-A7/A11, review round 1 item 1)
MANUAL_OVERRIDE_LOG_MESSAGE_FORMAT = "manual override: commanded {commanded}, reported {reported}"
ATTR_MANUAL_OVERRIDE = "manual_override"
# HA's own default climate step per unit system, used when a device reports no
# target_temp_step (e.g. a real Nest entity, which reports whole degrees).
DEFAULT_TARGET_TEMP_STEP_F = 1.0
DEFAULT_TARGET_TEMP_STEP_C = 0.5

# History-friendly diagnostic entity identity and attributes
DIAG_DEVICE_NAME_PREFIX = "Hybrid Climate - "
DIAG_MANUFACTURER = "Hybrid Climate"
DIAG_MASTER_MODEL = "Master Controller"
DIAG_ZONE_MODEL = "Zone"
DIAG_REASON_SUFFIX = "reason"
DIAG_SPREAD_SUFFIX = "temperature_spread"
DIAG_STAGE_SUFFIX = "stage"
DIAG_OUTDOOR_SOURCE_SUFFIX = "outdoor_source"
DIAG_UNCONTROLLED_SUFFIX = "uncontrolled"
DIAG_OUTDOOR_FALLBACK_SUFFIX = "outdoor_fallback_active"
DIAG_DEVICE_ID_PREFIX = "device"
STAGE_NONE = "none"
STAGE_HEAT_PREFIX = "heating_stage_"
STAGE_COOL_PREFIX = "cooling_stage_"
STAGE_OPPORTUNISTIC = "heating_stage_1_opportunistic"
ATTR_CODES = "codes"
ATTR_METHOD = "method"
ATTR_PRIMARY = "primary"
ATTR_REPORTED_MODE = "reported_mode"
TRANSLATION_REASON = "zone_reason"
TRANSLATION_SPREAD = "zone_temperature_spread"
TRANSLATION_STAGE = "zone_stage"
TRANSLATION_OUTDOOR_SOURCE = "outdoor_source"
TRANSLATION_UNCONTROLLED = "device_uncontrolled"
TRANSLATION_OUTDOOR_FALLBACK = "outdoor_fallback_active"
CAPABILITY_UI_HEAT_LABEL = "Can Heat"
CAPABILITY_UI_COOL_LABEL = "Can Cool"
CAPABILITY_UI_HEAT_FIELD = "can_heat"
CAPABILITY_UI_COOL_FIELD = "can_cool"
