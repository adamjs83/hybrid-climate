# Idle setback and restore

This page covers what a device does when its zone has nothing to heat or cool, and how Hybrid Climate takes back a
device that was left running. Read it if a thermostat sits at a surprising setpoint after a restart, a save or a mode
change.

## Idle setback

A zone is idle when the room is at or above the target (for heating). Each device chooses what to do then:

- **Off** turns the device off completely.
- **Setback** sets the device to the zone target minus the setback, which keeps a minimum temperature.

For example, with a setback of 5°F and a zone target of 70°F, an idle zone sets the device to 65°F. When the zone
needs heat again, the device goes back to 70°F, or to the regulated setpoint if the zone uses PI regulation.

## When a zone goes idle

When the room reaches the target, the zone stops heating and then handles each device by type:

1. A device under PI regulation (for example a floor heating loop) holds its current regulated setpoint, such as
   77°F. This keeps the balance the PI controller found, and it keeps the integral value instead of resetting it.
2. A device without PI regulation (for example a heat pump) applies its idle action: setback to the target minus the
   setback, or off.
3. On the next cycle, if the room drops below the target minus the hysteresis (69.5°F in a 70°F zone), heating
   restarts, and the PI controller picks up where it left off.

When an outdoor heat lockout is active, an idle device may be set back further than usual. See
[Outdoor temperature](outdoor.md).

## Startup restore

Home Assistant does not remember which zone owned a device across a restart or an integration reload (a configuration
save counts as a reload). A device that a restart leaves in heat or cool, with no zone using it, would stay in that
mode until a zone happened to need it. To prevent that, Hybrid Climate runs a startup restore: a one-time pass that
sends each such device its idle action.

### What the restore does

- It covers every device that a zone's heat or cool stages reference.
- It sends each device its idle action (off or setback) exactly once per pass.
- If every zone that uses the device is disabled (master off, zone off, the "disable all" preset, or an open door or
  window lockout), it turns the device off.
- Otherwise it uses the most careful target among the zones that use the device: the lowest heating target or the
  highest cooling target. A shared device never gets a warmer setback than intended.
- It retries a device that cannot be commanded yet (unavailable, blocked by compressor protection, waiting on a
  mutex, or in a zone whose sensors have not reported) on the following cycles.

### What it never does

- It never turns equipment on.
- It never touches a device that is off or in a mode other than heat or cool.
- It never touches a device a zone already owns, or one that normal control has already addressed this cycle.
- It never touches a device under PI regulation, because those devices are refreshed every idle cycle anyway.
- It never touches a device again after the one command succeeds. A change you make by hand afterwards sticks until
  the next pass.

### When it runs

- After every Home Assistant start and every integration reload.
- About 10 seconds after the master mode settles following a change between Home, Away, Sleep, Vacation, Boost and
  Off. This includes the automatic Home and Away switch from your presence entity. A device that someone nudged by
  hand is brought back in line the next time the whole-home mode changes.
- When you press a zone's **Restore control** button, or call the `hybrid_climate.restore_control` service. See
  [Services](../reference/services.md).
- Not after a save that changes nothing structural. Structural means zones added or removed, zone sensors, stage
  device lists, device capabilities, mutex rules or heat source groups. Renaming a zone or editing a setpoint,
  threshold, regulation setting or global setting does not send every thermostat its idle action. See
  [Saving](../configuration/saving.md).

## The Restore control button

Each zone has a **Restore control** button in the Configuration category. Pressing it runs one restore pass over that
zone's devices, the same pass that runs after a mode change.

## Related

- [Outdoor temperature](outdoor.md)
- [Holds](holds.md)
- [Saving](../configuration/saving.md)
- [Services](../reference/services.md)
- [Heating PI regulation](../regulation/heating-pi.md)
- [Entities](../entities.md)
