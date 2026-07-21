/**
 * Irrigation Sequencer cards
 * Two graphical Lovelace cards for the "Irrigation Sequencer" integration,
 * styled after Home Assistant's native Tile cards:
 *   - irrigation-sequencer-status-card: read-only status overview
 *   - irrigation-sequencer-settings-card: all configuration controls
 * No build dependencies - plain Web Components (Shadow DOM).
 * UI text follows the Home Assistant language (hass.language), falling
 * back to English.
 */

const DOMAIN = "irrigation_sequencer";

// Plain script resources (no build step) are easy for browsers/mobile to
// cache indefinitely across updates, with no visible sign anything is
// stale - logging the version on load gives a quick way to check, in the
// browser console, whether an update actually took effect versus just
// looking "the same" as before. Keep this in step with manifest.json's
// "version" on every release.
const CARD_VERSION = "0.10.0";
// eslint-disable-next-line no-console
console.info(
  `%c IRRIGATION-SEQUENCER-CARD %c v${CARD_VERSION} `,
  "color: white; background: #4caf50; font-weight: 700;",
  "color: #4caf50; background: transparent; font-weight: 700;"
);

const TRANSLATIONS = {
  en: {
    status: {
      idle: "Idle",
      running: "Irrigating",
      paused_between_zones: "Pause between zones",
      winter_mode: "Winter mode active",
      rain_pause: "Rain pause active",
    },
    statusCardTitle: "Irrigation",
    settingsCardTitle: "Irrigation settings",
    zonesLabel: (n) => `${n} zones`,
    pauseBetweenZones: "Pause between zones",
    nightStart: "Automatic start",
    addTime: "Add time",
    startTimesOverlap: (a, b, minutes) =>
      `${a} and ${b} are too close together (a full run currently takes about ${minutes} min) - they would overlap. Not saved.`,
    winterMode: "Winter mode",
    rainPause: "Rain pause",
    rainPauseClear: (until) => `until ${until} · clear`,
    rainPauseOff: "Off",
    days: "days",
    day: "day",
    weatherAdjustment: "Weather-based duration",
    weatherEntity: "Weather entity",
    weatherEntityNone: "- none -",
    notifyTarget: "Notify on completion",
    notifyNone: "- none -",
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
    zoneNamePlaceholder: "Zone name",
    zones: "Zones",
    layout: "Layout",
    layoutVertical: "Vertical (tall)",
    layoutHorizontal: "Horizontal (wide)",
    forecastHigh: "Today's forecast high",
    schedule: "Schedule",
  },
  de: {
    status: {
      idle: "Bereit",
      running: "Bewässerung läuft",
      paused_between_zones: "Pause zwischen Zonen",
      winter_mode: "Wintermodus aktiv",
      rain_pause: "Regen-Pause aktiv",
    },
    statusCardTitle: "Bewässerung",
    settingsCardTitle: "Bewässerungseinstellungen",
    zonesLabel: (n) => `${n} Zonen`,
    pauseBetweenZones: "Pause zwischen Zonen",
    nightStart: "Automatischer Start",
    addTime: "Zeit hinzufügen",
    startTimesOverlap: (a, b, minutes) =>
      `${a} und ${b} liegen zu nah beieinander (ein Durchlauf dauert aktuell ca. ${minutes} min) - sie würden sich überschneiden. Nicht gespeichert.`,
    winterMode: "Wintermodus",
    rainPause: "Regen-Pause",
    rainPauseClear: (until) => `bis ${until} · aufheben`,
    rainPauseOff: "Aus",
    days: "Tage",
    day: "Tag",
    weatherAdjustment: "Wetterbasierte Dauer",
    weatherEntity: "Wetter-Entität",
    weatherEntityNone: "- keine -",
    notifyTarget: "Benachrichtigung nach Abschluss",
    notifyNone: "- keine -",
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
    zoneNamePlaceholder: "Zonen-Name",
    zones: "Zonen",
    layout: "Layout",
    layoutVertical: "Vertikal (hoch)",
    layoutHorizontal: "Horizontal (breit)",
    forecastHigh: "Tageshöchsttemperatur (Prognose)",
    schedule: "Zeitplan",
  },
};

function resolveLanguage(hass) {
  // hass.language was the original field; newer frontends moved language
  // to hass.locale.language and may drop the old alias entirely. Falling
  // back to the <html lang="..."> attribute HA sets on the top-level page
  // covers that regardless of which (if either) hass field still exists.
  return (
    hass?.locale?.language ||
    hass?.language ||
    hass?.selectedLanguage ||
    document?.documentElement?.lang ||
    "en"
  );
}

function getTranslations(hass) {
  const lang = resolveLanguage(hass).split("-")[0];
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

/** Rounds a stored value to the nearest multiple of a slider's step size.
 * A range input's own snap-while-dragging behavior always lands on a clean
 * multiple of `step` from `min`, but a *stored* value can predate a step
 * change (e.g. seconds-granularity data from before pause-between-zones
 * switched to whole-minute steps) or otherwise not be step-aligned. Some
 * browsers/WebViews then snap relative to that already-off-grid value
 * instead of to min when the user next drags it, producing odd results
 * (e.g. dragging down two 60s steps from a stored 170 landing on 50
 * instead of 60) - rendering an always-aligned value sidesteps that. */
function roundToStep(value, step) {
  return Math.round((value || 0) / step) * step;
}

function friendlyName(hass, entityId) {
  const state = hass.states[entityId];
  return state?.attributes?.friendly_name || entityId;
}

function zoneDisplayName(hass, zone) {
  return zone.name?.trim() ? zone.name : friendlyName(hass, zone.entity_id);
}

/** Turns a notify.mobile_app_* service name into a readable label, e.g.
 * "mobile_app_pixel_8" -> "pixel 8". */
function notifyTargetLabel(serviceName) {
  return serviceName.replace(/^mobile_app_/, "").replace(/_/g, " ");
}

const MIN_START_TIMES = 1;
const MAX_START_TIMES = 3;

const MIN_WEATHER_FACTOR = 0.1;
const MAX_WEATHER_FACTOR = 3.0;

function linearFactor(temp, referenceTemp, hotTemp, hotFactor) {
  const span = hotTemp - referenceTemp;
  if (!span) return 1.0;
  const factor = 1.0 + ((temp - referenceTemp) * (hotFactor - 1.0)) / span;
  return Math.max(MIN_WEATHER_FACTOR, Math.min(MAX_WEATHER_FACTOR, factor));
}

const FORECAST_CACHE_TTL_MS = 10 * 60 * 1000;

/** Forecast high for today, from the weather entity's legacy `forecast`
 * state attribute. Modern weather integrations (e.g. Met.no, DWD) dropped
 * this attribute in favor of the `weather.get_forecasts` action, so this is
 * only a fast synchronous path for integrations that still expose it. */
function legacyForecastHigh(hass, weatherEntityId) {
  const state = weatherEntityId ? hass.states[weatherEntityId] : null;
  const forecast = state?.attributes?.forecast;
  if (!Array.isArray(forecast) || !forecast.length) return null;
  const temp = forecast[0]?.temperature;
  return typeof temp === "number" ? temp : null;
}

/** Shared base: config, hass, service calls, entity lookup. */
class IrrigationSequencerBaseCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please select an Irrigation Sequencer status entity (entity).");
    }
    this._config = config;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      // The hass setter fires on every state change anywhere in Home
      // Assistant, not just this card's entity, and _render() replaces the
      // whole innerHTML. Without this guard, opening a native picker (e.g.
      // the Android time picker) gets destroyed mid-interaction by an
      // unrelated update elsewhere in the house. Listeners live on
      // shadowRoot itself, which innerHTML replacement never touches, so
      // they survive every re-render.
      //
      // Suppression starts as soon as a pointer/keyboard interaction begins
      // (pointerdown/focusin) and is only lifted - via _scheduleRenderResume -
      // once the specific field's own "change" handler runs (the value was
      // actually committed) or a safety timeout fires. It is deliberately NOT
      // lifted on blur/focusout: Android's native time picker is a real OS
      // dialog, so the underlying <input> loses DOM focus the instant it
      // opens - long before the user has picked anything - and clearing
      // suppression there would re-open the exact race this guard exists to
      // close.
      const startSuppression = (e) => {
        if (e.target.closest?.("input, select, textarea")) {
          this._suppressRender = true;
          this._scheduleRenderResume(60000);
        }
      };
      // pointerdown covers mouse/touch/pen in any standards-compliant
      // browser; touchstart is added as a redundant fallback because some
      // embedded WebViews (e.g. the Home Assistant Companion App on
      // Android/iOS) have been observed with incomplete or delayed Pointer
      // Events support, where pointerdown can fail to fire for a tap -
      // leaving suppression never engaged and a field losing focus/input
      // the instant an unrelated hass update lands. focusin is a third,
      // even older/more universally supported layer for the same guard.
      this.shadowRoot.addEventListener("pointerdown", startSuppression);
      this.shadowRoot.addEventListener("touchstart", startSuppression, { passive: true });
      this.shadowRoot.addEventListener("focusin", (e) => {
        if (e.target.matches?.("input, select, textarea")) {
          this._suppressRender = true;
          this._scheduleRenderResume(60000);
        }
      });
      // Belt-and-suspenders on top of pointerdown/touchstart/focusin: some
      // mobile browsers/WebViews don't dispatch pointer/touch/focus events
      // at all for interactions with native form controls that have their
      // own built-in gesture handling - <input type="range">'s thumb-drag
      // is exactly that. If none of the above ever fire for such a control
      // on a given platform, suppression never engages and a slider's
      // dragged-to value gets wiped by the next unrelated hass update
      // before it's ever committed - indistinguishable from the value
      // "snapping back". "input" itself is not platform-dependent this way
      // - every live-updating label next to a slider already relies on it
      // firing during the drag, so it's a safe universal fallback trigger.
      this.shadowRoot.addEventListener("input", startSuppression);
    }
  }

  /** Resumes rendering (and forces one fresh render right away) after
   * delayMs. Used both as the long safety net while a field is being
   * edited, and - via _releaseRenderSuppression - as a short buffer after a
   * value is committed: calling a service is async, so re-rendering the
   * instant "change" fires would rebuild the DOM from attributes that
   * haven't caught up with our own edit yet, which looks like the value
   * snapping back to its old number for a moment. Waiting lets the
   * round-trip land first. this._hass itself keeps updating during
   * suppression regardless - only the DOM rebuild is deferred - so the
   * forced render here already reflects the latest state. */
  _scheduleRenderResume(delayMs) {
    clearTimeout(this._suppressRenderTimeout);
    this._suppressRenderTimeout = setTimeout(() => {
      this._suppressRender = false;
      // Don't force a rebuild while the user is still actively focused on a
      // field (e.g. still typing a zone name) - _isEditingField() in the
      // hass setter keeps blocking renders until they actually leave it.
      if (!this._isEditingField()) {
        this._render();
      }
    }, delayMs);
  }

  /** Call once a field's value has been committed and its service call
   * kicked off (pass the promise _callService returns as pendingCall).
   * Leaves rendering suppressed until that call actually settles - plus a
   * short extra buffer, since the call resolving doesn't guarantee our own
   * entity's updated state has propagated back to us yet - rather than a
   * blind fixed delay. A blind ~1s delay worked against the demo mock's
   * effectively instant round trip, but real service calls over a real
   * (especially mobile) network can take longer, and rendering from attrs
   * that haven't caught up yet is exactly what makes a value visually snap
   * back to its old number right after being changed. Falls back to the
   * old fixed-delay behavior if no promise is given, and always keeps an
   * 8s safety net in case the call never settles for some reason. */
  _releaseRenderSuppression(pendingCall) {
    clearTimeout(this._suppressRenderTimeout);
    if (!pendingCall || typeof pendingCall.then !== "function") {
      this._scheduleRenderResume(1000);
      return;
    }
    this._suppressRenderTimeout = setTimeout(() => this._scheduleRenderResume(0), 8000);
    pendingCall.then(
      () => this._scheduleRenderResume(400),
      () => this._scheduleRenderResume(400)
    );
  }

  /** Commits a range input's value via onCommit(value), triggered by
   * "change" AND pointerup/touchend redundantly (deduped so a value is
   * only ever committed once per distinct drag). Some Android WebViews
   * have been reported to not reliably fire "change" for a touch-dragged
   * <input type="range"> - if that's the case here, relying on "change"
   * alone means the new value is silently never persisted at all, and the
   * next re-render (e.g. once the 60s safety-net suppression timer
   * expires) then shows the old, still-unpersisted value, which looks
   * exactly like the drag "snapping back". pointerup/touchend are a more
   * primitively-supported pair of events to fall back on. */
  _attachRangeCommit(input, onCommit) {
    let lastCommitted = input.value;
    const commit = () => {
      if (input.value === lastCommitted) return;
      lastCommitted = input.value;
      this._releaseRenderSuppression(onCommit(input.value));
    };
    input.addEventListener("change", commit);
    input.addEventListener("pointerup", commit);
    input.addEventListener("touchend", commit);
  }

  /** True while an input/select/textarea inside this card's shadow root has
   * focus. Belt-and-suspenders alongside _suppressRender: whatever the
   * timing of the pointerdown/change-driven flag, never blow away a field
   * the user is actually, currently typing into. */
  _isEditingField() {
    const active = this.shadowRoot?.activeElement;
    return !!active && active.matches?.("input, select, textarea");
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._suppressRender && !this._isEditingField()) {
      this._render();
    }
  }

  _entityState() {
    return this._hass?.states[this._config.entity];
  }

  _callService(service, extra) {
    const stateObj = this._entityState();
    if (!stateObj) return undefined;
    const entryId = stateObj.attributes.entry_id;
    return this._hass.callService(DOMAIN, service, { entry_id: entryId, ...extra });
  }

  /** Today's forecast high for a weather entity, preferring the legacy
   * synchronous `forecast` attribute and otherwise fetching it via the
   * `weather.get_forecasts` action. That action is async, so this returns
   * whatever's currently cached (or null on the first call for an entity)
   * and kicks off a fetch in the background, cached per entity for
   * FORECAST_CACHE_TTL_MS and triggering one re-render once it resolves. */
  _forecastHighFor(weatherEntityId) {
    const legacy = legacyForecastHigh(this._hass, weatherEntityId);
    if (legacy != null) return legacy;

    const cache = this._forecastCache;
    if (cache && cache.entityId === weatherEntityId) {
      if (Date.now() - cache.fetchedAt < FORECAST_CACHE_TTL_MS) return cache.high;
    }

    if (this._forecastFetchEntityId !== weatherEntityId) {
      this._forecastFetchEntityId = weatherEntityId;
      Promise.resolve(
        this._hass.callService(
          "weather",
          "get_forecasts",
          { type: "daily" },
          { entity_id: weatherEntityId },
          true,
          true
        )
      )
        .then((result) => {
          const forecast = result?.response?.[weatherEntityId]?.forecast;
          const temp = Array.isArray(forecast) && forecast.length ? forecast[0]?.temperature : null;
          this._forecastCache = {
            entityId: weatherEntityId,
            high: typeof temp === "number" ? temp : null,
            fetchedAt: Date.now(),
          };
        })
        .catch(() => {
          this._forecastCache = { entityId: weatherEntityId, high: null, fetchedAt: Date.now() };
        })
        .finally(() => {
          this._forecastFetchEntityId = null;
          if (!this._suppressRender && !this._isEditingField()) this._render();
        });
    }
    return cache && cache.entityId === weatherEntityId ? cache.high : null;
  }

  /** Proportional zone/pause timeline. Segments are colored done/active/upcoming
   * based on last_zone_index (persists through the pause after a zone) and
   * current_zone_index (set only while a zone is actively running). */
  _renderTimeline(zones, attrs, t) {
    const factor = attrs.weather_current_factor || 1;
    const isRunning = attrs.current_zone_index != null;
    const isPaused = !isRunning && attrs.last_zone_index != null && attrs.seconds_remaining_total > 0;
    const lastIndex = attrs.last_zone_index;

    const segments = [];
    zones.forEach((zone, index) => {
      const seconds = Math.max(1, Math.round(zone.duration_minutes * 60 * factor));
      let cls = "zone-upcoming";
      if (isRunning && index === attrs.current_zone_index) cls = "zone-active";
      else if (lastIndex != null && index <= lastIndex && !(isPaused && index === lastIndex)) cls = "zone-done";
      const label = zoneDisplayName(this._hass, zone);
      segments.push({
        weight: seconds,
        cls,
        title: `${index + 1}. ${label} · ${zone.duration_minutes} min`,
        label: index + 1,
      });

      if (index < zones.length - 1 && attrs.pause_between_zones_seconds > 0) {
        let pauseCls = "pause-upcoming";
        if (isPaused && index === lastIndex) pauseCls = "pause-active";
        else if (lastIndex != null && index < lastIndex) pauseCls = "pause-done";
        segments.push({
          weight: attrs.pause_between_zones_seconds,
          cls: pauseCls,
          title: `${t.pauseBetweenZones}: ${formatSeconds(attrs.pause_between_zones_seconds)}`,
          label: "",
        });
      }
    });

    return `
      <div class="timeline">
        ${segments
          .map(
            (s) =>
              `<div class="segment ${s.cls}" style="flex-grow:${s.weight}" title="${s.title}">${s.label}</div>`
          )
          .join("")}
      </div>
      <div class="timeline-legend">
        <span><i style="background: var(--success-color, #4caf50)"></i>${t.status.running}</span>
        <span><i style="background: var(--warning-color, #ff9800)"></i>${t.pauseBetweenZones}</span>
      </div>
    `;
  }

  _renderForecastStat(attrs, t) {
    if (!attrs.weather_adjustment_enabled || !attrs.weather_entity) return "";
    const high = this._forecastHighFor(attrs.weather_entity);
    if (high == null) return "";
    const factor = linearFactor(
      high,
      attrs.weather_reference_temp,
      attrs.weather_hot_temp,
      attrs.weather_hot_factor
    );
    return `
      <div class="stat" style="--tile-color: var(--warning-color, #ff9800)">
        <ha-icon icon="mdi:thermometer-high"></ha-icon>
        <div>
          <div class="stat-value">${high}° · ×${factor.toFixed(2)}</div>
          <div class="stat-label">${t.forecastHigh}</div>
        </div>
      </div>
    `;
  }

  _sharedStyles() {
    return `
      ha-card { padding: 12px 16px; }
      .tile-header { display: flex; align-items: center; gap: 12px; }
      .tile-icon { width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;
        background: color-mix(in srgb, var(--tile-color) 20%, transparent); color: var(--tile-color); }
      .tile-icon.spraying { animation: pulse 1s ease-in-out infinite; }
      @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.65; transform: scale(1.1); } }
      .tile-text { flex: 1; min-width: 0; }
      .tile-primary { font-size: 1.05em; font-weight: 600; color: var(--primary-text-color); }
      .tile-secondary { font-size: 0.85em; color: var(--secondary-text-color); }
      .tile-actions { display: flex; gap: 6px; flex-shrink: 0; }
      .tile-icon-btn { width: 36px; height: 36px; border-radius: 50%; border: none; cursor: pointer;
        display: flex; align-items: center; justify-content: center; background: var(--secondary-background-color); color: var(--primary-text-color); }
      .tile-icon-btn.primary { background: var(--success-color, #4caf50); color: white; }
      .tile-icon-btn.danger { background: var(--error-color, #db4437); color: white; }
      .tile-icon-btn:disabled { opacity: 0.35; cursor: not-allowed; }

      .tile-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 14px;
        background: var(--secondary-background-color, rgba(127,127,127,0.08)); margin-top: 8px; }
      .tile-row-icon { width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0; display: flex;
        align-items: center; justify-content: center; background: color-mix(in srgb, var(--tile-color, var(--primary-color)) 18%, transparent);
        color: var(--tile-color, var(--primary-color)); }
      .tile-row-label { flex: 0 0 auto; min-width: 130px; font-size: 0.88em; color: var(--primary-text-color); }
      .tile-row-control { flex: 1 1 180px; display: flex; align-items: center; gap: 8px; min-width: 0; }
      .tile-row-control input[type="range"] { flex: 1; accent-color: var(--tile-color, var(--primary-color)); height: 6px; touch-action: none; }
      .tile-row-control input[type="number"],
      .tile-row-control input[type="time"],
      .tile-row-control input[type="text"],
      .tile-row-control select { flex: 1; min-width: 0; padding: 6px 8px; border-radius: 10px;
        border: 1px solid var(--divider-color, #555); background: var(--card-background-color); color: var(--primary-text-color); }
      .tile-row-value { font-size: 0.8em; color: var(--secondary-text-color); min-width: 46px; text-align: right; flex-shrink: 0; }

      .progress-bar { height: 10px; border-radius: 999px; background: var(--divider-color, #444); overflow: hidden; margin-top: 10px; }
      .progress-fill { height: 100%; border-radius: 999px; background: var(--success-color, #4caf50); transition: width 1s linear; }

      .chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
      .chip { border: 1px solid var(--divider-color, #555); background: transparent; color: var(--primary-text-color);
        border-radius: 999px; padding: 4px 10px; font-size: 0.8em; cursor: pointer; }
      .chip:hover { background: var(--secondary-background-color); }
      .chip-clear { border-color: var(--warning-color, #ff9800); color: var(--warning-color, #ff9800); }
      .chip-static { cursor: default; display: flex; align-items: center; gap: 6px; }
      .chip-static.active { border-color: var(--success-color, #4caf50); color: var(--success-color, #4caf50); background: color-mix(in srgb, var(--success-color, #4caf50) 12%, transparent); }
      .chip-badge { width: 16px; height: 16px; border-radius: 50%; background: var(--primary-color); color: white;
        display: flex; align-items: center; justify-content: center; font-size: 0.65em; flex-shrink: 0; }

      .switch { position: relative; display: inline-block; width: 40px; height: 22px; flex-shrink: 0; }
      .switch input { opacity: 0; width: 0; height: 0; }
      .slider-toggle { position: absolute; cursor: pointer; inset: 0; background: var(--disabled-text-color, #888);
        border-radius: 22px; transition: 0.2s; }
      .slider-toggle::before { content: ""; position: absolute; height: 16px; width: 16px; left: 3px; bottom: 3px;
        background: white; border-radius: 50%; transition: 0.2s; }
      .switch input:checked + .slider-toggle { background: var(--tile-color, var(--info-color, #03a9f4)); }
      .switch input:checked + .slider-toggle::before { transform: translateX(18px); }

      .footer-note { margin-top: 10px; font-size: 0.8em; color: var(--secondary-text-color); text-align: center; }
      .not-found { padding: 16px; color: var(--error-color); }
      .drag-handle { cursor: grab; color: var(--secondary-text-color); flex-shrink: 0; }
      .zone-row.drag-over { outline: 2px dashed var(--primary-color); }

      /* Timeline: proportional zone/pause segments in irrigation order */
      .timeline { display: flex; gap: 3px; height: 30px; margin-top: 12px; }
      .segment { border-radius: 8px; display: flex; align-items: center; justify-content: center;
        overflow: hidden; font-size: 0.68em; font-weight: 600; color: white; min-width: 4px; }
      .segment.zone-upcoming { background: color-mix(in srgb, var(--success-color, #4caf50) 30%, var(--divider-color, #888)); color: var(--primary-text-color); }
      .segment.zone-done { background: var(--success-color, #4caf50); opacity: 0.5; }
      .segment.zone-active { background: var(--success-color, #4caf50); animation: pulse-bg 1.2s ease-in-out infinite; }
      .segment.pause-upcoming { background: color-mix(in srgb, var(--warning-color, #ff9800) 22%, var(--divider-color, #888)); }
      .segment.pause-done { background: var(--warning-color, #ff9800); opacity: 0.45; }
      .segment.pause-active { background: var(--warning-color, #ff9800); animation: pulse-bg 1.2s ease-in-out infinite; }
      @keyframes pulse-bg { 0%, 100% { filter: brightness(1); } 50% { filter: brightness(1.35); } }
      .timeline-legend { display: flex; gap: 14px; margin-top: 6px; font-size: 0.72em; color: var(--secondary-text-color); }
      .timeline-legend span { display: inline-flex; align-items: center; gap: 4px; }
      .timeline-legend i { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }

      .stat-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 10px; }
      .stat { flex: 1 1 130px; display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 12px;
        background: var(--secondary-background-color, rgba(127,127,127,0.08)); min-width: 0; }
      .stat ha-icon { color: var(--tile-color, var(--primary-color)); flex-shrink: 0; }
      .stat-value { font-size: 0.92em; font-weight: 600; color: var(--primary-text-color); overflow-wrap: break-word; word-break: break-word; }
      .stat-label { font-size: 0.72em; color: var(--secondary-text-color); overflow-wrap: break-word; word-break: break-word; }

      /* Layout: horizontal arranges content side-by-side for wide/short cards */
      .layout-horizontal .status-columns { display: flex; gap: 16px; align-items: flex-start; }
      .layout-horizontal .status-columns .timeline-col { flex: 1.4; min-width: 0; }
      .layout-horizontal .status-columns .stats-col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
      .layout-horizontal .stat-row { flex-direction: column; margin-top: 0; }
      .layout-horizontal .zones-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
      .layout-horizontal .settings-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; align-items: start; }
      .layout-horizontal .zones-grid .tile-row,
      .layout-horizontal .settings-grid .tile-row { margin-top: 0; min-width: 0; }
      .layout-horizontal .settings-grid .tile-row-control { flex-wrap: wrap; }
    `;
  }
}

/* -------------------------------------------------------------------- */
/* Status card - read-only overview                                     */
/* -------------------------------------------------------------------- */

class IrrigationSequencerStatusCard extends IrrigationSequencerBaseCard {
  static getConfigElement() {
    return document.createElement("irrigation-sequencer-status-card-editor");
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && hass.states[id].attributes?.zones !== undefined
    );
    return { entity: entity || "" };
  }

  getCardSize() {
    return this._config?.layout === "horizontal" ? 3 : 4;
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
    const title = this._config.title || t.statusCardTitle;
    const statusColor = STATUS_COLORS[status] || STATUS_COLORS.idle;
    const isRunning = status === "running";
    const isBusy = status === "running" || status === "paused_between_zones";
    const layout = this._config.layout === "horizontal" ? "horizontal" : "vertical";

    const activeZone = attrs.current_zone_index != null ? zones[attrs.current_zone_index] : null;
    const totalPlanned =
      zones.reduce((sum, z) => sum + Math.round(z.duration_minutes * 60 * (attrs.weather_current_factor || 1)), 0) +
      attrs.pause_between_zones_seconds * Math.max(0, zones.length - 1);
    const remaining = attrs.seconds_remaining_total || 0;
    const pct = isBusy && totalPlanned > 0 ? Math.max(0, Math.min(100, 100 - (remaining / totalPlanned) * 100)) : 0;

    const statsCol = `
      <div class="stat-row">
        ${
          isBusy
            ? `<div class="stat" style="--tile-color: ${statusColor}">
                <ha-icon icon="mdi:sprinkler-variant"></ha-icon>
                <div>
                  <div class="stat-value">${activeZone ? zoneDisplayName(this._hass, activeZone) : t.pauseBetweenZones}</div>
                  <div class="stat-label">${activeZone ? t.remainingZone(formatSeconds(attrs.seconds_remaining_zone)) : t.remainingTotal(formatSeconds(remaining))}</div>
                </div>
              </div>`
            : `<div class="stat" style="--tile-color: var(--info-color, #03a9f4)">
                <ha-icon icon="mdi:calendar-clock"></ha-icon>
                <div>
                  <div class="stat-value">${attrs.next_run ? new Date(attrs.next_run).toLocaleString(resolveLanguage(this._hass), { weekday: "short", hour: "2-digit", minute: "2-digit" }) : "-"}</div>
                  <div class="stat-label">${t.nextRun}</div>
                </div>
              </div>`
        }
        ${
          attrs.weather_adjustment_enabled && attrs.weather_current_temp != null
            ? `<div class="stat" style="--tile-color: var(--primary-color)">
                <ha-icon icon="mdi:weather-partly-cloudy"></ha-icon>
                <div>
                  <div class="stat-value">${attrs.weather_current_temp}° · ×${attrs.weather_current_factor.toFixed(2)}</div>
                  <div class="stat-label">${t.currentFactor}</div>
                </div>
              </div>`
            : ""
        }
        ${this._renderForecastStat(attrs, t)}
      </div>
    `;

    const timelineCol = `
      ${isBusy ? `<div class="progress-bar"><div class="progress-fill" style="width:${pct}%; background:${statusColor}"></div></div>` : ""}
      ${this._renderTimeline(zones, attrs, t)}
    `;

    const body =
      layout === "horizontal"
        ? `<div class="status-columns"><div class="timeline-col">${timelineCol}</div><div class="stats-col">${statsCol}</div></div>`
        : `${timelineCol}${statsCol}`;

    this.shadowRoot.innerHTML = `
      <style>${this._sharedStyles()}</style>
      <ha-card class="${layout === "horizontal" ? "layout-horizontal" : ""}">
        <div class="tile-header" style="--tile-color: ${statusColor}">
          <div class="tile-icon ${isRunning ? "spraying" : ""}"><ha-icon icon="mdi:sprinkler-variant"></ha-icon></div>
          <div class="tile-text">
            <div class="tile-primary">${title}</div>
            <div class="tile-secondary">${t.status[status] || status}</div>
          </div>
          <div class="tile-actions">
            <button class="tile-icon-btn danger" id="stop-btn" ${status === "idle" ? "disabled" : ""} title="${t.stop}">
              <ha-icon icon="mdi:stop"></ha-icon>
            </button>
            <button class="tile-icon-btn primary" id="start-btn" ${isBusy ? "disabled" : ""} title="${t.start}">
              <ha-icon icon="mdi:play"></ha-icon>
            </button>
          </div>
        </div>
        ${body}
      </ha-card>
    `;

    this.shadowRoot.getElementById("start-btn")?.addEventListener("click", () => this._callService("start_now"));
    this.shadowRoot.getElementById("stop-btn")?.addEventListener("click", () => this._callService("stop"));
  }
}

/* -------------------------------------------------------------------- */
/* Settings card - all configuration controls                           */
/* -------------------------------------------------------------------- */

class IrrigationSequencerSettingsCard extends IrrigationSequencerBaseCard {
  static getConfigElement() {
    return document.createElement("irrigation-sequencer-settings-card-editor");
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && hass.states[id].attributes?.zones !== undefined
    );
    return { entity: entity || "" };
  }

  getCardSize() {
    const zones = this._entityState()?.attributes?.zones?.length || 4;
    return 4 + Math.ceil(zones / 2);
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
    const title = this._config.title || t.settingsCardTitle;
    const layout = this._config.layout === "horizontal" ? "horizontal" : "vertical";

    this.shadowRoot.innerHTML = `
      <style>${this._sharedStyles()}</style>
      <ha-card class="${layout === "horizontal" ? "layout-horizontal" : ""}">
        <div class="tile-header" style="--tile-color: var(--primary-color)">
          <div class="tile-icon"><ha-icon icon="mdi:tune-variant"></ha-icon></div>
          <div class="tile-text">
            <div class="tile-primary">${title}</div>
            <div class="tile-secondary">${t.zonesLabel(zones.length)}</div>
          </div>
        </div>

        <div class="zones zones-grid">
          ${zones.map((zone, index) => this._renderZoneRow(zone, index, t)).join("")}
        </div>

        <div class="settings-grid">
          <div class="tile-row" style="--tile-color: var(--warning-color, #ff9800)">
            <div class="tile-row-icon"><ha-icon icon="mdi:timer-sand"></ha-icon></div>
            <div class="tile-row-label">${t.pauseBetweenZones}</div>
            <div class="tile-row-control">
              <input type="range" min="0" max="900" step="60" value="${roundToStep(attrs.pause_between_zones_seconds, 60)}" id="pause-range" />
              <span class="tile-row-value">${formatSeconds(roundToStep(attrs.pause_between_zones_seconds, 60))}</span>
            </div>
          </div>
          <div class="tile-row" style="--tile-color: var(--info-color, #03a9f4); align-items: flex-start;">
            <div class="tile-row-icon"><ha-icon icon="mdi:weather-night"></ha-icon></div>
            <div class="tile-row-label">${t.nightStart}</div>
            <div class="tile-row-control" style="flex-direction: column; align-items: stretch; gap: 8px;">
              ${this._renderStartTimes(attrs)}
            </div>
          </div>
          <div class="tile-row" style="--tile-color: var(--info-color, #03a9f4)">
            <div class="tile-row-icon"><ha-icon icon="mdi:snowflake"></ha-icon></div>
            <div class="tile-row-label">${t.winterMode}</div>
            <div class="tile-row-control">
              <label class="switch">
                <input type="checkbox" id="winter-toggle" ${attrs.winter_mode ? "checked" : ""} />
                <span class="slider-toggle"></span>
              </label>
            </div>
          </div>
          <div class="tile-row" style="--tile-color: var(--info-color, #03a9f4); align-items: flex-start;">
            <div class="tile-row-icon"><ha-icon icon="mdi:weather-rainy"></ha-icon></div>
            <div class="tile-row-label">${t.rainPause}</div>
            <div class="tile-row-control" style="flex-direction: column; align-items: stretch; gap: 8px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <input type="range" min="0" max="24" step="1" id="rain-pause-days" value="${this._rainPauseDefaultDays(attrs)}" />
                <span class="tile-row-value" id="rain-pause-days-value">${this._formatRainPauseDays(this._rainPauseDefaultDays(attrs), t)}</span>
              </div>
              ${
                attrs.rain_pause_until
                  ? `<div class="chip-row" style="margin-top:0;"><button class="chip chip-clear" id="clear-rain">${t.rainPauseClear(attrs.rain_pause_until)}</button></div>`
                  : ""
              }
            </div>
          </div>

          ${this._renderNotifySection(attrs, t)}
          ${this._renderWeatherSection(attrs, t)}
        </div>
      </ha-card>
    `;

    this._attachListeners(zones, t);
  }

  /** Optional notify.<target> call after a completed run. Populated from
   * the instance's registered notify.mobile_app_* services (the Companion
   * App's per-device targets) - "none" (the default) disables it
   * entirely. */
  _renderNotifySection(attrs, t) {
    const notifyServices = this._hass?.services?.notify
      ? Object.keys(this._hass.services.notify).filter((name) => name.startsWith("mobile_app_"))
      : [];
    return `
      <div class="tile-row" style="--tile-color: var(--info-color, #03a9f4)">
        <div class="tile-row-icon"><ha-icon icon="mdi:cellphone-message"></ha-icon></div>
        <div class="tile-row-label">${t.notifyTarget}</div>
        <div class="tile-row-control">
          <select id="notify-target">
            <option value="">${t.notifyNone}</option>
            ${notifyServices
              .map(
                (name) =>
                  `<option value="${name}" ${name === attrs.notify_target ? "selected" : ""}>${notifyTargetLabel(name)}</option>`
              )
              .join("")}
          </select>
        </div>
      </div>
    `;
  }

  _renderZoneRow(zone, index, t) {
    return `
      <div class="tile-row zone-row" style="--tile-color: var(--success-color, #4caf50);" data-index="${index}" data-entity="${zone.entity_id}">
        <div class="drag-handle" draggable="true" title="${t.dragHandle}"><ha-icon icon="mdi:drag-vertical"></ha-icon></div>
        <div class="tile-row-icon"><ha-icon icon="mdi:sprinkler"></ha-icon></div>
        <div class="tile-row-control" style="flex-direction: column; align-items: stretch; gap: 6px;">
          <input type="text" class="zone-name" data-entity="${zone.entity_id}" placeholder="${t.zoneNamePlaceholder}" value="${zoneDisplayName(this._hass, zone)}" />
          <div style="display:flex; align-items:center; gap:8px;">
            <input type="range" min="1" max="30" value="${zone.duration_minutes}" class="zone-duration" data-entity="${zone.entity_id}" />
            <span class="tile-row-value">${zone.duration_minutes} min</span>
          </div>
        </div>
      </div>
    `;
  }

  /** Slider value: days remaining on an active rain pause (clamped to the
   * 1-24 range), or 0 when there's no active pause - 0 is the slider's own
   * "off" position, so this always reflects the real current state instead
   * of a suggested starting point. */
  _rainPauseDefaultDays(attrs) {
    if (attrs.rain_pause_until) {
      const remaining = Math.ceil(
        (new Date(attrs.rain_pause_until) - new Date()) / 86400000
      );
      return Math.min(24, Math.max(1, remaining));
    }
    return 0;
  }

  /** Renders the rain-pause slider's day count, with 0 shown as "off"
   * instead of "0 days". */
  _formatRainPauseDays(days, t) {
    if (days <= 0) return t.rainPauseOff;
    return `${days} ${days > 1 ? t.days : t.day}`;
  }

  /** 1-3 daily start times, each a pair of plain hour/minute number inputs
   * (instead of <input type="time">, sidestepping platform-specific native
   * picker widgets entirely) plus a remove button, and an "add" button while
   * under the cap. Every add/remove/edit submits the full list. */
  _renderStartTimes(attrs) {
    const t = getTranslations(this._hass);
    const times = attrs.start_times && attrs.start_times.length ? attrs.start_times : ["05:00:00"];
    const rows = times
      .map((time, index) => {
        const [hh, mm] = time.split(":");
        return `
          <div class="start-time-row" data-index="${index}" style="display:flex; align-items:center; gap:6px;">
            <input type="number" class="start-time-hour" data-index="${index}" min="0" max="23" value="${parseInt(hh, 10)}"
              style="width: 52px; text-align: center;" inputmode="numeric" />
            <span>:</span>
            <input type="number" class="start-time-minute" data-index="${index}" min="0" max="59" value="${parseInt(mm, 10)}"
              style="width: 52px; text-align: center;" inputmode="numeric" />
            ${
              times.length > MIN_START_TIMES
                ? `<button class="chip chip-clear" data-remove-time="${index}" style="padding: 2px 10px;">✕</button>`
                : ""
            }
          </div>
        `;
      })
      .join("");
    const addButton =
      times.length < MAX_START_TIMES
        ? `<button class="chip" id="add-start-time">+ ${t.addTime}</button>`
        : "";
    return `${rows}${addButton}<div id="start-times-warning" style="display:none; color: var(--error-color, #db4437); font-size: 0.8em;"></div>`;
  }

  /** Same overlap rule the backend enforces (manager._raise_if_start_times_overlap),
   * checked client-side first so the user gets immediate inline feedback
   * instead of only a service-call error toast after the fact. */
  _findOverlappingStartTimes(times, estimatedTotalSeconds) {
    if (times.length < 2) return null;
    const toSeconds = (value) => {
      const [h, m, s] = value.split(":").map(Number);
      return h * 3600 + m * 60 + (s || 0);
    };
    const sorted = [...times].sort();
    const seconds = sorted.map(toSeconds);
    for (let i = 0; i < seconds.length; i++) {
      const nextIndex = (i + 1) % seconds.length;
      const gap = ((seconds[nextIndex] - seconds[i]) % 86400 + 86400) % 86400;
      if (gap < estimatedTotalSeconds) {
        return [sorted[i], sorted[nextIndex]];
      }
    }
    return null;
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
      <div class="tile-row" style="--tile-color: var(--info-color, #03a9f4)">
        <div class="tile-row-icon"><ha-icon icon="mdi:weather-partly-cloudy"></ha-icon></div>
        <div class="tile-row-label">${t.weatherAdjustment}</div>
        <div class="tile-row-control">
          <label class="switch">
            <input type="checkbox" id="weather-toggle" ${enabled ? "checked" : ""} />
            <span class="slider-toggle"></span>
          </label>
        </div>
      </div>
      ${
        enabled
          ? `
        <div class="tile-row" style="--tile-color: var(--info-color, #03a9f4)">
          <div class="tile-row-icon"><ha-icon icon="mdi:cloud-outline"></ha-icon></div>
          <div class="tile-row-label">${t.weatherEntity}</div>
          <div class="tile-row-control">
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
        </div>
        <div class="tile-row" style="--tile-color: var(--primary-color)">
          <div class="tile-row-icon"><ha-icon icon="mdi:thermometer-low"></ha-icon></div>
          <div class="tile-row-label">${t.referenceTemp}</div>
          <div class="tile-row-control"><input type="number" id="weather-reference-temp" value="${attrs.weather_reference_temp}" step="0.5" /></div>
        </div>
        <div class="tile-row" style="--tile-color: var(--primary-color)">
          <div class="tile-row-icon"><ha-icon icon="mdi:thermometer-high"></ha-icon></div>
          <div class="tile-row-label">${t.hotTemp}</div>
          <div class="tile-row-control"><input type="number" id="weather-hot-temp" value="${attrs.weather_hot_temp}" step="0.5" /></div>
        </div>
        <div class="tile-row" style="--tile-color: var(--primary-color)">
          <div class="tile-row-icon"><ha-icon icon="mdi:water-percent"></ha-icon></div>
          <div class="tile-row-label">${t.hotFactor}</div>
          <div class="tile-row-control"><input type="number" id="weather-hot-factor" value="${attrs.weather_hot_factor}" step="0.1" min="0.1" max="3" /></div>
        </div>
        ${currentFactorLabel ? `<div class="footer-note">${currentFactorLabel}</div>` : ""}
        `
          : ""
      }
    `;
  }

  _attachListeners(zones, t) {
    const root = this.shadowRoot;

    root.getElementById("winter-toggle")?.addEventListener("change", (e) => {
      this._releaseRenderSuppression(this._callService("set_winter_mode", { enabled: e.target.checked }));
    });

    const submitStartTimes = (times) => {
      const warningEl = root.getElementById("start-times-warning");
      const estimatedTotalSeconds = this._entityState().attributes.estimated_total_seconds || 0;
      const overlap = this._findOverlappingStartTimes(times, estimatedTotalSeconds);
      if (overlap) {
        warningEl.textContent = t.startTimesOverlap(overlap[0].slice(0, 5), overlap[1].slice(0, 5), Math.round(estimatedTotalSeconds / 60));
        warningEl.style.display = "block";
        return;
      }
      warningEl.style.display = "none";
      this._releaseRenderSuppression(this._callService("set_start_times", { start_times: times }));
    };
    const readRowTimes = () => {
      const hours = Array.from(root.querySelectorAll(".start-time-hour"));
      const minutes = Array.from(root.querySelectorAll(".start-time-minute"));
      return hours.map((hourEl, i) => {
        const hour = Math.min(23, Math.max(0, parseInt(hourEl.value, 10) || 0));
        const minute = Math.min(59, Math.max(0, parseInt(minutes[i].value, 10) || 0));
        return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00`;
      });
    };

    root.querySelectorAll(".start-time-hour, .start-time-minute").forEach((input) => {
      input.addEventListener("change", () => submitStartTimes(readRowTimes()));
    });
    root.querySelectorAll("[data-remove-time]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const times = readRowTimes();
        times.splice(parseInt(btn.dataset.removeTime, 10), 1);
        submitStartTimes(times);
      });
    });
    root.getElementById("add-start-time")?.addEventListener("click", () => {
      const times = readRowTimes();
      times.push("12:00:00");
      submitStartTimes(times);
    });

    const pauseRange = root.getElementById("pause-range");
    pauseRange?.addEventListener("input", (e) => {
      pauseRange.nextElementSibling.textContent = formatSeconds(e.target.value);
    });
    if (pauseRange) {
      this._attachRangeCommit(pauseRange, (value) =>
        this._callService("set_pause_between_zones", { seconds: parseInt(value, 10) })
      );
    }

    const rainPauseDays = root.getElementById("rain-pause-days");
    rainPauseDays?.addEventListener("input", (e) => {
      const days = parseInt(e.target.value, 10);
      root.getElementById("rain-pause-days-value").textContent = this._formatRainPauseDays(days, t);
    });
    if (rainPauseDays) {
      this._attachRangeCommit(rainPauseDays, (value) => {
        const days = parseInt(value, 10);
        return days <= 0 ? this._callService("clear_rain_pause", {}) : this._callService("set_rain_pause", { days });
      });
    }
    root.getElementById("clear-rain")?.addEventListener("click", () => {
      this._releaseRenderSuppression(this._callService("clear_rain_pause", {}));
    });

    root.querySelectorAll(".zone-name").forEach((input) => {
      input.addEventListener("change", (e) => {
        this._releaseRenderSuppression(
          this._callService("set_zone_name", {
            entity_id: e.target.dataset.entity,
            name: e.target.value,
          })
        );
      });
    });

    root.querySelectorAll(".zone-duration").forEach((input) => {
      input.addEventListener("input", (e) => {
        e.target.nextElementSibling.textContent = `${e.target.value} min`;
      });
      this._attachRangeCommit(input, (value) =>
        this._callService("set_zone_duration", {
          entity_id: input.dataset.entity,
          minutes: parseInt(value, 10),
        })
      );
    });

    root.getElementById("notify-target")?.addEventListener("change", (e) => {
      this._releaseRenderSuppression(this._callService("set_notify_target", { target: e.target.value || null }));
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
      this._releaseRenderSuppression(
        this._callService("set_weather_adjustment", readWeatherForm({ enabled: e.target.checked }))
      );
    });
    root.getElementById("weather-entity")?.addEventListener("change", (e) => {
      this._releaseRenderSuppression(
        this._callService("set_weather_adjustment", readWeatherForm({ weather_entity: e.target.value }))
      );
    });
    root.getElementById("weather-reference-temp")?.addEventListener("change", (e) => {
      this._releaseRenderSuppression(
        this._callService(
          "set_weather_adjustment",
          readWeatherForm({ reference_temp: parseFloat(e.target.value) })
        )
      );
    });
    root.getElementById("weather-hot-temp")?.addEventListener("change", (e) => {
      this._releaseRenderSuppression(
        this._callService("set_weather_adjustment", readWeatherForm({ hot_temp: parseFloat(e.target.value) }))
      );
    });
    root.getElementById("weather-hot-factor")?.addEventListener("change", (e) => {
      this._releaseRenderSuppression(
        this._callService(
          "set_weather_adjustment",
          readWeatherForm({ hot_factor: parseFloat(e.target.value) })
        )
      );
    });
  }

  _attachDragAndDrop(root, zones) {
    // Only the drag-handle icon is draggable="true" (see _renderZoneRow) -
    // not the whole row. A draggable row would swallow every mousedown
    // inside it as a potential drag gesture, including the slightest mouse
    // wobble while clicking into the zone-name text field, which blurred it
    // instantly and made typing impossible. dragover/drop stay on the row
    // so you can still drop anywhere over it, just not start the drag from
    // anywhere in it.
    const zoneEls = Array.from(root.querySelectorAll(".zone-row"));
    zoneEls.forEach((el) => {
      el.querySelector(".drag-handle")?.addEventListener("dragstart", (e) => {
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
        if (this._dragIndex === null || this._dragIndex === undefined || this._dragIndex === targetIndex) return;

        const ordered = [...zones];
        const [moved] = ordered.splice(this._dragIndex, 1);
        ordered.splice(targetIndex, 0, moved);
        this._callService("set_zone_order", { zones: ordered.map((z) => z.entity_id) });
        this._dragIndex = null;
      });
    });
  }
}

/* -------------------------------------------------------------------- */
/* Card editors (visual config UI)                                      */
/* -------------------------------------------------------------------- */

class IrrigationSequencerCardEditorBase extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._suppressRender && !this._isEditingField()) {
      this._render();
    }
  }

  _isEditingField() {
    const active = this.shadowRoot?.activeElement;
    return !!active && active.matches?.("input, select, textarea");
  }

  _scheduleRenderResume(delayMs) {
    clearTimeout(this._suppressRenderTimeout);
    this._suppressRenderTimeout = setTimeout(() => {
      this._suppressRender = false;
      if (!this._isEditingField()) {
        this._render();
      }
    }, delayMs);
  }

  _releaseRenderSuppression() {
    this._scheduleRenderResume(1000);
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("pointerdown", (e) => {
        if (e.target.closest?.("input, select, textarea")) {
          this._suppressRender = true;
          this._scheduleRenderResume(60000);
        }
      });
      this.shadowRoot.addEventListener("focusin", (e) => {
        if (e.target.matches?.("input, select, textarea")) {
          this._suppressRender = true;
          this._scheduleRenderResume(60000);
        }
      });
    }
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
      <div class="row">
        <label>${t.layout}</label>
        <select id="layout">
          <option value="vertical" ${this._config?.layout !== "horizontal" ? "selected" : ""}>${t.layoutVertical}</option>
          <option value="horizontal" ${this._config?.layout === "horizontal" ? "selected" : ""}>${t.layoutHorizontal}</option>
        </select>
      </div>
    `;
    this.shadowRoot.getElementById("entity").addEventListener("change", (e) => {
      this._releaseRenderSuppression();
      this._updateConfig({ entity: e.target.value });
    });
    this.shadowRoot.getElementById("title").addEventListener("change", (e) => {
      this._releaseRenderSuppression();
      this._updateConfig({ title: e.target.value });
    });
    this.shadowRoot.getElementById("layout").addEventListener("change", (e) => {
      this._releaseRenderSuppression();
      this._updateConfig({ layout: e.target.value });
    });
  }

  _updateConfig(partial) {
    this._config = { ...this._config, ...partial };
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config } }));
  }
}

class IrrigationSequencerStatusCardEditor extends IrrigationSequencerCardEditorBase {}
class IrrigationSequencerSettingsCardEditor extends IrrigationSequencerCardEditorBase {}

customElements.define("irrigation-sequencer-status-card", IrrigationSequencerStatusCard);
customElements.define("irrigation-sequencer-settings-card", IrrigationSequencerSettingsCard);
customElements.define("irrigation-sequencer-status-card-editor", IrrigationSequencerStatusCardEditor);
customElements.define("irrigation-sequencer-settings-card-editor", IrrigationSequencerSettingsCardEditor);

window.customCards = window.customCards || [];
window.customCards.push(
  {
    type: "irrigation-sequencer-status-card",
    name: "Irrigation Sequencer - Status",
    description: "Read-only status overview: active zone, progress and next run.",
  },
  {
    type: "irrigation-sequencer-settings-card",
    name: "Irrigation Sequencer - Settings",
    description: "All configuration controls: zone names, order, duration, schedule, winter mode, rain pause, weather adjustment.",
  }
);
