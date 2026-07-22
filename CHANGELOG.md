# Changelog

All notable changes to this project are documented here. Versioning follows
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`, bumped in
`custom_components/irrigation_sequencer/manifest.json` and tagged as a
GitHub release (`vX.Y.Z`) once pushed.

## [1.2.5] - 2026-07-22

- Fixed: changing a zone's duration (or name) didn't live-update the status
  card's timeline - only pause-between-zones changes did. Root cause:
  `extra_state_attributes` hands out the zones list by reference, and
  `async_set_zone_duration`/`async_set_zone_name` mutated the existing
  zone dicts in place instead of replacing them, so Home Assistant's
  state-diffing saw the "old" and "new" zones attribute as the literal
  same (already-mutated) object and never detected a change. Now builds
  fresh list/dict objects on every zone change. Added regression tests.

## [1.2.4] - 2026-07-22

- Documentation only: expanded the "close and reopen the tab" tip to also
  cover cards showing "Configuration error" or vanishing after adding or
  removing a zone (same stale-tab cause), plus a pointer to filter the
  browser console for "irrigation" to rule out unrelated custom-card
  errors before assuming this integration is at fault. Investigated a live
  report where the console showed real errors, but all from other
  installed HACS cards - the cards recovered after closing/reopening the
  browser, no code issue found.

## [1.2.3] - 2026-07-22

- Documentation only: added a note to use "Restart Home Assistant", not
  "Quick Reload", after installing/updating - Quick Reload only reloads
  YAML config, not custom integration Python code, so it silently keeps
  running the old version with no error. Confirmed live: a user updated to
  v1.2.2 but the integration still showed v1.2.0 and the bug persisted
  until a real restart.

## [1.2.2] - 2026-07-22

- Fixed: "Configure" on the integration (used to add/remove zones after
  initial setup) crashed with a 500 error on current Home Assistant core.
  `IrrigationSequencerOptionsFlow.__init__` manually assigned
  `self.config_entry` - the long-standing pattern, but HA core deprecated
  it in favor of an auto-populated property and current versions now raise
  instead of just warning. Caught live by a user trying to add a second
  zone. Added a regression test.

## [1.2.1] - 2026-07-22

- Documentation only: added a note that a browser tab (or the mobile app)
  already open before installing/updating won't pick up the self-hosted
  card until fully closed and reopened - the injected `<script>` tag is
  only added on a fresh full page load. Confirmed live: a user couldn't
  find the cards in the picker until closing and reopening the browser.

## [1.2.0] - 2026-07-22

- The integration now self-hosts the Lovelace card and registers it
  automatically on startup (`custom_components/irrigation_sequencer/frontend/`,
  served via a static path + `add_extra_js_url`, matching the pattern used
  by many other custom integrations). This removes the two-HACS-category
  split entirely: **HACS Integration** is now the only category needed -
  one repository entry, one download, cards and backend update together.
  Manual installs are simplified the same way - just copy
  `custom_components/irrigation_sequencer/`, no `www/` copy or Lovelace
  resource needed. Raises the minimum Home Assistant version to 2024.7.0
  (`hass.http.async_register_static_paths`).

## [1.1.7] - 2026-07-22

- Documentation only: reverted 1.1.6's "add as Integration, download,
  remove the HACS entry, re-add as Dashboard" fresh-install dance - user
  feedback confirmed this is impractical for a first-time setup. Back to
  the 1.1.5 recommendation as the primary path: Dashboard via HACS for the
  cards (gives update tracking), plus a one-time manual copy of
  `custom_components/irrigation_sequencer` for the backend (which changes
  rarely). Removes the swap-categories workflow from the docs entirely.

## [1.1.6] - 2026-07-22

- Documentation only: added explicit steps for a completely fresh install
  (nothing installed yet) - install as Integration first, remove that HACS
  tracking entry (confirmed this does not delete already-downloaded
  files), then re-add as Dashboard for the cards. Previously the
  instructions only covered the case where the backend was already
  installed manually.

## [1.1.5] - 2026-07-22

- Documentation only: corrected 1.1.4's claim that this repo can be added
  to HACS twice (once per category) - a user confirmed HACS rejects a
  second custom-repository add for the same URL with "exists in the
  store," even with a different category selected. Updated instructions
  to recommend Dashboard via HACS (for the cards) plus a manual copy of
  `custom_components/irrigation_sequencer` (for the backend), with
  category-swapping as an alternative if HACS-tracked backend updates are
  wanted occasionally.

## [1.1.4] - 2026-07-22

- Documentation only: clarified the HACS installation instructions after
  working through this live with a user - this repo provides both an
  integration and a Lovelace plugin and needs to be added to HACS
  **twice** (same URL, once per category), and the frontend category is
  currently labelled **"Dashboard"** in HACS's UI, not "Plugin" - a
  common point of confusion that looked like a broken installation
  (Konfigurationsfehler) but was actually just the wrong/missing
  category. Added troubleshooting notes for when re-adding a URL doesn't
  create a second tracked entry.

## [1.1.3] - 2026-07-22

- **Fixed HACS not being able to properly discover/install the frontend
  plugin**: confirmed by reading HACS's own source
  (`repositories/plugin.py`, `update_filenames()`/`generate_dashboard_resource_url()`)
  that a `hacs.json` `filename` containing a subdirectory path causes HACS
  to log "have defined an invalid file name" and mismatches the actual
  file location against the dashboard resource URL it registers. Moved
  `irrigation-sequencer-card.js` from the `irrigation-sequencer-card/`
  subdirectory to the repository root (HACS requires the plugin JS file to
  live at the repo root or in a `dist/` folder) and updated `hacs.json`'s
  `filename` to the bare filename. Fixes [#33](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/33).

## [1.1.2] - 2026-07-21

- **Fixed**: a zone's duration slider/label could revert to displaying its
  *previous* value right after starting a run, even though the new value
  was correctly persisted and used for the actual run - confirmed a pure
  display bug, not a data bug. Rather than continuing to chase the exact
  render-suppression timing race, the settings card now remembers the last
  duration the user committed per zone and displays that optimistically
  until the backend's own attribute value actually matches it - making the
  display structurally consistent with user intent regardless of
  hass-update timing/ordering. Verified live with an injected stale-update
  race. Fixes [#32](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/32).

## [1.1.1] - 2026-07-21

- **Fixed**: toggling weather adjustment (or any checkbox/select) no longer
  needed a full page refresh to show/hide its dependent section live.
  `_isEditingField()` treated any focused `input, select, textarea` as
  "still being edited" and kept blocking the render scheduled after the
  toggle's own service call resolved - but a checkbox/select/range slider
  is an atomic, one-shot interaction with nothing left to "still edit"
  once it's flipped/chosen/dragged, even though it commonly keeps DOM
  focus afterward. Narrowed the guard to text/number inputs and
  textareas only. Fixes [#31](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/31).

## [1.1.0] - 2026-07-21

- **Icon now shows up in Devices & Services**: corrects what v0.3.1
  documented as a hard platform limitation - that was accurate for older
  HA versions, but as of HA 2026.3.0, custom integrations can bundle their
  own brand icon directly via a `brand/` folder (see the [Brands Proxy API
  announcement](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api)),
  no `home-assistant/brands` PR needed anymore. Added
  `custom_components/irrigation_sequencer/brand/icon.png` +
  `icon@2x.png`. Requires HA 2026.3.0+. The integration's *name* in that
  same list still can't be localized - that part of the limitation still
  stands, unrelated to this fix. Fixes [#30](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/30).

## [1.0.0] - 2026-07-21

First stable release. Feature set: multi-zone sequencing with per-zone
name/duration/order, pause between zones, 1-3 daily start times with
overlap protection, winter mode, rain pause (0-24 days), weather-based
duration adjustment with a forecast preview, optional mobile notification
on completion, two Lovelace cards (status + settings) with a
vertical/horizontal layout option, and an automated test suite for the
backend logic running on every push via GitHub Actions. No functional
changes from 0.10.1 - this tag marks the point where the integration has
been tested against real hardware and real usage over multiple days and
is considered ready for general use, not a pre-release under active
testing.

## [0.10.1] - 2026-07-21

- Fixed the completion notification service call missing `blocking=True`
  (caught by the new test suite on CI, not locally) - without it,
  `hass.services.async_call` schedules the call and returns immediately
  rather than waiting for it, so the notification could silently not have
  been sent yet by the time the run's `finally` block finished.

## [0.10.0] - 2026-07-21

- **Optional mobile notification after a completed run**: pick a device in
  the settings card, sourced from the instance's registered
  `notify.mobile_app_*` services - defaults to "none" (no notifications).
  Adds `irrigation_sequencer.set_notify_target`, persisted like the other
  settings. The notification message follows the instance language (same
  `hass.config.language` convention as the config flow's default entry
  name), independent of any per-user setting. Notification failures are
  logged but never affect the irrigation run itself. Fixes [#28](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/28).

## [0.9.9] - 2026-07-21

- Fixed the pause-between-zones and rain-pause value text getting pushed
  off-screen on narrow phones - `.tile-row` (used for most settings-card
  rows) never wrapped, and its label had a fixed non-shrinking 130px
  min-width, so icon + label + slider + value could add up to more than
  the available width. Row now wraps the control (slider + value) onto its
  own line when needed instead of overflowing. Fixes [#29](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/29).

## [0.9.8] - 2026-07-20

- Confirmed via the backend that the zone-duration value genuinely never
  changed across all previous fix attempts (v0.9.1, v0.9.4, v0.9.6, v0.9.7)
  - ruling out a pure rendering glitch. New root cause theory: some mobile
  browsers/WebViews don't dispatch pointerdown/touchstart/focusin at all
  for interactions with native form controls that have their own built-in
  gesture handling - `<input type="range">`'s thumb-drag is exactly that.
  If none of those ever fire for such a control on a given platform,
  render suppression never engages in the first place, regardless of any
  fix downstream of that point. The render-suppression guard now also
  engages on the first "input" event, which - unlike pointer/touch/focus
  events - is already proven to fire during a drag (every live-updating
  label next to a slider depends on it).

## [0.9.7] - 2026-07-20

- User reported the zone-duration slider still snaps back after v0.9.6's
  `touch-action: none` attempt. New hypothesis: some Android WebViews may
  not reliably fire the "change" event for a touch-dragged
  `<input type="range">` at all - if so, the new value was never actually
  persisted (no service call ever made), and the *next* re-render (e.g.
  once the 60s safety-net suppression timer expires) shows the old,
  still-unpersisted value, which looks identical to "snapping back".
  Range-input commits (zone duration, pause between zones, rain pause) now
  also fire on `pointerup`/`touchend` as a redundant fallback to "change",
  deduped so a value is never committed twice for the same drag. Still
  unverified on a real device - see [#25](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/25).

## [0.9.6] - 2026-07-20

- Attempted fix for the zone-duration slider still losing focus and
  snapping back to its old value on Android, after v0.9.1/v0.9.4 fixed
  other cases in the same area: added `touch-action: none` to
  `.tile-row-control input[type="range"]`. Sliders sit inside a vertically
  scrollable settings card, and without an explicit `touch-action`, some
  Android WebViews can misinterpret a horizontal drag as an attempted page
  scroll partway through, canceling the native slider drag and reverting
  its value before "change" even fires - independent of anything the card
  itself does with render suppression. Couldn't be reproduced/verified in
  a desktop testing environment; needs live confirmation. See
  [#25](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/25).

## [0.9.5] - 2026-07-20

- Fixed the forecast stat tile still overflowing the card width on narrow
  phone screens even after 0.9.2's word-wrap fix - `.stat-row` forced all 3
  tiles onto a single line regardless of available width. Now wraps onto a
  second row when they don't fit. Fixes [#26](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/26).
- Fixed the pause-between-zones value being able to display/land off the
  whole-minute grid (e.g. "0:50 min") when the stored value predates 0.9.0's
  switch to 60s steps. Rendered value is now always rounded to the nearest
  step. Fixes [#27](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/27).

## [0.9.4] - 2026-07-19

- **Fixed**: values (zone duration, pause between zones, rain pause, start
  times, winter mode, weather settings) could snap back to their old
  number right after being changed, on a real Home Assistant instance over
  a real network. Root cause: rendering was suppressed for a blind fixed
  ~1000ms buffer after a change, assuming the service call would have
  round-tripped by then - true for `screenshots/demo.html`'s effectively
  instant mock, not guaranteed on a real (especially mobile) network. If an
  unrelated hass update lifted suppression before our own change had
  actually landed, the card re-rendered from stale attrs. `_callService()`
  now returns its service-call promise, and rendering stays suppressed
  until that promise actually settles (plus a short buffer for the
  resulting state update to arrive), with an 8s safety-net fallback.
  Verified live with a simulated genuinely-stale background update landing
  mid-flight. Fixes [#24](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/24).

## [0.9.3] - 2026-07-19

- Fixed the new test suite's CI run (introduced in 0.9.2): `pytest tests/`
  failed with `ModuleNotFoundError: No module named 'custom_components'`
  since pytest's default import mode doesn't add the repo root to
  `sys.path`. Added `pytest.ini` (`pythonpath = .`, `asyncio_mode = auto`).
  Verified green on GitHub Actions (Linux) - no runtime code changed, test
  infrastructure only.

## [0.9.2] - 2026-07-19

- Fixed the forecast stat's label overflowing its tile on narrow mobile
  screens for long, unbroken German compound words (e.g.
  "Tageshöchsttemperatur") - CSS only wraps at spaces/hyphens by default,
  so a single long word overruns the tile instead of wrapping. Added
  `overflow-wrap`/`word-break` to `.stat-label`/`.stat-value`. Fixes
  [#23](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/23).
- Added a pytest test suite (`tests/`, `pytest-homeassistant-custom-component`)
  for `IrrigationSequencerManager`'s core logic: zone order/duration/name,
  pause between zones, start-times validation and overlap detection
  (including past-midnight wraparound), winter mode and rain pause
  blocking/expiry, and the weather duration factor's interpolation and
  clamping. Runs automatically via a new GitHub Actions workflow on every
  push/PR. Fixes [#22](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/22).

## [0.9.1] - 2026-07-19

- Reopened and hardened [#14](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/14): zone name field losing focus immediately on tap, confirmed
  real and current on the Home Assistant Companion App (v0.9.0 already
  active, so not the stale-cache issue this session's other reports turned
  out to be). Added a `touchstart` listener alongside `pointerdown` as a
  redundant trigger for the render-suppression guard - some embedded
  WebViews (including the Companion App's) have incomplete or delayed
  Pointer Events support, where `pointerdown` can fail to fire for a tap,
  leaving the guard never engaged.

## [0.9.0] - 2026-07-19

- Renamed "Night start" / "Nachtstart" to "Automatic start" / "Automatischer
  Start" - a scheduled start isn't necessarily at night. Fixes [#12](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/12).
- **Rain pause overhauled**: range extended from 1-14 to 1-24 days
  (`set_rain_pause` service and slider), and the slider now goes down to 0,
  where 0 means "off" and directly clears an active pause - no more need to
  separately find the clear button just to turn it back off. Fixes
  [#11](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/11), [#17](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/17).
- Pause-between-zones slider now steps in whole minutes instead of 10-second
  increments. Fixes [#21](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/21).
- Zone name fields in the settings card are now pre-filled with the
  underlying entity's current name (still fully editable) instead of
  starting blank, both initially and whenever the field is cleared back out
  - makes it possible to tell zones apart at a glance when testing with
    similarly-generic entities. Fixes [#13](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/13).
- Card now logs its version to the browser console on load, and the manual
  installation docs recommend a `?v=...` cache-busting query string on the
  resource URL - plain `.js` Lovelace resources can otherwise be cached
  indefinitely by browsers (especially mobile), silently serving a stale
  copy after an update with no visible sign anything is wrong. Fixes
  [#20](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/20).
- German config flow dialog title no longer embeds the English product name
  ("Irrigation Sequencer einrichten" -> "Bewässerungssequenzer
  einrichten"). The integration's name in the "Add Integration" search and
  the Devices & Services overview still can't be localized - that comes
  directly from `manifest.json` in stock Home Assistant with no per-language
  override for private integrations, the same constraint already documented
  for the missing brand icon. Fixes [#18](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/18).
- Investigated three more reports that turned out not to reproduce against
  the current code when tested directly (live focus/typing simulation for
  the zone-name field, and direct service calls for winter mode on/off both
  via the dedicated service and the raw switch entity) - all evidence points
  to stale cached card JS rather than real bugs, consistent with #20.
  Closed [#14](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/14), [#16](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/16).

## [0.8.1] - 2026-07-19

- **Fixed**: the "Today's forecast high" stat could silently disappear on
  real instances - modern weather integrations (e.g. Met.no, DWD) dropped
  the legacy `forecast` state attribute the card relied on, in favor of the
  `weather.get_forecasts` action. The card now fetches the forecast through
  that action (cached per entity for 10 minutes, re-rendering once it
  resolves), falling back to the legacy attribute first for integrations
  that still expose it. Fixes [#10](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/10).

## [0.8.0] - 2026-07-19

- `light` domain support (added for testing) is now a permanent option,
  not a temporary allowance - decided in #4.
- **Overlap protection for start times**: with 1-3 daily start times, two of
  them landing closer together than a full sequence takes to run (estimated
  from currently configured zone durations + pauses) is now rejected with a
  clear message naming the two conflicting times, both server-side
  (`manager.async_set_start_times`, surfaced as a proper validation error)
  and client-side in the settings card (immediate inline warning, no
  service call made at all if it would overlap).

## [0.7.1] - 2026-07-19

- Refreshed all README screenshots to match the current UI (icon, rain-pause
  slider, multi start-time rows).
- `screenshots/demo.html`'s mock is now genuinely stateful/interactive:
  service calls (zone order/name/duration, pause, start times, winter mode,
  rain pause, weather adjustment) actually mutate the mock sensor and push
  the update back to both cards, instead of being no-ops. Verified 1-3
  start times can be edited and removed back down to 1 through it.

## [0.7.0] - 2026-07-19

- **Fixed**: the zone-name field (and other row content) could lose focus
  after a keystroke or two - even on desktop. Root cause: the whole zone
  row had `draggable="true"` for reordering, so any tiny mouse movement
  while clicking into the text field was interpreted as starting a drag of
  the row, blurring the field instantly. Only the drag-handle icon is
  draggable now; the row itself only handles dragover/drop, so reordering
  still works exactly the same way. Not related to the previous
  render-suppression work, which was confirmed still working correctly.
- Lowered the maximum per-zone duration from 60 to 30 minutes (slider and
  the `set_zone_duration` service).
- **Multiple daily start times**: the sequence can now have 1 to 3 start
  times instead of exactly one, each independently triggering a full run
  (e.g. an early-morning and a late-evening watering). The settings card
  gained add/remove controls for the extra rows; `set_start_time` was
  replaced by `set_start_times` (list of 1-3 times). Existing single
  `start_time` storage is migrated automatically on first load.

## [0.6.0] - 2026-07-19

- Replaced the rain-pause quick-select buttons (1/3/7/14 days) with a
  1-14 day slider, matching the other duration/pause controls.
- Fixed the zone-name field (and other text inputs) losing focus after a
  few keystrokes: rendering could still be forced through in some timing
  windows despite the suppression flag. Both cards and the visual editor
  now also check, as a hard backstop, whether an input/select/textarea in
  the card currently has real DOM focus before ever rebuilding the DOM -
  regardless of any timer state.
- Clarified (no code change): the thin bar above the zone timeline is the
  overall sequence progress (fills 0-100% as the whole run proceeds); the
  colored timeline below it shows the same run per zone, with the active
  segment pulsing. Both are intentional and were working correctly.

## [0.5.0] - 2026-07-19

- Fixed the winter mode toggle failing with "must contain at least one of
  entity_id..." on non-English instances. The card guessed the winter-mode
  switch's `entity_id` by checking whether it contained the literal string
  "winter_mode" - but entity IDs are generated from the (translated) entity
  name, so on a German instance the switch is `..._wintermodus`, and the
  guess silently returned nothing. Added a proper
  `irrigation_sequencer.set_winter_mode` service and switched the card to
  use it, the same way `set_weather_adjustment` already worked - no more
  entity_id guessing.

## [0.4.2] - 2026-07-19

- Fixed sliders/fields visually snapping back to their old value right after
  being committed (e.g. a zone duration flashing back to 10 min). The
  "change" handlers released the render-suppression guard immediately, but
  the service call that actually persists the new value is asynchronous -
  any unrelated Home Assistant update landing in that gap re-rendered the
  card from attributes that hadn't caught up yet. Committing a value now
  keeps rendering suppressed for a short buffer (and then forces one fresh
  render) instead of lifting it immediately.

## [0.4.1] - 2026-07-19

- Fixed the card's language detection falling back to English on recent
  Home Assistant frontends: `hass.language` was the original field the card
  read, but newer frontends moved language to `hass.locale.language` and may
  no longer expose the old alias at all. Now checks `hass.locale.language`
  first, with `hass.language`, `hass.selectedLanguage`, and finally the
  page's `<html lang="...">` attribute as fallbacks.

## [0.4.0] - 2026-07-19

- Replaced the night-start `<input type="time">` with two plain number
  fields (hour/minute). Sidesteps platform-specific native time-picker
  widgets entirely instead of racing against them - just the regular
  numeric keyboard, consistent on Android, iOS, and desktop.

## [0.3.3] - 2026-07-19

- Fixed the 0.3.2 fix: it relied on `focusout` to re-enable rendering, which
  doesn't work for Android's native time picker - that's a real OS dialog,
  so the underlying `<input>` loses DOM focus the instant it opens, long
  before the user has picked anything. Rendering is now only re-enabled once
  the field's own "change" event fires (value actually committed), with a
  60s safety timeout as a fallback. Applied to both cards and the visual
  card editor (e.g. the title field).

## [0.3.2] - 2026-07-19

- Fixed: any input in either card (night start time, weather entity, zone
  name, temperature fields) could get wiped out mid-interaction - e.g. the
  native Android time picker closing itself right after opening. Caused by
  the card re-rendering its entire DOM on every Home Assistant state change
  anywhere in the house, not just its own entity. Now suppressed while any
  field inside the card has focus.

## [0.3.1] - 2026-07-19

- Redesigned icon/logo artwork (flat illustrated sprinkler over soil with
  water and sprouts), also shown at the top of the README
- Documented that Home Assistant's "Devices & Services" list icon is sourced
  exclusively from the public `home-assistant/brands` repository - a locally
  bundled `icon.png` cannot populate that specific spot for a private
  integration, no matter how it's placed

## [0.3.0] - 2026-07-18

- Integration icon/logo (bundled `icon.png`/`icon@2x.png`/`logo.png`/`logo@2x.png`)
- Config flow's default entry name now follows the Home Assistant instance
  language (e.g. "Rasenbewässerung" on a German instance) instead of always
  defaulting to English

## [0.2.0] - 2026-07-18

Initial tagged version, still under active testing on real hardware.

- Multi-zone sequencing: order, per-zone duration, pause between zones,
  custom zone names
- Night start schedule, winter mode, manual 1-14 day rain pause
- Weather-based duration adjustment (linear factor between two temperature
  reference points), with a forecast-based preview on the status card
- Two Lovelace cards (status + settings) styled after Home Assistant Tile
  cards, with a vertical/horizontal layout option
- Options flow to reconfigure zones after initial setup
- 1 to 10 zones; `light` entities accepted alongside `switch`/`valve` for
  testing convenience (tracked in [#4](https://github.com/ReneSattler/ha-irrigation-sequencer/issues/4)
  for later removal/gating)
