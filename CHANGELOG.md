# Changelog

All notable changes to this project are documented here. Versioning follows
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`, bumped in
`custom_components/irrigation_sequencer/manifest.json` and tagged as a
GitHub release (`vX.Y.Z`) once pushed.

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
