# Troubleshooting

This page helps you find out why Hybrid Climate is not doing what you expect. Find your symptom below. The sections after it tell you where to look when the quick check is not enough.

## Problems by symptom

### The integration does not load

Check the integration's setup screens under **Settings → Devices & Services → Hybrid Climate**. If this was a first YAML import, also check the `hybrid_climate:` include in `configuration.yaml` and the imported file. See [YAML configuration](yaml.md).

### A zone does not respond

Read the zone's **Reason** diagnostic entity first: it names an outdoor lockout, an open door or window, a shared-equipment rule, a hold, or a stage with no usable device. Then check that the zone's stage devices are available and not unavailable in **Settings → Devices & Services → Entities**. If the room is close to target, remember that equipment starts only when the error reaches the stage 1 threshold. See [Staging](concepts/staging.md) and [Entities](entities.md#diagnostic-entities).

### A zone shows no temperature

Check the zone's sensor ids on its **Basics & sensors** page, and make sure each sensor is available (not `unavailable` or `unknown`). See [Zones](configuration/zones.md).

### Outdoor limits do nothing

Confirm that at least one outdoor sensor is set and returns a valid temperature. With more than one sensor, run `hybrid_climate.get_status` from **Developer tools → Actions** with **Return response** ticked and read `outdoor.candidates` to see which one is `ok`. The **Outdoor source** diagnostic entity shows which sensor is in use. See [Outdoor limits](concepts/outdoor.md) and [Status and config fields](reference/status-fields.md#get_statusoutdoor).

### A wall thermostat change is ignored

On the zone's **Behaviour** page, check that the thermostat is listed under **Wall thermostats that follow hand changes** (in YAML, `allow_command: true` in the stage's device entry). It is set per zone, not per device. See [Wall thermostats](concepts/wall-thermostats.md).

### The zone target snaps back

If the device is still in the `commanding` state, wait 10 seconds for the grace period before you judge the change. Check `command_state` in `get_status.devices.<id>`. See [Wall thermostats](concepts/wall-thermostats.md).

### A zone ignores a mode or occupancy change

The zone is probably held: its hold switch is on and its climate entity shows the `hold` preset. Turn the switch off, or press **Resume saved temperatures** on the card, and the saved temperatures apply again. See [Holds](concepts/holds.md).

### Home Assistant says Hybrid Climate is logging too frequently

Update Hybrid Climate to the latest release in HACS, then restart Home Assistant. See the [release changelog](https://github.com/adamjs83/hybrid-climate/blob/main/CHANGELOG.md).

## Check the logs

Go to **Settings → System → Logs** and filter for `hybrid_climate`. For verbose output, add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.hybrid_climate: debug   # remove when you are done
```

## Check Repairs

Conditions that need you appear under **Settings → System → Repairs**. Each issue names the entity and where to go, and clears itself when the condition ends. The list is in [Entities](entities.md#repairs-issues).

## Download Diagnostics

For a detailed snapshot, download **Diagnostics** from the integration's menu in **Settings → Devices & Services**. It covers:

- Sensor availability.
- Zone lockouts.
- Compressor holds.
- Requested versus reported device modes.

## Related

- [Entities](entities.md)
- [YAML configuration](yaml.md)
- [Wall thermostats](concepts/wall-thermostats.md)
- [Outdoor limits](concepts/outdoor.md)
- [Services](reference/services.md)
- [Status and config fields](reference/status-fields.md)
