# Staging, thresholds and hysteresis

This page explains how a zone decides when to heat or cool and which devices to use. Read it when a zone starts too
early or too late, or when you set up the **Heating stages**, **Cooling stages** and **Behaviour** pages of a zone.

## Hysteresis: when a zone starts and stops

The **Start/stop temperature buffer (hysteresis)** on the **Behaviour** page creates a deadband around the target.
It stops a zone from switching on and off rapidly when the room sits close to the target.

```
   Start cooling above this line
              ↓
    ┌─────────●─────────┐ target + hysteresis (70.5°F)
    │                   │
    │    DEADBAND       │ ← No action taken in this zone
    │                   │
    ├─────────●─────────┤ target (70°F): heating and cooling both stop here
    │                   │
    │    DEADBAND       │
    │                   │
    └─────────●─────────┘ target - hysteresis (69.5°F)
              ↑
   Start heating below this line
```

The rules:

- **Start heating** when the room drops below the target minus the hysteresis.
- **Stop heating** when the room reaches the target (not the target plus the hysteresis).
- **Start cooling** when the room rises above the target plus the hysteresis.
- **Stop cooling** when the room reaches the target.

For example, with a target of 70°F, a hysteresis of 0.5°F and a stage 1 threshold no larger than that:

1. The room is at 70.2°F: the zone is idle, because it is inside the deadband.
2. The room drops to 69.4°F: heating starts, because that is below 69.5°F.
3. The room reaches 70°F: heating stops and the zone goes idle.
4. The room rises to 70.6°F: cooling starts, because that is above 70.5°F.
5. The room reaches 70°F: cooling stops and the zone goes idle.

## Stage thresholds: which stage runs

Hysteresis decides whether the zone heats or cools at all. A stage **threshold** decides which stage runs. The
threshold is how far the room is from the target, in °F. You set it per stage on the **Heating stages** and
**Cooling stages** pages ("start heating when the room is this far below target").

With a target of 70°F, a hysteresis of 0.5°F, a stage 1 threshold of 1.0°F and a stage 2 threshold of 3.0°F:

| Room temperature | Error | Hysteresis check | Stage selected |
|------------------|-------|------------------|----------------|
| 70.5°F | -0.5°F | Inside the deadband | Idle |
| 69.4°F | +0.6°F | Needs heat | Idle: no stage reaches its threshold |
| 68.5°F | +1.5°F | Needs heat | Stage 1 |
| 66.0°F | +4.0°F | Needs heat | Stage 2 |

The highest stage whose threshold the room meets wins. If no stage reaches its threshold, nothing runs: when the stage 1
threshold is larger than the hysteresis, equipment starts only once the error reaches that threshold.

## Time escalation

A stage can also start because it has waited long enough, even when the room has not reached its threshold. On the
**Heating stages** page, **Add backup equipment after** (minutes) sets that wait for stage 2. If stage 1 runs for that
long without the room reaching the target, stage 2 switches on even when the error is only 2°F.

Boost mode skips the wait: as soon as the zone needs heat or cooling, every stage that has a wait time switches on at
once, and stages without one still follow their thresholds.

## Additive staging

Stages add to each other. When stage 2 switches on, the stage 1 devices stay on:

```
Stage 1: [radiant_floor]
Stage 2: [radiant_floor, heat_pump]  ← the floor stays on
```

Some systems replace stage 1 with stage 2. Hybrid Climate does not.

## Stage conditions

A stage can carry a condition. For example, the **stage 2 minimum outdoor temperature** on the **Heating stages** page
keeps a heat pump out of use when it is too cold outside. If a condition is not met, the zone skips that stage even
when the threshold or the wait time says it should run.

In YAML, the same stage looks like this:

```yaml
heat_stages:
  - stage: 2
    devices: [heat_pump]
    threshold: 3.0            # change: the error in °F that adds this stage
    time_escalation: 1800     # or after 30 minutes in stage 1
    conditions:
      outdoor_temp_min: 35    # skip this stage below 35°F outside
```

| Key | What it does | Where in the UI |
|-----|--------------|-----------------|
| `threshold` | Error in °F that adds the stage | **Heating stages** and **Cooling stages** |
| `time_escalation` | Seconds in the previous stage before this stage is added | **Add backup equipment after** (minutes) |
| `outdoor_temp_min` | Lowest outdoor temperature in °F at which the stage may run | **Stage 2 minimum outdoor temperature** |

## How a decision is made

Each control cycle the zone works through these steps:

1. It reads the room temperature and the target, and calculates the error (target minus room temperature).
2. It applies the hysteresis rules. A heating zone stops when the error reaches 0 or below. A cooling zone stops when
   the error reaches 0 or above. An idle zone starts heating when the error is above the hysteresis, and starts
   cooling when the error is below minus the hysteresis.
3. If the zone is heating or cooling, it checks each stage in order. A stage qualifies when its conditions are met and
   either its threshold or its wait time is reached. The highest qualifying stage wins. If no stage qualifies, no device
   runs.
4. It switches on every device from stage 1 up to the winning stage, and skips devices that another zone or a shared
   equipment rule is blocking.

## Related

- [Zones](../configuration/zones.md)
- [Shared equipment](../configuration/shared-equipment.md)
- [Holds](holds.md)
- [Idle setback and restore](idle-and-restore.md)
- [Outdoor temperature](outdoor.md)
