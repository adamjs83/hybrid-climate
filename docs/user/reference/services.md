# Services

This page documents the Hybrid Climate services: reading status and configuration, changing tuning values, restoring control and holding a zone. Read it when you write automations, scripts or REST calls. For the fields the read services return, see [Status and config fields](status-fields.md).

All services are for administrators. Use `get_config` to discover your zone IDs, stage positions, device IDs and writable fields. Use only entity ids you discover that way; never build them by hand. `entry_id` is optional only when exactly one Hybrid Climate entry is loaded.

## The services

| Service | Purpose | Response |
|---|---|---|
| `hybrid_climate.get_status` | Read cached status and recorded restrictions | Required |
| `hybrid_climate.get_config` | Read active tuning values, bounds, controls and optional structure | Required |
| `hybrid_climate.set_config` | Validate or apply a change to an existing tuning field | Optional; recommended |
| `hybrid_climate.restore_control` | Run one restore pass over devices no zone owns | Optional; recommended |
| `hybrid_climate.set_hold` | Start, time or end one zone's hold | Optional |

## Where to run them

Run any of them from **Developer tools → Actions**: pick the action, fill in the fields, tick **Return response** for
the read services, and press **Perform action**; the response appears below the form. Automations and scripts call
them the same way, with `response_variable` to capture the response.

## REST calls

POST to `/api/services/hybrid_climate/{get_status|get_config|set_config|restore_control|set_hold}?return_response` with an administrator token. The reply is `{"changed_states":[],"service_response":{...}}`. Read `service_response`; the reply is not a bare result.

`get_config` accepts `include_structure: true` to return the discoverable IDs. A `set_config` call takes these parts, which together make up the patch:

- `global`: global fields.
- `zones`: fields keyed by a discovered zone ID.
- `devices`: fields keyed by a discovered, loaded device ID.
- A zone's `stages` list: stage edits, addressed by `direction` (`heat` or `cool`) and the zero-based stored `index`.

## What the read services return

`get_status` reports:

- Active global conflicts.
- Per-device control ownership, including devices that report heat or cool with no owner and no matching command (most often after a restart).
- Per-sensor readings.
- Each zone's temperature aggregation, with spread and outlier hints.

`get_config` also exposes read-only reference fields: the active outdoor sensor, each device's idle behavior and command permission, each zone's regulation settings, and compressor groups. You can change these only in the integration's options. A `set_config` patch that names one of them is rejected.

## Writable cooling fields

`get_config` exposes nine writable cooling fields per device.

| Field | Values | Default |
|---|---|---|
| `cool_regulation` | `off`, `overdrive`, `compensation`, `pi` | Not set |
| `cool_overdrive` | 0-10 °F | 0 |
| `cool_compensation_max` | 0-10 °F | 3 |
| `cool_pi_compensation` | true or false | false |
| `cool_max_total_push` | 0-15 °F | 8 |
| `cool_regulation_threshold` | 0-5 °F | 0.5 |
| `cool_regulation_min_period` | 0-60 minutes | 10 |
| `cool_dry_out` | true or false | false |
| `cool_dry_out_minutes` | 1-30 | 10 |

`cool_compensation_sensor` is read-only here; set it in YAML or the options screens. Set a field through `set_config` under the discovered device ID:

```json
{"devices": {"hp": {"cool_regulation": "compensation"}}}
```

`get_status.devices.<id>.desired_target_temperature` shows the target actually commanded, after the cooling offset and device clamping.

## Change settings with set_config

Work in two steps.

1. Call `set_config` with a `reason` and `dry_run: true`. This is the default. Inspect `valid`, `errors`, `warnings`, `diff` and `revision_before.stored`.
2. Confirm the change, then repeat the call with `dry_run: false` and the `revision_before.stored` value from step 1
   as `expected_hash` (for example `expected_hash: "3f9c1a…"`). The hash proves nobody changed the options in between.

If the hash is stale, read and dry-run again. You can only tune existing blocks and stages. Entity-controlled setpoints, presets, PI gains and the balance point use their own number or climate entities and the matching entity services; they are not `set_config` fields.

```yaml
action: hybrid_climate.set_config
data:
  reason: "Raise lockout floor"   # the line you change: say why
  dry_run: true                   # set false, with expected_hash, to apply
  global:
    lockout_heat_floor: 57
response_variable: result
```

### When an apply does not load

An apply can save your options but fail to reload. The response then shows `saved=true`, `reloaded=false` and `pending=true`. Check the response, the logbook entry, the "Saved Hybrid Climate settings are not active" Repairs issue and the logs. Fix the cause, then recover the integration through Home Assistant.

- A pending loaded entry still supports reads and dry runs but rejects another apply.
- After a setup failure, you can unload the entry. Service calls for it then raise an error until it is reloaded.
- If the unload fails and Home Assistant marks the entry `FAILED_UNLOAD`, restart Home Assistant to recover it.
- Saved options are not rolled back automatically.

## Restoring control

`hybrid_climate.restore_control` runs one restore pass. It is the same pass a settled master mode change triggers automatically. Every device that no zone owns gets its configured idle action, applied exactly once: off, or a setback that respects the outdoor heat lockout floor. A device under PI regulation is skipped, because its own regulation already commands it every cycle.

The pass never turns equipment on and never touches a device another zone is using. Both fields are optional.

| Field | Required | Meaning |
|---|---|---|
| `entry_id` | No | Config entry ID; optional only when exactly one entry is loaded |
| `zone_id` | No | A configured zone ID. Restores only that zone's devices. A device shared with another zone is still skipped if that zone owns it. |

The response reports every device in the requested scope:

```json
{
  "entry_id": "01ABCDEF...",
  "zone_id": "hybrid_first_floor",
  "source": "manual",
  "devices": [
    {
      "device_id": "nest_thermostat_3",
      "entity_id": "climate.nest_thermostat_3",
      "result": "sent",
      "reason": "sent",
      "command": {"mode": "heat", "target": 55.0}
    }
  ]
}
```

### Result codes

`result` groups the outcome codes of the pass. `command` is filled in only for `sent` and `unchanged`.

| `result` | `reason` values | Meaning |
|---|---|---|
| `sent` | `sent` | The idle command was sent. |
| `unchanged` | `unchanged` | The device already matched. |
| `skipped` | `owned` | A zone already owns the device. |
| `skipped` | `pending_normal_request` | A normal, non-restore command is already in flight for it. |
| `skipped` | `not_found` | The device was not found. |
| `skipped` | `not_heat_or_cool` | The device is off or not reporting heat or cool, so there is nothing to restore. It does not mean the device is incapable. |
| `skipped` | `pi_regulated` | PI regulation already commands it every cycle. |
| `pending` | `unavailable_retry`, `missing_temperature_retry`, `blocked_retry`, `in_flight_retry` | Retried on later cycles, the same as the automatic pass. |
| `superseded` | none | A newer restore request replaced this one before it ran. |

The same pass is available per zone as the **Restore control** button (see [Entities](../entities.md)). The button needs no administrator role, only Home Assistant's normal entity permissions.

## Holding a zone

`hybrid_climate.set_hold` starts or ends a zone's hold. The zone stays at its current temperatures until the hold ends, then resumes its saved temperatures. This service is the only way to set a timed hold. The zone's **Hold** switch and the `hold` preset give untimed holds.

| Field | Required | Meaning |
|---|---|---|
| `entity_id` | Yes | The zone's climate entity or its Hold switch |
| `hold` | Yes | `true` starts the hold (on a held zone it only changes the end time). `false` ends it and resumes the saved temperatures. |
| `until` | No | End time. A time without a UTC offset is read in Home Assistant's time zone. Must be in the future. |
| `duration` | No | Length in minutes, 1-1440 |

`until` and `duration` cannot be used together, and both need `hold: true`.

```yaml
action: hybrid_climate.set_hold
data:
  entity_id: climate.hybrid_climate_upstairs
  hold: true
  duration: 120   # the line you change: minutes, 1-1440
```

The response is `{"zone_id": "...", "hold": {"since", "until", "heat", "cool"}}`. After you end a hold, `hold` is `null`. `get_status.zones.<id>` reports the same `hold` object and `target_source`.

## Related

- [Status and config fields](status-fields.md)
- [Holds](../concepts/holds.md)
- [Idle and restore](../concepts/idle-and-restore.md)
- [Cooling regulation](../regulation/cooling.md)
- [Entities](../entities.md)
- [Troubleshooting](../troubleshooting.md)
