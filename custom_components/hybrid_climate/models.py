"""Data models for Hybrid Climate integration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from homeassistant.util import dt as dt_util
from .const import EXTERNAL_CHANGE_TOLERANCE_F


class DeviceCapability(Enum):
    """Device capabilities."""
    HEAT = "heat"
    COOL = "cool"


class MasterMode(Enum):
    """Master operating modes."""
    HOME = "home"
    AWAY = "away"
    SLEEP = "sleep"
    VACATION = "vacation"
    BOOST = "boost"
    OFF = "off"


class HvacMode(Enum):
    """Zone HVAC modes."""
    HEAT = "heat"
    COOL = "cool"
    OFF = "off"
    AUTO = "auto"


class HvacAction(Enum):
    """Zone HVAC actions."""
    HEATING = "heating"
    COOLING = "cooling"
    IDLE = "idle"
    OFF = "off"


class DeviceCommandState(Enum):
    """State machine states for allow_command devices.
    
    LISTENING: Underlay matches our last command. Any change from underlay
               that differs from desired state = external change → sync to overlay.
    COMMANDING: We sent a command, waiting for underlay to match. Ignore 
                underlay changes (assume lag until timeout).
    """
    LISTENING = "listening"
    COMMANDING = "commanding"


class AggregationMethod(Enum):
    """Sensor aggregation methods."""
    AVERAGE = "average"
    MIN = "min"
    MAX = "max"


@dataclass
class StageCondition:
    """Conditions that must be met for a stage to activate."""
    outdoor_temp_min: float | None = None
    outdoor_temp_max: float | None = None
    _last_outdoor_result: bool = field(default=False, repr=False, compare=False)

    def evaluate(self, outdoor_temp: float | None) -> bool:
        """Check if conditions are met."""
        if outdoor_temp is None:
            # A never-verified outdoor limit stays closed during an outage.
            return self._last_outdoor_result if (self.outdoor_temp_min is not None or self.outdoor_temp_max is not None) else True

        self._last_outdoor_result = not (
            (self.outdoor_temp_min is not None and outdoor_temp < self.outdoor_temp_min)
            or (self.outdoor_temp_max is not None and outdoor_temp > self.outdoor_temp_max)
        )
        return self._last_outdoor_result


@dataclass
class StageDevice:
    """A device reference within a stage, with per-zone settings."""
    device_id: str
    allow_command: bool = False  # If True, external changes on this device sync to zone overlay


@dataclass
class Stage:
    """A heating or cooling stage."""
    stage_number: int
    devices: list[StageDevice]  # device references with per-zone settings
    threshold: float
    time_escalation: int | None = None  # seconds, None = threshold only
    conditions: StageCondition = field(default_factory=StageCondition)

    def should_activate_by_threshold(self, temp_diff: float) -> bool:
        """Check if stage should activate based on temperature differential."""
        return abs(temp_diff) >= self.threshold

    def get_device_ids(self) -> list[str]:
        """Get list of device IDs in this stage."""
        return [d.device_id for d in self.devices]

    def get_allow_command_device_ids(self) -> list[str]:
        """Get list of device IDs that have allow_command=True."""
        return [d.device_id for d in self.devices if d.allow_command]


@dataclass
class DeviceIdleConfig:
    """Configuration for device behavior when not actively heating/cooling."""
    action: str = "off"  # "off" = turn off, "setback" = set to target +/- setback
    setback: float = 5.0  # degrees to setback from zone target when idle


@dataclass
class Device:
    """A climate device in the pool."""
    device_id: str  # our internal ID
    entity_id: str  # Home Assistant entity_id
    capabilities: list[DeviceCapability]
    idle_config: DeviceIdleConfig = field(default_factory=DeviceIdleConfig)

    # Runtime state
    current_mode: str | None = None  # heat, cool, off
    current_target_temp: float | None = None
    is_available: bool = True

    # Command state machine (for allow_command devices)
    command_state: DeviceCommandState = DeviceCommandState.LISTENING
    desired_temp: float | None = None  # What we last commanded
    desired_mode: str | None = None  # heat, cool, off
    command_sent_at: datetime | None = None  # For timeout detection

    def can_heat(self) -> bool:
        """Check if device supports heating."""
        return DeviceCapability.HEAT in self.capabilities

    def can_cool(self) -> bool:
        """Check if device supports cooling."""
        return DeviceCapability.COOL in self.capabilities

    def start_command(self, mode: str, temp: float | None) -> None:
        """Transition to COMMANDING state."""
        self.command_state = DeviceCommandState.COMMANDING
        self.desired_mode = mode
        self.desired_temp = temp  # None for OFF mode (no temp tracking)
        self.command_sent_at = dt_util.utcnow()

    def command_acknowledged(self) -> None:
        """Transition back to LISTENING state after ack."""
        self.command_state = DeviceCommandState.LISTENING
        # desired_temp/mode stay set - they represent "what we expect"

    def command_timeout(self, current_temp: float, current_mode: str) -> None:
        """Handle timeout - sync desired to current and go back to LISTENING."""
        self.command_state = DeviceCommandState.LISTENING
        self.desired_temp = current_temp
        self.desired_mode = current_mode
        self.command_sent_at = None

    def is_commanding(self) -> bool:
        """Check if device is in COMMANDING state."""
        return self.command_state == DeviceCommandState.COMMANDING

    def is_listening(self) -> bool:
        """Check if device is in LISTENING state."""
        return self.command_state == DeviceCommandState.LISTENING

    def matches_desired(self, temp: float, mode: str, temp_tolerance: float = EXTERNAL_CHANGE_TOLERANCE_F) -> bool:
        """Check if given temp/mode matches our desired state."""
        if self.desired_mode is None:
            return True  # No desired state = matches anything
        
        mode_matches = mode == self.desired_mode
        
        # For OFF mode, only check mode match (temp is irrelevant when off)
        if self.desired_mode == "off":
            return mode_matches
        
        # For heat/cool modes, check both mode and temp
        if self.desired_temp is None:
            return mode_matches
        
        temp_matches = abs(temp - self.desired_temp) <= temp_tolerance
        return temp_matches and mode_matches


@dataclass
class ZoneSetpoints:
    """Setpoint configuration for a zone."""
    default: float
    away: float | None = None
    sleep: float | None = None
    vacation: float | None = None
    occupied: float | None = None
    unoccupied: float | None = None
    occupancy_entity: str | None = None

    def get_setpoint_by_name(self, name: str) -> float | None:
        """Get a setpoint by name (for use_zone_setpoint config)."""
        setpoint_map = {
            "default": self.default,
            "away": self.away,
            "sleep": self.sleep,
            "vacation": self.vacation,
            "occupied": self.occupied,
            "unoccupied": self.unoccupied,
        }
        return setpoint_map.get(name)

    def get_effective_setpoint(
        self,
        master_mode: MasterMode,
        is_occupied: bool | None = None,
        setpoint_name: str | None = None,
    ) -> float:
        """Get the effective setpoint based on mode, occupancy, or explicit name.
        
        Args:
            master_mode: Current master mode
            is_occupied: Zone occupancy state (if available)
            setpoint_name: Explicit setpoint name from mode config (e.g., "sleep")
        """
        # If explicit setpoint name provided, use it (with fallback to default)
        if setpoint_name:
            setpoint = self.get_setpoint_by_name(setpoint_name)
            return setpoint if setpoint is not None else self.default

        # Master mode overrides
        if master_mode == MasterMode.OFF:
            return self.default  # Will be ignored anyway since system is off

        if master_mode == MasterMode.AWAY:
            return self.away if self.away is not None else self.default

        if master_mode == MasterMode.VACATION:
            return self.vacation if self.vacation is not None else self.default

        # Home or Boost mode - check occupancy
        if is_occupied is not None and self.occupancy_entity:
            if is_occupied and self.occupied is not None:
                return self.occupied
            elif not is_occupied and self.unoccupied is not None:
                return self.unoccupied

        return self.default


@dataclass
class ZoneSensors:
    """Sensor configuration for a zone."""
    indoor: list[str]  # entity_ids
    aggregation: AggregationMethod = AggregationMethod.AVERAGE
    smoothing_samples: int = 1  # number of samples for moving average (1 = no smoothing)


@dataclass
class ZoneOutdoorResetConfig:
    """Per-zone override for outdoor reset limits.
    
    Allows zones to override global never_heat_above/never_cool_below.
    Use None to disable a restriction entirely for this zone.
    Use a float to set a zone-specific limit.
    If not set (field is None), global config applies.
    """
    never_heat_above: float | None = None  # None = use global, numeric = zone override
    never_cool_below: float | None = None  # None = use global, numeric = zone override
    # Special sentinel to indicate "disabled" vs "not set"
    heat_override_set: bool = False  # True if user explicitly set (even to None)
    cool_override_set: bool = False  # True if user explicitly set (even to None)


@dataclass
class ZoneSettings:
    """Runtime settings for a zone."""
    hysteresis: float = 0.5
    min_runtime: int = 300  # seconds
    outdoor_reset: ZoneOutdoorResetConfig | None = None  # Per-zone outdoor reset override


@dataclass
class RegulationConfig:
    """PI regulation config for controlling underlying devices.

    Instead of sending zone target directly to devices, a PI controller
    calculates an offset to push devices harder or softer based on error.
    """
    type: str = "direct"  # "direct" or "pi"
    devices: list[str] = field(default_factory=list)  # devices to apply PI to
    kp: float = 1.0  # Proportional gain
    ki: float = 0.01  # Integral gain
    k_ext: float = 0.0  # External (outdoor) temperature factor
    offset_max: float = 10.0  # Maximum offset to apply
    stabilization_threshold: float = 0.1  # Error below this = stable
    accumulated_error_threshold: float = 240.0  # Anti-windup cap
    balance_point: float = 65.0  # Outdoor temp where no heating/cooling offset needed
    # Integral management for state changes
    integral_reset_threshold: float = 2.5  # °F setpoint change triggers partial reset
    integral_reset_factor: float = 0.3  # Fraction to keep on reset (0.3 = keep 30%)
    integral_decay_halflife: float = 120.0  # Minutes for idle decay (0 = no decay)


@dataclass
class HeatSourceConfig:
    """Configuration for a shared heat source (e.g., boiler).

    Devices in the same heat source group can use opportunistic heating -
    when the boiler is running for one zone, other zones can piggyback.
    """
    source_id: str
    name: str
    devices: list[str]  # device IDs that share this heat source


@dataclass
class OpportunisticConfig:
    """Per-zone opportunistic heating configuration.

    When another zone in the same heat source group is heating,
    this zone can turn on early to piggyback on the boiler cycle.
    """
    enabled: bool = False  # Opt-in/opt-out
    threshold: float = 0.5  # Turn on if error > threshold (degrees below setpoint)


@dataclass
class ZoneTouModeConfig:
    """TOU config for a single mode (heat or cool) within a zone."""
    pre_condition_minutes: int = 60
    relaxation_amount: float = 2.0  # °F


@dataclass
class ZoneTouConfig:
    """Per-zone TOU optimization configuration.

    Each zone can independently configure TOU behavior for heat and cool.
    If heat or cool is None, TOU does not apply for that mode.
    """
    heat: ZoneTouModeConfig | None = None
    cool: ZoneTouModeConfig | None = None


@dataclass
class TouGlobalConfig:
    """Global TOU configuration."""
    rate_sensor: str | None = None  # Entity ID of rate period sensor


@dataclass
class ZoneConfig:
    """Configuration for a zone."""
    zone_id: str
    name: str
    sensors: ZoneSensors
    setpoints: ZoneSetpoints
    heat_stages: list[Stage]
    cool_stages: list[Stage]
    settings: ZoneSettings = field(default_factory=ZoneSettings)
    regulation: RegulationConfig | None = None  # Optional PI regulation
    opportunistic: OpportunisticConfig | None = None  # Optional opportunistic heating
    tou: ZoneTouConfig | None = None  # Optional TOU optimization

    def get_all_device_ids(self) -> list[str]:
        """Get all device IDs from all stages."""
        device_ids = []
        for stage in self.heat_stages + self.cool_stages:
            device_ids.extend(stage.get_device_ids())
        return list(set(device_ids))  # dedupe

    def get_allow_command_device_ids(self) -> list[str]:
        """Get device IDs that have allow_command=True in any stage."""
        device_ids = []
        for stage in self.heat_stages + self.cool_stages:
            device_ids.extend(stage.get_allow_command_device_ids())
        return list(set(device_ids))  # dedupe


@dataclass
class ZoneState:
    """Runtime state for a zone.

    Dual-setpoint support:
    - target_temperature: The heating setpoint (heat when room drops below)
    - target_temperature_cool: The cooling setpoint (cool when room rises above)
    - The range between them is the comfort deadband
    """
    zone_id: str
    current_temperature: float | None = None
    target_temperature: float | None = None  # Heat setpoint (target_temp_low)
    target_temperature_cool: float | None = None  # Cool setpoint (target_temp_high)
    hvac_mode: HvacMode = HvacMode.OFF
    hvac_action: HvacAction = HvacAction.OFF
    current_stage: str | None = None  # e.g., "heating_stage_1"
    active_devices: list[str] = field(default_factory=list)
    blocked_devices: list[str] = field(default_factory=list)
    stage_start_time: datetime | None = None
    escalated_at: datetime | None = None  # Latches an upper stage for this demand direction
    sensor_values: dict[str, float] = field(default_factory=dict)  # raw current values
    sensor_smoothed_values: dict[str, float] = field(default_factory=dict)  # smoothed values
    is_available: bool = True
    sensor_status: str | None = None  # None=normal, "failed"=sensors offline past grace period
    last_update: datetime | None = None
    last_active_action: HvacAction | None = None  # Last heating/cooling action (for idle setback direction)
    last_direction_stop_time: datetime | None = None  # Time equipment last fully released
    
    # User mode override: None=auto, HEAT=heat-only, COOL=cool-only, OFF=disabled
    user_mode_override: HvacMode | None = None

    # PI regulation state
    accumulated_error: float = 0.0  # Integral term accumulator (error-minutes)
    regulation_offset: float = 0.0  # Current calculated offset
    regulated_setpoint: float | None = None  # Setpoint sent to regulated devices
    last_pi_update_time: datetime | None = None  # For dt-scaled integral

    # TOU state
    tou_state: str = "normal"  # "normal", "pre_conditioning", "peak_relaxed"

    def time_in_current_stage(self) -> int:
        """Get seconds in current stage."""
        if self.stage_start_time is None:
            return 0
        return int((dt_util.utcnow() - self.stage_start_time).total_seconds())


@dataclass
class DeviceMutexRule:
    """A device mutex conflict rule.
    
    When device_id is active in the specified mode for for_zone:
    - block_heat: list of zone IDs that cannot heat
    - block_cool: list of zone IDs that cannot cool
    - blocked_devices_heat: list of OTHER device IDs that cannot heat (for shared condensers)
    - blocked_devices_cool: list of OTHER device IDs that cannot cool (for shared condensers)
    """
    device_id: str
    mode: str  # heat or cool
    for_zone: str
    block_heat: list[str] = field(default_factory=list)  # zone IDs
    block_cool: list[str] = field(default_factory=list)  # zone IDs
    blocked_devices_heat: list[str] = field(default_factory=list)  # device IDs that can't heat
    blocked_devices_cool: list[str] = field(default_factory=list)  # device IDs that can't cool


@dataclass
class OutdoorResetConfig:
    """Outdoor reset configuration."""
    never_heat_above: float | None = None
    never_cool_below: float | None = None


@dataclass
class ConflictConfig:
    """Conflict resolution configuration."""
    outdoor_reset: OutdoorResetConfig = field(default_factory=OutdoorResetConfig)
    device_mutex: list[DeviceMutexRule] = field(default_factory=list)


@dataclass
class MasterModeConfig:
    """Configuration for a master mode."""
    use_zone_defaults: bool = False
    use_zone_away_setpoints: bool = False  # Deprecated - use use_zone_setpoint instead
    use_zone_setpoint: str | None = None  # Named setpoint to use (e.g., "away", "sleep", "vacation")
    setpoint_offset: float = 0
    skip_time_escalation: bool = False
    disable_all: bool = False


@dataclass
class MasterConfig:
    """Master entity configuration."""
    name: str
    occupancy_entity: str | None = None
    modes: dict[MasterMode, MasterModeConfig] = field(default_factory=dict)


@dataclass
class MasterState:
    """Runtime state for master entity."""
    mode: MasterMode = MasterMode.HOME
    last_active_mode: MasterMode = MasterMode.HOME  # Last non-OFF mode for restore
    outdoor_temperature: float | None = None
    zones_heating: list[str] = field(default_factory=list)
    zones_cooling: list[str] = field(default_factory=list)
    zones_idle: list[str] = field(default_factory=list)
    active_conflicts: list[str] = field(default_factory=list)


@dataclass
class HybridClimateConfig:
    """Full configuration for the integration."""
    outdoor_sensor: str | None
    master: MasterConfig
    conflicts: ConflictConfig
    devices: dict[str, Device]
    zones: dict[str, ZoneConfig]
    heat_sources: dict[str, HeatSourceConfig] = field(default_factory=dict)
    tou_global: TouGlobalConfig = field(default_factory=TouGlobalConfig)
