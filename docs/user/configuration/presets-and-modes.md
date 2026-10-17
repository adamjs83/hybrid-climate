# Presets and modes

This page covers the master modes, the **Presets** page that sets what each mode does, the occupancy and time-of-use settings on a zone, and the number entities that hold your saved temperatures. You need it when you want Away to behave differently from Home, or when you tune a setpoint from a dashboard or an automation.

## Master modes

The master climate entity has six modes: Home, Away, Sleep, Vacation, Boost and Off. Each mode decides which saved temperatures the zones use and how aggressively they stage. Pick a mode on the master
climate entity (its preset list), with the `climate.set_preset_mode` action, or from the dashboard card's Overview
view.

If you set a **Presence entity** under [Global settings](global-settings.md), the master switches between Home and Away on its own when that entity changes.

## The Presets page

Open **Configure → Presets** to set the behaviour of each mode. The page names the setpoints a mode uses, for example "Away uses the Sleep setpoints."

| Setting | What it does | Default | Where |
|---------|--------------|---------|-------|
| Use zone setpoint | Which named setpoint the mode uses: default, away, sleep or vacation. | none | Configure → Presets |
| Setpoint offset | An extra temperature offset applied on top of that setpoint. | 0 | Configure → Presets |
| Skip time escalation | Activates all stages immediately. Meant for Boost. | off | Configure → Presets |
| Disable all zones | Turns off every zone. Meant for Off. | off | Configure → Presets |

```yaml
# Vacation: use the away setpoints, 5°F further out
master:
  modes:
    vacation:
      use_zone_away_setpoints: true
      setpoint_offset: -5   # change this
```

## Occupancy and setpoints

On a zone's **Setpoints & occupancy** page (see [Zones](zones.md)), the description names the zone's setpoint number entities. Change setpoints there or on a dashboard. For a new zone it says they are created when the zone is saved.

The fields on the page are:

- Enable occupancy override.
- Occupancy sensor.
- On delay, in minutes (0 to 120): how long the sensor must stay on before the zone counts as occupied. Short walk-throughs are ignored and do not extend the off delay. The default of 0 applies occupancy at once. A sensor that is already on when Home Assistant starts counts as occupied immediately.
- Off delay, in minutes (0 to 120): how long the occupied setpoints stay after the sensor last showed the zone occupied.
- Occupied and unoccupied offsets for heating. Cooling uses the Occupied Cool and Unoccupied Cool numbers instead.

If you clear the sensor while the override is enabled, the integration removes the sensor.

Occupancy only applies while the house is in Home. Away, Sleep and Vacation use their own saved temperatures.

After a restart, a zone whose occupancy sensor has not reported yet keeps the occupancy it last published. If there is nothing to fall back to, the zone waits up to two minutes for the sensor before its first command rather than using its Home temperatures.

## Time-of-use

A zone's **Time-of-use** page sets, for each direction, whether it is enabled, the pre-condition minutes and the relaxation amount. A note at the top tells you when no TOU rate sensor is set under [Global settings](global-settings.md). The adjustments have no effect until you set one.

The rate sensor's state must be `peak`, `off_peak` or `super_off_peak`, and its `next_peak_start` attribute (a time) is what pre-conditioning counts down to. During a peak period the targets relax by the relaxation amount (heating lower, cooling higher); pre-conditioning does the opposite for the set number of minutes before the next peak.

## Saved temperatures and PI numbers

The integration creates number entities for each zone. They are grouped under the zone's device, sit in the Configuration category, and take effect without a reload. Adjust them in the UI, in automations or in scripts.

| Group | Numbers |
|-------|---------|
| Heating targets | Heating target: Home, Away, Sleep, Vacation. Home applies when no occupancy sensor is set. |
| Cooling targets | Cooling target: Home, Away, Occupied, Unoccupied, Sleep, Vacation. |
| Heating PI | Proportional gain (0.1 to 5.0), integral gain (0.001 to 0.5), outdoor gain (0.0 to 1.0), maximum offset (1 to 20°F), outdoor balance point (30 to 80°F). |
| Cooling PI (zones with cooling stages) | Proportional gain (0.1 to 5.0), integral gain (0.001 to 0.5), maximum push (0 to 10°F), outdoor gain (0 to 1, step 0.05, default 0 = off), outdoor balance point (50 to 100°F, default 75). |

Names start with the zone's name, for example "Basement Heating target: Home". What the PI numbers do is explained in [Heating PI](../regulation/heating-pi.md) and [Cooling regulation](../regulation/cooling.md).

Home Assistant generates entity IDs from the entity's name when it first registers them, so they follow the zone's display name and can differ between installs. Existing installs keep the IDs they have. Find a zone's IDs under **Settings → Devices & Services → Hybrid Climate**, on the zone's device page, or in the `entity_controlled` list that `get_config` returns. Never build an entity ID from the zone name.

```yaml
# Set the basement heating setpoint to 70°F
service: number.set_value
target:
  entity_id: number.hybrid_climate_basement_default_heat_temp  # look yours up; IDs vary by install
data:
  value: 70
```

## Related

- [Global settings](global-settings.md)
- [Zones](zones.md)
- [Saving changes](saving.md)
- [Heating PI](../regulation/heating-pi.md)
- [Cooling regulation](../regulation/cooling.md)
- [Entities](../entities.md)
