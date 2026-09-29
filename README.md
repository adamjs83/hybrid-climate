# Hybrid Climate

A Home Assistant custom integration for whole-home HVAC orchestration. Coordinates multiple climate devices (radiant heat, heat pumps, AC) into a unified control system with intelligent staging, conflict resolution, and zone management.

## Features

- **Multi-Zone Control**: Each zone has its own climate entity with independent setpoints
- **Intelligent Staging**: Automatically escalates through heating/cooling stages based on temperature differential or time
- **Additive Staging**: Stage 2 adds devices to Stage 1 (doesn't replace)
- **Conflict Resolution**: Outdoor reset rules (global and per-zone), device mutex for shared equipment
- **PI Regulation**: Optional proportional-integral control for precise temperature management
- **Opportunistic Heating**: Zones can piggyback on active boiler cycles for efficiency
- **Sensor Aggregation**: Multiple sensors per zone with average/min/max aggregation and smoothing
- **Fallback Logic**: Uses underlying climate entity sensors if primary sensors unavailable
- **Master Modes**: Home, Away, Vacation, Boost, Off with configurable behaviors
- **Auto Home/Away**: Optional occupancy entity for automatic mode switching
- **Bidirectional Sync**: External thermostat changes propagate back to zone targets (configurable per-zone)
- **Weather Entity Support**: Can use `weather.*` entities for outdoor temperature
- **Compressor Protection**: Optional shared-compressor groups with minimum run and off intervals
- **Door/Window Lockout**: Optional zone contacts pause equipment with configurable open and close delays
- **Diagnostics**: Download a live control snapshot from the integration's Home Assistant diagnostics menu

## Installation

### HACS (recommended)

1. In HACS, open the menu (⋮) → **Custom repositories**
2. Add `https://github.com/adamjs83/hybrid-climate` with category **Integration**
3. Search for **Hybrid Climate** in HACS and download it
4. Restart Home Assistant
5. Add the integration via Settings → Devices & Services → Add Integration → Hybrid Climate

### Manual Installation

1. Copy `custom_components/hybrid_climate/` to your Home Assistant `config/custom_components/` directory
2. Optionally prepare YAML for a one-time import (see Configuration)
3. Restart Home Assistant
4. Add the integration via Settings → Devices & Services → Add Integration → Hybrid Climate
5. Configure the integration in the UI

## Configuration

Hybrid Climate stores its active configuration in the integration's UI options. You can configure it entirely in the UI, or import an existing YAML configuration once and then manage it in the UI.

### UI Configuration (v0.7.0+)

After adding the integration, click **Configure** to access the options menu. The UI is the source of truth after setup, including after a YAML import.

#### Main Menu

The configuration menu shows:
- Current master entity name
- Number of zones and devices configured

Available sections:

| Section | Purpose |
|---------|---------|
| **Global Settings** | Master entity name, sensors, outdoor reset limits |
| **Zones** | Create/edit/delete zones with multi-step wizard |
| **Heat Source Groups** | Group devices sharing a heat source for opportunistic heating |
| **Preset Modes** | Configure behavior for each master mode |
| **Device Conflicts** | Set up mutex rules for shared equipment |
| **Device Behaviors** | Configure per-device idle behavior |

#### Global Settings

Configure integration-wide settings:

| Setting | Description |
|---------|-------------|
| Master name | Display name for the master climate entity |
| Outdoor sensors | Ordered list of `sensor.*` and/or `weather.*` entities for outdoor temperature. Each cycle uses the first entity in the list with a valid reading; later entries are backups, read in priority order |
| Occupancy entity | `binary_sensor.*` for automatic home/away switching |
| Never heat above | Disable heating when outdoor temp exceeds this value |
| Lockout heat floor | Maximum idle heat setpoint (default 55°F, 40–60°F) while the "never heat above" lockout is active; a device's setback is never raised above this floor while heating is locked out |
| Never cool below | Disable cooling when outdoor temp is below this value |

#### Zone Configuration (6-Step Wizard)

Creating or editing a zone walks through these steps:

**Step 1: Basic Settings**
- Zone ID (unique identifier, lowercase, no spaces)
- Display name
- Temperature sensors (or leave empty to use device's built-in sensor)
- Sensor aggregation method (average/min/max/median/weighted). Choosing weighted adds a follow-up step to set each selected sensor's weight (0.1–10.0)
- Smoothing samples (moving average window)

**Step 2: Occupancy**
- Enable/disable occupancy-based setpoint adjustments
- Select occupancy sensor (binary_sensor)
- Set temperature offsets for occupied/unoccupied states

**Step 3: Heat Stages**
- Enable/disable heating for this zone
- Stage 1: Primary heating devices and activation threshold
- Stage 2: Backup heating devices, threshold, time escalation, outdoor temp minimum

**Step 4: Cool Stages**
- Enable/disable cooling for this zone
- Stage 1: Primary cooling devices and threshold
- Stage 2: Backup cooling devices, threshold, time escalation

**Step 5: Zone Settings**
- Hysteresis (deadband to prevent short-cycling)
- Minimum runtime (seconds)
- Door/window binary sensors and their open/close delays (optional)
- Opportunistic heating enable/threshold (piggyback on boiler cycles)
- Zone-specific outdoor reset override (disable/override global limits)
- Regulation type: Direct or PI Control

**Step 6: PI Control** (if PI selected)
- Select devices to regulate (only heat-capable devices from this zone's stages are offered — PI regulation only ever applies to heating, so a cool-only device such as a shared AC is excluded)
- Kp (proportional gain)
- Ki (integral gain)
- K_ext (outdoor temperature factor)
- Maximum offset
- Balance point (outdoor temp where no offset needed)

#### Heat Source Groups

Group devices that share a physical heat source (e.g., boiler, heat pump):

- **Group ID**: Unique identifier
- **Display name**: Human-readable name
- **Devices**: Climate entities in this group

When one zone in a group is heating, other zones can activate "opportunistically" to piggyback on the shared heat source cycle.

#### Preset Modes

Configure behavior for each master mode (Home, Away, Sleep, Vacation, Boost, Off):

| Setting | Description |
|---------|-------------|
| Use zone setpoint | Which named setpoint to use (default/away/sleep/vacation) |
| Setpoint offset | Additional temperature offset to apply |
| Skip time escalation | Activate all stages immediately (for Boost) |
| Disable all | Turn off all zones (for Off mode) |

#### Device Conflicts (Mutex Rules)

Create rules to prevent conflicting HVAC operations:

- **Device**: The climate device this rule applies to
- **Mode**: Heating or cooling
- **In zone**: The zone that triggers the block
- **Block heating in**: Zones that cannot heat while rule is active
- **Block cooling in**: Zones that cannot cool while rule is active

Example: When the shared heat pump is cooling the basement, block heating in the main floor.

#### Device Behaviors

Configure what each device does when its zone is satisfied (idle):

| Setting | Description |
|---------|-------------|
| Turn Off | Device turns off completely when idle |
| Setback | Device maintains a setback temperature (target ± offset) |
| Setback amount | Degrees below (heat) or above (cool) target |
| Compressor group | Shared outdoor compressor identifier; use the same value on all members |
| Minimum compressor runtime/off time | Seconds to hold the shared group on or off |

Compressor protection is optional. For a shared group, the longest configured interval among its members applies. It uses each climate entity's reported HVAC mode as a proxy for compressor activity; a thermostat that cycles its compressor while remaining in `heat` or `cool` cannot be timed precisely. On startup, the previous transition is unknown, so the first observed state begins a full interval. Explicit shutdowns, including door/window lockouts, bypass the minimum runtime.

An opening contact uses `on` for open and `off` for closed. An already-open contact at startup, or a missing or unavailable contact, locks the zone immediately. After a later open event, the configured open delay applies; all contacts must stay closed for the close delay before control resumes. A lockout sends equipment to `off` even if its normal idle action is setback.

### UI and YAML Configuration

- UI settings are stored in the config entry options and used on subsequent starts.
- If the entry has no UI configuration, existing YAML is imported into those options once.
- After import, edit zones and devices in the UI. Editing the YAML file does not update the active configuration; it is not merged on later starts.
- Device entries are auto-created for climate entities used in UI zones.

### Dynamic dashboard card

The `custom:hybrid-climate-card` uses the zones and devices in the active integration configuration. Add or remove zones through **Settings → Devices & Services → Hybrid Climate → Configure**; the card picks up the resulting configuration without editing each dashboard view. The card provides five views: Climate Overview, Zone Details, Setpoints, PI Controller, and All Devices. A paste-ready example is in [`dashboard_dynamic_example.yaml`](dashboard_dynamic_example.yaml).

After installing or updating Hybrid Climate, restart Home Assistant so it registers the card asset route. In **Settings → Dashboards → Resources**, add `/hybrid_climate/hybrid-climate-card.js` as a JavaScript module. Then create a YAML dashboard using the example file, or add a card to an existing dashboard:

For the zone cards to appear side by side, put the custom card in a **Panel** view. A Panel view contains one card and gives it the full dashboard width; the card then arranges zones in a responsive grid. In a Masonry view, Home Assistant restricts each card to one dashboard column, so the zones will stack. The paste-ready example sets `type: panel` on all five views. In a Sections view, the card requests full section width.

```yaml
type: custom:hybrid-climate-card
view: overview
rows:
  - status
  - thermostat
  - targets
  - lockout_reason
zone_order:
  - living_room
  - upstairs
```

`zone_order` contains zone IDs from **Configure → Zones**. Listed zones appear first in that order; any newly configured zones append automatically. `rows` is an ordered list of sections to show in each zone: `status`, `thermostat`, `targets`, `lockout_reason`, `sensors`, `openings`, `equipment`, `setpoints`, or `pi`. Optional `zone_rows` overrides that list for a specific zone; `hidden_zones` hides selected IDs. Omit `zone_order` to follow integration order and omit `rows` for the view's defaults. The card's graphical editor can also reorder zones and sections. The example shows a separate card for each of the five views.

Temperature and mode changes on the card are live controls. Its setpoint and PI controls use the integration's `number.*` entities and take effect without a reload. To add or remove zones, devices, stages, sensors, opening contacts, and other structural settings, use the integration's **Configure** flow. The card does not edit those settings.

### Live-Tunable Number Entities

The integration automatically creates `number.*` entities for each zone, allowing real-time adjustment of setpoints and PI parameters without reloading.

**Automatically created entities:**

For each zone with heating:
- `number.hybrid_climate_{zone}_default_heat_temp` - Default heating setpoint
- `number.hybrid_climate_{zone}_away_heat_temp` - Away mode heating
- `number.hybrid_climate_{zone}_sleep_heat_temp` - Sleep mode heating
- `number.hybrid_climate_{zone}_vacation_heat_temp` - Vacation mode heating

For each zone with cooling:
- `number.hybrid_climate_{zone}_default_cool_temp` - Default cooling setpoint
- `number.hybrid_climate_{zone}_away_cool_temp` - Away mode cooling
- `number.hybrid_climate_{zone}_sleep_cool_temp` - Sleep mode cooling
- `number.hybrid_climate_{zone}_vacation_cool_temp` - Vacation mode cooling

For zones with PI regulation:
- `number.hybrid_climate_{zone}_pi_kp` - Proportional gain (0.1-5.0)
- `number.hybrid_climate_{zone}_pi_ki` - Integral gain (0.001-0.5)
- `number.hybrid_climate_{zone}_pi_k_ext` - Outdoor factor (0.0-1.0)
- `number.hybrid_climate_{zone}_pi_offset_max` - Max offset (1-20°F)
- `number.hybrid_climate_{zone}_pi_balance_point` - Balance point (30-80°F)

**Usage:**
- Entities appear automatically in Home Assistant
- Adjust via UI, automations, or scripts
- Changes take effect immediately (no restart needed)
- Values are read each coordinator update cycle
- Entities are grouped under the zone's device

**Example:** Adjust basement heating setpoint to 70°F:
```yaml
service: number.set_value
target:
  entity_id: number.hybrid_climate_basement_default_heat_temp
data:
  value: 70
```

### YAML Configuration

To import an existing YAML configuration on first setup, add to your `configuration.yaml`:

```yaml
hybrid_climate: !include hybrid_climate_config.yaml
```

Create `hybrid_climate_config.yaml`. After the first import, make further changes through **Settings → Devices & Services → Hybrid Climate → Configure**:

```yaml
outdoor_sensors:  # sensor.* and/or weather.* entities, in priority order
  - sensor.outdoor_temperature
  - weather.home  # backup, used only while the primary is missing/unavailable/invalid

lockout_heat_floor: 55  # Optional: max idle heat setpoint during outdoor heat lockout (40-60, default 55)

master:
  name: "Home HVAC"
  occupancy_entity: binary_sensor.home_occupied  # Optional: auto home/away
  modes:
    home:
      use_zone_defaults: true
    away:
      use_zone_away_setpoints: true
      setpoint_offset: -3  # Additional offset in away mode
    boost:
      skip_time_escalation: true  # Activate all stages immediately
    off:
      disable_all: true

conflicts:
  outdoor_reset:
    never_heat_above: 75  # Don't heat when outdoor > 75°F
    never_cool_below: 55  # Don't cool when outdoor < 55°F
  device_mutex:
    - when:
        device: shared_heat_pump
        mode: cool
        for_zone: basement
      then:
        block_heat: [main_floor]  # Can't heat main floor while basement cools

devices:
  # Device definition - no allow_command here (moved to zone stage config)
  basement_hp:
    entity_id: climate.basement_heat_pump
    capabilities: [heat, cool]
    compressor_group: basement_outdoor  # shared by indoor units on this compressor
    min_compressor_runtime: 300          # seconds
    min_compressor_off_time: 180         # seconds
    idle:
      action: setback  # or "off"
      setback: 5

  living_room_nest:
    entity_id: climate.nest_thermostat
    capabilities: [heat]
    idle:
      action: setback
      setback: 5

zones:
  basement:
    name: "Basement"
    sensors:
      indoor:
        - sensor.basement_temperature
      aggregation: average  # average | min | max | median | weighted
      # weights:  # Optional; only used by "weighted"; missing entries default to 1.0
      #   sensor.basement_temperature: 1.0
      smoothing_samples: 3
    setpoints:
      default: 68
      away: 62
      occupancy_entity: binary_sensor.basement_occupied
      occupied: 70
      unoccupied: 65
    heat_stages:
      - stage: 1
        devices: [basement_hp]  # Simple format: no allow_command
        threshold: 1.0
      - stage: 2
        devices: [basement_hp, backup_heat]
        threshold: 3.0
        time_escalation: 1800  # Escalate after 30 min
    cool_stages:
      - stage: 1
        devices: [basement_hp]
        threshold: 1.0
    settings:
      hysteresis: 0.5
      min_runtime: 300
      # Optional: Override global outdoor reset for this zone
      outdoor_reset:
        never_cool_below: null  # null = disable restriction (allow cooling in winter)
        # never_heat_above: 80  # Or set zone-specific limit
    # Optional: pause this zone while a door or window is open
    openings:
      entities: [binary_sensor.basement_window]
      open_delay: 60   # seconds
      close_delay: 60  # seconds
    # Optional: Opportunistic heating (piggyback on boiler cycles)
    opportunistic:
      enabled: true
      threshold: 0.5  # Activate when 0.5°F below setpoint

  living_room:
    name: "Living Room"
    sensors:
      indoor: []  # Empty = fall back to device's current_temperature
      aggregation: average
    setpoints:
      default: 70
      away: 65
    heat_stages:
      - stage: 1
        devices:
          # Extended format: allow_command enables bidirectional sync
          - device: living_room_nest
            allow_command: true  # External changes sync to zone overlay
        threshold: 1.0
    cool_stages:
      - stage: 1
        devices: [whole_house_ac]  # Shared device, no allow_command
        threshold: 1.0
```

## Overlay/Underlay Architecture

Hybrid Climate uses a two-layer architecture:

- **Overlay**: The hybrid climate zone entity (e.g., `climate.living_room`)
- **Underlay**: The actual physical device (e.g., `climate.nest_thermostat`)

### Bidirectional Sync with `allow_command`

When `allow_command: true` is set for a device in a zone's stage config:

1. **Overlay controls underlay**: Changing the zone target updates the thermostat
2. **Underlay syncs to overlay**: Changing the physical thermostat updates the zone target

This is useful for single-zone thermostats where users may adjust the physical device directly.

### State Machine

For `allow_command` devices, a state machine manages synchronization:

| State | Description |
|-------|-------------|
| **LISTENING** | Device matches desired state. Any external change syncs to overlay. |
| **COMMANDING** | We sent a command, waiting for device to respond. Ignores mismatches for 10s. |

**Transitions:**
- Overlay change → COMMANDING (command sent to device)
- Device matches command → LISTENING (acknowledged)
- Device differs by >3°F after 10s → external override detected → sync to overlay
- Timeout (60s) → sync overlay to device's current value

### Idle Setback

When a zone is idle (room temp at or above target), devices can be configured to:

- `action: off` - Turn off completely
- `action: setback` - Set to target minus setback degrees (maintains minimum temp)

For example, with `setback: 5` and zone target 70°F:
- Zone idle → device set to 65°F (prevents pipes from freezing, etc.)
- Zone needs heat → device set to 70°F (or regulated setpoint)

### Startup Takeover

Ownership of a device is not persisted across a Home Assistant restart or an integration reload (including saving a configuration change). Historically, a device left in `heat` or `cool` by no zone at the moment of restart stayed in that mode indefinitely — the integration never took it back until a zone happened to need it.

Once, after each startup or reload, every such device (any device referenced by a zone's heat or cool stages) is handed its configured idle action exactly one time:
- A device already owned by a zone, or already addressed by normal control this cycle, is left alone.
- A device that is off, or in a mode other than heat/cool, is left alone — the takeover **never turns equipment on**.
- If every zone that references the device is currently disabled (master off, zone off, "disable all" preset, or an opening lockout), the device is forced off.
- Otherwise the device receives its normal idle action (off or setback) using the most conservative target among the zones that reference it — the lowest heat target or highest cool target, so a shared device never gets a warmer-than-intended setback.
- Devices under PI regulation are excluded; they're already refreshed every idle cycle by the existing PI/equilibrium logic.

After that one command succeeds, the takeover never touches the device again until the next restart or reload — any manual change you make afterward sticks. A device that can't be commanded yet (unavailable, blocked by compressor protection, waiting on a device mutex, or a zone whose sensors haven't reported) is retried on the following cycles.

### Sensor Aggregation

Each zone combines its configured indoor sensors with one of five methods:

| Method | Behavior |
|---|---|
| `average` (default) | Arithmetic mean of all present readings |
| `min` | Coldest reading (conservative for heating) |
| `max` | Warmest reading (conservative for cooling) |
| `median` | Middle value; ignores a single outlier without needing per-sensor weights |
| `weighted` | Weighted average using each sensor's configured weight (default 1.0) |

`weighted` is useful when one sensor reads consistently high or low relative to the others (for example, a sensor placed near a heat source) — give it a lower weight instead of excluding it. Configure weights per sensor in the zone wizard (Step 1); weights outside 0.1–10.0 are rejected. A weighted zone with no stored weights behaves exactly like `average`. A stale/unavailable sensor simply drops out of whichever method is configured.

### Outdoor Sensor Fallback

The outdoor temperature source is an ordered list (Global Settings → Outdoor sensors). Each cycle, every configured entity is read in order and the **first valid reading wins**; later entities are still checked so status reporting can show them, but only the winning value drives outdoor reset logic. If every entity is invalid or unavailable, the last verified reading is retained for up to 10 minutes. After that retention window expires with still no valid reading, each zone simply keeps whatever heat/cool permission it last latched — an outage does **not** reset an already-running zone to blocked. The one case that defaults to blocked is at startup, before any zone has ever received a single valid outdoor reading with a limit configured; this is exactly the case the ordered fallback list exists to cover, by giving a backup source a chance to supply a valid reading at boot if the primary is down. A single-entity configuration behaves exactly as before. Switching to a fallback logs a warning; recovering to the primary logs an info message — neither logs every cycle.

### Idle Heat Floor During Outdoor Lockout

The **Lockout heat floor** (Global Settings, default 55°F, 40–60°F) caps how high (how close to target) an idle heating setpoint is allowed to sit while the outdoor heat lockout ("never heat above") is currently blocking heat for a zone — heating is locked out, so the idle setpoint should not sit warm enough that the device's own thermostat could call for heat on its own. Normally an idle device sets back to `target − setback`; while the lockout is active for every zone that would otherwise set the target, the device is instead sent to `min(lockout_heat_floor, target − setback)`. This can only pull the setpoint *down* to a deeper setback than configured — it never raises the setpoint above the normal setback. This applies to both the regular idle release path and the startup takeover above.

The lockout starting or ending never sends a command by itself; the floor is only evaluated the next time a device is actually idled. A device idled with the floor applied stays there until its next release, even after the lockout clears. This does not change PI-regulated devices, which continue to hold their existing equilibrium setpoint while idle.

### Zone-Specific Outdoor Reset Override

By default, global outdoor reset rules (`never_heat_above`, `never_cool_below`) apply to all zones. However, some zones may need to override these:

**Use case:** A basement with boiler equipment that gets hot and needs cooling even in winter when outdoor temp is below the global `never_cool_below` threshold.

**Configuration:**
```yaml
zones:
  basement:
    settings:
      outdoor_reset:
        never_cool_below: null  # Disable cooling restriction for this zone
        # never_heat_above: 80  # Or set zone-specific limit
```

**Behavior:**
| Setting | Meaning |
|---------|---------|
| Not set (no `outdoor_reset` key) | Use global outdoor reset limits |
| `null` | Disable this restriction entirely for this zone |
| Numeric value | Use this zone-specific limit instead of global |

**UI Configuration:** In the zone wizard (Step 5: Settings), check "Override global outdoor reset limits" and then either:
- Check "Disable cooling temperature limit" to allow cooling regardless of outdoor temp
- Enter a zone-specific "Never cool below" value
- Same options available for heating limits

### Opportunistic Heating

Zones can piggyback on active boiler cycles from other zones in the same heat source group. This improves efficiency by using waste heat.

**Configuration:**
```yaml
zones:
  living_room:
    opportunistic:
      enabled: true
      threshold: 0.5  # Activate when 0.5°F below setpoint
```

When opportunistic heating activates:
1. Another zone in the same heat source group must be actively heating
2. This zone's temperature must be below setpoint by at least `threshold`
3. Only Stage 1 devices activate (opportunistic doesn't trigger Stage 2)

**UI Configuration:** In the zone wizard (Step 5: Settings), toggle "Enable opportunistic heating" and set the threshold.

## Complete Control Flow

This section explains how all the pieces work together during each update cycle (every 10 seconds).

### Update Cycle Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     UPDATE CYCLE (10s)                       │
├─────────────────────────────────────────────────────────────┤
│ 1. Update device states from HA                             │
│ 2. Check external device changes (allow_command sync)       │
│ 3. Check master occupancy (auto home/away)                  │
│ 4. Get outdoor temperature                                  │
│ 5. For each zone:                                           │
│    a. Get aggregated indoor temperature                     │
│    b. Get zone target (from overlay)                        │
│    c. Check conflicts (outdoor reset, device mutex)         │
│    d. Determine needed mode (hysteresis check)              │
│    e. Calculate PI offset (if regulated)                    │
│    f. Select stage (threshold/time escalation)              │
│    g. Activate devices with appropriate setpoints           │
│ 6. Apply opportunistic heating                              │
│ 7. Update master summaries                                  │
└─────────────────────────────────────────────────────────────┘
```

### Detailed Example: Heating with PI Regulation

**Scenario:** Main floor zone with radiant floors (PI-regulated) and heat pump backup.

**Configuration:**
```yaml
zones:
  main_floor:
    sensors:
      indoor: [sensor.living_room_temp, sensor.kitchen_temp]
      aggregation: average
      smoothing_samples: 3
    setpoints:
      default: 70
    heat_stages:
      - stage: 1
        devices: [floor_heat_1, floor_heat_2]
        threshold: 0.5
      - stage: 2
        devices: [heat_pump]
        threshold: 2.0
        time_escalation: 1800
    settings:
      hysteresis: 0.5
    regulation:
      type: pi
      devices: [floor_heat_1, floor_heat_2]
      kp: 1.0
      ki: 0.01
      k_ext: 0.15
```

**State:** Room at 68.5°F, target 70°F, outdoor 35°F, stage 1 running for 20 minutes.

**Update cycle walkthrough:**

1. **Get temperatures**
   - Living room: 68.3°F, kitchen: 68.7°F
   - Smoothed average: 68.5°F

2. **Calculate error**
   - Error = 70 - 68.5 = +1.5°F (needs heat)

3. **Hysteresis check**
   - Currently heating, error > 0 → continue heating

4. **Conflict check**
   - Outdoor 35°F, no outdoor reset triggered
   - No device mutex conflicts

5. **PI calculation**
   - P_term = 1.0 × 1.5 = +1.5°F
   - I_term = 0.01 × 90 (accumulated) = +0.9°F
   - External = 0.15 × (65 - 35) = +4.5°F
   - **Offset = +6.9°F, regulated_setpoint = 76.9°F**

6. **Stage selection**
   - Error 1.5°F ≥ stage 1 threshold (0.5°F) ✓
   - Error 1.5°F < stage 2 threshold (2.0°F) ✗
   - Time in stage: 20min < 30min (time_escalation) ✗
   - **Stage 1 selected**

7. **Device activation**
   - floor_heat_1: set to 77°F (regulated setpoint)
   - floor_heat_2: set to 77°F (regulated setpoint)

### How PI and Staging Interact

```
           Zone Target: 70°F
                 │
                 ▼
    ┌────────────────────────┐
    │     PI Controller      │
    │  (for radiant floors)  │
    └────────────────────────┘
                 │
                 ▼
         Regulated Setpoint: 77°F
                 │
                 ├─────────────────────────────┐
                 ▼                             ▼
    ┌────────────────────────┐    ┌────────────────────────┐
    │    floor_heat_1        │    │    floor_heat_2        │
    │    (PI-regulated)      │    │    (PI-regulated)      │
    │    setpoint: 77°F      │    │    setpoint: 77°F      │
    └────────────────────────┘    └────────────────────────┘

                 Zone Target: 70°F (not regulated)
                 │
                 ▼
    ┌────────────────────────┐
    │      heat_pump         │
    │    (NOT regulated)     │
    │    setpoint: 70°F      │
    └────────────────────────┘
```

**Key insight:** PI regulation only applies to configured `regulation.devices`. Other devices in the same zone get the raw zone target.

### When Things Go Idle

When the room reaches target (error ≤ 0):

1. **Hysteresis check** → Stop heating (error ≤ 0)

2. **PI-regulated devices** (floor_heat_1, floor_heat_2):
   - Hold at current regulated_setpoint (e.g., 77°F)
   - This maintains the equilibrium the PI found
   - Integral value is preserved (doesn't reset)

3. **Non-regulated devices** (heat_pump):
   - Apply idle behavior from device config
   - `action: setback` → set to target - setback (e.g., 65°F)
   - `action: off` → turn off completely

4. **Next cycle:**
   - If room drops below target - hysteresis (69.5°F), heating restarts
   - PI picks up where it left off (integral preserved)

### External Change Flow (allow_command)

When a user adjusts a physical thermostat:

```
User changes Nest from 70°F to 72°F
         │
         ▼
┌─────────────────────────────────────┐
│  Device State Machine Check (10s)   │
├─────────────────────────────────────┤
│ Device in LISTENING state?          │
│ Current temp (72) ≠ desired (70)?   │
│ → External change detected!         │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│     Sync Overlay to Underlay        │
├─────────────────────────────────────┤
│ zone_target = 72°F                  │
│ device.desired_temp = 72°F          │
│ State remains LISTENING             │
└─────────────────────────────────────┘
```

When the overlay changes (user adjusts in HA):

```
User changes zone from 70°F to 68°F in HA
         │
         ▼
┌─────────────────────────────────────┐
│   set_zone_target_temp(68)          │
├─────────────────────────────────────┤
│ Update zone_target_temps[zone] = 68 │
│ Immediate device update triggered   │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│   Device Manager Command            │
├─────────────────────────────────────┤
│ device.start_command(68, 'heat')    │
│ State → COMMANDING                  │
│ Service call: climate.set_temp(68)  │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│   Wait for Acknowledgment           │
├─────────────────────────────────────┤
│ Device reports 68°F → LISTENING     │
│ OR timeout (60s) → sync overlay     │
│ OR >3°F diff after 10s → override   │
└─────────────────────────────────────┘
```

## Architecture

```
Master Entity (modes: home/away/vacation/boost/off)
└── Zone Entities (each has independent setpoint, staging logic)
    └── Device Manager (controls underlying climate.* entities)
        └── Conflict Resolver (outdoor reset, device mutex)
```

### State Machine Flow

```
User changes overlay (zone target)
    │
    ▼
Coordinator.set_zone_target_temp()
    │
    ├─► Update zone_target_temps
    │
    └─► _immediate_device_update()
            │
            ├─► Active device? → set_device_mode(target)
            │
            └─► Idle device? → set_device_idle(setback)
                    │
                    └─► Device.start_command() → COMMANDING state

Update cycle runs (every 10s)
    │
    ▼
_check_external_device_changes()
    │
    ├─► Device in LISTENING?
    │       │
    │       └─► Underlay changed? → Sync overlay, stay LISTENING
    │
    └─► Device in COMMANDING?
            │
            ├─► Underlay matches desired? → LISTENING (ack)
            │
            ├─► >3°F diff after 10s? → External override, sync overlay
            │
            └─► Timeout (60s)? → Sync overlay to current
```

### Component Files

| File | Purpose |
|------|---------|
| `coordinator.py` | Central orchestration, sensor polling, state management, external change detection |
| `device_manager.py` | Device pool, state tracking, command dispatch |
| `conflict_resolver.py` | Outdoor reset, device mutex rules |
| `zone.py` | ZoneClimateEntity - per-zone climate control |
| `master.py` | MasterClimateEntity - whole-home modes |
| `models.py` | Dataclasses for configuration and state, DeviceCommandState enum |
| `config_loader.py` | YAML parsing and validation |

## Entities Created

- **Master Entity** (`climate.home_hvac` or configured name): Whole-home control with preset modes
- **Zone Entities** (`climate.<zone_id>`): Per-zone climate control

### Master Entity Attributes

- `version`: Integration version
- `outdoor_temperature`: Current outdoor temp
- `zone_count`: Number of configured zones
- `zones_heating`: List of zones currently heating
- `zones_cooling`: List of zones currently cooling
- `zones_idle`: List of idle zones
- `active_conflicts`: List of active conflict descriptions

### Zone Entity Attributes

- `master_mode`: Current master mode
- `current_stage`: Active heating/cooling stage (e.g., "heating_stage_1")
- `active_devices`: Devices currently running
- `blocked_devices`: Devices blocked by conflicts
- `time_in_stage`: Seconds in current stage
- `sensor_values`: Raw sensor readings
- `sensor_smoothed_values`: Smoothed sensor readings
- `regulation_offset`: PI controller offset (if enabled)
- `accumulated_error`: PI integral term
- `regulated_setpoint`: Actual setpoint sent to regulated devices

## Staging, Thresholds, and Hysteresis

Understanding how hybrid climate decides when to heat/cool and which devices to use.

### Hysteresis (Start/Stop Deadband)

Hysteresis prevents rapid on/off cycling by creating a "deadband" around the target:

```
        Stop cooling
              ↓
    ┌─────────●─────────┐ target + hysteresis (70.5°F)
    │                   │
    │    DEADBAND       │ ← No action taken in this zone
    │                   │
    ├─────────●─────────┤ target (70°F)
    │                   │
    │    DEADBAND       │
    │                   │
    └─────────●─────────┘ target - hysteresis (69.5°F)
              ↑
        Start heating
```

**Rules:**
- **Start heating**: When temp drops below `target - hysteresis`
- **Stop heating**: When temp reaches `target` (not `target + hysteresis`)
- **Start cooling**: When temp rises above `target + hysteresis`
- **Stop cooling**: When temp reaches `target`

**Example** (target=70°F, hysteresis=0.5°F):
1. Room at 72°F → idle (above target, but not calling for cool)
2. Room drops to 69.4°F → start heating (below 69.5°F threshold)
3. Room reaches 70°F → stop heating, go idle
4. Room rises to 70.6°F → start cooling (above 70.5°F threshold)
5. Room reaches 70°F → stop cooling, go idle

### Stage Thresholds

Within each mode (heating/cooling), **threshold** determines which stage activates based on how far the room is from target:

```yaml
heat_stages:
  - stage: 1
    devices: [radiant_floor]
    threshold: 1.0        # Activate when error ≥ 1.0°F
  - stage: 2
    devices: [heat_pump]
    threshold: 3.0        # Add heat pump when error ≥ 3.0°F
    time_escalation: 1800 # OR after 30 min in stage 1
```

**Threshold vs Hysteresis:**
- **Hysteresis**: Decides whether to heat/cool at all (mode selection)
- **Threshold**: Decides which stage to use (stage selection)

**Example** (target=70°F, hysteresis=0.5°F, stage 1 threshold=1.0°F, stage 2 threshold=3.0°F):

| Room Temp | Error | Hysteresis Check | Stage Selected |
|-----------|-------|------------------|----------------|
| 70.5°F | -0.5°F | Within deadband | Idle |
| 69.4°F | +0.6°F | Below hysteresis | Stage 1 (error ≥ 0.5, < 1.0) |
| 68.5°F | +1.5°F | Needs heat | Stage 1 (error ≥ 1.0, < 3.0) |
| 66.0°F | +4.0°F | Needs heat | Stage 2 (error ≥ 3.0) |

### Time Escalation

Even if threshold isn't met, stages can escalate after a time delay:

```yaml
heat_stages:
  - stage: 1
    devices: [radiant_floor]
    threshold: 1.0
  - stage: 2
    devices: [heat_pump]
    threshold: 3.0
    time_escalation: 1800  # 30 minutes
```

If stage 1 runs for 30 minutes without reaching setpoint, stage 2 activates even though the error might only be 2°F.

**Boost mode** skips time escalation entirely - all stages that meet threshold activate immediately.

### Additive Staging

Stages are **additive** - when stage 2 activates, stage 1 devices stay on:

```
Stage 1: [radiant_floor]
Stage 2: [radiant_floor, heat_pump]  ← radiant stays on
```

This differs from systems where stage 2 replaces stage 1.

### Stage Conditions

Stages can have additional conditions:

```yaml
heat_stages:
  - stage: 2
    devices: [heat_pump]
    threshold: 3.0
    conditions:
      outdoor_temp_min: 35  # Don't use HP below 35°F
```

If conditions aren't met, the stage is skipped even if threshold/time criteria are met.

### Decision Flow Summary

```
1. Get room temperature and target
2. Calculate error = target - current
3. HYSTERESIS CHECK:
   - Currently heating? Stop if error ≤ 0
   - Currently cooling? Stop if error ≥ 0
   - Currently idle?
     - Start heating if error > hysteresis
     - Start cooling if error < -hysteresis
4. STAGE SELECTION (if heating/cooling):
   - For each stage in order:
     - Check conditions (outdoor temp, etc.)
     - Check threshold OR time escalation
     - Highest qualifying stage wins
5. DEVICE ACTIVATION:
   - Activate all devices from stage 1 up to target stage
   - Skip blocked devices (conflicts)
```

## PI Regulation

Optional proportional-integral control for radiant floor or other slow-response systems.

### Why PI Control?

Radiant floor heating has significant thermal lag - it can take 30-60 minutes to respond to setpoint changes. Traditional on/off control causes:
- Overshooting: Floor keeps heating after room reaches target
- Undershooting: Room cools significantly before floor catches up
- Oscillations: Temperature swings above and below setpoint

PI control solves this by dynamically adjusting the floor setpoint based on how far the room is from target and how long it's been off target.

PI regulation only ever applies to heating, so only heat-capable devices can be regulated. The wizard's device list already excludes cool-only devices (for example a shared AC); if a zone's stored configuration still lists one — from an older version, or a hand-edited YAML file — it is dropped at load with a warning logged, and reported under `get_config`'s `regulation.ignored_devices` so it stays visible. This fixes a repeating background "turn the AC off" command that could override a manually-started cool-only device sharing a PI zone's stages.

### Configuration

```yaml
zones:
  main_floor:
    regulation:
      type: pi
      devices: [floor_heat_1, floor_heat_2]
      kp: 1.0                  # Proportional gain
      ki: 0.01                 # Integral gain  
      k_ext: 0.15              # Outdoor temp influence (feedforward)
      balance_point: 65        # Outdoor temp where no offset needed
      offset_max: 10           # Max ±10° adjustment
      stabilization_threshold: 0.5  # Error deadband for integral
      accumulated_error_threshold: 240  # Anti-windup cap
      # Integral state management (optional, these are defaults)
      integral_reset_threshold: 2.5   # °F change triggers partial reset
      integral_reset_factor: 0.3      # Keep 30% of integral on reset
      integral_decay_halflife: 120    # 2hr half-life when idle (0 = disabled)
```

### How It Works

The PI controller calculates an **offset** that's added to the zone target:

```
regulated_setpoint = zone_target + offset
offset = P_term + I_term + external_term

Where:
  P_term = kp × error           (proportional response)
  I_term = ki × accumulated_error   (integral response)
  external_term = k_ext × (balance_point - outdoor_temp)
```

**Example:** Zone target 70°F, room currently at 68°F (error = +2°F)
- P_term: 1.0 × 2 = +2°F (immediate response to error)
- I_term: 0.01 × 60 = +0.6°F (accumulated over ~30 error-minutes)
- External: 0.15 × (65 - 30) = +5.25°F (cold outside, push harder)
- **Regulated setpoint: 70 + 2 + 0.6 + 5.25 = 77.85°F**

The floor thermostat gets 78°F, which makes it heat harder to overcome the cold conditions.

### PI Terms Explained

| Term | Purpose | Effect |
|------|---------|--------|
| **P (Proportional)** | Immediate response | Large error → large correction. Fast but can't eliminate steady-state error. |
| **I (Integral)** | Eliminate steady-state error | Accumulates over time. If room stays 0.5°F cold, integral slowly builds until corrected. |
| **External (k_ext)** | Feedforward compensation | Anticipates heating load based on outdoor temp. Cold outside → higher floor temp. |

### Tuning Parameters

| Parameter | Description | Start Value | Adjust If |
|-----------|-------------|-------------|-----------|
| `kp` | Proportional gain | 1.0 | Room slow to respond: increase. Oscillating: decrease. |
| `ki` | Integral gain | 0.01 | Steady-state error persists: increase. Overshoots after long runs: decrease. |
| `k_ext` | Outdoor influence | 0.15 | House loses heat fast in cold: increase. Well-insulated: decrease. |
| `balance_point` | Outdoor temp for zero offset | 65 | Adjust to your climate |
| `offset_max` | Maximum offset (±) | 10 | Floor can handle more: increase. Comfort issues: decrease. |
| `stabilization_threshold` | Error deadband | 0.5 | Room oscillates ±0.3°F: increase. Never quite reaches target: decrease. |
| `accumulated_error_threshold` | Anti-windup cap | 240 | Prevents runaway integral during long recovery periods. |
| `integral_reset_threshold` | Setpoint change trigger | 2.5 | °F change that triggers partial integral reset. |
| `integral_reset_factor` | Reset retention | 0.3 | Fraction of integral to keep on reset (0.3 = keep 30%). |
| `integral_decay_halflife` | Idle decay rate | 120 | Minutes for integral to decay to 50% when idle. 0 = no decay. |

### Anti-Windup and Integral Management

The integral term is protected from "windup" (growing unboundedly) and stale state:

**Anti-Windup (prevents runaway accumulation):**
1. **Output saturation**: Stops accumulating when offset hits `offset_max`
2. **Deadband**: Stops accumulating when error < `stabilization_threshold`
3. **Hard cap**: `accumulated_error_threshold` limits maximum integral

**Integral State Management (adapts to changing conditions):**
4. **Setpoint change reset**: Big setpoint jumps (> `integral_reset_threshold`) scale down the integral by `integral_reset_factor`. This prevents dragging stale PI state into a new operating regime.
5. **Idle decay**: When at setpoint (idle), the integral decays exponentially with the configured half-life. This gradually "forgets" old assumptions during extended idle periods while preserving responsiveness for short idle periods.

### Idle Behavior for PI Devices

When a PI-regulated zone goes idle (room at target), the floor is held at the **current regulated setpoint** rather than applying a setback. This:
- Maintains the equilibrium the PI found
- Prevents the room from cooling and triggering another heat cycle
- Acts like a learned "maintenance" temperature

### Monitoring PI State

Zone entity attributes show PI controller state:

| Attribute | Description |
|-----------|-------------|
| `regulation_offset` | Current PI offset being applied |
| `accumulated_error` | Integral term accumulation |
| `regulated_setpoint` | Actual setpoint sent to regulated devices |

## Services

Hybrid Climate provides administrator-only services for inspecting status and making validated tuning changes. Find the integration's loaded configuration entry and use `get_config` to discover its actual zone IDs, stage positions, device IDs, and writable fields. Use only entity IDs discovered from `get_config`; never construct them. `entry_id` is optional only when exactly one entry is loaded.

| Service | Purpose | Response |
|---|---|---|
| `hybrid_climate.get_status` | Read cached status and recorded restrictions | Required |
| `hybrid_climate.get_config` | Read active tuning values, bounds, controls, and optional structure | Required |
| `hybrid_climate.set_config` | Validate or apply an existing tuning field | Optional; recommended |

For REST calls, POST to `/api/services/hybrid_climate/{get_status|get_config|set_config}?return_response` with an administrator token. The JSON reply is `{"changed_states":[],"service_response":{...}}`; read `service_response`, rather than treating the reply as a bare result. `get_config` accepts `include_structure: true` for discoverable IDs. A patch may contain `global` fields, `zones` keyed by discovered zone ID, and `devices` keyed by discovered loaded model ID. Stage edits go in a zone's `stages` list, addressed by `direction` (`heat` or `cool`) and zero-based stored `index`.

`get_status` also reports active global conflicts, per-device control ownership (including devices that report heat or cool with no owner and no matching command, most often after a restart), per-sensor readings, and each zone's temperature aggregation with spread and outlier hints. `get_config` also exposes read-only reference fields — the active outdoor sensor, each device's idle behavior and command permission, each zone's regulation settings, and compressor groups; these can only be changed in the integration's options, and a `set_config` patch naming one of them is rejected.

### Observability fields

These `get_status`/`get_config` fields are read-only projections of cached state for troubleshooting; none of them re-evaluate control or change any command.

**`get_status.zones.<id>`**
- `tou`: `{"active": bool, "period": str|null, "mode": "peak_relaxation"|"pre_conditioning"|null, "relaxation_applied_heat": float, "relaxation_applied_cool": float}`. `active` is whether the zone has time-of-use configured; `period` is the rate sensor's current cached state (`null` if unconfigured/unavailable); `mode` and the two deltas describe the last adjustment actually applied, and are `0.0`/`null` before the first one.
- `stage_since` / `hvac_action_since`: ISO timestamps of when the zone's current stage / current `hvac_action` last changed, or `null` (always `null` for `hvac_action_since` until the first real transition after a restart).
- `temperature_aggregation.control_value`: the cached temperature control actually used this cycle (`value` is kept as an alias). `temperature_aggregation.weights`: the effective weight (default 1.0) for every configured indoor sensor, present regardless of aggregation method. `temperature_aggregation.method` can now be `median`/`weighted`. `outlier_action` is always the constant `"flagged_only"` — outliers are a hint, never used for control.
- `reasons` gains `heating_demand`/`cooling_demand` entries (`{"code", "detail", "stage", "error"}`) for a zone that is simply heating or cooling on demand, reported from the cached `hvac_action` alone. `error` is the signed distance from target, rounded to 2 decimals, and is `null` only when the current temperature or target isn't a usable number — the reason itself is still reported.

**`get_status.devices.<id>`**
- `last_command_at`: ISO timestamp of the last time this device actually received a service call, or `null` if none since start. Unlike `command_sent_at` (documented next), this is never cleared.
- `command_state` / `command_sent_at`: `command_state` is `"listening"` (device matches our last command) or `"commanding"` (a command was just sent, in flight). `command_sent_at` is the time of the *most recent* send and is only cleared on a command timeout — it is **not** cleared when a command is acknowledged, so a non-`null` `command_sent_at` on a `"listening"` device means "last sent at this time," not "currently in flight." Use `last_command_at` to answer "when was this device last commanded."
- `control.idle_setpoint_basis`: `"lockout_floor"` or `"setback"` after a matching successful idle heat command, `null` otherwise — tells you whether the last idle heat setpoint was capped by the outdoor lockout floor.
- `control.reason`: one code explaining the device's current control state, first match wins: `not_referenced` (no zone stage references it) → `owned_active` (a zone currently owns it) → `awaiting_startup_takeover` (the one-time startup takeover hasn't reached it yet) → `taken_over_at_startup` (its last command was the startup takeover's) → `released_idle` (commanded since start, but not owned) → `never_owned_since_start`.

**`get_status.outdoor`**
- `source`: the entity ID whose reading produced `temperature` (or produced the retained value), or `null`.
- `using_fallback`: `true` when `source` isn't the primary (first-configured) outdoor entity.
- `retained`: `true` when `temperature` comes from the up-to-10-minute retention window rather than a fresh reading.
- `candidates`: every configured outdoor entity from the last cycle, in priority order: `{"entity_id", "status", "value"}`, `status` one of `ok`/`missing`/`unavailable`/`invalid`.

**`get_config.global`**
- `outdoor_sensors` (read-only): the configured outdoor entities in priority order. `outdoor_sensor` (read-only) remains the primary (first) entity, for compatibility.
- `outdoor_thresholds` (read-only): `{"never_heat_above", "heat_resume_at_or_below", "never_cool_below", "cool_resume_at_or_above", "hysteresis_degrees", "no_operation_band"}` — the effective release points (including the built-in hysteresis) computed the same way the conflict resolver evaluates them, and the "neither heat nor cool" outdoor band when both limits are set. Any limit not configured is `null`.
- `lockout_heat_floor` (writable): current value, bounds (40–60°F), and source (`ui_config` or `default`).

**`get_config.zones.<id>`**
- `sensors.weights` (read-only): effective weight (default 1.0) for every configured indoor sensor. Weights themselves are only set through the zone wizard, not `set_config`.
- `outdoor_thresholds` (read-only): same shape as the global one, using this zone's effective (override-or-global) limits.
- `regulation.devices` / `regulation.ignored_devices` (read-only): `devices` is the effective PI regulation list actually used by control (heat-capable only); `ignored_devices` lists any stored device IDs that were dropped because they can't heat, without rewriting your saved options.

Call `set_config` with a `reason` and `dry_run: true` first (the default). Inspect `valid`, `errors`, `warnings`, `diff`, and `revision_before.stored`; confirm the change, then repeat with `dry_run: false` and that stored hash as `expected_hash`. If the hash is stale, read and dry-run again. Only existing blocks and stages can be tuned. Entity-controlled setpoints, presets, PI gains, and balance point use their discovered number or climate entities and corresponding entity services; they are not `set_config` fields.

An apply can save options but fail to reload. In that case `saved=true`, `reloaded=false`, and `pending=true`: inspect the response, persistent notification, and logs, fix the cause, and recover the integration through Home Assistant. A pending loaded entry still supports reads and dry runs but rejects another apply. After setup failure, the entry can be unloaded and service calls for it will raise until it is reloaded. If unload fails and HA marks the entry `FAILED_UNLOAD`, a Home Assistant restart is required to recover it. Saved options are not rolled back automatically.

## Design Decisions

- **Additive staging**: Stage 2 adds devices to Stage 1 (doesn't replace)
- **Conflict resolution**: Blocked device → fall back to other available devices
- **Boost mode**: Uses `skip_time_escalation` config to activate all stages immediately
- **Zone independence**: Each zone directly controllable, not just via master
- **Idle behavior**: Per-device config for what to do when idle (off vs setback)
- **allow_command per-zone**: The same device can have different sync behavior in different zones
- **State machine for sync**: Prevents race conditions between overlay and underlay changes
- **10s grace period**: Allows device time to respond before detecting external override
- **3°F threshold**: Distinguishes between lag and intentional external changes

## Troubleshooting

### Check Logs

Settings → System → Logs, filtered for `hybrid_climate`. For verbose output, add to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.hybrid_climate: debug
```

### Common Issues

1. **Integration not loading**: Check the integration's UI configuration. If this is the first YAML import, also check the `configuration.yaml` include and the imported file.
2. **Zones not responding**: Verify device entity_ids match actual HA entities
3. **Temperature not reading**: Check sensor entity_ids and ensure sensors are available
4. **Conflicts not working**: Verify at least one outdoor sensor is configured and returning valid temps (check `get_status.outdoor.candidates` if using more than one)
5. **External changes not syncing**: Ensure `allow_command: true` is set in the stage devices config
6. **Overlay snapping back**: Check if device is in COMMANDING state (wait 10s for grace period)

For a detailed snapshot of sensor availability, zone lockouts, compressor holds, and requested versus reported device modes, download **Diagnostics** from the integration's menu in Settings → Devices & Services.

## Changelog

### v0.7.0
**Full UI Configuration** - Complete options flow for configuring without YAML:
- **Main menu** with 6 configuration sections
- **Zone wizard** (6 steps): basics, occupancy, heat stages, cool stages, settings, PI control
- **Heat source groups** for opportunistic heating configuration
- **Preset modes** configuration (home/away/sleep/vacation/boost/off)
- **Device conflicts** (mutex rules) for shared equipment
- **Device idle behavior** configuration (off vs setback)
- **Live helpers** support for real-time setpoint/PI tuning (manual creation)
- At the time, UI config merged with YAML; current versions import YAML once and then use UI options

### v0.6.0
- Sleep mode and named setpoints (sleep, vacation)
- Flexible `use_zone_setpoint` for mode config

### v0.5.x
- State machine for bidirectional sync with external thermostats
- Hysteresis fixes, external override detection
- `allow_command` moved to per-zone stage config

See [CHANGELOG.md](CHANGELOG.md) for complete version history.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
