/**
 * Irrigation Sequencer Card
 * Graphical Lovelace card for the "Irrigation Sequencer" integration.
 * No build dependencies - a plain Web Component (Shadow DOM).
 * UI text follows the Home Assistant language (hass.language), falling
 * back to English.
 */

const DOMAIN = "irrigation_sequencer";

const TRANSLATIONS = {
  en: {
    status: {
      idle: "Idle",
      running: "Irrigating",
      paused_between_zones: "Pause between zones",
      winter_mode: "Winter mode active",
      rain_pause: "Rain pause active",
    },
    pauseBetweenZones: "Pause between zones",
    nightStart: "Night start",
    winterMode: "Winter mode",
    rainPause: "Rain pause",
    rainPauseClear: (until) => `until ${until} · clear`,
    days: "days",
    day: "day",
    weatherAdjustment: "Weather-based duration",
    weatherEntity: "Weather entity",
    weatherEntityNone: "- none -",
    referenceTemp: "Reference temp. (factor 1.0)",
    hotTemp: "Hot temp.",
    hotFactor: "Factor at hot temp.",
    currentFactor: "Current factor",
    start: "Start now",
    stop: "Stop",
    nextRun: "Next run",
    remainingTotal: (t) => `${t} remaining (total)`,
    remainingZone: (t) => `${t} remaining`,
    dragHandle: "Drag to reorder",
    notFound: (entity) => `Entity ${entity} not found.`,
    pickEntity: "Irrigation Sequencer status entity",
    pickEntityPlaceholder: "- select -",
    title: "Title (optional)",
  },
  de: {
    status: {
      idle: "Bereit",
      running: "Bewässerung läuft",
      paused_between_zones: "Pause zwischen Zonen",
      winter_mode: "Wintermodus aktiv",
      rain_pause: "Regen-Pause aktiv",
    },
    pauseBetweenZones: "Pause zwischen Zonen",
    nightStart: "Nachtstart",
    winterMode: "Wintermodus",
    rainPause: "Regen-Pause",
    rainPauseClear: (until) => `bis ${until} · aufheben`,
    days: "Tage",
    day: "Tag",
    weatherAdjustment: "Wetterbasierte Dauer",
    weatherEntity: "Wetter-Entität",
    weatherEntityNone: "- keine -",
    referenceTemp: "Referenztemp. (Faktor 1.0)",
    hotTemp: "Hitzetemp.",
    hotFactor: "Faktor bei Hitzetemp.",
    currentFactor: "Aktueller Faktor",
    start: "Jetzt starten",
    stop: "Stoppen",
    nextRun: "Nächster Lauf",
    remainingTotal: (t) => `noch ${t} gesamt`,
    remainingZone: (t) => `noch ${t}`,
    dragHandle: "Ziehen zum Umsortieren",
    notFound: (entity) => `Entität ${entity} nicht gefunden.`,
    pickEntity: "Irrigation-Sequencer-Status-Entität",
    pickEntityPlaceholder: "- auswählen -",
    title: "Titel (optional)",
  },
};

function getTranslations(hass) {
  const lang = (hass?.language || hass?.locale?.language || "en").split("-")[0];
  return TRANSLATIONS[lang] || TRANSLATIONS.en;
}

const STATUS_COLORS = {
  idle: "var(--disabled-text-color, #9e9e9e)",
  running: "var(--success-color, #4caf50)",
  paused_between_zones: "var(--warning-color, #ff9800)",
  winter_mode: "var(--info-color, #03a9f4)",
  rain_pause: "var(--info-color, #03a9f4)",
};

function formatSeconds(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds || 0));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")} min`;
}

function friendlyName(hass, entityId) {
  const state = hass.states[entityId];
  return state?.attributes?.friendly_name || entityId;
}

class IrrigationSequencerCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("irrigation-sequencer-card-editor");
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && hass.states[id].attributes?.zones !== undefined
    );
    return { entity: entity || "", title: "Irrigation" };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please select an Irrigation Sequencer status entity (entity).");
    }
    this._config = config;
    this._dragIndex = null;
    this._suppressRender = false;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._suppressRender) {
      this._render();
    }
  }

  getCardSize() {
    const zones = this._entityState()?.attributes?.zones?.length || 4;
    return 4 + Math.ceil(zones / 2);
  }

  _entityState() {
    return this._hass?.states[this._config.entity];
  }

  _callService(service, extra) {
    const stateObj = this._entityState();
    if (!stateObj) return;
    const entryId = stateObj.attributes.entry_id;
    this._hass.callService(DOMAIN, service, { entry_id: entryId, ...extra });
  }

  _render() {
    const t = getTranslations(this._hass);
    const stateObj = this._entityState();
    if (!stateObj) {
      this.shadowRoot.innerHTML = `<ha-card><div class="not-found">${t.notFound(
        this._config.entity
      )}</div></ha-card>`;
      return;
    }

    const attrs = stateObj.attributes;
    const zones = [...(attrs.zones || [])].sort((a, b) => a.position - b.position);
    const status = stateObj.state;
    const title = this._config.title || "Irrigation";

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card>
        <div class="header">
          <div class="title">${title}</div>
          <div class="status-pill" style="--status-color: ${STATUS_COLORS[status] || STATUS_COLORS.idle}">
            <span class="dot"></span>${t.status[status] || status}
          </div>
        </div>

        ${this._renderProgress(attrs, zones, status, t)}

        <div class="zones">
          ${zones.map((zone, index) => this._renderZone(zone, index, attrs, status, t)).join("")}
        </div>

        <div class="settings">
          <div class="setting-row">
            <ha-icon icon="mdi:timer-sand"></ha-icon>
            <label>${t.pauseBetweenZones}</label>
            <input type="range" min="0" max="900" step="10" value="${attrs.pause_between_zones_seconds}" id="pause-range" />
            <span class="value">${formatSeconds(attrs.pause_between_zones_seconds)}</span>
          </div>
          <div class="setting-row">
            <ha-icon icon="mdi:weather-night"></ha-icon>
            <label>${t.nightStart}</label>
            <input type="time" id="start-time" value="${(attrs.start_time || "05:00:00").slice(0, 5)}" step="60" />
          </div>
          <div class="setting-row">
            <ha-icon icon="mdi:snowflake"></ha-icon>
            <label>${t.winterMode}</label>
            <label class="switch">
              <input type="checkbox" id="winter-toggle" ${attrs.winter_mode ? "checked" : ""} />
              <span class="slider"></span>
            </label>
          </div>
          <div class="setting-row rain-row">
            <ha-icon icon="mdi:weather-rainy"></ha-icon>
            <label>${t.rainPause}</label>
            <div class="rain-buttons">
              ${[1, 3, 7, 14]
                .map(
                  (d) => `<button class="chip" data-days="${d}">${d} ${d > 1 ? t.days : t.day}</button>`
                )
                .join("")}
              ${
                attrs.rain_pause_until
                  ? `<button class="chip chip-clear" id="clear-rain">${t.rainPauseClear(attrs.rain_pause_until)}</button>`
                  : ""
              }
            </div>
          </div>

          ${this._renderWeatherSection(attrs, t)}
        </div>

        <div class="actions">
          <button class="action-btn stop" id="stop-btn" ${status === "idle" ? "disabled" : ""}>
            <ha-icon icon="mdi:stop"></ha-icon> ${t.stop}
          </button>
          <button class="action-btn start" id="start-btn" ${status === "running" || status === "paused_between_zones" ? "disabled" : ""}>
            <ha-icon icon="mdi:play"></ha-icon> ${t.start}
          </button>
        </div>
        ${attrs.next_run ? `<div class="next-run">${t.nextRun}: ${new Date(attrs.next_run).toLocaleString(this._hass.language)}</div>` : ""}
      </ha-card>
    `;

    this._attachListeners(zones, t);
  }

  _renderProgress(attrs, zones, status, t) {
    if (status !== "running" && status !== "paused_between_zones") return "";
    const factor = attrs.weather_current_factor || 1;
    const totalPlanned =
      zones.reduce((sum, z) => sum + Math.round(z.duration_minutes * 60 * factor), 0) +
      attrs.pause_between_zones_seconds * Math.max(0, zones.length - 1);
    const remaining = attrs.seconds_remaining_total || 0;
    const pct = totalPlanned > 0 ? Math.max(0, Math.min(100, 100 - (remaining / totalPlanned) * 100)) : 0;
    return `
      <div class="progress-wrap">
        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
        <div class="progress-label">${t.remainingTotal(formatSeconds(remaining))}</div>
      </div>
    `;
  }

  _renderZone(zone, index, attrs, status, t) {
    const isActive = attrs.current_zone_index === index && status === "running";
    const name = this._hass ? friendlyName(this._hass, zone.entity_id) : zone.entity_id;
    const remaining = isActive ? attrs.seconds_remaining_zone : null;
    return `
      <div class="zone ${isActive ? "active" : ""}" draggable="true" data-index="${index}" data-entity="${zone.entity_id}">
        <div class="zone-drag-handle" title="${t.dragHandle}">
          <ha-icon icon="mdi:drag-vertical"></ha-icon>
        </div>
        <div class="zone-badge">${index + 1}</div>
        <div class="zone-icon ${isActive ? "spraying" : ""}">
          <ha-icon icon="mdi:sprinkler${isActive ? "-variant" : ""}"></ha-icon>
        </div>
        <div class="zone-info">
          <div class="zone-name">${name}</div>
          ${
            isActive
              ? `<div class="zone-remaining">${t.remainingZone(formatSeconds(remaining))}</div>`
              : `<div class="zone-duration-row">
                  <input type="range" min="1" max="60" value="${zone.duration_minutes}" class="zone-duration" data-entity="${zone.entity_id}" />
                  <span class="value">${zone.duration_minutes} min</span>
                </div>`
          }
        </div>
      </div>
    `;
  }

  _renderWeatherSection(attrs, t) {
    const weatherEntities = this._hass
      ? Object.keys(this._hass.states).filter((id) => id.startsWith("weather."))
      : [];
    const enabled = !!attrs.weather_adjustment_enabled;
    const currentFactorLabel =
      enabled && attrs.weather_current_temp != null
        ? `${t.currentFactor}: ×${attrs.weather_current_factor.toFixed(2)} (${attrs.weather_current_temp}°)`
        : "";

    return `
      <div class="weather-section">
        <div class="setting-row">
          <ha-icon icon="mdi:weather-partly-cloudy"></ha-icon>
          <label>${t.weatherAdjustment}</label>
          <label class="switch">
            <input type="checkbox" id="weather-toggle" ${enabled ? "checked" : ""} />
            <span class="slider"></span>
          </label>
        </div>
        ${
          enabled
            ? `
          <div class="setting-row">
            <ha-icon icon="mdi:cloud-outline"></ha-icon>
            <label>${t.weatherEntity}</label>
            <select id="weather-entity">
              <option value="">${t.weatherEntityNone}</option>
              ${weatherEntities
                .map(
                  (id) =>
                    `<option value="${id}" ${id === attrs.weather_entity ? "selected" : ""}>${friendlyName(
                      this._hass,
                      id
                    )}</option>`
                )
                .join("")}
            </select>
          </div>
          <div class="setting-row">
            <ha-icon icon="mdi:thermometer-low"></ha-icon>
            <label>${t.referenceTemp}</label>
            <input type="number" id="weather-reference-temp" value="${attrs.weather_reference_temp}" step="0.5" />
          </div>
          <div class="setting-row">
            <ha-icon icon="mdi:thermometer-high"></ha-icon>
            <label>${t.hotTemp}</label>
            <input type="number" id="weather-hot-temp" value="${attrs.weather_hot_temp}" step="0.5" />
          </div>
          <div class="setting-row">
            <ha-icon icon="mdi:water-percent"></ha-icon>
            <label>${t.hotFactor}</label>
            <input type="number" id="weather-hot-factor" value="${attrs.weather_hot_factor}" step="0.1" min="0.1" max="3" />
          </div>
          ${currentFactorLabel ? `<div class="weather-current">${currentFactorLabel}</div>` : ""}
          `
            : ""
        }
      </div>
    `;
  }

  _attachListeners(zones, t) {
    const root = this.shadowRoot;

    root.getElementById("start-btn")?.addEventListener("click", () => this._callService("start_now"));
    root.getElementById("stop-btn")?.addEventListener("click", () => this._callService("stop"));

    root.getElementById("winter-toggle")?.addEventListener("change", (e) => {
      const entryId = this._entityState().attributes.entry_id;
      this._hass.callService("switch", e.target.checked ? "turn_on" : "turn_off", {
        entity_id: this._switchEntityId(entryId, "winter_mode"),
      });
    });

    root.getElementById("start-time")?.addEventListener("change", (e) => {
      this._callService("set_start_time", { start_time: `${e.target.value}:00` });
    });

    const pauseRange = root.getElementById("pause-range");
    pauseRange?.addEventListener("input", (e) => {
      pauseRange.nextElementSibling.textContent = formatSeconds(e.target.value);
    });
    pauseRange?.addEventListener("change", (e) => {
      this._callService("set_pause_between_zones", { seconds: parseInt(e.target.value, 10) });
    });

    root.querySelectorAll(".chip[data-days]").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._callService("set_rain_pause", { days: parseInt(btn.dataset.days, 10) });
      });
    });
    root.getElementById("clear-rain")?.addEventListener("click", () => {
      this._callService("clear_rain_pause", {});
    });

    root.querySelectorAll(".zone-duration").forEach((input) => {
      input.addEventListener("input", (e) => {
        this._suppressRender = true;
        e.target.nextElementSibling.textContent = `${e.target.value} min`;
      });
      input.addEventListener("change", (e) => {
        this._suppressRender = false;
        this._callService("set_zone_duration", {
          entity_id: e.target.dataset.entity,
          minutes: parseInt(e.target.value, 10),
        });
      });
    });

    this._attachWeatherListeners(root);
    this._attachDragAndDrop(root, zones);
  }

  _attachWeatherListeners(root) {
    const attrs = this._entityState().attributes;

    const readWeatherForm = (overrides = {}) => ({
      enabled: overrides.enabled ?? attrs.weather_adjustment_enabled,
      weather_entity:
        overrides.weather_entity !== undefined
          ? overrides.weather_entity || null
          : attrs.weather_entity,
      reference_temp: overrides.reference_temp ?? attrs.weather_reference_temp,
      hot_temp: overrides.hot_temp ?? attrs.weather_hot_temp,
      hot_factor: overrides.hot_factor ?? attrs.weather_hot_factor,
    });

    root.getElementById("weather-toggle")?.addEventListener("change", (e) => {
      this._callService("set_weather_adjustment", readWeatherForm({ enabled: e.target.checked }));
    });
    root.getElementById("weather-entity")?.addEventListener("change", (e) => {
      this._callService(
        "set_weather_adjustment",
        readWeatherForm({ weather_entity: e.target.value })
      );
    });
    root.getElementById("weather-reference-temp")?.addEventListener("change", (e) => {
      this._callService(
        "set_weather_adjustment",
        readWeatherForm({ reference_temp: parseFloat(e.target.value) })
      );
    });
    root.getElementById("weather-hot-temp")?.addEventListener("change", (e) => {
      this._callService(
        "set_weather_adjustment",
        readWeatherForm({ hot_temp: parseFloat(e.target.value) })
      );
    });
    root.getElementById("weather-hot-factor")?.addEventListener("change", (e) => {
      this._callService(
        "set_weather_adjustment",
        readWeatherForm({ hot_factor: parseFloat(e.target.value) })
      );
    });
  }

  _switchEntityId(entryId, translationKey) {
    return Object.keys(this._hass.states).find(
      (id) =>
        id.startsWith("switch.") &&
        this._hass.states[id].attributes?.entry_id === entryId &&
        id.includes(translationKey)
    );
  }

  _attachDragAndDrop(root, zones) {
    const zoneEls = Array.from(root.querySelectorAll(".zone"));
    zoneEls.forEach((el) => {
      el.addEventListener("dragstart", (e) => {
        this._dragIndex = parseInt(el.dataset.index, 10);
        e.dataTransfer.effectAllowed = "move";
      });
      el.addEventListener("dragover", (e) => {
        e.preventDefault();
        el.classList.add("drag-over");
      });
      el.addEventListener("dragleave", () => el.classList.remove("drag-over"));
      el.addEventListener("drop", (e) => {
        e.preventDefault();
        el.classList.remove("drag-over");
        const targetIndex = parseInt(el.dataset.index, 10);
        if (this._dragIndex === null || this._dragIndex === targetIndex) return;

        const ordered = [...zones];
        const [moved] = ordered.splice(this._dragIndex, 1);
        ordered.splice(targetIndex, 0, moved);
        this._callService("set_zone_order", { zones: ordered.map((z) => z.entity_id) });
        this._dragIndex = null;
      });
    });
  }

  _styles() {
    return `
      ha-card { padding: 16px; }
      .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
      .title { font-size: 1.2em; font-weight: 500; }
      .status-pill { display: flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px;
        background: color-mix(in srgb, var(--status-color) 15%, transparent); color: var(--status-color);
        font-size: 0.85em; font-weight: 500; }
      .status-pill .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--status-color); }

      .progress-wrap { margin-bottom: 14px; }
      .progress-bar { height: 8px; border-radius: 4px; background: var(--divider-color, #444); overflow: hidden; }
      .progress-fill { height: 100%; background: var(--success-color, #4caf50); transition: width 1s linear; }
      .progress-label { font-size: 0.8em; color: var(--secondary-text-color); margin-top: 4px; }

      .zones { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
      .zone { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 10px;
        background: var(--secondary-background-color, rgba(127,127,127,0.08)); transition: background 0.2s, transform 0.15s; }
      .zone.active { background: color-mix(in srgb, var(--success-color, #4caf50) 18%, transparent); }
      .zone.drag-over { transform: scale(1.02); outline: 2px dashed var(--primary-color); }
      .zone-drag-handle { cursor: grab; color: var(--secondary-text-color); }
      .zone-badge { width: 22px; height: 22px; border-radius: 50%; background: var(--primary-color); color: white;
        display: flex; align-items: center; justify-content: center; font-size: 0.75em; flex-shrink: 0; }
      .zone-icon { color: var(--secondary-text-color); }
      .zone-icon.spraying { color: var(--success-color, #4caf50); animation: pulse 1s ease-in-out infinite; }
      @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.6; transform: scale(1.15); } }
      .zone-info { flex: 1; min-width: 0; }
      .zone-name { font-weight: 500; font-size: 0.95em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .zone-remaining { font-size: 0.8em; color: var(--success-color, #4caf50); }
      .zone-duration-row { display: flex; align-items: center; gap: 8px; }
      .zone-duration-row input[type="range"] { flex: 1; }
      .zone-duration-row .value { font-size: 0.8em; color: var(--secondary-text-color); min-width: 46px; text-align: right; }

      .settings { display: flex; flex-direction: column; gap: 10px; padding-top: 8px;
        border-top: 1px solid var(--divider-color, rgba(127,127,127,0.2)); margin-bottom: 12px; }
      .setting-row { display: flex; align-items: center; gap: 10px; font-size: 0.9em; }
      .setting-row label { flex: 0 0 auto; min-width: 150px; color: var(--secondary-text-color); }
      .setting-row input[type="range"] { flex: 1; }
      .setting-row input[type="number"], .setting-row select { flex: 1; padding: 4px 6px; border-radius: 6px;
        border: 1px solid var(--divider-color, #555); background: var(--card-background-color); color: var(--primary-text-color); }
      .setting-row .value { min-width: 60px; text-align: right; font-size: 0.85em; }
      .rain-row { align-items: flex-start; }
      .rain-buttons { display: flex; flex-wrap: wrap; gap: 6px; }
      .chip { border: 1px solid var(--divider-color, #555); background: transparent; color: var(--primary-text-color);
        border-radius: 999px; padding: 4px 10px; font-size: 0.8em; cursor: pointer; }
      .chip:hover { background: var(--secondary-background-color); }
      .chip-clear { border-color: var(--warning-color, #ff9800); color: var(--warning-color, #ff9800); }

      .weather-section { display: flex; flex-direction: column; gap: 10px; padding-top: 8px;
        border-top: 1px dashed var(--divider-color, rgba(127,127,127,0.2)); }
      .weather-current { font-size: 0.8em; color: var(--success-color, #4caf50); padding-left: 34px; }

      .switch { position: relative; display: inline-block; width: 40px; height: 22px; flex-shrink: 0; }
      .switch input { opacity: 0; width: 0; height: 0; }
      .slider { position: absolute; cursor: pointer; inset: 0; background: var(--disabled-text-color, #888);
        border-radius: 22px; transition: 0.2s; }
      .slider::before { content: ""; position: absolute; height: 16px; width: 16px; left: 3px; bottom: 3px;
        background: white; border-radius: 50%; transition: 0.2s; }
      .switch input:checked + .slider { background: var(--info-color, #03a9f4); }
      .switch input:checked + .slider::before { transform: translateX(18px); }

      .actions { display: flex; gap: 10px; }
      .action-btn { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px;
        padding: 10px; border-radius: 10px; border: none; font-weight: 500; cursor: pointer; }
      .action-btn.start { background: var(--success-color, #4caf50); color: white; }
      .action-btn.stop { background: var(--error-color, #db4437); color: white; }
      .action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
      .next-run { margin-top: 10px; font-size: 0.8em; color: var(--secondary-text-color); text-align: center; }
      .not-found { padding: 16px; color: var(--error-color); }
    `;
  }
}

class IrrigationSequencerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const t = getTranslations(this._hass);
    const candidates = Object.keys(this._hass?.states || {}).filter(
      (id) => id.startsWith("sensor.") && this._hass.states[id].attributes?.zones !== undefined
    );
    this.shadowRoot.innerHTML = `
      <style>
        .row { display: flex; flex-direction: column; gap: 4px; padding: 12px; }
        label { font-size: 0.9em; color: var(--secondary-text-color); }
        select, input { padding: 8px; border-radius: 6px; border: 1px solid var(--divider-color, #555); }
      </style>
      <div class="row">
        <label>${t.pickEntity}</label>
        <select id="entity">
          <option value="">${t.pickEntityPlaceholder}</option>
          ${candidates
            .map(
              (id) =>
                `<option value="${id}" ${id === this._config?.entity ? "selected" : ""}>${friendlyName(
                  this._hass,
                  id
                )}</option>`
            )
            .join("")}
        </select>
      </div>
      <div class="row">
        <label>${t.title}</label>
        <input id="title" type="text" value="${this._config?.title || ""}" />
      </div>
    `;
    this.shadowRoot.getElementById("entity").addEventListener("change", (e) =>
      this._updateConfig({ entity: e.target.value })
    );
    this.shadowRoot.getElementById("title").addEventListener("change", (e) =>
      this._updateConfig({ title: e.target.value })
    );
  }

  _updateConfig(partial) {
    this._config = { ...this._config, ...partial };
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config } }));
  }
}

customElements.define("irrigation-sequencer-card", IrrigationSequencerCard);
customElements.define("irrigation-sequencer-card-editor", IrrigationSequencerCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "irrigation-sequencer-card",
  name: "Irrigation Sequencer Card",
  description: "Graphical control for the Irrigation Sequencer irrigation sequence.",
});
