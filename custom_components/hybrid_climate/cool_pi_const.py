"""Purpose: Constants for the zone-level cooling PI regulation block (v0.17.0).

Key dependencies: None.
Used by: cool_regulation_config.py, cool_pi.py, config_schemas.py, config_parsers.py, config_converter.py,
agent_api (status, config_readonly), dashboard_api.py,
number_definitions.py, number_lookup.py, number_entities.py.
"""
from __future__ import annotations

# Zone-level block; the device key of the same name is a mode (const.CONF_COOL_REGULATION).
CONF_ZONE_COOL_REGULATION = "cool_regulation"

DEFAULT_COOL_PI_KP = 1.0
DEFAULT_COOL_PI_KI = 0.01
DEFAULT_COOL_PI_OFFSET_MAX = 5.0  # °F, maximum cooling push
MIN_COOL_PI_OFFSET_MAX = 0.0
MAX_COOL_PI_OFFSET_MAX = 10.0
DEFAULT_COOL_PI_STABILIZATION = 0.1  # °F, error below this counts as stable
DEFAULT_COOL_PI_ERROR_CAP = 240.0  # error-minutes, anti-windup cap
DEFAULT_COOL_PI_HALFLIFE = 120.0  # minutes of idle integral decay

# Cooling PI gain number entities (unique id hybrid_climate_<zone_id>_<key>).
PARAM_TYPE_COOL_PI = "cool_pi"
NUMBER_KEY_COOL_PI_KP = "cool_pi_kp"
NUMBER_KEY_COOL_PI_KI = "cool_pi_ki"
NUMBER_KEY_COOL_PI_OFFSET_MAX = "cool_pi_offset_max"
MIN_COOL_PI_KP = 0.1
MAX_COOL_PI_KP = 5.0
STEP_COOL_PI_KP = 0.1
MIN_COOL_PI_KI = 0.001
MAX_COOL_PI_KI = 0.5
STEP_COOL_PI_KI = 0.001
STEP_COOL_PI_OFFSET_MAX = 0.5

# Log label for the shared PI step ("Zone <label> PI: ..."), so cooling lines are told apart.
COOL_PI_LOG_LABEL = "%s cooling"

# Zone climate attributes and status fields for the cooling PI state (v0.17.0 §2b).
ATTR_COOL_REGULATION_OFFSET = "cool_regulation_offset"
ATTR_COOL_ACCUMULATED_ERROR = "cool_accumulated_error"
ATTR_COOL_REGULATED_SETPOINT = "cool_regulated_setpoint"
