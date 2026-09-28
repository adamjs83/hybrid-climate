# Changelog

All notable user-facing changes to Hybrid Climate are listed here.
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
