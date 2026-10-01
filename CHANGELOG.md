# Changelog

All notable user-facing changes to Hybrid Climate are listed here.
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
