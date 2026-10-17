# Devices

A device is one climate entity that a zone uses, such as a thermostat, a mini-split or a heat pump. This page covers the **Devices** page: what each device can do, what it does when idle, compressor protection and door and window contacts. You need it when you add equipment or want to change how a device rests between calls.

Open it from **Configure → Devices**.

## The device list and page

The list shows each device as `<id> (heat+cool, setback 5°F, cooling: compensation)`. Choose a device to open its page.

| Setting | What it does | Default | Where |
|---------|--------------|---------|-------|
| Can Heat / Can Cool | Which directions the device supports. | From the entity's supported HVAC modes, until you save a choice | Configure → Devices |
| When idle: Turn Off | The device turns off completely when idle. | the default | Configure → Devices |
| When idle: Setback from target | The device holds a setback temperature (target plus or minus the offset). | off | Configure → Devices |
| Setback amount | Degrees below target (heat) or above target (cool). | 5°F | Configure → Devices |
| Compressor group | A shared outdoor compressor name. Use the same value on every member. | none | Configure → Devices |
| Minimum compressor run time / off time | Seconds to hold the shared group on or off. | none | Configure → Devices |
| Run fan after cooling (`cool_dry_out`) | Cool-capable devices only. Runs the fan only mode after a cooling run instead of the idle action. It shows the next time you open the page after ticking Can Cool. | off | Configure → Devices |
| Fan run time after cooling (`cool_dry_out_minutes`) | How long the fan only mode runs before the normal idle action. Range 1 to 30 minutes. | 10 | Configure → Devices |

The page shows cooling regulation read-only, for example "Cooling regulation: <mode> (set under Zones → <zones> → Regulation).", or a note that no zone's cooling stages use the device yet. Saving the device page keeps that setting. You change it on the zone's **Regulation** page (see [Zones](zones.md)).

## Compressor protection

Compressor protection is optional. Give every device that shares an outdoor compressor the same **Compressor group**, then set the minimum run time and off time. For a shared group, the longest configured interval among its members applies.

The integration watches each climate entity's reported HVAC mode as a stand-in for compressor activity. A thermostat that cycles its compressor while it stays in heat or cool cannot be timed precisely. At startup the previous transition is unknown, so the first state it sees begins a full interval.

Explicit shutdowns, including door and window lockouts, bypass the minimum run time. The fan only mode counts as a compressor stop.

## Door and window contacts

You pick opening contacts per zone on the zone's **Behaviour** page, with an open delay and a close delay. A contact reports `on` for open and `off` for closed.

A contact that is already open at startup, or missing or unavailable, locks the zone immediately. After a later open event, the open delay applies. All contacts must then stay closed for the close delay before control resumes.

A lockout sends equipment to off, even when its normal idle action is a setback.

## Related

- [Zones](zones.md)
- [Global settings](global-settings.md)
- [Shared equipment](shared-equipment.md)
- [Saving changes](saving.md)
- [Idle and restore](../concepts/idle-and-restore.md)
- [Cooling regulation](../regulation/cooling.md)
