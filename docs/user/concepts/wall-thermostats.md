# Wall thermostats that follow hand changes

Some zones have a physical thermostat that people adjust by hand. This page explains how Hybrid Climate keeps the
zone and that thermostat in step. You need it if you want a wall change to become the zone's new target.

## The setting

Each zone is a Hybrid Climate entity (the zone) that controls one or more physical thermostats or devices. Normally
the zone sends its target to the device and nothing flows back.

When a device has **Wall thermostats that follow hand changes** switched on, the sync runs both ways:

- Changing the zone target updates the thermostat.
- Changing the physical thermostat updates the zone target.

This suits a single-zone thermostat that people adjust on the wall. You set it on the zone's **Behaviour** page. It
applies to every stage that uses the device.

| Setting | What it does | Default | Where |
|---------|--------------|---------|-------|
| `allow_command` | Lets a hand change on the thermostat become the zone target | Off | **Behaviour** page, or the stage's device entry in YAML |

If the zone is held, a wall change releases the hold and its value becomes the zone target. See [Holds](holds.md).

## The two states

Hybrid Climate tracks each of these devices in one of two states.

| State | What it means | What happens to a change |
|-------|---------------|--------------------------|
| **Listening** | The device matches what the zone wants. | Any outside change syncs to the zone target. |
| **Commanding** | The zone just sent a command and is waiting for the device to answer. | Mismatches are ignored while it waits. |

| Value | Setting |
|-------|---------|
| Grace period after a command | 10 seconds |
| Difference that counts as a hand change | More than 0.1°F |
| Timeout while waiting | 60 seconds |

After a command the device moves to Commanding and stays there until it reports the commanded value (back to
Listening) or 60 seconds pass. On that timeout the device goes back to Listening without changing the zone target, so
a thermostat that lags or refuses a value never overwrites what you set. Hand changes are only read in Listening; the
10-second grace period after a command keeps a slow reply from being mistaken for one.

## When you change the wall thermostat

For example, you change a Nest from 70°F to 72°F.

1. Within one control cycle (10 seconds), Hybrid Climate sees that the device is Listening and its temperature (72°F)
   differs from the one the zone wants (70°F).
2. It treats that as a hand change and sets the zone target to 72°F.
3. The device stays in Listening.

## When you change the zone

For example, you change a zone from 70°F to 68°F in Home Assistant.

1. The zone stores 68°F as its new target and updates its devices at once.
2. Hybrid Climate sends 68°F to the thermostat and moves the device to Commanding.
3. When the device reports 68°F, it returns to Listening. If nothing arrives within 60 seconds, it returns to
   Listening anyway and the zone keeps 68°F; the next hand change on the wall is read as usual.

## Related

- [Holds](holds.md)
- [Zones](../configuration/zones.md)
- [Devices](../configuration/devices.md)
- [Idle setback and restore](idle-and-restore.md)
