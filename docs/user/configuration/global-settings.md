# Global settings

This page covers the settings that apply to the whole house: the master name, outdoor temperature sources, presence, the time-of-use rate sensor, device outage grace and the outdoor limits. You need it when you first set up the integration, when an outdoor sensor changes, or when heating or cooling is blocked by the weather.

Open it from **Settings → Devices & Services → Hybrid Climate → Configure → Global settings**.

## Settings

| Setting | What it does | Default | Where |
|---------|--------------|---------|-------|
| Master name | Display name for the master climate entity. | none | Configure → Global settings |
| Outdoor temperature entities (in priority order) | An ordered list of `sensor.*` and `weather.*` entities. Each cycle uses the first entity with a valid reading; later entries are backups. | empty | Configure → Global settings |
| Presence entity (home/away) | A `binary_sensor.*` or `input_boolean.*` that switches the master between Home and Away. | none | Configure → Global settings |
| TOU rate period sensor | The `sensor.*` that each zone's **Time-of-use** page reads. | none | Configure → Global settings |
| Device outage grace period | Keeps a running stage going through a brief device outage. Range 0 to 1800 seconds; 0 turns it off. | 300 seconds | Configure → Global settings |
| Never heat above (outdoor temp) | Disables heating when the outdoor temperature is above this value. | none | Configure → Global settings |
| Never cool below (outdoor temp) | Disables cooling when the outdoor temperature is below this value. | none | Configure → Global settings |
| Maximum idle heat target during outdoor lockout | The highest idle heat setpoint while the "never heat above" lockout is active. Range 40 to 60°F. | 55°F | Configure → Global settings |

The outdoor limits are the last two limit fields on the page, in the order shown above. All temperatures are in °F. A zone can override the two outdoor limits on its own **Behaviour** page (see [Zones](zones.md)).

## Outdoor sensor fallback

The first entity in the list with a valid reading wins each cycle; the others are backups. If none reads, the last
good value is kept for 10 minutes, and after that each zone keeps its last permission. How this plays out, and the
idle heat floor during an outdoor lockout, are explained in [Outdoor temperature](../concepts/outdoor.md).

```yaml
# Order matters: the first valid reading wins
outdoor_sensors:
  - sensor.outdoor_temperature   # primary
  - weather.home                 # backup
```

## Related

- [Zones](zones.md)
- [Devices](devices.md)
- [Presets and modes](presets-and-modes.md)
- [Saving changes](saving.md)
- [Outdoor limits](../concepts/outdoor.md)
- [Idle and restore](../concepts/idle-and-restore.md)
