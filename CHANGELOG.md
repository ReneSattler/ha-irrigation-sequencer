# Changelog

All notable changes to this project are documented here. Versioning follows
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`, bumped in
`custom_components/irrigation_sequencer/manifest.json` and tagged as a
GitHub release (`vX.Y.Z`) once pushed.

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
