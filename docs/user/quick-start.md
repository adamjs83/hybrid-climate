# Quick start: your first zone

This page takes you from a freshly added integration to one working zone: an outdoor sensor, a room sensor and
one thermostat. Budget about ten minutes. You need the integration installed and added (see the README) and the
entity ids of one outdoor temperature sensor, one room temperature sensor and one `climate` device.

Every step below happens in **Settings → Devices & Services → Hybrid Climate → Configure**. Each page saves on
its own and closes the menu; reopen **Configure** for the next page.

## 1. Tell it the outdoor temperature

1. Open **Configure → Global settings**.
2. In **Outdoor temperature entities (in priority order)**, pick your outdoor sensor. A `weather` entity works
   too. Add a second one if you have it; it is used only while the first has no reading.
3. Leave the outdoor limits empty for now. Press **Save**.

What you should see: the integration reloads, and the master climate entity's `outdoor_temperature` attribute
shows the reading (open **Developer tools → States** and search for the master entity).

<!-- screenshot: images/global-settings.png -->

## 2. Add the zone

1. Open **Configure → Zones → + Add New Zone**.
2. On **Basics & sensors**: a **Zone ID** (lowercase, no spaces, for example `living_room`), a **Display name**,
   and the room's **Temperature sensors**. Leave **Sensor aggregation** at average and **Smoothing samples** at
   its default. Press **Next**.
3. On **Heating stages**: tick **Enable heating**, pick the thermostat under stage 1, and keep the stage 1
   threshold at 1.0 (heating starts when the room is 1 °F below target). Leave stage 2 empty. Press **Next**.
4. On **Cooling stages**: tick **Enable cooling** and pick the device under stage 1 if the room can cool;
   otherwise leave it unticked. Press **Save**.

What you should see after the reload:

| Entity | Example id |
|---|---|
| Zone climate | `climate.hybrid_climate_living_room` |
| Hold switch | `switch.living_room_hold` |
| Saved temperatures | `number.living_room_heating_target_home` and the other mode targets |
| Temperature sensor | `sensor.living_room_temperature` |

Ids are generated from the names, so yours may differ. Find them on the zone's device page under the integration.

<!-- screenshot: images/zone-menu.png -->

## 3. Set a temperature

The master starts in **Home**, and a new zone's climate entity runs in heat/cool mode, so it heats or cools as
needed without you choosing a direction.

1. Open the zone climate entity and set the heating target 2 °F above the room temperature.
2. Within ten seconds the thermostat you picked for stage 1 is set to that target in heat mode.
3. The zone's hold switch turns on: a temperature set by hand is a hold and stays until you turn the switch off.
   Turn it off now; the zone goes back to its saved **Heating target: Home** number (find it on the zone's device
   page and set it to what you want).

The saved temperatures live in the zone's number entities. Change **Heating target: Home** there, or on a
dashboard, and that is what the zone returns to when no hold is active.

## 4. Choose what the device does when the room is satisfied

1. Open **Configure → Devices** and pick the thermostat.
2. **When idle** decides what the device is sent once the room reaches target: **Turn Off**, or **Setback from
   target** with a **Setback amount** (for example 5 °F below the heating target, so the device keeps a floor
   temperature of its own). Press **Save**.

## 5. Optional: a second stage and outdoor limits

- Back on the zone's **Heating stages** page, add a backup device under stage 2 with a larger threshold (for
  example 3.0) and **Add backup equipment after** 30 minutes. Stage 2 joins stage 1; it does not replace it.
  → [Staging](concepts/staging.md)
- In **Global settings**, set **Never heat above** and **Never cool below** outdoor temperatures to stop the
  system fighting the season. → [Outdoor](concepts/outdoor.md)

## 6. Add the card

Add `/hybrid_climate/hybrid-climate-card.js` under **Settings → Dashboards → Resources** as a JavaScript
module, then add a card:

```yaml
type: custom:hybrid-climate-card
view: overview   # overview, zone, setpoints, pi or devices
```

Put it in a **Panel** view so the zones sit side by side. → [Dashboard card](dashboard-card.md)

<!-- screenshot: images/card-overview.png -->

## Where next

- Occupied and unoccupied temperatures, and what Away and Sleep do:
  [Presets and modes](configuration/presets-and-modes.md)
- Let the wall thermostat's dial change the zone: [Wall thermostats](concepts/wall-thermostats.md)
- A radiant floor that overshoots: [Heating PI](regulation/heating-pi.md)
- Something did not happen as described: [Troubleshooting](troubleshooting.md)
