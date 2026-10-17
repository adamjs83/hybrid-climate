# Status and config fields

This page lists the read-only troubleshooting fields returned by `get_status` and `get_config`, one table per block. Read it when you need to know why a zone or device is doing what it does. They show the last recorded result; reading them never re-runs control or changes a command.

For how to call the services, see [Services](services.md).

## get_status.zones.\<id\>

| Field | Meaning | Values |
|---|---|---|
| `tou` | Time-of-use state. `active` says whether the zone has time-of-use configured. `period` is the rate sensor's current cached state. `mode` and the two deltas describe the last adjustment actually applied. | `{"active": bool, "period": str or null, "mode": "peak_relaxation" or "pre_conditioning" or null, "relaxation_applied_heat": float, "relaxation_applied_cool": float}`. `period` is `null` if unconfigured or unavailable. Before the first adjustment, `mode` is `null` and the deltas are `0.0`. |
| `cool_regulation_offset` | Cooling PI offset: the push below the cool target. Sits next to the heating `regulation_offset`. | 0 or below |
| `cool_accumulated_error` | Cooling PI integral term. Sits next to the heating `accumulated_error`. | Number |
| `cool_regulated_setpoint` | Cooling PI setpoint. Sits next to the heating `regulated_setpoint`. A device's applied value is still `devices.<id>.control.cool_offset`. | Number, or `null` until cooling PI has run |
| `stage_since` | When the zone's current stage last changed. | ISO timestamp or `null` |
| `hvac_action_since` | When the zone's current `hvac_action` last changed. | ISO timestamp or `null`. Always `null` until the first real transition after a restart. |
| `temperature_aggregation.control_value` | The cached temperature actually used for control this cycle. `value` is kept as an alias. | Number |
| `temperature_aggregation.weights` | The effective weight for every configured indoor sensor, present for every aggregation method. | Default 1.0 per sensor |
| `temperature_aggregation.method` | The aggregation method. | `average`, `min`, `max`, `median`, `weighted` |
| `temperature_aggregation.outlier_action` | Outliers are a hint and are never used for control. | Always `"flagged_only"` |
| `outage_hold` | Set while a running stage is held through a device outage. The reason `holding_through_device_outage` carries the same fields. | `null`, or `{"since", "until", "devices"}` |
| `hold` | The zone's hold. Also reported by `set_hold`. | Hold object, or `null` |
| `target_source` | Where the zone's current target comes from. | See [Holds](../concepts/holds.md) |

### Reason entries

`reasons` lists why a zone is doing (or not doing) something. These entries can appear:

| Code | When it appears | Fields |
|---|---|---|
| `heating_demand`, `cooling_demand` | The zone is heating or cooling on demand, reported from the cached `hvac_action` alone. | `{"code", "detail", "stage", "error"}`. `error` is the signed distance from target, rounded to 2 decimals. It is `null` only when the current temperature or target is not a usable number; the reason is still reported. |
| `above_cool_target_below_start`, `below_heat_target_below_start` | An idle zone is past its cool or heat target but has not yet crossed that direction's start threshold. | `{"code", "detail", "margin_to_target", "margin_to_start", "start_threshold", "hysteresis", "stage_threshold"}`. `start_threshold` is the larger of the zone's hysteresis and that direction's stage-1 threshold. Below it, hysteresis alone would never start equipment, so this definite cause replaces `unknown` in that band. |
| `stage_without_usable_devices` | Every device in the zone's active stage is unusable (missing the needed capability, unavailable, blocked or not found). Ranked after recorded restrictions and before demand. | Reason fields |

`stage_devices_unusable` is filled whenever any stage device is unusable, even when the reason code is not emitted because at least one device still works.

| Field | Meaning | Values |
|---|---|---|
| `stage_devices_unusable` | One entry per unusable stage device. | `[{"device", "why"}]`; `why` is `missing_capability`, `unavailable`, `blocked` or `not_found` |

## get_status.devices.\<id\>

| Field | Meaning | Values |
|---|---|---|
| `last_command_at` | The last time this device received a service call. Never cleared. Use it to answer "when was this device last commanded". | ISO timestamp, or `null` if none since start |
| `command_state` | Whether the device matches the last command. | `"listening"` or `"commanding"` (a command was sent and is in flight). `commanding` clears when the device reports the commanded mode (and a target within tolerance), or after 60 s. After a timeout the device is `listening` while its reported state may still differ, which is how a manual override is detected. |
| `command_sent_at` | Time of the most recent send. Cleared only on a command timeout, not when a command is acknowledged. A non-`null` value on a `"listening"` device means "last sent at this time", not "in flight now". | ISO timestamp or `null` |
| `control.idle_setpoint_basis` | Whether the last idle heat setpoint was capped by the outdoor lockout floor. Set after a matching successful idle heat command. | `"lockout_floor"`, `"setback"` or `null` |
| `control.reason` | One code for the device's control state. The first match wins (see the next table). | See below |
| `control.override` | Filled when the device's reported mode or setpoint differs from what was last commanded, outside the brief in-flight window. Clears when the device matches again, for example after a restore. A device turned off by hand stays flagged, because restore never turns equipment on. Devices with `allow_command` are never flagged; their changes are adopted into the owning zone's target. | `{"commanded": {"mode", "target"}, "reported": {"mode", "target"}, "since": iso}` or `null` |
| `control.cool_regulation` | The effective cooling mode. | Mode name |
| `control.cool_offset` | The signed °F actually added to the zone cool target in the last owned cool send. In fallback the raw offset is 0, but the limiter can keep the last sent offset applied until the change passes the threshold and minimum period, so read this field for what is applied. | Number; 0 when none |
| `control.cool_regulation_fallback` | Compensation has no usable unit reading. | `true` or `false` |
| `control.cool_compensation_part` | The unit-minus-room °F used in the last computed offset. | Number; 0 when unused or settling |
| `control.cool_compensation_settling` | True during the first 3 minutes of a cooling run that uses the unit reading. | `true` or `false` |
| `control.missing_capabilities` | Every stage that references this device in a direction it lacks. | `[{"zone", "stage", "capability"}]`; empty otherwise |
| `desired_target_temperature` | The target actually commanded, after the cooling offset, device clamping and rounding to the device's target step. | Number |

### control.reason codes

Codes are listed in the order they are checked; the first match wins.

| Order | Code | Meaning |
|---|---|---|
| 1 | `not_referenced` | No zone stage references the device. |
| 2 | `manual_override` | Its mode or setpoint was changed outside Hybrid Climate. See `control.override`. |
| 3 | `owned_active` | A zone currently owns it. |
| 4 | `drying_coil` | Released from cooling and running `fan_only` for coil dry-out. |
| 5 | `awaiting_startup_takeover` | The one-time startup takeover has not reached it yet. |
| 5 | `awaiting_control_restore` | A mode-change or manual restore pass has not reached it yet. |
| 6 | `taken_over_at_startup` | Its last command was the startup takeover's. |
| 6 | `control_restored` | Its last command was a mode-change or manual restore pass's. |
| 7 | `released_idle` | Commanded since start, but not owned. |
| 8 | `referenced_without_capability` | The device is staged in a direction it does not support, and owns no stage direction it does support. |
| 9 | `skipped_non_structural_reload` | The reload right after a non-structural options save skipped the startup takeover. Never for a PI device. |
| 10 | `never_owned_since_start` | None of the above applies. |

## get_status.outdoor

| Field | Meaning | Values |
|---|---|---|
| `source` | The entity whose reading produced `temperature` (or the retained value). | Entity id or `null` |
| `using_fallback` | `source` is not the primary (first configured) outdoor entity. | `true` or `false` |
| `retained` | `temperature` comes from the retention window of up to 10 minutes, not a fresh reading. | `true` or `false` |
| `candidates` | Every configured outdoor entity from the last cycle, in priority order. | `{"entity_id", "status", "value"}`; `status` is `ok`, `missing`, `unavailable` or `invalid` |

## get_config.global

| Field | Meaning | Values |
|---|---|---|
| `outdoor_sensors` (read-only) | The configured outdoor entities in priority order. | List of entity ids |
| `outdoor_sensor` (read-only) | The primary (first) outdoor entity. | Entity id |
| `outdoor_thresholds` (read-only) | The effective release points, including the built-in hysteresis, computed the way the conflict resolver evaluates them, plus the "neither heat nor cool" outdoor band when both limits are set. | `{"never_heat_above", "heat_resume_at_or_below", "never_cool_below", "cool_resume_at_or_above", "hysteresis_degrees", "no_operation_band"}`; any limit not configured is `null` |
| `lockout_heat_floor` (writable) | Current value, bounds and source. | 40-60 °F; source `ui_config` or `default` |
| `device_unavailable_grace` (writable) | How long a running stage is held through a device outage. | Whole seconds, 0-1800; default 300 |

## get_config.zones.\<id\>

| Field | Meaning | Values |
|---|---|---|
| `setpoints.occupancy_entity` (read-only) | The zone's occupancy sensor. | Entity id |
| `setpoints.occupancy_on_delay` (writable) | How long the occupancy sensor must stay on before the zone counts as occupied. A sensor already on at startup counts as occupied at once. | Whole seconds, 0-7200 |
| `setpoints.occupancy_off_delay` (writable) | Delay, measured from the last time this integration saw the zone occupied. After a restart, an off sensor selects the unoccupied setpoints immediately. | Whole seconds, 0-7200 |
| `sensors.weights` (read-only) | The effective weight for every configured indoor sensor. Set weights only on the zone's **Basics & sensors** page (or in YAML), not through `set_config`. | Default 1.0 per sensor |
| `outdoor_thresholds` (read-only) | Same shape as the global one, using this zone's effective limits (zone override or global). | See `get_config.global` |
| `cool_regulation` (read-only) | The zone's cooling PI block. Source is `ui_config` when stored, otherwise `default`. Tune the gains through the zone's cooling PI number entities; `set_config` returns `read_only`. | `{"kp", "ki", "offset_max", "stabilization_threshold", "accumulated_error_threshold", "integral_decay_halflife"}` |
| `regulation.devices` (read-only) | The effective PI regulation list used by control (heat-capable devices only). | List of device ids |
| `regulation.ignored_devices` (read-only) | Stored device ids that were dropped because they cannot heat. Your saved options are not rewritten. | List of device ids |

## get_config.devices.\<id\>

| Field | Meaning | Values |
|---|---|---|
| `capabilities` (read-only) | The device's loaded heat and cool capabilities. | List |
| `capabilities_source` (read-only) | Where the capabilities came from. | `ui` (explicit device entry in the options), `auto_created` (only referenced by a zone stage, capabilities inferred), `yaml` |

In the device editor, the **Can Heat** and **Can Cool** checkboxes default from the entity's supported HVAC modes when you have not saved a capability choice yet. A saved choice is always shown as saved. Saving a zone's stages adds a capability that a staged device supports but was not marked for. It never removes one.

If a stage still references a device that lacks the needed capability, Home Assistant logs one warning at startup or reload. The warning names the zone, stage, device and the options page to fix.

## Related

- [Services](services.md)
- [Entities](../entities.md)
- [Staging](../concepts/staging.md)
- [Wall thermostats](../concepts/wall-thermostats.md)
- [Outdoor limits](../concepts/outdoor.md)
- [Cooling regulation](../regulation/cooling.md)
- [Troubleshooting](../troubleshooting.md)
