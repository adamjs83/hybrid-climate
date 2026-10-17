# Saving changes

This page explains what happens when you press Save in the options flow, and which changes make the integration take over your thermostats again. You need it when you tune a setting and want to know whether your equipment will be touched.

## What happens when you press Save

Each page saves on its own and closes the options flow. Home Assistant then reloads the integration with the new settings. A page whose values match what is stored writes nothing for that zone.

Every save is either **structural** or **non-structural**.

| Structural | Non-structural |
|------------|----------------|
| Adding or removing a zone (including a YAML-only zone's first UI save) | Names, setpoints, occupancy |
| A zone's temperature sensors | Thresholds, escalation times, hysteresis, minimum runtime |
| The devices in a heating or cooling stage, and which stage number each sits in | Wall thermostats that follow hand changes (`allow_command`) |
| A new or removed device entry (the first save of a device with no stored entry, from the device page or the Regulation page), or a device's Can Heat / Can Cool (a stage save that adds a missing capability counts) | Heating and cooling regulation, idle action, compressor and dry-out settings |
| Mutex rules and heat source groups | Time-of-use, presets, global settings |

## What the reload does to your equipment

After a non-structural save, the reload skips the startup takeover. Tuning a setpoint or a regulation setting does not send every thermostat its idle action.

After a structural save, and on any later reload, Home Assistant restart or configuration apply through the services, the takeover runs as usual. Each device that no zone currently owns gets its idle action once. See [Idle and restore](../concepts/idle-and-restore.md).

## Related

- [Zones](zones.md)
- [Devices](devices.md)
- [Shared equipment](shared-equipment.md)
- [Global settings](global-settings.md)
- [Idle and restore](../concepts/idle-and-restore.md)
- [Services](../reference/services.md)
