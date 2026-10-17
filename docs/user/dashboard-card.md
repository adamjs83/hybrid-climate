# Dashboard card

This page shows how to install the Hybrid Climate dashboard card and choose what it displays. Read it when you build a dashboard for your zones.

The card (`custom:hybrid-climate-card`) reads the zones and devices in the active integration configuration. When you add or remove a zone in **Settings → Devices & Services → Hybrid Climate → Configure**, the card picks up the change without you editing each dashboard view.

The card has five views: Climate Overview, Zone Details, Setpoints, PI Controller and All Devices.

## Install

1. Restart Home Assistant after installing or updating Hybrid Climate, so it registers the card file.
2. Go to **Settings → Dashboards → Resources** and add `/hybrid_climate/hybrid-climate-card.js` as a **JavaScript module**.
3. Open the dashboard, choose **Edit dashboard** from its ⋮ menu, then **Add card → Manual**. Paste the YAML from
   [Configure the card](#configure-the-card) below and save.
4. For a side-by-side layout, open the view's settings (the pencil next to the view name while editing) and set
   **View type** to **Panel**.

To start from the example instead, create a new dashboard, open its **Raw configuration editor** from the ⋮ menu and
paste in [`dashboard_dynamic_example.yaml`](../../dashboard_dynamic_example.yaml). It has one card for each of the five
views, each in a Panel view.

## Use a Panel view

Put the card in a **Panel** view so the zone cards sit side by side. A Panel view holds one card and gives it the full dashboard width, and the card arranges the zones in a responsive grid.

In a Masonry view, Home Assistant limits each card to one column, so the zones stack. In a Sections view, the card asks for the full section width. The example file sets `type: panel` on all five views.

## Configure the card

```yaml
type: custom:hybrid-climate-card
view: overview
rows:
  - status
  - thermostat
  - targets
  - lockout_reason
zone_order:
  - living_room   # zone IDs from Configure → Zones
  - upstairs
```

| Option | What it does | Default |
|---|---|---|
| `view` | Which of the five views the card shows. | `overview` in the example |
| `rows` | Ordered list of sections shown in each zone: `status`, `thermostat`, `targets`, `lockout_reason`, `sensors`, `openings`, `equipment`, `setpoints`, `pi`. | The view's defaults |
| `zone_order` | Zone IDs from **Configure → Zones**. Listed zones come first, in this order. New zones are added at the end automatically. | Integration order |
| `zone_rows` | Overrides `rows` for one zone. | None |
| `hidden_zones` | Zone IDs to hide. | None |

The card's graphical editor can also reorder zones and sections.

## What the card changes

Temperature and mode changes on the card are live controls. Its setpoint and PI controls use the integration's `number.*` entities and take effect without a reload.

The card does not edit structure. To add or remove zones, devices, stages, sensors, opening contacts and other structural settings, use **Configure**.

## Related

- [Entities](entities.md)
- [Holds](concepts/holds.md)
- [Heating PI regulation](regulation/heating-pi.md)
- [Zones](configuration/zones.md)
- [Troubleshooting](troubleshooting.md)
