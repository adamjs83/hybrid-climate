"""Purpose: Constants for the zone-level cooling PI regulation block (v0.17.0).

Key dependencies: None.
Used by: cool_regulation_config.py, cool_pi.py, config_schemas.py, config_parsers.py, config_converter.py,
models.py, agent_api (fields, status, config_readonly), dashboard_api.py,
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

# Optional outdoor term (v0.17.4): gain 0 = off.
NUMBER_KEY_COOL_PI_K_EXT = "cool_pi_k_ext"
NUMBER_KEY_COOL_PI_BALANCE_POINT = "cool_pi_balance_point"
DEFAULT_COOL_PI_K_EXT = 0.0
DEFAULT_COOL_PI_BALANCE_POINT = 75.0  # °F, outdoor temperature with no extra push
MIN_COOL_PI_K_EXT = 0.0
MAX_COOL_PI_K_EXT = 1.0
STEP_COOL_PI_K_EXT = 0.05
MIN_COOL_PI_BALANCE_POINT = 50.0
MAX_COOL_PI_BALANCE_POINT = 100.0
STEP_COOL_PI_BALANCE_POINT = 1.0
COOL_PI_EXT_SIGN = -1.0  # hotter outside means more cooling push

# Log label for the shared PI step ("Zone <label> PI: ..."), so cooling lines are told apart.
COOL_PI_LOG_LABEL = "%s cooling"

# Zone climate attributes and status fields for the cooling PI state (v0.17.0 §2b).
ATTR_COOL_REGULATION_OFFSET = "cool_regulation_offset"
ATTR_COOL_ACCUMULATED_ERROR = "cool_accumulated_error"
ATTR_COOL_REGULATED_SETPOINT = "cool_regulated_setpoint"

# Per-device "Cooling PI with compensation" keys (v0.17.3): PI also adds the unit-minus-room difference.
CONF_COOL_PI_COMPENSATION = "cool_pi_compensation"
DEFAULT_COOL_PI_COMPENSATION = False
CONF_COOL_MAX_TOTAL_PUSH = "cool_max_total_push"
DEFAULT_COOL_MAX_TOTAL_PUSH = 8.0  # °F, largest total push below the zone cool target
MIN_COOL_MAX_TOTAL_PUSH = 0.0
MAX_COOL_MAX_TOTAL_PUSH = 15.0
COOL_MAX_TOTAL_PUSH_STEP = 0.5
COOL_COMPENSATION_SETTLE_MINUTES = 3  # minutes after a run starts before the unit reading is used
