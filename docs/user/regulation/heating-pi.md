# Heating PI regulation

PI regulation adjusts the setpoint a slow heating system receives, based on how far the room is from the target and how long it has been off target. You need this page when a zone has radiant floors or another system that reacts slowly and overshoots or swings under plain on/off control.

## Why PI

Radiant floor heating can take 30 to 60 minutes to respond to a setpoint change. Plain on/off control then causes three problems:

- **Overshoot:** the floor keeps heating after the room reaches the target.
- **Undershoot:** the room cools well below the target before the floor catches up.
- **Oscillation:** the temperature swings above and below the setpoint.

PI control avoids this by moving the floor setpoint up or down as the room error and the outdoor temperature change.

Heating PI only applies to heating, so only heat-capable devices can be regulated. The **Regulation** page lists only those devices, so a cool-only device such as a shared AC never appears. If a stored or hand-edited configuration lists a cool-only device anyway, it is dropped when the zone loads, a warning is logged, and `get_config` shows it under `regulation.ignored_devices`.

## Choose PI for a zone

Open **Configure → Zones → your zone → Regulation**. The **Heating** section has these settings:

| Setting | What it does | Default | Where |
|---------|--------------|---------|-------|
| **Heating regulation** | **Direct** sends the zone target to the thermostats. **PI** adjusts the thermostat setpoint from the room error. Choosing **Direct** removes the stored PI settings | Direct | **Regulation** page |
| Heating thermostats | The devices PI adjusts. Only heat-capable devices from the zone's stages are listed, stages 3 and up included | none | **Regulation** page |
| **Minimum heating command change** | Smallest change in °F (0 to 5) before a new regulated setpoint is sent. 0 sends every change | 0 | **Regulation** page |
| **Minimum time between changes** | Minutes (0 to 60) between regulated setpoint changes. 0 allows every change | 0 | **Regulation** page |

The five PI gains are the zone's number entities (see [Tune the five live numbers](#tune-the-five-live-numbers)). The page description lists them read-only with their current values. For a **Direct** zone they appear after you choose **PI** and save.

## Tuning

The first five values in this table are the zone's live number entities (see below). The rest are in the **Heating PI: advanced** section of the same Regulation page (it opens collapsed), or in the zone's YAML regulation block.

| Setting | What it does | Start value | Adjust if |
|---------|--------------|-------------|-----------|
| Proportional gain (`kp`) | Response to the current error | 1.0 | The room is slow to respond: increase. It oscillates: decrease. |
| Integral gain (`ki`) | Response to the accumulated error | 0.01 | A steady error persists: increase. It overshoots after long runs: decrease. |
| Outdoor gain (`k_ext`) | How strongly the outdoor temperature adds to the offset | 0.15 | The house loses heat fast in the cold: increase. It is well insulated: decrease. |
| Maximum offset (`offset_max`) | Largest offset in either direction, in °F | 10 | The floor can take more: increase. You see comfort problems: decrease. |
| Outdoor balance point (`balance_point`) | Outdoor °F at which the outdoor term is zero | 65 | Adjust for your climate. |
| Error deadband (`stabilization_threshold`) | °F of error below which the integral stops accumulating | 0.5 | The room oscillates by 0.3°F: increase. It never quite reaches the target: decrease. |
| Minimum setpoint change (`regulation_threshold`) | Smallest change in °F before a new setpoint is sent (0 to 5) | 0 | Thermostat commands are too frequent: increase. |
| Minimum time between changes (`regulation_min_period`) | Minutes between regulated setpoint changes (0 to 60) | 0 | Commands are too frequent: increase. |
| Integral cap (`accumulated_error_threshold`) | Largest value the accumulated error can reach | 240 | Stops runaway buildup during long recoveries. |
| Reset trigger (`integral_reset_threshold`) | Setpoint change in °F that partly resets the integral | 2.5 | Raise it to reset less often. |
| Reset retention (`integral_reset_factor`) | Share of the integral kept on a reset (0.3 keeps 30%) | 0.3 | Raise it to keep more. |
| Idle decay half-life (`integral_decay_halflife`) | Minutes for the integral to fall to 50% while idle. 0 turns decay off | 120 | Lower it to forget old conditions sooner. |

### How to tune

Change one value at a time, by about a quarter of its current value, and watch the room and `regulated_setpoint` for a few hours, because a floor takes that long to answer. Start with the proportional gain, then the outdoor gain for undershoot in cold weather, and touch the integral gain last.

### Tune the five live numbers

The proportional gain, integral gain, outdoor gain, maximum offset and outdoor balance point are number entities, so you can change them from the dashboard card or the entity page without a reload. All are in the Configuration category and are named after the zone's device, for example "Basement Heating PI proportional gain".

| Number entity | Range |
|---------------|-------|
| Heating PI proportional gain | 0.1 to 5.0 |
| Heating PI integral gain | 0.001 to 0.5 |
| Heating PI outdoor gain | 0.0 to 1.0 |
| Heating PI maximum offset | 1 to 20°F |
| Heating PI outdoor balance point | 30 to 80°F |

Home Assistant generates entity IDs from the entity name when it first registers them, so IDs differ between installs. Find a zone's IDs in the entity registry, or in `get_config` under `entity_controlled`. Never build an ID from the zone name.

### YAML reference

```yaml
zones:
  main_floor:
    regulation:
      type: pi
      devices: [floor_heat_1, floor_heat_2]
      kp: 1.0                       # proportional gain
      ki: 0.01                      # integral gain
      k_ext: 0.15                   # outdoor gain
      balance_point: 65             # outdoor temperature with no offset
      offset_max: 10                # largest offset, plus or minus
      stabilization_threshold: 0.5
      regulation_threshold: 0.5     # change this to limit tiny setpoint changes
      regulation_min_period: 10
      accumulated_error_threshold: 240
      integral_reset_threshold: 2.5
      integral_reset_factor: 0.3
      integral_decay_halflife: 120
```

## How it works

The controller adds an offset to the zone target:

```
regulated setpoint = zone target + offset
offset = P term + I term + outdoor term

P term       = proportional gain x error
I term       = integral gain x accumulated error
outdoor term = outdoor gain x (balance point - outdoor temperature)
```

Error is the zone target minus the room temperature. Take a zone target of 70°F, a room at 68°F (error +2°F) and an outdoor temperature of 30°F:

- P term: 1.0 x 2 = +2°F, the immediate response to the error.
- I term: 0.01 x 60 = +0.6°F, built up over about 30 minutes of error.
- Outdoor term: 0.15 x (65 - 30) = +5.25°F. It is cold outside, so the controller pushes harder.
- Regulated setpoint: 70 + 2 + 0.6 + 5.25 = 77.85°F, rounded to the thermostat's own step (for example whole degrees) and then sent. It is sent again only when the thermostat's reported target is clearly away from it, so a setpoint the thermostat has rounded is not re-sent every cycle.

| Term | Purpose | Effect |
|------|---------|--------|
| **P (proportional)** | Immediate response | A large error gives a large correction. It is fast but cannot remove a steady error. |
| **I (integral)** | Removes steady error | It accumulates over time. If the room stays 0.5°F cold, the I term builds until the room catches up. |
| **Outdoor** | Anticipates the heating load | Cold outside raises the floor setpoint before the room drops. |

## Worked example

A main floor zone has radiant floors (PI) and a heat pump as stage 2. Only the floors are regulated.

```yaml
zones:
  main_floor:
    heat_stages:
      - {stage: 1, devices: [floor_heat_1, floor_heat_2], threshold: 0.5}
      - {stage: 2, devices: [heat_pump], threshold: 2.0, time_escalation: 1800}
    regulation:
      type: pi
      devices: [floor_heat_1, floor_heat_2]   # only these get the PI setpoint
      kp: 1.0
      ki: 0.01
      k_ext: 0.15
```

The room is at 68.5°F, the target is 70°F, it is 35°F outside and stage 1 has been running for 20 minutes. Each update cycle works like this:

1. **Get temperatures.** Living room 68.3°F and kitchen 68.7°F average to 68.5°F.
2. **Calculate the error.** 70 - 68.5 = +1.5°F, so the zone needs heat.
3. **Check hysteresis.** The zone is heating and the error is above 0, so it keeps heating.
4. **Check conflicts.** No outdoor reset applies and no device is blocked by a mutex rule.
5. **Run the PI calculation.** P = 1.0 x 1.5 = +1.5°F. I = 0.01 x 90 = +0.9°F. Outdoor = 0.15 x (65 - 35) = +4.5°F. The offset is +6.9°F, so the regulated setpoint is 76.9°F.
6. **Select the stage.** An error of 1.5°F is at least the stage 1 threshold (0.5°F) and below the stage 2 threshold (2.0°F). Stage 1 has run 20 minutes, under the 30 minute escalation. Stage 1 stays selected.
7. **Activate the devices.** Both floor thermostats are set to 76.9°F, the regulated setpoint.

PI applies only to the regulated devices. If the heat pump joins in at stage 2, it receives the plain zone target of 70°F.

## Anti-windup and integral management

The integral term is protected against growing without limit and against holding stale state.

To prevent runaway accumulation:

1. **Output saturation.** The integral stops accumulating when the offset reaches the maximum offset.
2. **Deadband.** It stops accumulating while the error is below the error deadband.
3. **Hard cap.** The integral cap limits the accumulated error.

To adapt to changing conditions:

4. **Setpoint change reset.** A setpoint jump larger than the reset trigger scales the integral by the reset retention. The controller does not drag its old correction into a very different target.
5. **Idle decay.** While the room is at the setpoint, the integral decays exponentially with the half-life. Long idle periods forget old assumptions and short ones keep the controller responsive.

## Limiting how often the setpoint changes

The minimum heating command change and the minimum time between changes both apply to PI heating, and a changed setpoint must pass both. These sends skip the limits:

- A changed heat target.
- The first cycle after a restart or reload.
- The first cycle after equipment is released, deactivated or reversed in direction.

While a change is held back, devices keep receiving the last selected regulated setpoint. Cooling and Direct zones are not affected.

## Idle behavior

When a PI zone goes idle because the room is at the target, the floor stays at the current regulated setpoint instead of dropping to a setback. This keeps the balance the controller found, stops the room from cooling and triggering another heat cycle, and acts as a learned maintenance temperature.

## Monitoring PI state

The zone entity shows the controller state as attributes:

| Attribute | What it shows |
|-----------|---------------|
| `regulation_offset` | The raw PI offset currently calculated |
| `accumulated_error` | The integral accumulation |
| `regulated_setpoint` | The setpoint sent to the regulated devices (the held value while a change is limited) |
| `cool_regulation_offset` | The cooling PI push as a signed offset (0 or below) on the cool target |
| `cool_accumulated_error` | The cooling integral term |
| `cool_regulated_setpoint` | The cool target minus the push, before the per-device limiter |

## Related

- [Cooling regulation](cooling.md)
- [Staging](../concepts/staging.md)
- [Idle and restore](../concepts/idle-and-restore.md)
- [Zones](../configuration/zones.md)
- [Devices](../configuration/devices.md)
