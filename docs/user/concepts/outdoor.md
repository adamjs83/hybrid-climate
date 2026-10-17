# Outdoor temperature

This page covers how Hybrid Climate reads the outdoor temperature, what happens when the reading is missing, and how
to change the outdoor limits for one zone. Read it when heating or cooling stops because of the weather, or when one
zone needs different limits from the rest.

## Outdoor sensors and fallback

On the **Global settings** page, **Outdoor temperature entities (in priority order)** takes an ordered list of sensor
and weather entities.

- Each cycle, Hybrid Climate reads every entity in order. The first valid reading wins, and only that value drives
  the outdoor limits. It still checks the later entities so the status report can show them.
- If every entity is invalid or unavailable, Hybrid Climate keeps the last good reading for up to 10 minutes.
- After that, each zone keeps whatever heat and cool permission it last had. An outage does not block a zone that is
  already running.
- At startup, a zone with an outdoor limit stays blocked until it has received one valid outdoor reading. A backup
  entity in the list gives it a chance to get that reading when the first sensor is down.
- Switching to a backup logs a warning and recovering to the first entity logs an info message. Neither repeats
  every cycle.

## House-wide outdoor limits

Two **Global settings** apply to every zone unless the zone overrides them:

| Setting | What it does | Default | Where |
|---------|--------------|---------|-------|
| Never heat above (outdoor temp) | Disables heating when the outdoor temperature is above this value | None | **Global settings** |
| Never cool below (outdoor temp) | Disables cooling when the outdoor temperature is below this value | None | **Global settings** |

The two limits sit last on the page, in that order.

A limit releases with a 1°F margin: heating blocked above 55°F resumes once the outdoor temperature is at or below
54°F, and cooling blocked below 63°F resumes at or above 64°F, so a reading hovering on the limit does not toggle
equipment.

## The lockout heat floor

While the outdoor heat lockout is blocking heating, Hybrid Climate does not let an idle heating setpoint sit warm
enough for the device's own thermostat to call for heat. It caps the idle setpoint at the **Maximum idle heat target
during outdoor lockout**. This can only pull the setpoint down to a deeper setback. It never raises it. The setting,
its default (55°F) and its bounds (40 to 60°F) are in [Global settings](../configuration/global-settings.md).

The floor applies when the lockout itself releases a device, too: a setback device goes straight to the floor instead of switching off first.

The lockout starting or ending never sends a command by itself. The floor applies the next time a device goes idle, and
it stays in place until the device's next release, even after the lockout clears. PI-regulated devices ignore it
while the zone idles at its regulated setpoint; when a forced lockout releases them, they go to the floor like any
setback device.

## A different outdoor limit for one zone

By default the house-wide limits apply to every zone. Some zones need an exception. A basement with boiler equipment
can get hot and need cooling in winter, when the outdoor temperature is below the house-wide cooling limit.

In the UI, open the zone's **Behaviour** page and set **Outdoor limit for heating** and **Outdoor limit for cooling**.
Each has three choices:

- **Use house limit**: the house-wide limit applies.
- **No limit**: the zone heats or cools whatever the outdoor temperature is.
- **This zone's value (below)**: the **Zone never heat above** or **Zone never cool below** value applies.

In YAML, the same exception looks like this:

```yaml
zones:
  basement:
    settings:
      outdoor_reset:
        never_cool_below: null  # change: null removes the cooling limit; a number sets this zone's own limit
        # never_heat_above: 80  # or set a heating limit for this zone
```

| Value | Meaning |
|-------|---------|
| No `outdoor_reset` entry | The house-wide limits apply |
| `null` | This restriction is switched off for the zone |
| A number | This zone uses that limit instead of the house-wide one |

## Related

- [Global settings](../configuration/global-settings.md)
- [Zones](../configuration/zones.md)
- [Idle setback and restore](idle-and-restore.md)
- [Staging](staging.md)
