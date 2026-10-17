# Zones

A zone is one area of the house with its own sensors, setpoints and heating and cooling stages. This page explains the zone list, the seven pages of a zone's menu, and how to add a zone. You need it whenever you change what a zone senses, which devices it uses, or how it behaves.

Open it from **Configure → Zones**.

## The zone list

The list labels each zone with its stages and regulation, for example:

```
Basement — heat 2 stages, cool 1 — heating PI, cooling: compensation
```

The cooling part names the mode of each cooling device. Different modes are joined with `/`. Choose a zone to open its zone menu. **+ Add New Zone** starts the add path. **🗑️ Delete <name>** opens a confirmation that lists what still refers to the zone (such as mutex rules that name it), with Cancel preselected.

A zone that exists only in YAML cannot be deleted here.

## The zone menu

The zone menu has seven pages and a **← Back to zones** entry. Each page opens on its saved values and shows **← Cancel / Save** first. Cancel returns to the zone menu. Save stores that page only.

| Page | Fields |
|------|--------|
| **Basics & sensors** | Display name; temperature sensors (leave empty to use each device's own sensor); sensor aggregation (average, min, max, median or weighted); smoothing samples (the moving-average window). With Weighted, each selected sensor gets a weight field (0.1 to 10.0, labelled by its entity ID) on the same page. If you choose Weighted in the same save that adds sensors, the page shows again with "set them in the fields below" instead of saving default weights. |
| **Setpoints & occupancy** | See [Presets and modes](presets-and-modes.md#occupancy-and-setpoints). |
| **Heating stages** | Enable heating; stage 1 devices and threshold ("start heating when the room is this far below target"); stage 2 devices, threshold, **Add backup equipment after** (minutes) and the stage 2 minimum outdoor temperature. Stages 3 and up (from a YAML import) are kept as saved; their thresholds can be tuned through the services. |
| **Cooling stages** | The same fields for cooling, without an outdoor minimum. |
| **Behaviour** | Start/stop temperature buffer (hysteresis); minimum runtime; door and window contacts with open and close delays; **Use an already-running shared heat source** with its threshold; an outdoor limit per direction (**Use house limit**, **No limit** or **This zone's value**, plus the value); and wall thermostats that follow hand changes (set on every stage that uses the device). |
| **Regulation** | A **Heating** section and one **Cooling device N** section per cooling device (see below). |
| **Time-of-use** | See [Presets and modes](presets-and-modes.md#time-of-use). |

For how stages, thresholds and the buffer work, see [Staging](../concepts/staging.md). For the opening contacts, see [Devices](devices.md#door-and-window-contacts). For the shared heat source option, see [Shared equipment](shared-equipment.md#opportunistic-heating).

### Outdoor limit per zone

On the **Behaviour** page, set **Outdoor limit for heating** and **Outdoor limit for cooling** each to one of three choices:

- **Use house limit**: the limit from [Global settings](global-settings.md) applies.
- **No limit**: the zone heats or cools regardless of the outdoor temperature.
- **This zone's value (below)**: the **Zone never heat above** or **Zone never cool below** value applies.

A basement with boiler equipment that needs cooling even in winter is the usual case for **No limit**. See [Outdoor limits](../concepts/outdoor.md).

### The Regulation page

Heat-only zones show only the Heating section. Cool-only zones show only the cooling sections.

**Heating** has these fields:

- Heating regulation: **Direct** sends the zone target to the thermostat. **PI** adjusts the thermostat setpoint from the room error.
- The heating thermostats that PI adjusts. Only heat-capable devices from the zone's stages are listed (stage 3 and up included), so a cool-only device such as a shared AC is left out.
- Minimum heating command change.
- Minimum time between changes, in minutes.

The PI gains are the zone's five PI number entities. The page description lists them read-only with their current values. For a Direct zone it says "these appear when PI is chosen and saved". Choosing Direct removes the stored PI settings. See [Heating PI](../regulation/heating-pi.md).

**Cooling device N** has one section for each device in the zone's cooling stages, up to six. Further devices are listed and kept as saved. The settings are stored on the device. A device that other zones also cool with is marked "Shared with <zones>; the setting applies to both". The description also lists the zone's five Cooling PI numbers with their values.

The fields in each cooling section are: Cooling regulation, Lower equipment cooling target by, Maximum sensor correction, Also correct the unit's temperature reading (Cooling PI), Maximum total push, Unit's own temperature sensor, Minimum cooling correction change, and Minimum time between cooling correction changes. Defaults and bounds are in [Cooling regulation](../regulation/cooling.md).

## Adding a zone

Adding a zone takes three pages: **Basics & sensors** (with the zone ID, which must be unique, lowercase and without spaces), then **Heating stages**, then **Cooling stages**. Use Back and Next to move between them. Save on the last page stores the new zone. Open the zone from the list afterwards to reach the other pages.

## Zones that exist only in YAML

A zone that is in your YAML file but not in the UI configuration (added to the file after the import) shows in the list but is not controlled. Saving any of its pages copies the whole zone into the UI configuration and makes it active. From then on you manage it in the UI. See [YAML import](../yaml.md).

## Related

- [Global settings](global-settings.md)
- [Devices](devices.md)
- [Presets and modes](presets-and-modes.md)
- [Shared equipment](shared-equipment.md)
- [Saving changes](saving.md)
- [Staging](../concepts/staging.md)
- [Wall thermostats](../concepts/wall-thermostats.md)
- [Heating PI](../regulation/heating-pi.md)
- [Cooling regulation](../regulation/cooling.md)
