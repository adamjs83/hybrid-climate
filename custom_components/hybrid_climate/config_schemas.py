"""Voluptuous validation schemas for YAML configuration.

Key dependencies: const.py (all CONF_* and DEFAULT_* constants)
Used by: config_loader.py (load_config validates against CONFIG_SCHEMA)
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.const import CONF_NAME
import homeassistant.helpers.config_validation as cv

from .const import (
    AGGREGATION_AVERAGE,
    CAPABILITY_COOL,
    CAPABILITY_HEAT,
    CONF_AGGREGATION,
    CONF_AWAY,
    CONF_SLEEP,
    CONF_VACATION,
    CONF_BLOCK_COOL,
    CONF_BLOCK_HEAT,
    CONF_CAPABILITIES,
    CONF_CONDITIONS,
    CONF_CONFLICTS,
    CONF_COOL_STAGES,
    CONF_DEFAULT,
    CONF_DEVICE,
    CONF_DEVICE_MUTEX,
    CONF_DEVICES,
    CONF_ALLOW_COMMAND,
    CONF_COMPRESSOR_GROUP,
    CONF_MIN_COMPRESSOR_RUNTIME,
    CONF_MIN_COMPRESSOR_OFF_TIME,
    CONF_OPENINGS,
    CONF_OPENING_ENTITIES,
    CONF_OPEN_DELAY,
    CONF_CLOSE_DELAY,
    CONF_ENTITY_ID,
    CONF_FOR_ZONE,
    CONF_HEAT_SOURCES,
    CONF_HEAT_STAGES,
    CONF_IDLE,
    CONF_IDLE_ACTION,
    CONF_IDLE_SETBACK,
    CONF_HYSTERESIS,
    CONF_INDOOR,
    CONF_INTEGRAL_DECAY_HALFLIFE,
    CONF_INTEGRAL_RESET_FACTOR,
    CONF_INTEGRAL_RESET_THRESHOLD,
    CONF_K_EXT,
    CONF_KI,
    CONF_KP,
    CONF_LEGACY_RATE_SENSOR,
    CONF_MASTER,
    CONF_MIN_RUNTIME,
    CONF_MODE,
    CONF_MODES,
    CONF_NEVER_COOL_BELOW,
    CONF_NEVER_HEAT_ABOVE,
    CONF_OCCUPANCY_ENTITY,
    CONF_OCCUPIED,
    CONF_OFFSET_MAX,
    CONF_OPPORTUNISTIC,
    CONF_OUTDOOR_RESET,
    CONF_OUTDOOR_SENSOR,
    CONF_TOU,
    CONF_TOU_COOL,
    CONF_TOU_HEAT,
    CONF_TOU_PRE_CONDITION_MINUTES,
    CONF_TOU_RATE_SENSOR,
    CONF_TOU_RELAXATION_AMOUNT,
    CONF_OUTDOOR_TEMP_MAX,
    CONF_OUTDOOR_TEMP_MIN,
    CONF_REGULATION,
    CONF_REGULATION_TYPE,
    CONF_SENSORS,
    CONF_SETPOINTS,
    CONF_SETTINGS,
    CONF_SMOOTHING_SAMPLES,
    CONF_STABILIZATION_THRESHOLD,
    CONF_STAGE,
    CONF_THEN,
    CONF_THRESHOLD,
    CONF_TIME_ESCALATION,
    CONF_UNOCCUPIED,
    CONF_ACCUMULATED_ERROR_THRESHOLD,
    CONF_BALANCE_POINT,
    CONF_WHEN,
    CONF_ZONES,
    DEFAULT_ACCUMULATED_ERROR_THRESHOLD,
    DEFAULT_ALLOW_COMMAND,
    DEFAULT_BALANCE_POINT,
    DEFAULT_HYSTERESIS,
    DEFAULT_IDLE_ACTION,
    DEFAULT_IDLE_SETBACK,
    DEFAULT_INTEGRAL_DECAY_HALFLIFE,
    DEFAULT_INTEGRAL_RESET_FACTOR,
    DEFAULT_INTEGRAL_RESET_THRESHOLD,
    DEFAULT_K_EXT,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_MIN_RUNTIME,
    DEFAULT_OPEN_DELAY,
    DEFAULT_CLOSE_DELAY,
    DEFAULT_OFFSET_MAX,
    DEFAULT_OPPORTUNISTIC_THRESHOLD,
    DEFAULT_SMOOTHING_SAMPLES,
    DEFAULT_TOU_PRE_CONDITION_MINUTES,
    DEFAULT_TOU_RELAXATION_AMOUNT,
    DEFAULT_STABILIZATION_THRESHOLD,
    IDLE_ACTIONS,
    MAX_SMOOTHING_SAMPLES,
    MIN_SMOOTHING_SAMPLES,
    REGULATION_DIRECT,
    REGULATION_PI,
)


# Validation schemas
STAGE_CONDITION_SCHEMA = vol.Schema({
    vol.Optional(CONF_OUTDOOR_TEMP_MIN): vol.Coerce(float),
    vol.Optional(CONF_OUTDOOR_TEMP_MAX): vol.Coerce(float),
})

# New format: device as object with allow_command
STAGE_DEVICE_SCHEMA = vol.Schema({
    vol.Required(CONF_DEVICE): cv.string,
    vol.Optional(CONF_ALLOW_COMMAND, default=DEFAULT_ALLOW_COMMAND): cv.boolean,
})


def validate_stage_devices(value: Any) -> list[dict[str, Any]]:
    """Validate stage devices - support both old (string list) and new (object list) formats."""
    if not isinstance(value, list):
        raise vol.Invalid("devices must be a list")

    result = []
    for item in value:
        if isinstance(item, str):
            # Old format: just device ID string -> convert to object with allow_command=False
            result.append({CONF_DEVICE: item, CONF_ALLOW_COMMAND: False})
        elif isinstance(item, dict):
            # New format: object with device and allow_command
            result.append(STAGE_DEVICE_SCHEMA(item))
        else:
            raise vol.Invalid(f"device must be string or object, got {type(item)}")
    return result


STAGE_SCHEMA = vol.Schema({
    vol.Required(CONF_STAGE): vol.Coerce(int),
    vol.Required(CONF_DEVICES): validate_stage_devices,
    vol.Required(CONF_THRESHOLD): vol.Coerce(float),
    vol.Optional(CONF_TIME_ESCALATION): vol.Coerce(int),
    vol.Optional(CONF_CONDITIONS): STAGE_CONDITION_SCHEMA,
})

ZONE_SENSORS_SCHEMA = vol.Schema({
    vol.Required(CONF_INDOOR): vol.All(cv.ensure_list, [cv.entity_id]),
    vol.Optional(CONF_AGGREGATION, default=AGGREGATION_AVERAGE): vol.In([
        AGGREGATION_AVERAGE, "min", "max"
    ]),
    vol.Optional(CONF_SMOOTHING_SAMPLES, default=DEFAULT_SMOOTHING_SAMPLES): vol.All(
        vol.Coerce(int),
        vol.Range(min=MIN_SMOOTHING_SAMPLES, max=MAX_SMOOTHING_SAMPLES),
    ),
})

ZONE_SETPOINTS_SCHEMA = vol.Schema({
    vol.Required(CONF_DEFAULT): vol.Coerce(float),
    vol.Optional(CONF_AWAY): vol.Coerce(float),
    vol.Optional(CONF_SLEEP): vol.Coerce(float),
    vol.Optional(CONF_VACATION): vol.Coerce(float),
    vol.Optional(CONF_OCCUPIED): vol.Coerce(float),
    vol.Optional(CONF_UNOCCUPIED): vol.Coerce(float),
    vol.Optional(CONF_OCCUPANCY_ENTITY): cv.entity_id,
    vol.Optional("occupancy_enabled"): bool,  # UI flag to persist checkbox state
})

def validate_optional_float_or_null(value: Any) -> float | None:
    """Validate a value that can be float, None, or 'null' string."""
    if value is None or value == "null":
        return None
    return vol.Coerce(float)(value)


ZONE_OUTDOOR_RESET_SCHEMA = vol.Schema({
    vol.Optional(CONF_NEVER_HEAT_ABOVE): validate_optional_float_or_null,
    vol.Optional(CONF_NEVER_COOL_BELOW): validate_optional_float_or_null,
    # These flags are added by UI config to track explicit overrides
    vol.Optional("override_enabled"): bool,  # UI flag to persist checkbox state
    vol.Optional("heat_override_set"): bool,
    vol.Optional("cool_override_set"): bool,
})

ZONE_SETTINGS_SCHEMA = vol.Schema({
    vol.Optional(CONF_HYSTERESIS, default=DEFAULT_HYSTERESIS): vol.Coerce(float),
    vol.Optional(CONF_MIN_RUNTIME, default=DEFAULT_MIN_RUNTIME): vol.Coerce(int),
    vol.Optional(CONF_OUTDOOR_RESET): ZONE_OUTDOOR_RESET_SCHEMA,
})

OPENINGS_SCHEMA = vol.Schema({
    vol.Required(CONF_OPENING_ENTITIES): vol.All(
        cv.ensure_list, [vol.All(cv.entity_id, vol.Match(r"^binary_sensor\."))]
    ),
    vol.Optional(CONF_OPEN_DELAY, default=DEFAULT_OPEN_DELAY): vol.All(
        vol.Coerce(int), vol.Range(min=0)
    ),
    vol.Optional(CONF_CLOSE_DELAY, default=DEFAULT_CLOSE_DELAY): vol.All(
        vol.Coerce(int), vol.Range(min=0)
    ),
})

REGULATION_SCHEMA = vol.Schema({
    vol.Optional(CONF_REGULATION_TYPE, default=REGULATION_PI): vol.In([REGULATION_DIRECT, REGULATION_PI]),
    vol.Required(CONF_DEVICES): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_KP, default=DEFAULT_KP): vol.Coerce(float),
    vol.Optional(CONF_KI, default=DEFAULT_KI): vol.Coerce(float),
    vol.Optional(CONF_K_EXT, default=DEFAULT_K_EXT): vol.Coerce(float),
    vol.Optional(CONF_BALANCE_POINT, default=DEFAULT_BALANCE_POINT): vol.Coerce(float),
    vol.Optional(CONF_OFFSET_MAX, default=DEFAULT_OFFSET_MAX): vol.Coerce(float),
    vol.Optional(CONF_STABILIZATION_THRESHOLD, default=DEFAULT_STABILIZATION_THRESHOLD): vol.Coerce(float),
    vol.Optional(CONF_ACCUMULATED_ERROR_THRESHOLD, default=DEFAULT_ACCUMULATED_ERROR_THRESHOLD): vol.Coerce(float),
    vol.Optional(CONF_INTEGRAL_RESET_THRESHOLD, default=DEFAULT_INTEGRAL_RESET_THRESHOLD): vol.Coerce(float),
    vol.Optional(CONF_INTEGRAL_RESET_FACTOR, default=DEFAULT_INTEGRAL_RESET_FACTOR): vol.All(
        vol.Coerce(float), vol.Range(min=0.0, max=1.0)
    ),
    vol.Optional(CONF_INTEGRAL_DECAY_HALFLIFE, default=DEFAULT_INTEGRAL_DECAY_HALFLIFE): vol.Coerce(float),
})

OPPORTUNISTIC_SCHEMA = vol.Schema({
    vol.Optional("enabled", default=False): cv.boolean,
    vol.Optional(CONF_THRESHOLD, default=DEFAULT_OPPORTUNISTIC_THRESHOLD): vol.Coerce(float),
})

TOU_MODE_SCHEMA = vol.Schema({
    vol.Optional(
        CONF_TOU_PRE_CONDITION_MINUTES,
        default=DEFAULT_TOU_PRE_CONDITION_MINUTES,
    ): vol.All(int, vol.Range(min=0, max=240)),
    vol.Optional(
        CONF_TOU_RELAXATION_AMOUNT,
        default=DEFAULT_TOU_RELAXATION_AMOUNT,
    ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=10.0)),
})

TOU_ZONE_SCHEMA = vol.Schema({
    vol.Optional(CONF_TOU_HEAT): TOU_MODE_SCHEMA,
    vol.Optional(CONF_TOU_COOL): TOU_MODE_SCHEMA,
})

HEAT_SOURCE_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_DEVICES): vol.All(cv.ensure_list, [cv.string]),
})

ZONE_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_SENSORS): ZONE_SENSORS_SCHEMA,
    vol.Required(CONF_SETPOINTS): ZONE_SETPOINTS_SCHEMA,
    vol.Optional(CONF_HEAT_STAGES, default=[]): vol.All(cv.ensure_list, [STAGE_SCHEMA]),
    vol.Optional(CONF_COOL_STAGES, default=[]): vol.All(cv.ensure_list, [STAGE_SCHEMA]),
    vol.Optional(CONF_SETTINGS): ZONE_SETTINGS_SCHEMA,
    vol.Optional(CONF_OPENINGS): OPENINGS_SCHEMA,
    vol.Optional(CONF_REGULATION): REGULATION_SCHEMA,
    vol.Optional(CONF_OPPORTUNISTIC): OPPORTUNISTIC_SCHEMA,
    vol.Optional(CONF_TOU): TOU_ZONE_SCHEMA,
})

DEVICE_IDLE_SCHEMA = vol.Schema({
    vol.Optional(CONF_IDLE_ACTION, default=DEFAULT_IDLE_ACTION): vol.In(IDLE_ACTIONS),
    vol.Optional(CONF_IDLE_SETBACK, default=DEFAULT_IDLE_SETBACK): vol.Coerce(float),
})

DEVICE_SCHEMA = vol.Schema({
    vol.Required(CONF_ENTITY_ID): cv.entity_id,
    vol.Required(CONF_CAPABILITIES): vol.All(
        cv.ensure_list,
        [vol.In([CAPABILITY_HEAT, CAPABILITY_COOL])]
    ),
    vol.Optional(CONF_IDLE): DEVICE_IDLE_SCHEMA,
    vol.Optional(CONF_COMPRESSOR_GROUP): vol.All(cv.string, vol.Length(min=1)),
    vol.Optional(CONF_MIN_COMPRESSOR_RUNTIME, default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
    vol.Optional(CONF_MIN_COMPRESSOR_OFF_TIME, default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
    # Note: allow_command moved to stage device config (per-zone, not per-device)
})

DEVICE_MUTEX_WHEN_SCHEMA = vol.Schema({
    vol.Required(CONF_DEVICE): cv.string,
    vol.Required(CONF_MODE): vol.In([CAPABILITY_HEAT, CAPABILITY_COOL]),
    vol.Required(CONF_FOR_ZONE): cv.string,
})

DEVICE_MUTEX_THEN_SCHEMA = vol.Schema({
    vol.Optional(CONF_BLOCK_HEAT, default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_BLOCK_COOL, default=[]): vol.All(cv.ensure_list, [cv.string]),
    # Blocked devices for shared condenser support
    vol.Optional("blocked_devices_heat", default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("blocked_devices_cool", default=[]): vol.All(cv.ensure_list, [cv.string]),
})

DEVICE_MUTEX_SCHEMA = vol.Schema({
    vol.Required(CONF_WHEN): DEVICE_MUTEX_WHEN_SCHEMA,
    vol.Required(CONF_THEN): DEVICE_MUTEX_THEN_SCHEMA,
})

OUTDOOR_RESET_SCHEMA = vol.Schema({
    vol.Optional(CONF_NEVER_HEAT_ABOVE): vol.Coerce(float),
    vol.Optional(CONF_NEVER_COOL_BELOW): vol.Coerce(float),
})

CONFLICTS_SCHEMA = vol.Schema({
    vol.Optional(CONF_OUTDOOR_RESET): OUTDOOR_RESET_SCHEMA,
    vol.Optional(CONF_DEVICE_MUTEX, default=[]): vol.All(
        cv.ensure_list,
        [DEVICE_MUTEX_SCHEMA]
    ),
})

MASTER_MODE_SCHEMA = vol.Schema({
    vol.Optional("use_zone_defaults", default=False): cv.boolean,
    vol.Optional("use_zone_away_setpoints", default=False): cv.boolean,  # Deprecated
    vol.Optional("use_zone_setpoint"): cv.string,  # Named setpoint: "away", "sleep", "vacation"
    vol.Optional("setpoint_offset", default=0): vol.Coerce(float),
    vol.Optional("skip_time_escalation", default=False): cv.boolean,
    vol.Optional("disable_all", default=False): cv.boolean,
})

MASTER_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Optional(CONF_OCCUPANCY_ENTITY): cv.entity_id,
    vol.Optional(CONF_MODES, default={}): vol.Schema({
        vol.Optional("home"): MASTER_MODE_SCHEMA,
        vol.Optional("away"): MASTER_MODE_SCHEMA,
        vol.Optional("sleep"): MASTER_MODE_SCHEMA,
        vol.Optional("vacation"): MASTER_MODE_SCHEMA,
        vol.Optional("boost"): MASTER_MODE_SCHEMA,
        vol.Optional("off"): MASTER_MODE_SCHEMA,
    }),
})

CONFIG_SCHEMA = vol.Schema({
    vol.Optional(CONF_OUTDOOR_SENSOR): cv.entity_id,
    vol.Optional(CONF_TOU_RATE_SENSOR): cv.entity_id,
    vol.Optional(CONF_LEGACY_RATE_SENSOR): cv.entity_id,  # Legacy YAML spelling.
    vol.Required(CONF_MASTER): MASTER_SCHEMA,
    vol.Optional(CONF_CONFLICTS, default={}): CONFLICTS_SCHEMA,
    # Devices and zones are optional to support pure UI setup with no initial config
    vol.Optional(CONF_DEVICES, default={}): vol.Schema({cv.string: DEVICE_SCHEMA}),
    vol.Optional(CONF_ZONES, default={}): vol.Schema({cv.string: ZONE_SCHEMA}),
    vol.Optional(CONF_HEAT_SOURCES, default={}): vol.Schema({cv.string: HEAT_SOURCE_SCHEMA}),
})
