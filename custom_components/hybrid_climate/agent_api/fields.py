"""Purpose: Define the Agent API writable tuning field catalog.

Key dependencies: Frozen dataclasses and static validation metadata.
Used by: Accessors, outdoor overrides, and field discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..const import CONF_LOCKOUT_HEAT_FLOOR, MIN_LOCKOUT_HEAT_FLOOR, MAX_LOCKOUT_HEAT_FLOOR


@dataclass(frozen=True)
class Field:
    """Describe one writable field and its API validation bounds."""

    scope: str
    key: str
    kind: str
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None
    description: str = ""
    enum: tuple[str, ...] = ()


FIELD_ROWS = (
    Field("global", CONF_LOCKOUT_HEAT_FLOOR, "float", MIN_LOCKOUT_HEAT_FLOOR, MAX_LOCKOUT_HEAT_FLOOR, "°F", "Maximum idle heat setpoint during outdoor heat lockout"),
    Field("global", "never_heat_above", "float", 30, 100, "°F", "Stop heating above this outdoor temperature"),
    Field("global", "never_cool_below", "float", 30, 100, "°F", "Stop cooling below this outdoor temperature"),
    Field("zones", "settings.hysteresis", "float", 0.1, 5, "°F", "Zone hysteresis"),
    Field("zones", "settings.min_runtime", "int", 60, 1800, "s", "Minimum zone runtime"),
    Field("zones", "sensors.aggregation", "enum", description="Combine indoor readings",
          enum=("average", "min", "max", "median", "weighted")),
    Field("zones", "sensors.smoothing_samples", "int", 1, 100, "samples", "Moving-average sample count"),
    Field("zones", "opportunistic.enabled", "bool", description="Permit opportunistic heating"),
    Field("zones", "opportunistic.threshold", "float", 0.1, 5, "°F", "Opportunistic heat error threshold"),
    Field("zones", "openings.open_delay", "int", 0, 3600, "s", "Delay before opening lockout"),
    Field("zones", "openings.close_delay", "int", 0, 3600, "s", "Closed-contact recovery delay"),
    Field("zones", "settings.outdoor_reset.heat", "operation", 40, 120, "°F", "Heat override", ("inherit", "disabled", "value")),
    Field("zones", "settings.outdoor_reset.cool", "operation", -20, 80, "°F", "Cool override", ("inherit", "disabled", "value")),
    Field("stage", "threshold", "float", 0.5, 10, "°F", "Stage entry error threshold"),
    Field("stage", "time_escalation", "int", 300, 7200, "s", "Stage escalation delay; null removes it"),
    Field("stage", "outdoor_temp_min", "float", -20, 80, "°F", "Heating stage 2 outdoor minimum"),
    Field("devices", "min_compressor_runtime", "int", 0, 3600, "s", "Minimum compressor runtime"),
    Field("devices", "min_compressor_off_time", "int", 0, 3600, "s", "Minimum compressor off interval"),
)
FIELDS = {(row.scope, row.key): row for row in FIELD_ROWS}
OUTDOOR_VALUE_FIELDS = {
    side: replace(FIELDS[("zones", "settings.outdoor_reset." + side)], kind="float")
    for side in ("heat", "cool")
}
