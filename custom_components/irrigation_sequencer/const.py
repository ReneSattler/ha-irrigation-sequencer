"""Constants for the Irrigation Sequencer integration."""
from __future__ import annotations

DOMAIN = "irrigation_sequencer"
PLATFORMS = ["sensor", "switch", "button"]

CONF_ZONE_ENTITIES = "zone_entities"

DEFAULT_ZONE_DURATION_MINUTES = 10
DEFAULT_PAUSE_SECONDS = 120
DEFAULT_START_TIME = "05:00:00"

MIN_ZONES = 2
MAX_ZONES = 10

MIN_RAIN_PAUSE_DAYS = 1
MAX_RAIN_PAUSE_DAYS = 14

# Weather-based duration adjustment: linear interpolation between
# (reference_temp -> factor 1.0) and (hot_temp -> hot_factor), extrapolated
# beyond those points and clamped to a sane range.
DEFAULT_WEATHER_REFERENCE_TEMP = 20.0
DEFAULT_WEATHER_HOT_TEMP = 30.0
DEFAULT_WEATHER_HOT_FACTOR = 2.0
MIN_WEATHER_FACTOR = 0.1
MAX_WEATHER_FACTOR = 3.0

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
SERVICE_SET_START_TIME = "set_start_time"
SERVICE_SET_RAIN_PAUSE = "set_rain_pause"
SERVICE_CLEAR_RAIN_PAUSE = "clear_rain_pause"
SERVICE_SET_WEATHER_ADJUSTMENT = "set_weather_adjustment"
SERVICE_START_NOW = "start_now"
SERVICE_STOP = "stop"

ATTR_ZONES = "zones"
ATTR_PAUSE_BETWEEN_ZONES_SECONDS = "pause_between_zones_seconds"
ATTR_START_TIME = "start_time"
ATTR_WINTER_MODE = "winter_mode"
ATTR_RAIN_PAUSE_UNTIL = "rain_pause_until"
ATTR_CURRENT_ZONE_INDEX = "current_zone_index"
ATTR_CURRENT_ZONE_ENTITY_ID = "current_zone_entity_id"
ATTR_SECONDS_REMAINING_ZONE = "seconds_remaining_zone"
ATTR_SECONDS_REMAINING_TOTAL = "seconds_remaining_total"
ATTR_NEXT_RUN = "next_run"
ATTR_WEATHER_ADJUSTMENT_ENABLED = "weather_adjustment_enabled"
ATTR_WEATHER_ENTITY = "weather_entity"
ATTR_WEATHER_REFERENCE_TEMP = "weather_reference_temp"
ATTR_WEATHER_HOT_TEMP = "weather_hot_temp"
ATTR_WEATHER_HOT_FACTOR = "weather_hot_factor"
ATTR_WEATHER_CURRENT_TEMP = "weather_current_temp"
ATTR_WEATHER_CURRENT_FACTOR = "weather_current_factor"
