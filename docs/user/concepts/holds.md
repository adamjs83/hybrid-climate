# Holds

A hold keeps a zone at the temperature you chose until you release it. Read this page when you change a temperature
on the card and want to know how long it lasts, or when a zone ignores a mode change and you want to know why.

## What a hold is

A temperature you set on a zone's card is a hold. The zone keeps that target until you release it.

A hold shows up in four places:

- The zone's hold switch turns on.
- The zone's climate entity shows the **hold** preset.
- The zone reports when a timed hold ends.
- The zone reports where its current targets came from: the hold, a saved preset such as Home or occupied, or a wall
  thermostat change.

The card's Status row also shows the hold, next to a **Resume saved temperatures** button.

## How a hold starts

- Edit the target on the zone's card.
- Turn on the zone's hold switch.
- Choose the **hold** preset on the zone's climate entity.
- Call the `hybrid_climate.set_hold` service to start a timed hold. See [Services](../reference/services.md).

## What a hold survives

While a zone is held, it ignores:

- Household mode changes between Home, Away, Sleep and Boost.
- Zone occupancy changes.
- Edits to the saved-temperature numbers.
- Options saves, integration reloads and Home Assistant restarts.

Time-of-use price adjustments pause until the hold ends. A hold switched on during an adjustment keeps the adjusted temperatures you see on the card, not the saved ones underneath.

## What ends a hold

A hold ends, and the zone resumes its saved temperatures, when any of these happens:

- You turn the hold switch off.
- You choose the **none** preset.
- A timed hold reaches its end time.
- The house enters Vacation. This stops a forgotten hold from heating an empty house for weeks.

## The wall thermostat exception

A hand change on a wall thermostat that follows hand changes releases the hold without the resume. The wall
thermostat's value becomes the zone target instead. The next household mode change replaces that target. See
[Wall thermostats](wall-thermostats.md).

## What stays stronger than a hold

A hold changes the target. It never changes whether the equipment is allowed to run. These all stay stronger than a
hold:

- Master Off and zone Off.
- Open doors and windows.
- Outdoor lockouts.
- Shared-equipment rules.

## The hold switch

Each zone has a hold switch. It is on while the zone holds its current temperatures, and it also reports when the hold
started, when it ends, and the held heating and cooling targets. Turning the switch off resumes the saved
temperatures. The [entities page](../entities.md) lists the switch with the other zone entities.

## Related

- [Wall thermostats](wall-thermostats.md)
- [Presets and modes](../configuration/presets-and-modes.md)
- [Dashboard card](../dashboard-card.md)
- [Services](../reference/services.md)
- [Entities](../entities.md)
