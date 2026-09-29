# Changelog

All notable user-facing changes to Hybrid Climate are listed here.
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
