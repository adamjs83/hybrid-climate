# Shared equipment

This page covers equipment that more than one zone depends on: heat source groups, rules for equipment that cannot run together, and opportunistic heating. You need it when two zones share a boiler or a heat pump, or when one piece of equipment must block another.

Open it from **Configure → Shared equipment**.

## Heat source groups

A heat source group collects the devices that share one physical heat source, such as a boiler or a heat pump. Each group has a Group ID, a display name and the devices in it.

When one zone in a group is heating, other zones in the group can start heating opportunistically and use the same heat source cycle (see below).

## Equipment that cannot run together

This section holds the rules that stop two things running at once (`device_mutex` rules in YAML). A rule has these fields:

- **Device**, **When device is** (heating or cooling) and **In zone**: what triggers the block.
- **Block heating in zones** and **Block cooling in zones**: the zones that cannot heat or cool while the rule is active.
- **Prevent these devices heating** and **cooling**: devices blocked directly, for example indoor units on a shared condenser.

Example: when the shared heat pump is cooling the basement, block heating in the main floor.

Editing a rule that came from a YAML import saves it as a UI rule.

## Deleting a group or a rule

Deleting a group or a rule asks you to confirm first, with Cancel preselected. The confirmation lists what refers to it: zones whose stage 1 heat devices are in the group, or the rule's device and blocked devices.

If another session changed the rules in the meantime, a rule delete stops and deletes nothing.

## Opportunistic heating

A zone can start heating when another zone in the same heat source group is already heating, which uses heat that is already being made. Three conditions apply:

1. Another zone in the same heat source group is actively heating.
2. This zone's temperature is below its setpoint by at least the threshold.
3. Only stage 1 devices start. Opportunistic heating never starts stage 2.

To set it, open the zone's **Behaviour** page, tick **Use an already-running shared heat source**, and set the threshold.

```yaml
zones:
  living_room:
    opportunistic:
      enabled: true
      threshold: 0.5   # °F below setpoint before this zone joins
```

## Related

- [Zones](zones.md)
- [Devices](devices.md)
- [Saving changes](saving.md)
- [Staging](../concepts/staging.md)
- [Outdoor limits](../concepts/outdoor.md)
