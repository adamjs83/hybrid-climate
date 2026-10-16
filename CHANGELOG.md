# Changelog

All notable user-facing changes to Hybrid Climate are listed here.
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.17.4] - 2026-10-16

### Added
- Cooling PI can now react to the outdoor temperature. Two new numbers per cooling zone, "Cooling PI outdoor gain" (default 0, which keeps today's behavior) and "Cooling PI outdoor balance point" (default 75 °F), add extra cooling push when it is hotter outside than the balance point and take some away when it is colder. The "Cooling PI maximum push" still limits the total. Both can also be set in the zone's `cool_regulation` block (`k_ext`, `balance_point`).

## [0.17.3] - 2026-10-16

### Added
- Cooling PI can also correct for the unit's own temperature reading: a new checkbox per cooling device on the zone Regulation page adds (unit reading − room reading) to the Cooling PI target, in either direction, so the push is felt on the unit's own scale. A new "Maximum total push" setting (default 8 °F) limits how far below the zone target it can go.

### Changed
- "Correct the unit's temperature reading" and the new Cooling PI correction ignore the unit's reading for the first 3 minutes of each cooling run, when many units' own sensors briefly dip, and then apply the correction at once.

## [0.17.2] - 2026-10-16

### Changed
- "Correct the unit's temperature reading" now only pushes: when the unit reads lower than the room it lowers the cooling target by the difference, as before, but when the unit reads at or above the room it sends the zone target unchanged instead of raising it.

## [0.17.1] - 2026-10-16

### Fixed
- The zone menu header showed a translation error instead of a title. It now reads "Zone settings"; the zone's name is in the text below it.
- A thermostat reporting a target up to 1.5 °F away from the one Hybrid Climate sent (for example a Nest showing 56 °F for a commanded 55 °F) is no longer flagged as a manual override.

## [0.17.0] - 2026-10-16

Cooling PI arrives, and the options pages are rebuilt so that editing one setting means opening one page and saving it.

### Added
- **Cooling PI** is a working cooling regulation mode. A device set to Cooling PI gets a push below the zone's cooling target that grows while the room stays warm and fades once it is at target, limited by a maximum push. Each zone with cooling stages gets three number entities to tune it: **Cooling PI proportional gain**, **Cooling PI integral gain** and **Cooling PI maximum push** (0–10 °F, default 5). Thresholds can be set in YAML under the zone's `cool_regulation` block. The zone climate, `get_status` and the dashboard show the cooling offset and setpoint.
- **A menu for each zone.** Zones opens a list, and each zone opens its own menu: Basics & sensors, Setpoints & occupancy, Heating stages, Cooling stages, Behaviour, Regulation and Time-of-use. Each page saves on its own. Adding a zone takes three pages: basics, heating stages and cooling stages.
- **Regulation page** per zone. It holds heating regulation (Direct or PI, which thermostats, how often) and one section per cooling device (mode, correction amounts, the unit's own sensor, minimum change and period). A device used by several zones shows the same settings on each and says so. The PI gains stay on their number entities, which the page lists with their current values.
- **Shared equipment** menu for Heat source groups and Equipment that cannot run together.
- Deleting a zone, heat source group or conflict rule now asks first and lists what refers to it.
- The dashboard card names every zone reason in plain words.

### Changed
- **Saving a page no longer makes every thermostat jump.** A save that does not change structure (zones, sensors, stage equipment, device capabilities, conflict rules or heat source groups) skips the startup takeover on the reload that follows. Home Assistant restarts, structural saves, Agent API changes and later reloads still run it.
- Cooling regulation settings moved from the device page to each zone's Regulation page. The device page keeps capabilities, idle action, compressor protection and coil dry-out, and shows which zones set its cooling mode.
- Thermostat sync is on the Behaviour page as "Wall thermostats that follow hand changes". Outdoor limits there are "Use house limit", "No limit" or a value for each direction.
- The top menu is Global settings · Zones · Devices · Presets · Shared equipment. Global settings lists the outdoor limits last, and Presets explains how a mode reuses another mode's setpoints.

## [0.16.1] - 2026-10-16

Quick wins from a full review of the setup experience. Nothing changes in how zones and devices are controlled; stored settings, the Agent API and the entity ids of existing installs are untouched.

### Fixed
- **Global Settings can be saved with its defaults.** They are now 55 °F (never heat above) and 63 °F (never cool below); the check that heat-above stays below cool-below remains.
- **Editing a zone no longer loses settings its pages do not show.** Stages 3 and up, a stage's `outdoor_temp_max`, and advanced PI settings (stabilization threshold, integral settings) survive a save. Turning a mode off on its page saves no stages for it.
- **PI gains are set on the number entities.** The wizard's Kp/Ki/K_ext/max offset/balance point fields only seeded numbers that already existed, so they are gone; the page now names the zone's PI number entities instead.
- In YAML, `action: off` for a device's idle action works without quotes.
- The **temperature spread** sensor is only created for zones with two or more sensors. On a single-sensor zone an existing one shows unavailable instead of unknown forever.
- "Enable heating" is no longer pre-ticked for a zone that has no heat stages.
- The device page shows its **cooling settings only for devices that can cool**, with the overdrive amount directly under the mode. "Cooling PI (next release)" is no longer offered.
- Saving a device conflict rule no longer writes a warning to the log.
- **Entity names no longer repeat the zone name** ("Hybrid Climate - Basement" instead of "Hybrid Climate - Basement Basement"; numbers read "Hybrid Climate - Basement Default Heat"). Uncontrolled-device sensors use the device's name. Existing installs keep every entity id; new installs get shorter ones such as `climate.hybrid_climate_basement`.

### Changed
- Clearer wording throughout the options pages: the menu item is **Devices**; cooling modes are "Use room target", "Fixed cooling correction" and "Correct the unit's temperature reading"; the zone pages say "Heating regulation", "Start/stop temperature buffer", "Add backup equipment after", "Electricity price adjustments" and "Equipment that cannot run together"; the global presence entity is an entity picker; four Reason states read as plain sentences ("Waiting for cooling start temperature", "No available equipment can run this stage", …).
- Units are `s` everywhere; the stage 2 escalation time and the occupancy off delay are entered in minutes (stored in seconds as before). The navigation choice is the first field on every page.

## [0.16.0] - 2026-10-15

### Added
- New per-device **Cooling regulation** mode in Device Behaviors: **Off** (send the zone's cooling target, the previous behavior), **Fixed overdrive** (the existing Cooling overdrive setting), **Compensate the unit's own sensor**, and **Cooling PI** (accepted now, active in a later release). A device that already has a cooling overdrive keeps behaving exactly as before; everything else defaults to Off.
- **Compensation** sends the zone's cooling target plus the difference between the unit's own temperature reading and the room temperature, limited by **Compensation maximum** (0–10 °F, default 3). The unit then stops when the room, not its own sensor, reaches the target. The reading comes from the climate entity, or from an optional **Compensation sensor** (a `sensor.*` entity that reports °F, used as-is). If the reading is missing, the offset falls back to 0 and a warning is logged once.
- Two per-device limits for compensation: **Cooling regulation threshold** (0–5 °F, default 0.5) and **Minimum cooling regulation period** (0–60 minutes, default 10). A changed offset is only re-sent once both pass; a changed cooling target is sent at once.
- Optional **Coil dry-out**: tick it and set **Dry-out minutes** (1–30, default 10) to run the unit's fan only for that long after it stops cooling, before its normal idle behavior, so the coil dries instead of sitting wet. Units without a fan-only mode get their idle behavior as before, with one warning.
- Agent API: `get_config`/`set_config` can read and change `cool_regulation`, `cool_compensation_max`, `cool_regulation_threshold`, `cool_regulation_min_period`, `cool_dry_out` and `cool_dry_out_minutes`; the compensation sensor is read-only. `get_status` shows each device's `cool_regulation`, the cooling offset actually applied (`cool_offset`), whether the unit reading is missing (`cool_regulation_fallback`), and a `drying_coil` control reason while a dry-out runs.

### Changed
- In YAML, `cool_regulation: off` can be written without quotes.

## [0.15.0] - 2026-10-15

### Added
- Two new PI regulation settings per zone, in the zone's PI settings step: **Regulation threshold** (0–5 °F, default 0) and **Minimum regulation period** (0–60 minutes, default 0). They limit how often a heating zone's regulated setpoint is re-sent to its PI devices: a new value is only sent once it has moved at least the threshold, and no sooner than the minimum period after the last change. This cuts the stream of small setpoint nudges that thermostats and heat pumps do not need. Changes to the zone's target, mode changes, direction reversals, releases and restarts are always sent at once. Both settings apply to heating PI only and appear read-only under the zone's `regulation` in `get_config`. Leave them at 0 (the default) to keep the old behavior.

## [0.14.0] - 2026-10-15

### Added
- New per-device **Cooling overdrive** setting (0–10 °F, default 0) in Device Behaviors. While a zone calls for cooling from a device, the device is sent a setpoint this many degrees below the zone's cooling target, so units that coast once their own sensor reaches the setpoint keep cooling until the zone itself is satisfied. The zone still stops at its own target. Heating, idle setbacks and devices no zone is cooling with are unaffected. If you change the setpoint on the device itself while a zone is cooling with it, the zone's target is updated with the overdrive added back. `get_config`/`set_config` can read and change the setting. Set it to 0 (the default) to keep the old behavior.

## [0.13.5] - 2026-10-15

### Added
- New global **Device outage grace period** setting (0–1800 seconds, default 300) in Global Settings. When a device that is running a zone's stage briefly becomes unavailable, the zone now keeps that stage and its device assignment for up to this long instead of releasing it and restaging. If the device comes back in time, the run simply continues; if not, or if the zone no longer needs heating or cooling, it is released as before. A hold never keeps a stage running past its normal stop point. Set it to 0 to keep the old behavior. `get_status` shows when a zone is holding through an outage and why, and `get_config`/`set_config` can read and change the setting.

### Fixed
- Global Settings now saves the outage grace as a whole number, and whole-number values saved by older versions are read back correctly.

## [0.13.4] - 2026-10-14

### Changed
- Maintenance only: the repository's validation workflow now uses `actions/checkout` v7. The integration itself is unchanged from 0.13.3, so updating is optional.

## [0.13.3] - 2026-10-14

### Added
- New per-zone **Occupancy off-delay** setting (0–7200 seconds, default 0 = unchanged behavior), next to the zone's occupancy sensor in the zone's occupancy settings. After the sensor turns off, the zone keeps its occupied setpoints until this long after Hybrid Climate last saw it occupied, so a flickering presence sensor no longer flips the setpoint back and forth. A restart or an unavailable sensor never counts as presence. `get_config` now shows each zone's occupancy sensor and delay, and `set_config` can change the delay.

### Fixed
- A device whose reported minimum or maximum temperature is rounded (for example 79 °F shown for a native 26.0 °C limit) could reject a target at that limit, leaving it running at an old setpoint and failing every cycle. Hybrid Climate now retries once at one step inside the limit, logs a warning, and uses that limit for the device until the next reload.

## [0.13.2] - 2026-10-01

### Added
- Changing the master preset (Home, Away, Sleep, Vacation, Boost, Off) now restores control once, about 10 seconds after the mode settles, for every configured device no zone is currently using — other than a device under PI regulation, which is already commanded every cycle by its own regulation and needs no restore. Each restored device gets its idle action applied exactly once — off, or a setback that respects the outdoor heat lockout floor when lockout is active. It never turns equipment on, it skips any device another zone is using, and it does not repeat. A manual change you make afterward still sticks until the next mode change or restore.
- A new service, `hybrid_climate.restore_control` (administrator only, optional `entry_id`/`zone_id`), runs that same restore pass on demand and reports a per-device result. A matching per-zone "Restore control" button (under each zone's Configuration section) does the same for just that zone.
- Manual-override detection: if a device's mode or setpoint is changed outside Hybrid Climate, its "Uncontrolled" problem sensor now also turns on, with a new `manual_override` attribute describing what was commanded, what's now reported, and when the change was first seen. One logbook entry is written per override; it clears once the device matches the commanded values (e.g. after a restore sends them); a device turned off by hand stays flagged, because restore never turns equipment on. Devices with `allow_command` enabled are never flagged, since their changes are adopted as the zone's new target instead.

### Changed
- `get_status` gains a new device control reason, `manual_override` (takes precedence over `owned_active`), and a new `control.override` field describing an active override's commanded/reported values and when it started.
- `get_status` also gains two more device control reasons, `control_restored` and `awaiting_control_restore`, describing a device last touched by a mode-change or manual restore pass rather than the one-time startup takeover.

## [0.13.1] - 2026-09-30

### Added
- New diagnostic entities (grouped under each zone/master device's "Diagnostic" section, hidden from the main dashboard view by default) so troubleshooting information now has history and can be charted or alerted on, instead of only being visible through a service call: per-zone **Reason** (why a zone is or isn't running, e.g. `within_target`, `heating_demand`, `unknown`), **Temperature spread** (the spread across a zone's smoothed sensor inputs), and **Stage** (the active heating/cooling stage, including opportunistic heating); an **Uncontrolled** problem sensor per device (a device reporting heat/cool that no zone currently owns); and two whole-home entities, **Outdoor fallback active** (a backup outdoor sensor is in use) and **Outdoor source** (which sensor is currently supplying the outdoor reading). The zone's existing **Temperature** sensor is the zone's control temperature — no separate entity was added for it, avoiding a duplicate history stream.
- `get_status` now reports why a device stage can't run: when a stage's devices are all unusable (missing the needed heat/cool capability, unavailable, blocked, or not found), the zone gets a new reason `stage_without_usable_devices`. Each device's control block gains `missing_capabilities`, listing any stage that references it without the needed capability, and `control.reason` becomes `referenced_without_capability` when nothing else (already owned and active, a startup takeover, or just released from idle) explains the device.
- `get_config` now shows each device's loaded heat/cool capabilities and where they came from, for reference.
- The device editor's "Can Heat"/"Can Cool" checkboxes now default from the underlying entity's supported modes when a device has no saved capability choice yet, and saving a zone's stages automatically adds a capability a staged device supports but wasn't marked for (never removes one). A one-time log warning names any remaining zone/stage/device mismatch and how to fix it in Options.
- Two new status reasons for an idle zone sitting between its target and where heating/cooling would actually start (`above_cool_target_below_start`, `below_heat_target_below_start`), replacing an unhelpful `unknown` in that narrow band.

### Changed
- Reduced background history-database growth: a few per-cycle attributes (individual sensor readings and time-in-stage) are excluded from recorder storage on the zone and Temperature sensor entities. They remain visible in the entity's current state; only long-term history storage is affected.

## [0.13.0] - 2026-09-29

### Changed
- **Startup behavior**: once after Home Assistant starts (and again after every integration reload, including saving a configuration change), each device that no zone is actively using but that is still reporting heat or cool now receives its configured idle action exactly one time. It is never turned on. Any manual change you make to that device afterward is left alone.
- Proportional-integral (PI) regulation now only ever applies to devices that can heat. A cool-only device (for example a shared whole-home AC) listed under a zone's PI regulation is ignored, with a warning logged, instead of being silently turned off in the background every idle cycle — this fixes PI regulation overriding a manually-started AC.

### Added
- New global setting **Lockout heat floor** (default 55°F, adjustable 40–60°F). While the outdoor heat lockout is active, an idle heating setback is never allowed above this floor. The lockout starting or ending never sends a command by itself; the floor only takes effect on the next idle release.
- Zones can now aggregate their indoor temperature sensors by **median** (ignores a single outlier) or **weighted average** (assign each sensor its own weight in the zone wizard), alongside the existing average/min/max.
- The outdoor temperature sensor is now an **ordered list of sensors**. Configure a primary plus one or more backups (`sensor.*` or `weather.*`) in Global Settings; each cycle uses the first one with a valid reading. Existing single-sensor setups keep working unchanged.
- `get_status`/`get_config` gained several read-only fields for troubleshooting: time-of-use status per zone, effective outdoor lockout thresholds, zone and device timestamps, per-device last-command time and a plain-language control reason, sensor aggregation weights and control value, and the ordered outdoor sensor candidates.

## [0.12.1] - 2026-09-29

### Added
- `get_status` now reports active global conflicts, and each device shows which zones own it, whether the integration currently commands it, and whether it reports heat or cool while no zone owns it and the integration has not commanded that mode (and no command is in flight).
- Each zone's sensor readings now include their cached value, smoothed value, and deviation from the zone's current temperature, and each zone reports a temperature aggregation summary with its inputs, spread, and any outlier readings (a hint, not used for control).
- An idle zone sitting within its heat/cool targets now reports a clear "within target" status instead of "unknown".
- `get_config` now shows the active outdoor sensor, each device's idle behavior and command permission, each zone's regulation settings, and compressor groups, for reference; these remain read-only and are changed in the integration options, not through configuration changes.

### Fixed
- Configuration change requests now consistently reject a blank or whitespace-only reason.

## [0.12.0] - 2026-09-29

### Added
- Administrator-only services to inspect climate status, explain recorded restrictions, and discover effective configuration and entity controls.
- Validated tuning changes with dry runs, before/after diffs, revision checks, and a single configuration reload.
- Persistent notifications and logbook records for saved changes, including changes that could not become active.

### Safety
- Saved and active revisions remain distinct when a reload fails. Correct the failure and recover the integration through Home Assistant before applying another change.
- Setpoints, presets, and PI controls remain managed through their existing entities; structural configuration remains in the UI.

## [0.11.0a5] - 2026-09-28

- Display zones in a responsive grid with clearer status styling when the card has enough width.
- Use full-width Panel views in the dashboard example, and request full width in Sections views.

## [0.11.0a4] - 2026-09-28

- Added a dynamic dashboard card with overview, zone details, setpoint, PI, and device views. Zones appear automatically and can be ordered along with their rows in dashboard YAML or the card editor.
- Added live zone restrictions, sensor and opening status, registered setpoint and PI controls, and a paste-ready five-view dashboard example.

## [0.11.0a3] - 2026-09-28

### Fixed
- Hybrid Climate no longer logs the full configuration entry at startup; configuration logs now use brief summaries.

## [0.11.0a2] - 2026-09-28

### Fixed
- Diagnostics now show outdoor heat/cool permissions for each zone and identify outdoor lockouts when a room needs a blocked direction.

## [0.11.0a1] - 2026-09-28

Alpha preview for testing new control safeguards.

### Added
- Optional shared-compressor minimum run and off times. The longest configured interval among group members applies; forced shutdowns bypass the minimum run time.
- Optional per-zone door/window contacts with open and close delays. Open contacts at startup and unavailable contacts pause immediately.
- Downloadable Home Assistant diagnostics showing zone and sensor state, opening lockouts, compressor holds, and device commands alongside reported state.

### Changed
- Forced shutdowns now command equipment off even when its normal idle action is setback.
- Documentation explains that YAML is imported once and subsequent configuration is managed in the UI.

Compressor timing uses the climate entity HVAC mode as a proxy, so thermostat-controlled compressor cycling cannot be measured precisely.

## [0.10.1] - 2026-09-28

### Changed
- Maintenance release: manifest metadata ordered for Home Assistant validation. No behavior changes.

## [0.10.0] - 2026-09-28

First public release, installable through HACS.

### Fixed
- Devices no longer keep running after a zone drops a stage or switches between heating and cooling; shared devices are released only when no other zone needs them.
- Heat-only devices (e.g. radiant floors) are never sent a cooling command, and turning a zone or the master off now actually stops PI-regulated heating.
- Cooling idle setback is calculated from the cooling target instead of the heating target.
- Heating and cooling stages hold until the setpoint is reached instead of short-cycling at the stage threshold.
- Outdoor heat/cool lockouts have hysteresis and a reversal delay, and a lost outdoor sensor keeps the last known state instead of allowing both heating and cooling.
- Overlapping heat/cool setpoints can no longer make a zone alternate between heating and cooling.
- PI regulation no longer winds up during cooling, and stage escalation timers reset when switching between heating and cooling.
- Setpoint changes only go to devices running in the matching direction.
- Shared devices get one command per cycle, redundant commands are skipped, and failed service calls are detected.
- Device exclusion (mutex) rules configured in the UI now match correctly.
- External thermostat changes on shared devices update every zone that uses the device.
- Away, unoccupied and preset cooling setpoints are derived correctly, and number-entity changes respect presets.
- UI configuration fixes: TOU rate sensor setting, per-stage outdoor limits, per-zone outdoor overrides, and deleted or disabled options no longer reappear after saving.
- Devices removed from the configuration are released on reload.
