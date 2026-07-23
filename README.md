# Irrigation Sequencer

*[Deutsche Version](README.de.md)*

Multi-zone irrigation control for Home Assistant with two graphical Lovelace
cards, styled after Home Assistant's native Tile cards.

Controls 1 to 10 valves or smart plugs in a freely configurable sequence -
each zone can have its own custom name, order and duration - including
pauses between zones, a nightly start time, a winter mode, a manual rain
pause, and an optional weather-based duration adjustment.

![Irrigation Sequencer status and settings cards - idle, 5 zones](screenshots/cards-idle-en.png)
![Irrigation Sequencer status and settings cards - running](screenshots/cards-running-en.png)

*Example with 5 zones. `screenshots/demo.html` is a standalone, interactive
copy of the real cards you can open in any browser to try them out without a
Home Assistant instance.*

## Features

- **Two cards**: a read-only **status card** (schedule timeline, active
  zone, weather factor, next run) and a **settings card** (everything
  configurable), so you can place the status on an overview dashboard and
  keep the settings elsewhere
- **Visual schedule timeline** - all zones and pauses shown as one
  proportional bar, colored by done/active/upcoming, so you can see at a
  glance which valve is running, for how long, and where the pauses are
- **Horizontal or vertical layout** - both cards have a `layout` option
  (also selectable in the visual editor) to switch between a tall, narrow
  arrangement and a wide, short one for wide dashboard columns
- **Custom zone names** - give each valve/plug its own display name,
  independent of the underlying entity name
- **Sequential order** - each zone is irrigated one after another; the order
  can be changed by drag & drop directly in the settings card
- **Per-zone duration** - every zone has its own irrigation duration (minutes)
- **Pause between zones** - configurable wait time before the next zone starts
- **1-3 daily start times** - e.g. an early-morning and a late-evening run, each independently triggering a full sequence. Times that would overlap (closer together than a full run takes) are rejected with a clear message, both in the card and if set via the service.
- **Winter mode** - a single switch that fully disables irrigation
- **Rain pause** - manually pause the sequence for 1 to 24 days (e.g. after
  rainfall) via a single slider that also turns it off again (drag to 0); the
  normal schedule resumes automatically once the pause expires
- **Weather-based duration adjustment** - optionally scale every zone's
  duration by a factor derived from the current outside temperature, linearly
  interpolated between two reference points. Example with the defaults
  (factor 1.0 at 20 °C, factor 2.0 at 30 °C): at 25 °C the factor is 1.5, so a
  5-minute zone runs for 7.5 minutes. The status card also shows today's
  forecast high (when the weather entity provides one) and the factor it
  would result in, so you can see tomorrow's plan at a glance.
- **Optional mobile notification** - pick a device from the settings card
  (sourced from your `notify.mobile_app_*` services) to get a notification
  after each completed run with its duration; defaults to "none" (no
  notifications). The message follows the instance language, same as the
  cards.

## Requirements

The integration controls existing `switch` or `valve` entities (e.g. Shelly
relays, smart plugs, native HA valves). It does not provide any hardware
integration itself - set up your valves/plugs in Home Assistant as usual
first. `light` entities are also accepted - handy for testing with a lamp
when you don't have a real valve on hand, and kept as a permanent option
for experimenting even though it isn't the primary use case.

## Installation via HACS

This is a single HACS entry, category **Integration**. The cards are bundled
inside the integration and register themselves automatically on startup -
no separate "Dashboard" repository entry, no manual Lovelace resource, and
no cache-busting query strings to babysit. Updating the one HACS entry
updates both the backend and the cards together.

1. HACS → three-dot menu (top right) → **Custom repositories**
2. Add `https://github.com/ReneSattler/ha-irrigation-sequencer`, type
   **Integration** → **Add**, then find "Irrigation Sequencer" under HACS's
   Integrations list and click the download button
3. Restart Home Assistant - **use "Restart Home Assistant"** (Settings →
   System → **Restart** → "Restart Home Assistant"), not "Quick Reload".
   Quick Reload only reloads YAML config, not custom integration Python
   code, so after an update it would keep running the old version without
   any error or warning - the version shown under Settings → Devices &
   Services → Irrigation Sequencer wouldn't match what HACS says it
   installed. If that ever happens, do a real restart and it resolves.
4. **Settings → Devices & Services → Add Integration** → search for
   "Irrigation Sequencer" and set it up (select 1 to 10 valve/plug entities)
5. Add the cards to a dashboard (see "Setting up the cards" below) - they're
   already available, no further setup needed

## Manual installation

1. Copy the `custom_components/irrigation_sequencer` folder into your
   `config/custom_components/` directory
2. Restart Home Assistant (see the "Restart" vs "Quick Reload" note above)
   and set up the integration as described above

The cards register themselves the same way as with HACS - no `www/` copy
and no Lovelace resource to add by hand, on either install path.

## Setting up the cards

> **Can't find the cards in the picker, or dashboard shows a "Configuration
> error" right after updating?** Since v1.2.8 the card is registered as a
> proper Lovelace resource (created/updated automatically, no manual setup)
> instead of being injected into the page shell - resources are fetched
> fresh on every dashboard load, so this shouldn't require any cache
> clearing anymore. If you still hit it (e.g. right after upgrading *to*
> v1.2.8 for the first time, since the old injected reference can itself be
> part of a cached page shell), fully close and reopen the tab or app; if
> that alone doesn't fix it, Home Assistant's frontend is a PWA with its
> own service worker that caches the app shell independently of what this
> integration serves - that's Home Assistant core behavior, not something a
> custom integration can control - so clear the browser's cache for your
> Home Assistant URL (desktop: DevTools → Application/Storage → "Clear site
> data", or just clear browsing data for the site; mobile app: clear the
> app's cache/storage in your phone's app settings), then reopen. From then
> on, updates shouldn't need this again.
>
> **Cards show "Configuration error" or vanish after adding/removing a
> zone?** Adding a zone reloads the integration's config entry, and a tab
> that was open beforehand can briefly render against a stale mix of old
> and new state - closing and reopening the tab/app resolves it. If that
> doesn't fix it, open the browser console (F12) and filter for
> "irrigation" - if nothing shows up there, the error is coming from a
> different custom card, not this one (with many HACS cards installed, an
> unrelated console error is easy to mistake for this integration's).

After setting up the integration, add two new Lovelace cards and choose
`Irrigation Sequencer - Status` and `Irrigation Sequencer - Settings`. In the
visual editor of each, select the status sensor entity
(`sensor.<name>_status`). Card text automatically follows the Home Assistant
UI language (falls back to English).

```yaml
type: custom:irrigation-sequencer-status-card
entity: sensor.lawn_irrigation_status
title: Lawn irrigation
```

```yaml
type: custom:irrigation-sequencer-settings-card
entity: sensor.lawn_irrigation_status
title: Lawn irrigation settings
```

Add `layout: horizontal` to either card's config (or pick it in the visual
editor) for a wider, shorter arrangement - handy in a wide dashboard column
or grid section:

![Irrigation Sequencer cards - horizontal layout](screenshots/cards-horizontal-en.png)

## Changing the configuration later

Only the *initial* zone selection is a classic "setup dialog" - everything
else is a live setting, not a one-time config step:

- **Zones (add/remove valves)**: go to **Settings → Devices & Services →
  Irrigation Sequencer → Configure**. This opens an options dialog where you
  can re-select the 1-10 valve/plug entities at any time. Zones that stay
  selected keep their configured name, duration and position; newly added
  zones get default values.
- **Zone names, order, durations, winter mode, rain pause, night start, pause
  between zones, weather adjustment**: these are not part of a config dialog
  at all - they are live settings you change directly through the settings
  card (recommended), through the exposed `switch.*_winter_mode` /
  `switch.*_weather_adjustment` entities, or via the services below (handy
  for your own automations, e.g. "turn on winter mode every November 1st").

## Services

Every setting can also be changed via a service call, e.g. from your own
automations:

| Service | Description |
|---|---|
| `irrigation_sequencer.start_now` | Start the sequence immediately |
| `irrigation_sequencer.stop` | Abort a running sequence immediately |
| `irrigation_sequencer.set_zone_order` | Set the irrigation order of the zones |
| `irrigation_sequencer.set_zone_name` | Set a custom display name for a zone |
| `irrigation_sequencer.set_zone_duration` | Set the irrigation duration of a zone |
| `irrigation_sequencer.set_pause_between_zones` | Set the pause between zones |
| `irrigation_sequencer.set_start_times` | Set the daily start times (1-3) |
| `irrigation_sequencer.set_rain_pause` | Pause irrigation for 1-24 days |
| `irrigation_sequencer.clear_rain_pause` | Clear an active rain pause |
| `irrigation_sequencer.set_winter_mode` | Enable or disable winter mode |
| `irrigation_sequencer.set_weather_adjustment` | Configure temperature-based duration adjustment |
| `irrigation_sequencer.set_notify_target` | Set (or clear) the notify target messaged after a completed run |

You can find the `entry_id` as an attribute on the integration's status
sensor.

## Development

Backend logic (`custom_components/irrigation_sequencer/manager.py`) has a
pytest test suite using
[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component):

```bash
pip install -r requirements-test.txt
pytest tests/ -v
```

Runs automatically on every push/PR via GitHub Actions
(`.github/workflows/tests.yml`).

> **Windows note**: `pytest-homeassistant-custom-component` can fail locally
> on Windows with a `pytest_socket.SocketBlockedError` during test setup -
> asyncio's default `ProactorEventLoop` needs a real OS socket for its
> internal self-pipe, which the test suite's socket-blocking safety net
> rejects. CI (Linux) isn't affected. If you need to run tests locally on
> Windows, use WSL, or try forcing the selector event loop policy
> (`asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())`)
> before pytest starts - this repo's `tests/conftest.py` already does this,
> though it hasn't fully resolved it in every environment tested so far.

## License

MIT - see [LICENSE](LICENSE)
