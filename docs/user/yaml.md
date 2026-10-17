# YAML configuration

This page is for you if you already have a Hybrid Climate YAML file, or if you prefer to write your setup as text. YAML is optional: the setup screens under **Settings → Devices & Services → Hybrid Climate → Configure** can do everything a typical setup needs; only stages 3 and up need YAML.

Hybrid Climate imports YAML once, on first setup. After that import, make changes through **Configure**. Editing the YAML file later does not change a configuration that already exists.

## Import your file

Add this line to `configuration.yaml`:

```yaml
hybrid_climate: !include hybrid_climate_config.yaml
```

Then create `hybrid_climate_config.yaml` with the blocks below, restart Home Assistant and add the integration. The setup dialog shows **Configuration found: N zones, M devices** when the file was read. The complete, working file is [`example_config.yaml`](../../example_config.yaml) at the repo root. Start there if you want a file to copy.

## Outdoor and global

```yaml
outdoor_sensors:  # sensor.* and/or weather.* entities, in priority order
  - sensor.outdoor_temperature
  - weather.home  # backup, used only while the primary is missing/unavailable/invalid

lockout_heat_floor: 55  # Optional: max idle heat setpoint during outdoor heat lockout (40-60, default 55)
device_unavailable_grace: 300  # Optional: hold running stage through device outage (0-1800 s)
```

## Master and modes

```yaml
master:
  name: "Home HVAC"
  occupancy_entity: binary_sensor.home_occupied  # Optional: auto home/away
  modes:
    home:
      use_zone_defaults: true
    away:
      use_zone_away_setpoints: true
      setpoint_offset: -3  # Additional offset in away mode
    boost:
      skip_time_escalation: true  # Activate all stages immediately
    off:
      disable_all: true
```

## Conflicts

```yaml
conflicts:
  outdoor_reset:
    never_heat_above: 55  # Don't heat when outdoor > 55°F
    never_cool_below: 63  # Don't cool when outdoor < 63°F
  device_mutex:
    - when:
        device: shared_heat_pump
        mode: cool
        for_zone: basement
      then:
        block_heat: [main_floor]  # Can't heat main floor while basement cools
```

## Devices

```yaml
devices:
  # allow_command belongs to a zone's stage, not to the device
  basement_hp:
    entity_id: climate.basement_heat_pump
    capabilities: [heat, cool]
    compressor_group: basement_outdoor  # shared by indoor units on this compressor
    min_compressor_runtime: 300          # seconds
    min_compressor_off_time: 180         # seconds
    cool_overdrive: 5                    # °F below zone cool target during active cooling; 0 disables
    cool_regulation: overdrive           # off | overdrive | compensation | pi; pi pushes below the cool target by the zone cooling PI; unset infers from cool_overdrive
    cool_compensation_max: 3             # °F; unit-minus-room limit (push only in compensation, both ways in pi with cool_pi_compensation)
    # cool_pi_compensation: true         # pi only: also add (unit - room), both ways; ignored for 3 min per cooling run
    # cool_max_total_push: 8             # °F; pi with cool_pi_compensation never goes more than this below the cool target
    # cool_compensation_sensor: sensor.basement_hp_return_temp  # optional; must report °F (no conversion); default is the unit's current_temperature
    cool_regulation_threshold: 0.5       # °F the compensation offset must move before a re-send
    cool_regulation_min_period: 10       # minutes between compensation re-sends
    cool_dry_out: false                  # run fan_only after a cooling run to dry the coil
    cool_dry_out_minutes: 10             # 1-30; then the normal idle action
    idle:
      action: setback  # or "off"
      setback: 5

  living_room_nest:
    entity_id: climate.nest_thermostat
    capabilities: [heat]
    idle:
      action: setback
      setback: 5
```

## Zones

The first zone shows sensors, setpoints, both stage lists, settings and the optional blocks. The second shows a zone with no indoor sensors and a wall thermostat.

```yaml
zones:
  basement:
    name: "Basement"
    sensors:
      indoor:
        - sensor.basement_temperature
      aggregation: average  # average | min | max | median | weighted
      # weights:  # Optional; only used by "weighted"; missing entries default to 1.0
      #   sensor.basement_temperature: 1.0
      smoothing_samples: 3
    setpoints:
      default: 68
      away: 62
      occupancy_entity: binary_sensor.basement_occupied
      occupancy_off_delay: 90  # Seconds since this integration last saw occupancy (0-7200; default 0)
      occupied: 70
      unoccupied: 65
    heat_stages:
      - stage: 1
        devices: [basement_hp]  # Simple format: no allow_command
        threshold: 1.0
      - stage: 2
        devices: [basement_hp, backup_heat]
        threshold: 3.0
        time_escalation: 1800  # Escalate after 30 min
    cool_stages:
      - stage: 1
        devices: [basement_hp]
        threshold: 1.0
    settings:
      hysteresis: 0.5
      min_runtime: 300
      # Optional: Override global outdoor reset for this zone
      outdoor_reset:
        never_cool_below: null  # null = disable restriction (allow cooling in winter)
        # never_heat_above: 80  # Or set zone-specific limit
    # Optional: pause this zone while a door or window is open
    openings:
      entities: [binary_sensor.basement_window]
      open_delay: 60   # seconds
      close_delay: 60  # seconds
    # Optional: Opportunistic heating (piggyback on boiler cycles)
    opportunistic:
      enabled: true
      threshold: 0.5  # Activate when 0.5°F below setpoint

  living_room:
    name: "Living Room"
    sensors:
      indoor: []  # Empty = fall back to device's current_temperature
      aggregation: average
    setpoints:
      default: 70
      away: 65
    heat_stages:
      - stage: 1
        devices:
          # Extended format: allow_command enables bidirectional sync
          - device: living_room_nest
            allow_command: true  # a hand change on this thermostat becomes the zone target
        threshold: 1.0
    cool_stages:
      - stage: 1
        devices: [whole_house_ac]  # Shared device, no allow_command
        threshold: 1.0
```

## Stage device formats

A stage lists its devices in one of two formats. You can mix them across stages and zones.

| Format | Example | Use it when |
|---|---|---|
| Simple list | `devices: [basement_hp]` | The device never sends changes back to the zone. No `allow_command`. |
| Extended form | `- device: living_room_nest` with `allow_command: true` | A wall thermostat should sync external changes into the zone target. |

```yaml
heat_stages:
  - stage: 1
    devices:
      - device: living_room_nest
        allow_command: true  # the one line you change: false or omit to ignore wall changes
    threshold: 1.0
```

`allow_command` belongs to the zone's stage, not to the device. The same device can sync in one zone and not in another.

## Related

- [Zones](configuration/zones.md)
- [Devices](configuration/devices.md)
- [Global settings](configuration/global-settings.md)
- [Staging](concepts/staging.md)
- [Wall thermostats](concepts/wall-thermostats.md)
- [Cooling regulation](regulation/cooling.md)
