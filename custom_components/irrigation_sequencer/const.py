"""Constants for the Irrigation Sequencer integration."""
from __future__ import annotations

DOMAIN = "irrigation_sequencer"
PLATFORMS = ["sensor", "switch", "button"]

CONF_ZONE_ENTITIES = "zone_entities"

DEFAULT_ZONE_DURATION_MINUTES = 10
MAX_ZONE_DURATION_MINUTES = 30
DEFAULT_PAUSE_SECONDS = 120
DEFAULT_START_TIME = "05:00:00"
MIN_START_TIMES = 1
MAX_START_TIMES = 3

MIN_ZONES = 1
MAX_ZONES = 10

# Default value for the config flow's free-text "name" field, picked by the
# instance's configured language (schema defaults are static, unlike
# strings.json translations). Extend as more languages are added.
DEFAULT_NAME_BY_LANGUAGE = {
    "en": "Lawn Irrigation",
    "de": "Rasenbewässerung",
}

# Whether a zone that came on outside a run gets closed again. On by
# default: the case that prompted this was a relay configured to switch on
# after a power cut, i.e. the garden quietly watering itself for however
# long nobody noticed. Turning it off keeps the reporting but leaves the
# valve alone - the right choice if you also water manually from the
# vendor's own app, which is indistinguishable from the device acting
# alone (see UNEXPECTED_SOURCE_DEVICE).
DEFAULT_AUTO_OFF_UNEXPECTED = True

MIN_RAIN_PAUSE_DAYS = 1
MAX_RAIN_PAUSE_DAYS = 24

# Weather-based duration adjustment: linear interpolation between
# (reference_temp -> factor 1.0) and (hot_temp -> hot_factor), extrapolated
# beyond those points and clamped to a sane range.
DEFAULT_WEATHER_REFERENCE_TEMP = 20.0
DEFAULT_WEATHER_HOT_TEMP = 30.0
DEFAULT_WEATHER_HOT_FACTOR = 2.0
MIN_WEATHER_FACTOR = 0.1
MAX_WEATHER_FACTOR = 3.0

# Which temperature the factor is derived from.
#
# "forecast_high" is the default because runs are typically scheduled for
# the night or early morning, when the current temperature is at its
# lowest and says nothing about how hot the day will get. Deriving the
# factor from it inverts the feature's intent: a 37 deg day with a 01:00
# run would water at ~0.8x instead of ~2.7x, i.e. least on the hottest
# days. The daily forecast's first entry covers the day the run starts in,
# which is what "how much water does the lawn need today" depends on.
#
# "current" keeps the pre-1.3.0 behaviour for anyone who wants it.
WEATHER_TEMP_SOURCE_FORECAST_HIGH = "forecast_high"
WEATHER_TEMP_SOURCE_CURRENT = "current"
WEATHER_TEMP_SOURCES = [WEATHER_TEMP_SOURCE_FORECAST_HIGH, WEATHER_TEMP_SOURCE_CURRENT]
DEFAULT_WEATHER_TEMP_SOURCE = WEATHER_TEMP_SOURCE_FORECAST_HIGH

# How often the cached forecast high is refreshed. The value is also
# refreshed unconditionally right before a sequence starts, so this only
# governs how fresh the number shown on the card is.
FORECAST_REFRESH_MINUTES = 30

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = f"{DOMAIN}_state"

STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_PAUSED_BETWEEN_ZONES = "paused_between_zones"
STATE_WINTER_MODE = "winter_mode"
STATE_RAIN_PAUSE = "rain_pause"

SERVICE_SET_ZONE_ORDER = "set_zone_order"
SERVICE_SET_ZONE_NAME = "set_zone_name"
SERVICE_SET_ZONE_DURATION = "set_zone_duration"
SERVICE_SET_PAUSE_BETWEEN_ZONES = "set_pause_between_zones"
SERVICE_SET_START_TIMES = "set_start_times"
SERVICE_SET_RAIN_PAUSE = "set_rain_pause"
SERVICE_CLEAR_RAIN_PAUSE = "clear_rain_pause"
SERVICE_SET_WEATHER_ADJUSTMENT = "set_weather_adjustment"
SERVICE_SET_WINTER_MODE = "set_winter_mode"
SERVICE_SET_NOTIFY_TARGET = "set_notify_target"
SERVICE_SET_AUTO_OFF_UNEXPECTED = "set_auto_off_unexpected"
SERVICE_START_NOW = "start_now"
SERVICE_STOP = "stop"

ATTR_ZONES = "zones"
ATTR_PAUSE_BETWEEN_ZONES_SECONDS = "pause_between_zones_seconds"
ATTR_START_TIMES = "start_times"
ATTR_WINTER_MODE = "winter_mode"
ATTR_RAIN_PAUSE_UNTIL = "rain_pause_until"
ATTR_CURRENT_ZONE_INDEX = "current_zone_index"
ATTR_LAST_ZONE_INDEX = "last_zone_index"
ATTR_CURRENT_ZONE_ENTITY_ID = "current_zone_entity_id"
ATTR_SECONDS_REMAINING_ZONE = "seconds_remaining_zone"
ATTR_SECONDS_REMAINING_TOTAL = "seconds_remaining_total"
ATTR_NEXT_RUN = "next_run"
ATTR_ESTIMATED_TOTAL_SECONDS = "estimated_total_seconds"
ATTR_WEATHER_ADJUSTMENT_ENABLED = "weather_adjustment_enabled"
ATTR_WEATHER_ENTITY = "weather_entity"
ATTR_WEATHER_REFERENCE_TEMP = "weather_reference_temp"
ATTR_WEATHER_HOT_TEMP = "weather_hot_temp"
ATTR_WEATHER_HOT_FACTOR = "weather_hot_factor"
ATTR_WEATHER_CURRENT_TEMP = "weather_current_temp"
# The factor that will actually be applied to every zone's duration. Named
# "current" since 0.x and kept for compatibility with already-installed
# cards; since 1.3.0 it is derived from whichever temperature source is
# configured, not necessarily the current temperature.
ATTR_WEATHER_CURRENT_FACTOR = "weather_current_factor"
ATTR_WEATHER_TEMP_SOURCE = "weather_temp_source"
ATTR_WEATHER_FORECAST_HIGH = "weather_forecast_high"
ATTR_WEATHER_EFFECTIVE_TEMP = "weather_effective_temp"
# Total run time with the weather factor applied - what the sequence will
# really take. Kept separate from ATTR_ESTIMATED_TOTAL_SECONDS, which stays
# unscaled because the start-time overlap check is validated against it.
ATTR_SCALED_TOTAL_SECONDS = "scaled_total_seconds"
ATTR_NOTIFY_TARGET = "notify_target"
# Per-zone record of what actually happened in the most recent run - the
# factor/target the code computed at zone start vs. how long the zone was
# really on for, so a mismatch (e.g. a device cutting itself off early) is
# visible without digging through logs.
ATTR_LAST_RUN_ZONES = "last_run_zones"
# Zones that switched on while no sequence was running, with who/what
# appears to have done it. See UNEXPECTED_SOURCE_* below.
ATTR_UNEXPECTED_ZONE_ACTIVATIONS = "unexpected_zone_activations"
ATTR_AUTO_OFF_UNEXPECTED_ENABLED = "auto_off_unexpected_enabled"

# How a zone came to be on outside a run, classified from the state
# change's context (Home Assistant tags every state change with one):
#   - a context carrying a user id means a person clicked it in the HA UI
#   - no user id but a parent id means another automation/script did it
#   - neither means nothing in Home Assistant asked for it at all
#
# That last case is genuinely ambiguous and the wording says so: a person
# tapping the zone in the vendor's own app looks *identical* to the relay
# switching itself on, because neither reaches Home Assistant as anything
# more than "this entity is now on". Home Assistant has no more
# information to go on here, so neither do we.
UNEXPECTED_SOURCE_USER = "ha_user"
UNEXPECTED_SOURCE_AUTOMATION = "other_automation"
UNEXPECTED_SOURCE_DEVICE = "outside_home_assistant"
# A zone found already on when Home Assistant finished starting - the
# device-side case we'd otherwise miss entirely, since a power cut that
# flips a relay on usually takes Home Assistant down with it.
UNEXPECTED_SOURCE_STARTUP = "already_on_at_startup"

# Cap on the retained activation history, so a device stuck in a loop
# can't grow the attribute (and the stored state file) without bound.
MAX_UNEXPECTED_ACTIVATIONS_KEPT = 20
# Per-entity quiet period after handling one activation. Without it, a
# device that immediately switches itself back on would produce an endless
# turn-off/turn-on ping-pong of log lines and service calls.
UNEXPECTED_ACTIVATION_COOLDOWN_SECONDS = 30

# Notification sent after a completed run, when a notify target is
# configured. Keyed by hass.config.language, same pattern as
# DEFAULT_NAME_BY_LANGUAGE - falls back to "en" for unmapped languages.
NOTIFY_MESSAGES_BY_LANGUAGE = {
    "en": {
        "title": "Irrigation finished",
        "message": "Ran for {minutes} minutes.",
    },
    "de": {
        "title": "Bewässerung abgeschlossen",
        "message": "Lief {minutes} Minuten.",
    },
}

# Notification sent when a zone was switched on outside a run and turned
# back off again. Same language handling as NOTIFY_MESSAGES_BY_LANGUAGE.
UNEXPECTED_ACTIVATION_MESSAGES_BY_LANGUAGE = {
    "en": {
        "title": "Irrigation zone turned on outside a run",
        "message_turned_off": "{zone} was switched on {source}. It has been turned off again.",
        "message_left_on": "{zone} was switched on {source}. It was left running.",
        "sources": {
            UNEXPECTED_SOURCE_AUTOMATION: "by another automation or script",
            UNEXPECTED_SOURCE_DEVICE: (
                "outside Home Assistant - the vendor app, a button on the device, "
                "or the device switching itself on"
            ),
            UNEXPECTED_SOURCE_STARTUP: "and was already on when Home Assistant started",
        },
    },
    "de": {
        "title": "Bewässerungszone außerhalb eines Laufs eingeschaltet",
        "message_turned_off": "{zone} wurde {source} eingeschaltet und wieder ausgeschaltet.",
        "message_left_on": "{zone} wurde {source} eingeschaltet und läuft weiter.",
        "sources": {
            UNEXPECTED_SOURCE_AUTOMATION: "von einer anderen Automatisierung oder einem Skript",
            UNEXPECTED_SOURCE_DEVICE: (
                "außerhalb von Home Assistant - Hersteller-App, Taster am Gerät "
                "oder das Gerät selbst"
            ),
            UNEXPECTED_SOURCE_STARTUP: "vor dem Start von Home Assistant",
        },
    },
}
