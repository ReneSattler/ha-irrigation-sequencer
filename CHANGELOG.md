# Changelog

All notable changes to this project are documented here. Versioning follows
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`, bumped in
`custom_components/irrigation_sequencer/manifest.json` and tagged as a
GitHub release (`vX.Y.Z`) once pushed.

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
