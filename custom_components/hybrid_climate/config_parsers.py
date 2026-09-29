"""Config parsing functions that convert validated dicts to model objects.

Key dependencies: models.py (all dataclasses), const.py
Used by: config_loader.py (load_config calls parse_* functions)
"""
from __future__ import annotations

import logging
from typing import Any

from .const import (
    AGGREGATION_AVERAGE,
    CAPABILITY_COOL,
    CAPABILITY_HEAT,
    CONF_ACCUMULATED_ERROR_THRESHOLD,
    CONF_AGGREGATION,
    CONF_AWAY,
    CONF_SLEEP,
    CONF_VACATION,
    CONF_BLOCK_COOL,
    CONF_BLOCK_HEAT,
    CONF_CAPABILITIES,
    CONF_CONDITIONS,
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
    CONF_FOR_ZONE,
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
    CONF_BALANCE_POINT,
    CONF_WHEN,
    CONF_ENTITY_ID,
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
    DEFAULT_STABILIZATION_THRESHOLD,
    DEFAULT_TOU_PRE_CONDITION_MINUTES,
    DEFAULT_TOU_RELAXATION_AMOUNT,
    REGULATION_PI,
)
from .models import (
    AggregationMethod,
    ConflictConfig,
    Device,
    DeviceCapability,
    DeviceIdleConfig,
    DeviceMutexRule,
    HeatSourceConfig,
    MasterConfig,
    MasterMode,
    MasterModeConfig,
    OpportunisticConfig,
    OpeningConfig,
    OutdoorResetConfig,
    TouGlobalConfig,
    RegulationConfig,
    Stage,
    StageCondition,
    StageDevice,
    ZoneConfig,
    ZoneOutdoorResetConfig,
    ZoneTouConfig,
    ZoneTouModeConfig,
    ZoneSensors,
    ZoneSetpoints,
    ZoneSettings,
)

from homeassistant.const import CONF_NAME

_LOGGER = logging.getLogger(__name__)


def parse_stage_condition(data: dict[str, Any] | None) -> StageCondition:
    """Parse stage condition from config."""
    if not data:
        return StageCondition()

    return StageCondition(
        outdoor_temp_min=data.get(CONF_OUTDOOR_TEMP_MIN),
        outdoor_temp_max=data.get(CONF_OUTDOOR_TEMP_MAX),
    )


def parse_stage_device(data: dict[str, Any]) -> StageDevice:
    """Parse a stage device from config."""
    return StageDevice(
        device_id=data[CONF_DEVICE],
        allow_command=data.get(CONF_ALLOW_COMMAND, DEFAULT_ALLOW_COMMAND),
    )


def parse_stage(data: dict[str, Any]) -> Stage:
    """Parse a stage from config."""
    # devices have already been normalized to object format by validate_stage_devices
    stage_devices = [parse_stage_device(d) for d in data[CONF_DEVICES]]

    return Stage(
        stage_number=data[CONF_STAGE],
        devices=stage_devices,
        threshold=data[CONF_THRESHOLD],
        time_escalation=data.get(CONF_TIME_ESCALATION),
        conditions=parse_stage_condition(data.get(CONF_CONDITIONS)),
    )


def parse_device_idle(data: dict[str, Any] | None) -> DeviceIdleConfig:
    """Parse device idle config."""
    if not data:
        return DeviceIdleConfig()

    return DeviceIdleConfig(
        action=data.get(CONF_IDLE_ACTION, DEFAULT_IDLE_ACTION),
        setback=data.get(CONF_IDLE_SETBACK, DEFAULT_IDLE_SETBACK),
    )


def parse_device(device_id: str, data: dict[str, Any]) -> Device:
    """Parse a device from config."""
    capabilities = [
        DeviceCapability.HEAT if c == CAPABILITY_HEAT else DeviceCapability.COOL
        for c in data[CONF_CAPABILITIES]
    ]

    return Device(
        device_id=device_id,
        entity_id=data[CONF_ENTITY_ID],
        capabilities=capabilities,
        idle_config=parse_device_idle(data.get(CONF_IDLE)),
        compressor_group=data.get(CONF_COMPRESSOR_GROUP),
        min_compressor_runtime=data.get(CONF_MIN_COMPRESSOR_RUNTIME, 0),
        min_compressor_off_time=data.get(CONF_MIN_COMPRESSOR_OFF_TIME, 0),
    )


def parse_zone_sensors(data: dict[str, Any]) -> ZoneSensors:
    """Parse zone sensors from config."""
    aggregation_map = {
        AGGREGATION_AVERAGE: AggregationMethod.AVERAGE,
        "min": AggregationMethod.MIN,
        "max": AggregationMethod.MAX,
    }

    return ZoneSensors(
        indoor=data[CONF_INDOOR],
        aggregation=aggregation_map.get(
            data.get(CONF_AGGREGATION, AGGREGATION_AVERAGE),
            AggregationMethod.AVERAGE,
        ),
        smoothing_samples=data.get(CONF_SMOOTHING_SAMPLES, DEFAULT_SMOOTHING_SAMPLES),
    )


def parse_zone_setpoints(data: dict[str, Any]) -> ZoneSetpoints:
    """Parse zone setpoints from config."""
    return ZoneSetpoints(
        default=data[CONF_DEFAULT],
        away=data.get(CONF_AWAY),
        sleep=data.get(CONF_SLEEP),
        vacation=data.get(CONF_VACATION),
        occupied=data.get(CONF_OCCUPIED),
        unoccupied=data.get(CONF_UNOCCUPIED),
        occupancy_entity=data.get(CONF_OCCUPANCY_ENTITY),
    )


def parse_zone_outdoor_reset(data: dict[str, Any] | None) -> ZoneOutdoorResetConfig | None:
    """Parse per-zone outdoor reset override config.

    Returns None if not configured (use global settings).
    When configured, None values in never_heat_above/never_cool_below mean "disabled".
    """
    if not data:
        return None

    # Flags distinguish inheritance from an explicitly disabled (null) limit.
    # Older configs without flags retain key-presence semantics.
    enabled = data.get("override_enabled", True)
    heat_override_set = enabled and data.get("heat_override_set", CONF_NEVER_HEAT_ABOVE in data)
    cool_override_set = enabled and data.get("cool_override_set", CONF_NEVER_COOL_BELOW in data)

    _LOGGER.info(
        "parse_zone_outdoor_reset: data=%s, heat_set=%s, cool_set=%s",
        data, heat_override_set, cool_override_set
    )

    return ZoneOutdoorResetConfig(
        never_heat_above=data.get(CONF_NEVER_HEAT_ABOVE),  # Can be None (disabled)
        never_cool_below=data.get(CONF_NEVER_COOL_BELOW),  # Can be None (disabled)
        heat_override_set=heat_override_set,
        cool_override_set=cool_override_set,
    )


def parse_zone_settings(data: dict[str, Any] | None) -> ZoneSettings:
    """Parse zone settings from config."""
    if not data:
        return ZoneSettings()

    return ZoneSettings(
        hysteresis=data.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS),
        min_runtime=data.get(CONF_MIN_RUNTIME, DEFAULT_MIN_RUNTIME),
        outdoor_reset=parse_zone_outdoor_reset(data.get(CONF_OUTDOOR_RESET)),
    )


def parse_regulation(data: dict[str, Any] | None) -> RegulationConfig | None:
    """Parse regulation config for PI control."""
    if not data:
        return None

    return RegulationConfig(
        type=data.get(CONF_REGULATION_TYPE, REGULATION_PI),
        devices=data.get(CONF_DEVICES, []),
        kp=data.get(CONF_KP, DEFAULT_KP),
        ki=data.get(CONF_KI, DEFAULT_KI),
        k_ext=data.get(CONF_K_EXT, DEFAULT_K_EXT),
        balance_point=data.get(CONF_BALANCE_POINT, DEFAULT_BALANCE_POINT),
        offset_max=data.get(CONF_OFFSET_MAX, DEFAULT_OFFSET_MAX),
        stabilization_threshold=data.get(CONF_STABILIZATION_THRESHOLD, DEFAULT_STABILIZATION_THRESHOLD),
        accumulated_error_threshold=data.get(CONF_ACCUMULATED_ERROR_THRESHOLD, DEFAULT_ACCUMULATED_ERROR_THRESHOLD),
        integral_reset_threshold=data.get(CONF_INTEGRAL_RESET_THRESHOLD, DEFAULT_INTEGRAL_RESET_THRESHOLD),
        integral_reset_factor=data.get(CONF_INTEGRAL_RESET_FACTOR, DEFAULT_INTEGRAL_RESET_FACTOR),
        integral_decay_halflife=data.get(CONF_INTEGRAL_DECAY_HALFLIFE, DEFAULT_INTEGRAL_DECAY_HALFLIFE),
    )


def parse_opportunistic(data: dict[str, Any] | None) -> OpportunisticConfig | None:
    """Parse opportunistic heating config."""
    if not data:
        return None

    return OpportunisticConfig(
        enabled=data.get("enabled", False),
        threshold=data.get(CONF_THRESHOLD, DEFAULT_OPPORTUNISTIC_THRESHOLD),
    )


def parse_tou_mode_config(data: dict[str, Any]) -> ZoneTouModeConfig:
    """Parse a TOU mode config (heat or cool) from validated dict."""
    return ZoneTouModeConfig(
        pre_condition_minutes=data.get(
            CONF_TOU_PRE_CONDITION_MINUTES, DEFAULT_TOU_PRE_CONDITION_MINUTES
        ),
        relaxation_amount=data.get(
            CONF_TOU_RELAXATION_AMOUNT, DEFAULT_TOU_RELAXATION_AMOUNT
        ),
    )


def parse_zone_tou_config(data: dict[str, Any] | None) -> ZoneTouConfig | None:
    """Parse per-zone TOU config from validated dict."""
    if data is None:
        return None

    heat = None
    cool = None
    if CONF_TOU_HEAT in data:
        heat = parse_tou_mode_config(data[CONF_TOU_HEAT])
    if CONF_TOU_COOL in data:
        cool = parse_tou_mode_config(data[CONF_TOU_COOL])

    if heat is None and cool is None:
        return None

    return ZoneTouConfig(heat=heat, cool=cool)


def parse_heat_source(source_id: str, data: dict[str, Any]) -> HeatSourceConfig:
    """Parse a heat source config."""
    return HeatSourceConfig(
        source_id=source_id,
        name=data[CONF_NAME],
        devices=data[CONF_DEVICES],
    )


def parse_zone(zone_id: str, data: dict[str, Any]) -> ZoneConfig:
    """Parse a zone from config."""
    tou = parse_zone_tou_config(data.get(CONF_TOU))
    return ZoneConfig(
        zone_id=zone_id,
        name=data[CONF_NAME],
        sensors=parse_zone_sensors(data[CONF_SENSORS]),
        setpoints=parse_zone_setpoints(data[CONF_SETPOINTS]),
        heat_stages=[parse_stage(s) for s in data.get(CONF_HEAT_STAGES, [])],
        cool_stages=[parse_stage(s) for s in data.get(CONF_COOL_STAGES, [])],
        settings=parse_zone_settings(data.get(CONF_SETTINGS)),
        regulation=parse_regulation(data.get(CONF_REGULATION)),
        opportunistic=parse_opportunistic(data.get(CONF_OPPORTUNISTIC)),
        tou=tou,
        openings=OpeningConfig(
            entities=data[CONF_OPENINGS][CONF_OPENING_ENTITIES],
            open_delay=data[CONF_OPENINGS].get(CONF_OPEN_DELAY, DEFAULT_OPEN_DELAY),
            close_delay=data[CONF_OPENINGS].get(CONF_CLOSE_DELAY, DEFAULT_CLOSE_DELAY),
        ) if data.get(CONF_OPENINGS) and data[CONF_OPENINGS][CONF_OPENING_ENTITIES] else None,
    )


def parse_outdoor_reset(data: dict[str, Any] | None) -> OutdoorResetConfig:
    """Parse outdoor reset config."""
    if not data:
        return OutdoorResetConfig()

    return OutdoorResetConfig(
        never_heat_above=data.get(CONF_NEVER_HEAT_ABOVE),
        never_cool_below=data.get(CONF_NEVER_COOL_BELOW),
    )


def parse_device_mutex(data: dict[str, Any]) -> DeviceMutexRule:
    """Parse a device mutex rule from config."""
    when = data[CONF_WHEN]
    then = data[CONF_THEN]

    return DeviceMutexRule(
        device_id=when[CONF_DEVICE],
        mode=when[CONF_MODE],
        for_zone=when[CONF_FOR_ZONE],
        block_heat=then.get(CONF_BLOCK_HEAT, []),
        block_cool=then.get(CONF_BLOCK_COOL, []),
        blocked_devices_heat=then.get("blocked_devices_heat", []),
        blocked_devices_cool=then.get("blocked_devices_cool", []),
    )


def parse_conflicts(data: dict[str, Any]) -> ConflictConfig:
    """Parse conflict config."""
    return ConflictConfig(
        outdoor_reset=parse_outdoor_reset(data.get(CONF_OUTDOOR_RESET)),
        device_mutex=[
            parse_device_mutex(m)
            for m in data.get(CONF_DEVICE_MUTEX, [])
        ],
    )


def normalize_mutex_device_ids(
    conflicts: ConflictConfig, devices: dict[str, Device],
) -> None:
    """Normalize every mutex device reference to the internal device ID."""
    entity_ids = {device.entity_id: device_id for device_id, device in devices.items()}
    for rule in conflicts.device_mutex:
        rule.device_id = entity_ids.get(rule.device_id, rule.device_id)
        rule.blocked_devices_heat = [entity_ids.get(ref, ref) for ref in rule.blocked_devices_heat]
        rule.blocked_devices_cool = [entity_ids.get(ref, ref) for ref in rule.blocked_devices_cool]
        for device_id in (rule.device_id, *rule.blocked_devices_heat, *rule.blocked_devices_cool):
            if device_id not in devices:
                raise ValueError(f"Mutex references unknown device '{device_id}'")


def parse_master_mode_config(data: dict[str, Any] | None) -> MasterModeConfig:
    """Parse master mode config."""
    if not data:
        return MasterModeConfig()

    return MasterModeConfig(
        use_zone_defaults=data.get("use_zone_defaults", False),
        use_zone_away_setpoints=data.get("use_zone_away_setpoints", False),
        use_zone_setpoint=data.get("use_zone_setpoint"),
        setpoint_offset=data.get("setpoint_offset", 0),
        skip_time_escalation=data.get("skip_time_escalation", False),
        disable_all=data.get("disable_all", False),
    )


def parse_master(data: dict[str, Any]) -> MasterConfig:
    """Parse master config."""
    modes = {}
    modes_data = data.get(CONF_MODES, {})

    for mode_name in ["home", "away", "sleep", "vacation", "boost", "off"]:
        mode_enum = MasterMode(mode_name)
        modes[mode_enum] = parse_master_mode_config(modes_data.get(mode_name))

    return MasterConfig(
        name=data[CONF_NAME],
        occupancy_entity=data.get(CONF_OCCUPANCY_ENTITY),
        modes=modes,
    )
