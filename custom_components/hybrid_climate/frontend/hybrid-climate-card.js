/* Hybrid Climate Lovelace card. No build step or third-party dependencies. */
const HC_VIEWS = ["overview", "details", "setpoints", "pi", "devices"];
const HC_ROWS = ["status", "thermostat", "targets", "lockout_reason", "sensors", "openings", "equipment", "setpoints", "pi"];
const HC_DEFAULT_ROWS = {
  overview: ["status", "thermostat", "targets", "lockout_reason"],
  details: ["status", "targets", "lockout_reason", "sensors", "openings", "equipment"],
  setpoints: ["setpoints"],
  pi: ["pi"],
  devices: ["equipment"],
};
const HC_ROW_LABELS = {
  status: "Status", thermostat: "Thermostat", targets: "Targets",
  lockout_reason: "Restrictions", sensors: "Sensors", openings: "Openings",
  equipment: "Equipment", setpoints: "Setpoints", pi: "PI controller",
};
const HC_REASON_LABELS = {
  outdoor_cool_lockout: "Cooling held by outdoor temperature",
  outdoor_heat_lockout: "Heating held by outdoor temperature",
  opening_lockout: "Open door or window",
  sensor_failure: "Temperature sensor unavailable",
  compressor_min_runtime: "Compressor minimum runtime",
  compressor_min_off_time: "Compressor minimum off time",
};

function hcEl(tag, className, value) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (value !== undefined && value !== null) el.textContent = String(value);
  return el;
}
function hcText(value, fallback = "—") {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}
function hcTemp(value, unit) {
  if (value === undefined || value === null || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number * 10) / 10}°${unit}` : "—";
}
function hcLabel(value) {
  return hcText(value).replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
function hcOrdered(zones, order) {
  const rank = new Map((Array.isArray(order) ? order : []).map((id, index) => [id, index]));
  return [...zones].sort((a, b) => {
    const ai = rank.has(a.id) ? rank.get(a.id) : Infinity;
    const bi = rank.has(b.id) ? rank.get(b.id) : Infinity;
    return ai - bi || (a.order ?? 0) - (b.order ?? 0);
  });
}
function hcRows(config, zoneId) {
  const selected = config.zone_rows?.[zoneId] ?? config.rows ?? HC_DEFAULT_ROWS[config.view || "overview"];
  return Array.isArray(selected) ? [...new Set(selected.filter((row) => HC_ROWS.includes(row)))] : [];
}
function hcFireConfig(target, config) {
  target.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
}

class HybridClimateCard extends HTMLElement {
  static getConfigElement() { return document.createElement("hybrid-climate-card-editor"); }
  static getStubConfig() { return { view: "overview" }; }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { view: "overview" };
    this._refs = [];
    this._cards = [];
    this._lastFetch = 0;
  }
  setConfig(config) {
    if (!config || !HC_VIEWS.includes(config.view || "overview")) throw new Error("Choose a valid Hybrid Climate view");
    this._config = { ...config, view: config.view || "overview" };
    this._render();
  }
  set hass(hass) {
    const connectionChanged = this._hass?.connection !== hass.connection;
    this._hass = hass;
    if (connectionChanged) this._data = undefined;
    this._refreshLive();
    if (connectionChanged || !this._data || Date.now() - this._lastFetch > 15000) this._load();
  }
  connectedCallback() {
    this._render();
    if (this._hass) this._load();
    this._poll = setInterval(() => this._load(), 15000);
  }
  disconnectedCallback() { clearInterval(this._poll); }
  getCardSize() { return Math.max(3, (this._zoneCount || 1) * 3); }
  getGridOptions() { return { columns: "full" }; }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    this._lastFetch = Date.now();
    try {
      const data = await this._hass.callWS({ type: "hybrid_climate/dashboard_info" });
      if (!this.isConnected) return;
      const oldStructure = this._structureKey;
      this._data = data;
      this._error = undefined;
      this._structureKey = JSON.stringify((data.entries || []).map((entry) => ({
        entry_id: entry.entry_id, master: entry.master,
        zones: entry.zones?.map(({ id, name, entity_id, order, controls, devices, outdoor_reset }) => ({ id, name, entity_id, order, controls, devices, outdoor_reset })),
      })));
      if (this._structureKey !== oldStructure) this._render();
      else {
        // Keep child controls mounted while updating their latest status snapshot.
        for (const entry of data.entries || []) {
          const oldEntry = this._renderedEntries?.find((item) => item.entry_id === entry.entry_id);
          for (const zone of entry.zones || []) {
            const oldZone = oldEntry?.zones?.find((item) => item.id === zone.id);
            if (oldZone) oldZone.status = zone.status;
          }
        }
        this._refreshLive();
      }
    } catch (error) {
      this._error = `Could not load Hybrid Climate dashboard data: ${error.message || error}`;
      this._render();
    } finally { this._loading = false; }
  }

  _render() {
    if (!this.shadowRoot) return;
    this._refs = [];
    this._cards = [];
    this.shadowRoot.replaceChildren();
    const style = hcEl("style");
    style.textContent = `
      :host { display:block; color:var(--primary-text-color); }
      .root { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr)); gap:16px; align-items:start; }
      .zone { --hc-accent:var(--secondary-text-color); min-width:0; padding:18px; border-radius:var(--ha-card-border-radius,14px); background:var(--card-background-color); box-shadow:var(--ha-card-box-shadow); border:1px solid var(--divider-color); border-left:4px solid var(--hc-accent); }
      .zone[data-action="heating"] { --hc-accent:var(--warning-color,#e89927); }
      .zone[data-action="cooling"] { --hc-accent:var(--info-color,#36a5d8); }
      .zone[data-action="off"] { --hc-accent:var(--disabled-text-color,#8a8a8a); }
      .zone-head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:14px; }
      .zone h2 { margin:0; font-size:1.1rem; line-height:1.3; }
      .action-badge { flex:none; padding:5px 9px; border-radius:999px; background:var(--secondary-background-color); color:var(--hc-accent); font-size:.76rem; font-weight:650; }
      .row { padding:12px 0; border-top:1px solid var(--divider-color); }
      .row:first-of-type { border-top:0; }
      .row-title { font-size:.75rem; font-weight:650; letter-spacing:.04em; text-transform:uppercase; color:var(--secondary-text-color); margin-bottom:8px; }
      .metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(105px,1fr)); gap:12px; }
      .metric { display:flex; flex-direction:column; gap:2px; }
      .metric small { color:var(--secondary-text-color); font-size:.76rem; }
      .metric > span { font-size:1rem; font-weight:550; }
      .status-metrics .metric:first-child > span { font-size:2rem; line-height:1.15; font-weight:350; letter-spacing:-.035em; }
      .targets-metrics .metric { padding:9px 10px; border-radius:9px; background:var(--secondary-background-color); }
      .reason { color:var(--warning-color,var(--primary-text-color)); }
      .muted { color:var(--secondary-text-color); }
      .item { padding:6px 0; display:flex; justify-content:space-between; gap:8px; align-items:center; }
      .item + .item { border-top:1px solid var(--divider-color); }
      button { border:0; border-radius:6px; padding:5px 8px; background:var(--secondary-background-color); color:var(--primary-text-color); cursor:pointer; }
      .message { grid-column:1/-1; padding:16px; border-radius:var(--ha-card-border-radius,12px); background:var(--card-background-color); }
      .master { grid-column:1/-1; padding:18px; border-radius:var(--ha-card-border-radius,14px); background:var(--card-background-color); border:1px solid var(--divider-color); }
      .master h2 { margin:0 0 12px; font-size:1.2rem; }
      .controls { display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
      select { padding:6px; border:1px solid var(--divider-color); border-radius:6px; background:var(--card-background-color); color:var(--primary-text-color); }
      .fallback { margin-top:6px; }
      .thermostat-row { --ha-card-box-shadow:none; --ha-card-background:transparent; }
      @media (max-width:600px) { .root { grid-template-columns:1fr; gap:12px; } .zone,.master { padding:14px; } }
    `;
    this.shadowRoot.append(style);
    const root = hcEl("div", "root");
    root.dataset.view = this._config.view;
    this.shadowRoot.append(root);
    if (!this._data) {
      root.append(hcEl("div", "message", this._error || "Loading Hybrid Climate zones…"));
      return;
    }
    const entries = (this._data.entries || []).filter((entry) => !this._config.entry_id || entry.entry_id === this._config.entry_id);
    this._renderedEntries = entries;
    if (!entries.length) {
      root.append(hcEl("div", "message", this._config.entry_id ? "Hybrid Climate entry not found" : "No Hybrid Climate entries found"));
      return;
    }
    this._zoneCount = 0;
    for (const entry of entries) {
      if (this._config.view === "overview" && this._config.show_master !== false) root.append(this._master(entry));
      if (this._config.view === "pi" && entry.master?.settings) root.append(this._systemSettings(entry.master.settings));
      for (const zone of hcOrdered(entry.zones || [], this._config.zone_order)) {
        if (Array.isArray(this._config.hidden_zones) && this._config.hidden_zones.includes(zone.id)) continue;
        if (this._config.view === "pi" && !Object.keys(zone.controls?.pi || {}).length) continue;
        this._zoneCount++;
        const section = hcEl("section", "zone");
        const head = hcEl("div", "zone-head");
        head.append(hcEl("h2", "", zone.name || zone.id));
        const badge = hcEl("span", "action-badge");
        head.append(badge);
        section.append(head);
        this._refs.push(() => {
          const action = this._zoneState(zone)?.attributes?.hvac_action || zone.status?.action || "idle";
          section.dataset.action = action;
          badge.textContent = hcLabel(action);
        });
        for (const row of hcRows(this._config, zone.id)) this._row(section, zone, row);
        root.append(section);
      }
    }
    if (!this._zoneCount && this._config.view === "pi") root.append(hcEl("div", "message", "No zones use a PI controller."));
    this._refreshLive();
  }

  _master(entry) {
    const section = hcEl("section", "master");
    section.append(hcEl("h2", "", entry.master?.name || "Whole Home Climate"));
    const entityId = entry.master?.entity_id;
    if (!entityId) { section.append(hcEl("div", "muted", "Master thermostat unavailable")); return section; }
    const controls = hcEl("div", "controls");
    const mode = hcEl("select");
    mode.setAttribute("aria-label", "Master HVAC mode");
    for (const [value, label] of [["auto", "On"], ["off", "Off"]]) {
      const option = hcEl("option", "", label); option.value = value; mode.append(option);
    }
    mode.addEventListener("change", () => this._hass.callService("climate", "set_hvac_mode", { entity_id: entityId, hvac_mode: mode.value }));
    controls.append(hcEl("span", "", "System"), mode);
    const preset = hcEl("select"); preset.setAttribute("aria-label", "Whole home preset");
    for (const value of ["Home", "Away", "Sleep", "Vacation", "Boost"]) {
      const option = hcEl("option", "", value); option.value = value; preset.append(option);
    }
    preset.addEventListener("change", () => this._hass.callService("climate", "set_preset_mode", { entity_id: entityId, preset_mode: preset.value }));
    controls.append(hcEl("span", "", "Preset"), preset);
    section.append(controls);
    const info = hcEl("div", "muted"); section.append(info);
    this._refs.push(() => {
      const state = this._hass?.states[entityId];
      mode.value = state?.state === "off" ? "off" : "auto";
      preset.value = state?.attributes?.preset_mode || "Home";
      info.textContent = state ? `Outdoor ${hcTemp(state.attributes.outdoor_temperature, this._unit())} · ${hcLabel(state.attributes.hvac_action || "idle")}` : "Master thermostat unavailable";
    });
    return section;
  }

  _systemSettings(settings) {
    const section = hcEl("section", "master");
    section.append(hcEl("h2", "", "System settings"));
    const grid = hcEl("div", "metrics"); section.append(grid);
    this._metric(grid, "Never heat above (outdoor)", () => hcTemp(settings.never_heat_above, this._unit()));
    this._metric(grid, "Never cool below (outdoor)", () => hcTemp(settings.never_cool_below, this._unit()));
    this._metric(grid, "Device mutex rules", () => hcText(settings.device_mutex_count, "0"));
    return section;
  }

  _row(section, zone, row) {
    const wrapper = hcEl("div", "row");
    wrapper.append(hcEl("div", "row-title", HC_ROW_LABELS[row]));
    section.append(wrapper);
    switch (row) {
      case "status": this._status(wrapper, zone); break;
      case "thermostat": this._thermostat(wrapper, zone); break;
      case "targets": this._targets(wrapper, zone); break;
      case "lockout_reason": this._reasons(wrapper, zone); break;
      case "sensors": this._simpleStatus(wrapper, zone, "sensor_status", "Normal"); break;
      case "openings": this._simpleStatus(wrapper, zone, "opening_status", "Disabled"); break;
      case "equipment": this._equipment(wrapper, zone); break;
      case "setpoints": this._setpoints(wrapper, zone); break;
      case "pi": this._pi(wrapper, zone); break;
    }
  }
  _metric(parent, label, getter) {
    const metric = hcEl("span", "metric"); metric.append(hcEl("small", "", label));
    const value = hcEl("span"); metric.append(value); parent.append(metric);
    this._refs.push(() => { value.textContent = hcText(getter()); });
  }
  _zoneState(zone) { return this._hass?.states[zone.entity_id]; }
  _unit() { return this._hass?.config?.unit_system?.temperature === "°C" ? "C" : "F"; }
  _status(parent, zone) {
    const grid = hcEl("div", "metrics status-metrics"); parent.append(grid);
    this._metric(grid, "Current", () => hcTemp(this._zoneState(zone)?.attributes?.current_temperature, this._unit()));
    this._metric(grid, "Mode", () => hcLabel(this._zoneState(zone)?.state));
    this._metric(grid, "Action", () => hcLabel(this._zoneState(zone)?.attributes?.hvac_action || zone.status?.action));
    this._metric(grid, "Stage", () => hcLabel(this._zoneState(zone)?.attributes?.current_stage || zone.status?.stage));
    this._metric(grid, "Active devices", () => (zone.status?.active_devices || []).join(", ") || "None");
  }
  _targets(parent, zone) {
    const grid = hcEl("div", "metrics targets-metrics"); parent.append(grid);
    const setpoints = zone.controls?.setpoints || {};
    const hasHeat = Object.values(setpoints).some((mode) => mode?.heat);
    const hasCool = Object.values(setpoints).some((mode) => mode?.cool);
    if (hasHeat) this._metric(grid, "Heat", () => hcTemp(this._zoneState(zone)?.attributes?.target_temp_low ?? (!hasCool ? this._zoneState(zone)?.attributes?.temperature : null), this._unit()));
    if (hasCool) this._metric(grid, "Cool", () => hcTemp(this._zoneState(zone)?.attributes?.target_temp_high ?? (!hasHeat ? this._zoneState(zone)?.attributes?.temperature : null), this._unit()));
    if (!hasHeat && !hasCool) parent.append(hcEl("div", "muted", "Target controls unavailable"));
  }
  _reasons(parent, zone) {
    const value = hcEl("div"); parent.append(value);
    const reset = zone.outdoor_reset;
    if (reset?.heat_override_set || reset?.cool_override_set) {
      const overrides = [];
      if (reset.heat_override_set) overrides.push(`Heat outdoor limit: ${reset.never_heat_above === null ? "disabled" : hcTemp(reset.never_heat_above, this._unit())}`);
      if (reset.cool_override_set) overrides.push(`Cool outdoor limit: ${reset.never_cool_below === null ? "disabled" : hcTemp(reset.never_cool_below, this._unit())}`);
      parent.append(hcEl("div", "muted", overrides.join(" · ")));
    }
    this._refs.push(() => {
      const reasons = zone.status?.blocking_reasons || [];
      const action = this._zoneState(zone)?.attributes?.hvac_action || zone.status?.action;
      value.className = reasons.length ? "reason" : "muted";
      value.textContent = reasons.length ? reasons.map((reason) => HC_REASON_LABELS[reason] || hcLabel(reason)).join(" · ")
        : action === "heating" || action === "cooling" ? "Zone is running" : "No active lockout reported";
    });
  }
  _simpleStatus(parent, zone, key, fallback) {
    const value = hcEl("div"); parent.append(value);
    this._refs.push(() => {
      const live = this._zoneState(zone)?.attributes?.[key];
      const status = live ?? zone.status?.[key];
      value.textContent = hcLabel(status || fallback);
    });
  }
  _thermostat(parent, zone) {
    if (!zone.entity_id) { parent.append(hcEl("div", "muted", "Zone thermostat unavailable")); return; }
    parent.classList.add("thermostat-row");
    this._haCard(parent, { type: "thermostat", entity: zone.entity_id });
  }
  _haCard(parent, config) {
    const fallback = hcEl("div", "muted fallback", "Loading controls…"); parent.append(fallback);
    const token = this._structureKey;
    Promise.resolve(window.loadCardHelpers?.()).then((helpers) => {
      if (!helpers || !this.isConnected || token !== this._structureKey || !fallback.isConnected) {
        if (fallback.isConnected) fallback.textContent = "Home Assistant card helpers unavailable";
        return;
      }
      const card = helpers.createCardElement(config);
      card.hass = this._hass;
      fallback.replaceWith(card);
      this._cards.push(card);
    }).catch(() => { if (fallback.isConnected) fallback.textContent = "Could not load controls"; });
  }
  _setpoints(parent, zone) {
    const controls = zone.controls?.setpoints || {};
    const entities = [];
    for (const mode of ["default", "away", "sleep", "vacation", "occupied", "unoccupied"]) {
      for (const direction of ["heat", "cool"]) {
        const entity = controls[mode]?.[direction];
        if (entity) entities.push({ entity, name: `${hcLabel(mode)} ${hcLabel(direction)}` });
      }
    }
    if (!entities.length) { parent.append(hcEl("div", "muted", "No live setpoint controls")); return; }
    this._haCard(parent, { type: "entities", entities });
  }
  _pi(parent, zone) {
    const controls = zone.controls?.pi || {};
    if (!Object.keys(controls).length) { parent.append(hcEl("div", "muted", "PI is not configured for this zone")); return; }
    const grid = hcEl("div", "metrics"); parent.append(grid);
    for (const [label, key] of [["Offset", "regulation_offset"], ["Accumulated error", "accumulated_error"], ["Regulated setpoint", "regulated_setpoint"]]) {
      this._metric(grid, label, () => {
        const value = this._zoneState(zone)?.attributes?.[key] ?? zone.status?.[key];
        return key === "accumulated_error" ? hcText(value) : hcTemp(value, this._unit());
      });
    }
    const entities = [["kp", "Kp"], ["ki", "Ki"], ["k_ext", "K_ext"], ["offset_max", "Maximum offset"], ["balance_point", "Balance point"]]
      .filter(([key]) => controls[key]).map(([key, name]) => ({ entity: controls[key], name }));
    if (entities.length) this._haCard(parent, { type: "entities", entities });
  }
  _equipment(parent, zone) {
    if (!zone.devices?.length) { parent.append(hcEl("div", "muted", "No equipment configured")); return; }
    for (const device of zone.devices) {
      const item = hcEl("div", "item");
      item.append(hcEl("span", "", device.name || device.id || device.entity_id));
      const value = hcEl("span", "muted"); item.append(value); parent.append(item);
      this._refs.push(() => {
        const state = this._hass?.states[device.entity_id];
        value.textContent = !device.entity_id || !state ? "Unavailable" : `${hcLabel(state.state)}${state.attributes?.hvac_action ? ` · ${hcLabel(state.attributes.hvac_action)}` : ""}`;
      });
      if (device.entity_id) {
        const button = hcEl("button", "", "Details"); button.type = "button";
        button.addEventListener("click", () => this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: device.entity_id } })));
        item.append(button);
      }
    }
  }
  _refreshLive() {
    if (!this._hass) return;
    for (const update of this._refs) update();
    for (const card of this._cards) card.hass = this._hass;
  }
}

class HybridClimateCardEditor extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: "open" }); }
  setConfig(config) { this._config = { ...config }; this._render(); }
  set hass(hass) { this._hass = hass; if (!this._loaded && hass) this._load(); }
  async _load() {
    if (this._loading) return;
    this._loading = true;
    try { this._data = await this._hass.callWS({ type: "hybrid_climate/dashboard_info" }); this._loaded = true; this._render(); }
    catch { this._loading = false; }
  }
  _change(changes) { this._config = { ...this._config, ...changes }; hcFireConfig(this, this._config); this._render(); }
  _move(key, list, index, direction) {
    const reordered = [...list];
    const next = index + direction;
    if (next < 0 || next >= reordered.length) return;
    [reordered[index], reordered[next]] = [reordered[next], reordered[index]];
    this._change({ [key]: reordered });
  }
  _render() {
    if (!this._config) return;
    this.shadowRoot.replaceChildren();
    const style = hcEl("style");
    style.textContent = `:host{display:block;padding:12px}section{margin:12px 0}label{display:block;font-weight:600;margin-bottom:6px}select,button{padding:6px;border:1px solid var(--divider-color);border-radius:5px;background:var(--card-background-color);color:var(--primary-text-color)}.item{display:flex;align-items:center;gap:6px;padding:4px}.item span{flex:1}`;
    this.shadowRoot.append(style);
    const viewSection = hcEl("section"); viewSection.append(hcEl("label", "", "View"));
    const view = hcEl("select"); for (const name of HC_VIEWS) { const option = hcEl("option", "", hcLabel(name)); option.value = name; view.append(option); }
    view.value = this._config.view || "overview";
    view.addEventListener("change", () => this._change({ view: view.value, rows: undefined }));
    viewSection.append(view); this.shadowRoot.append(viewSection);
    const zones = (this._data?.entries || []).filter((entry) => !this._config.entry_id || entry.entry_id === this._config.entry_id)
      .flatMap((entry) => entry.zones || []);
    if (zones.length) {
      const section = hcEl("section"); section.append(hcEl("label", "", "Zone order (new zones append automatically)"));
      const ordered = hcOrdered(zones, this._config.zone_order);
      ordered.forEach((zone, index) => {
        const item = hcEl("div", "item"); item.append(hcEl("span", "", zone.name || zone.id));
        for (const [label, direction] of [["↑", -1], ["↓", 1]]) {
          const button = hcEl("button", "", label); button.type = "button"; button.disabled = index + direction < 0 || index + direction >= ordered.length;
          button.addEventListener("click", () => this._move("zone_order", ordered.map((z) => z.id), index, direction)); item.append(button);
        }
        section.append(item);
      }); this.shadowRoot.append(section);
    }
    const section = hcEl("section"); section.append(hcEl("label", "", "Row order"));
    const rows = this._config.rows || HC_DEFAULT_ROWS[this._config.view || "overview"];
    rows.forEach((row, index) => {
      const item = hcEl("div", "item"); item.append(hcEl("span", "", HC_ROW_LABELS[row] || row));
      for (const [label, direction] of [["↑", -1], ["↓", 1]]) {
        const button = hcEl("button", "", label); button.type = "button"; button.disabled = index + direction < 0 || index + direction >= rows.length;
        button.addEventListener("click", () => this._move("rows", rows, index, direction)); item.append(button);
      }
      const remove = hcEl("button", "", "×"); remove.type = "button"; remove.setAttribute("aria-label", `Remove ${HC_ROW_LABELS[row]}`);
      remove.addEventListener("click", () => this._change({ rows: rows.filter((candidate) => candidate !== row) })); item.append(remove); section.append(item);
    });
    const add = hcEl("select"); add.setAttribute("aria-label", "Add row");
    const prompt = hcEl("option", "", "Add row…"); prompt.value = ""; add.append(prompt);
    for (const row of HC_ROWS.filter((candidate) => !rows.includes(candidate))) { const option = hcEl("option", "", HC_ROW_LABELS[row]); option.value = row; add.append(option); }
    add.addEventListener("change", () => { if (add.value) this._change({ rows: [...rows, add.value] }); });
    section.append(add); this.shadowRoot.append(section);
  }
}

if (!customElements.get("hybrid-climate-card")) customElements.define("hybrid-climate-card", HybridClimateCard);
if (!customElements.get("hybrid-climate-card-editor")) customElements.define("hybrid-climate-card-editor", HybridClimateCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "hybrid-climate-card")) {
  window.customCards.push({ type: "hybrid-climate-card", name: "Hybrid Climate", description: "Live zones and controls with configurable ordering" });
}
