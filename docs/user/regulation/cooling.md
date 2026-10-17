# Cooling regulation

Cooling regulation changes the temperature your zone sends to a cooling unit so that the room, not the unit's own sensor, ends up at the target. You need this page when a mini-split or heat pump cools unevenly, short-cycles, or reads a different temperature than the room sensor.

You choose a mode for each cooling device, inside each zone that cools with it. Open **Configure → Zones → your zone → Regulation → Cooling device N**. The zone still stops cooling at its own target in every mode.

## The four modes

Set **Cooling regulation** to one of these. If you leave it unset, the mode is **Fixed cooling correction** when **Lower equipment cooling target by** is above 0, and **Use room target** otherwise. An explicit **Use room target** always wins.

| Mode | When to use it | What it sends |
|------|----------------|---------------|
| **Use room target** | The unit cools accurately and needs no help. | The zone cool target, unchanged. |
| **Fixed cooling correction** | The unit stops early or cycles before the room is cool. | The zone cool target minus **Lower equipment cooling target by**, while the zone actively calls for cooling. |
| **Correct the unit's temperature reading** | The unit's own sensor reads cooler than the room, so it quits too soon. | The zone cool target plus (unit reading minus room temperature), when the unit reads below the room. |
| **Cooling PI** | You want the unit pushed harder the longer the room stays above target. | The zone cool target minus a push calculated from the room error. |

### Correct the unit's temperature reading

A unit that reads 1°F below the room gets 71°F for a 72°F target. The correction is clamped to **Maximum sensor correction**.

It only pushes. A unit that reads at or above the room gets the zone target unchanged, because it already sees itself as warm.

The unit reading is ignored for the first 3 minutes of each cooling run, since a unit's own sensor often dips when its fan starts. When that settling period ends, the correction goes out at once without waiting for the minimum period.

### How corrections are limited

A new correction goes out only when it has moved by **Minimum cooling correction change** and **Minimum time between cooling correction changes** has passed. A first send, or a changed cool target, goes out at once.

If the unit reading is missing or not a number, the correction is 0 and one warning is logged. The limiter still applies, so a correction already sent stays in place until the change passes both limits.

## Settings

Each setting is stored on the device and applies wherever the device cools. A device that other zones also cool with is marked "Shared with <zones>; the setting applies to both". A zone page lists up to six cooling devices, one section each, and keeps any extra devices as saved.

| Setting | What it does | Default | Where |
|---------|--------------|---------|-------|
| **Cooling regulation** (`cool_regulation`) | The mode: **Use room target**, **Fixed cooling correction**, **Correct the unit's temperature reading** or **Cooling PI** | Fixed cooling correction when the lowering below is above 0, otherwise Use room target | Configure → Zones → <zone> → Regulation → Cooling device N |
| **Lower equipment cooling target by** (`cool_overdrive`) | °F (0 to 10, step 0.5) subtracted from the device's cool setpoint while the zone calls for cooling | 0 | Configure → Zones → <zone> → Regulation → Cooling device N |
| **Maximum sensor correction** (`cool_compensation_max`) | °F (0 to 10, step 0.5), the largest unit-minus-room correction. In compensation it only pushes. In Cooling PI with the unit correction it works both ways | 3 | Configure → Zones → <zone> → Regulation → Cooling device N |
| **Also correct the unit's temperature reading (Cooling PI)** (`cool_pi_compensation`) | Cooling PI only. Adds (unit reading minus room reading) to the PI target in both directions, so the push is felt on the unit's own scale | Off | Configure → Zones → <zone> → Regulation → Cooling device N |
| **Maximum total push** (`cool_max_total_push`) | °F (0 to 15, step 0.5). Cooling PI with the unit correction never lowers the target by more than this | 8 | Configure → Zones → <zone> → Regulation → Cooling device N |
| **Unit's own temperature sensor** (`cool_compensation_sensor`) | Optional `sensor.*` read as the unit's temperature. It must report °F, because its number is used as is with no unit check or conversion, so a °C sensor miscompensates and usually sits at the maximum. Blank uses the climate entity's own current temperature | Blank | Configure → Zones → <zone> → Regulation → Cooling device N |
| **Minimum cooling correction change** (`cool_regulation_threshold`) | °F (0 to 5) the correction must move before it is re-sent | 0.5 | Configure → Zones → <zone> → Regulation → Cooling device N |
| **Minimum time between cooling correction changes** (`cool_regulation_min_period`) | Minutes (0 to 60) between re-sends | 10 | Configure → Zones → <zone> → Regulation → Cooling device N |
| **Run fan after cooling** (`cool_dry_out`) | Tick box on the device page for cool-capable devices (it shows on the next open after you tick **Can Cool**). Runs fan-only after a cooling run instead of the idle action | Off | Configure → Devices → <device> |
| **Fan run time after cooling** (`cool_dry_out_minutes`) | Minutes (1 to 30) the fan runs before the normal idle action | 10 | Configure → Devices → <device> |

The **Devices** page shows the regulation mode read-only ("Cooling regulation: <mode> (set under Zones → <zones> → Regulation)") and keeps it when you save the device.

## Cooling PI

With **Cooling regulation** set to **Cooling PI**, the zone that owns the cooling request drives the device. It is a separate controller from the heating PI, with the same maths:

- **Error** is the room temperature minus the cool target. Positive means the room needs more cooling.
- **Push** is the proportional term plus the integral term plus the outdoor term, limited between 0 and the maximum push. The device is sent the cool target minus the push. Cooling PI never warms the setpoint above the cool target.
- **Gains** are the zone's five Cooling PI numbers (below). A number entity that is missing or has no valid value falls back to the zone's YAML value.
- **Limiter:** the device's **Minimum cooling correction change** and **Minimum time between cooling correction changes** decide when a changed correction is re-sent.
- **Integral** accumulates only while the zone needs cooling and one of its selected devices uses Cooling PI. It decays while idle, resets to zero on a direction reversal, and shrinks by the heating reset rule when the cool target changes a lot. It is restored after a restart.
- **At target** the device is not kept at its last setpoint the way heating PI keeps a floor; it gets its idle action or its coil dry-out.
- If no Cooling PI device is activated, or all fail or go to another zone in a cycle, the cooling values keep their previous readings. A zone without a Cooling PI device never runs it.

### The five Cooling PI numbers

Zones with cool stages get these number entities, in the Configuration category. You can change them live from the dashboard card.

| Number entity | Range |
|---------------|-------|
| Cooling PI proportional gain | 0.1 to 5.0 |
| Cooling PI integral gain | 0.001 to 0.5 |
| Cooling PI maximum push | 0 to 10°F |
| Cooling PI outdoor gain | 0 to 1, step 0.05. The default 0 turns the term off |
| Cooling PI outdoor balance point | 50 to 100°F. The default is 75 |

### The outdoor term

With the outdoor gain above 0, the push gains outdoor gain x (outdoor temperature - balance point), and the maximum push caps the total. Hotter than the balance point adds push. Colder reduces it, never below 0. It uses the same outdoor reading as heating, and with no reading it adds nothing.

For example, with gain 0.1, balance point 75°F, outdoor 90°F and a room 1°F over target, the push is 2.5°F.

### The unit correction

With **Also correct the unit's temperature reading (Cooling PI)** on, the device is sent:

cool target + max(-maximum total push, -push + clamp(unit - room, plus or minus maximum sensor correction))

The sensor part works in both directions and is 0 for the first 3 minutes of each cooling run. It lands at once when the settling ends. For example, with a target of 76, a push of 1, a unit reading of 75 and a room at 77, the device gets 73.

### Zone settings

The remaining tuning values are in the **Cooling PI: advanced** section of the zone's Regulation page (it opens collapsed) or in the zone's cooling block in YAML; they are read-only in `get_config`. Defaults are shown.

```yaml
zones:
  basement:
    cool_regulation:          # optional; omit for the defaults shown
      kp: 1.0
      ki: 0.01
      offset_max: 5           # °F, 0 to 10; the maximum push
      stabilization_threshold: 0.1
      accumulated_error_threshold: 240
      integral_decay_halflife: 120
```

## Coil dry-out

Turn on **Run fan after cooling** and a device released from cooling runs fan-only for **Fan run time after cooling** minutes. Then it gets its normal idle action: off, or the setback from the highest cool target of its enabled zones. Any new heat, cool or off command ends the dry-out early.

A unit without a fan-only mode logs one warning and gets the idle action. Fan-only counts as a compressor stop for compressor protection.

## Change the settings through the services

`get_config` exposes every setting in the table above except the unit's own sensor as a writable field per device, and the sensor is read-only there (set it in YAML or the options UI). Use `set_config` under the discovered device ID:

```json
{"devices": {"hp": {"cool_regulation": "compensation"}}}
```

`get_status.devices.<id>.desired_target_temperature` shows the temperature actually commanded after the correction and device clamping.

## Monitoring

The zone entity shows the Cooling PI state:

| Attribute | What it shows |
|-----------|---------------|
| `cool_regulation_offset` | The push as a signed offset (0 or below) on the cool target |
| `cool_accumulated_error` | The cooling integral term |
| `cool_regulated_setpoint` | The cool target minus the push, before the limiter. It is empty until Cooling PI has run |

For each device, `get_status` reports under `control`:

| Field | What it shows |
|-------|---------------|
| `cool_regulation` | The mode in effect |
| `cool_offset` | The signed °F actually added to the cool target in the last send. Read this for what is applied |
| `cool_regulation_fallback` | `true` while the unit correction has no usable unit reading. The limiter can keep the last offset applied |
| `cool_compensation_part` | The unit-minus-room °F used in the last offset, 0 when unused or settling |
| `cool_compensation_settling` | `true` during the first 3 minutes of a cooling run that uses the unit reading |

## Related

- [Heating PI regulation](heating-pi.md)
- [Devices](../configuration/devices.md)
- [Zones](../configuration/zones.md)
- [Idle and restore](../concepts/idle-and-restore.md)
- [Outdoor limits and fallback](../concepts/outdoor.md)
- [Services](../reference/services.md)
