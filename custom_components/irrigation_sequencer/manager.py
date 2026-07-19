"""Runtime manager: state, persistence and the irrigation sequence logic."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_PAUSE_SECONDS,
    DEFAULT_START_TIME,
    DEFAULT_WEATHER_HOT_FACTOR,
    DEFAULT_WEATHER_HOT_TEMP,
    DEFAULT_WEATHER_REFERENCE_TEMP,
    DEFAULT_ZONE_DURATION_MINUTES,
    MAX_START_TIMES,
    MAX_WEATHER_FACTOR,
    MIN_START_TIMES,
    MIN_WEATHER_FACTOR,
    STATE_IDLE,
    STATE_PAUSED_BETWEEN_ZONES,
    STATE_RAIN_PAUSE,
    STATE_RUNNING,
    STATE_WINTER_MODE,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class IrrigationSequencerManager:
    """Holds configuration/state and drives the irrigation sequence."""

    def __init__(self, hass: HomeAssistant, entry_id: str, zone_entities: list[str]) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}_{entry_id}")

        self.zones: list[dict[str, Any]] = [
            {
                "entity_id": entity_id,
                "name": "",
                "duration_minutes": DEFAULT_ZONE_DURATION_MINUTES,
                "position": index,
            }
            for index, entity_id in enumerate(zone_entities)
        ]
        self.pause_between_zones_seconds: int = DEFAULT_PAUSE_SECONDS
        self.start_times: list[str] = [DEFAULT_START_TIME]
        self.winter_mode: bool = False
        self.rain_pause_until: str | None = None

        self.weather_adjustment_enabled: bool = False
        self.weather_entity: str | None = None
        self.weather_reference_temp: float = DEFAULT_WEATHER_REFERENCE_TEMP
        self.weather_hot_temp: float = DEFAULT_WEATHER_HOT_TEMP
        self.weather_hot_factor: float = DEFAULT_WEATHER_HOT_FACTOR

        self.status: str = STATE_IDLE
        self.current_zone_index: int | None = None
        # Unlike current_zone_index, this stays set through the pause after a
        # zone (current_zone_index is None while paused) so the UI can still
        # tell which zone just finished.
        self.last_zone_index: int | None = None
        self.seconds_remaining_zone: int = 0
        self.seconds_remaining_total: int = 0

        self._run_task: asyncio.Task | None = None
        self._stop_requested = False
        self._unsub_daily_triggers: list[Callable[[], None]] = []
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ #
    # Setup / persistence
    # ------------------------------------------------------------------ #

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data:
            stored_zones = {z["entity_id"]: z for z in data.get("zones", [])}
            for zone in self.zones:
                stored = stored_zones.get(zone["entity_id"])
                if stored:
                    zone["name"] = stored.get("name", "")
                    zone["duration_minutes"] = stored.get(
                        "duration_minutes", DEFAULT_ZONE_DURATION_MINUTES
                    )
                    zone["position"] = stored.get("position", zone["position"])
            self.zones.sort(key=lambda z: z["position"])

            self.pause_between_zones_seconds = data.get(
                "pause_between_zones_seconds", DEFAULT_PAUSE_SECONDS
            )
            # Migrate the pre-0.7 single "start_time" field to the new
            # "start_times" list transparently on first load.
            if "start_times" in data:
                self.start_times = data["start_times"] or [DEFAULT_START_TIME]
            elif "start_time" in data:
                self.start_times = [data["start_time"]]
            self.winter_mode = data.get("winter_mode", False)
            self.rain_pause_until = data.get("rain_pause_until")

            self.weather_adjustment_enabled = data.get("weather_adjustment_enabled", False)
            self.weather_entity = data.get("weather_entity")
            self.weather_reference_temp = data.get(
                "weather_reference_temp", DEFAULT_WEATHER_REFERENCE_TEMP
            )
            self.weather_hot_temp = data.get("weather_hot_temp", DEFAULT_WEATHER_HOT_TEMP)
            self.weather_hot_factor = data.get("weather_hot_factor", DEFAULT_WEATHER_HOT_FACTOR)

        self._schedule_daily_trigger()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "zones": self.zones,
                "pause_between_zones_seconds": self.pause_between_zones_seconds,
                "start_times": self.start_times,
                "winter_mode": self.winter_mode,
                "rain_pause_until": self.rain_pause_until,
                "weather_adjustment_enabled": self.weather_adjustment_enabled,
                "weather_entity": self.weather_entity,
                "weather_reference_temp": self.weather_reference_temp,
                "weather_hot_temp": self.weather_hot_temp,
                "weather_hot_factor": self.weather_hot_factor,
            }
        )

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    @callback
    def _notify_listeners(self) -> None:
        for listener in self._listeners:
            listener()

    async def async_unload(self) -> None:
        for unsub in self._unsub_daily_triggers:
            unsub()
        self._unsub_daily_triggers = []
        if self._run_task and not self._run_task.done():
            self._stop_requested = True
            await self._run_task

    # ------------------------------------------------------------------ #
    # Configuration changes (called from services / the card)
    # ------------------------------------------------------------------ #

    async def async_set_zone_order(self, ordered_entity_ids: list[str]) -> None:
        zones_by_id = {z["entity_id"]: z for z in self.zones}
        new_zones = []
        for position, entity_id in enumerate(ordered_entity_ids):
            zone = zones_by_id.get(entity_id)
            if zone is None:
                continue
            zone["position"] = position
            new_zones.append(zone)
        if len(new_zones) == len(self.zones):
            self.zones = new_zones
            await self._async_save()
            self._notify_listeners()

    async def async_set_zone_duration(self, entity_id: str, minutes: int) -> None:
        for zone in self.zones:
            if zone["entity_id"] == entity_id:
                zone["duration_minutes"] = max(1, int(minutes))
                await self._async_save()
                self._notify_listeners()
                return

    async def async_set_zone_name(self, entity_id: str, name: str) -> None:
        for zone in self.zones:
            if zone["entity_id"] == entity_id:
                zone["name"] = name.strip()
                await self._async_save()
                self._notify_listeners()
                return

    async def async_set_pause_between_zones(self, seconds: int) -> None:
        self.pause_between_zones_seconds = max(0, int(seconds))
        await self._async_save()
        self._notify_listeners()

    async def async_set_start_times(self, start_times: list[str]) -> None:
        if not MIN_START_TIMES <= len(start_times) <= MAX_START_TIMES:
            raise ServiceValidationError(
                f"start_times must have {MIN_START_TIMES}-{MAX_START_TIMES} entries"
            )
        sorted_times = sorted(start_times)
        self._raise_if_start_times_overlap(sorted_times)
        self.start_times = sorted_times
        await self._async_save()
        self._schedule_daily_trigger()
        self._notify_listeners()

    def _raise_if_start_times_overlap(self, sorted_times: list[str]) -> None:
        """Reject start times closer together than a full sequence takes to
        run. The duration is an estimate from the currently configured zone
        durations/pauses (unadjusted by weather, which varies at runtime and
        can't be known in advance) - good enough to catch the common case of
        two triggers landing on top of each other."""
        if len(sorted_times) < 2:
            return

        def to_seconds(value: str) -> int:
            hour, minute, second = (int(part) for part in value.split(":"))
            return hour * 3600 + minute * 60 + second

        duration = self.estimated_total_seconds
        seconds = [to_seconds(t) for t in sorted_times]
        for index, current in enumerate(seconds):
            next_index = (index + 1) % len(seconds)
            gap = (seconds[next_index] - current) % 86400
            if gap < duration:
                raise ServiceValidationError(
                    f"Start times {sorted_times[index]} and {sorted_times[next_index]} are only "
                    f"{gap // 60} min apart, but a full sequence currently takes about "
                    f"{duration // 60} min - they would overlap."
                )

    async def async_set_winter_mode(self, enabled: bool) -> None:
        self.winter_mode = enabled
        await self._async_save()
        self._notify_listeners()

    async def async_set_rain_pause(self, days: int) -> None:
        until = date.today() + timedelta(days=int(days))
        self.rain_pause_until = until.isoformat()
        await self._async_save()
        self._notify_listeners()

    async def async_clear_rain_pause(self) -> None:
        self.rain_pause_until = None
        await self._async_save()
        self._notify_listeners()

    async def async_set_weather_adjustment(
        self,
        enabled: bool,
        weather_entity: str | None,
        reference_temp: float,
        hot_temp: float,
        hot_factor: float,
    ) -> None:
        self.weather_adjustment_enabled = enabled
        self.weather_entity = weather_entity or None
        self.weather_reference_temp = float(reference_temp)
        self.weather_hot_temp = float(hot_temp)
        self.weather_hot_factor = float(hot_factor)
        await self._async_save()
        self._notify_listeners()

    # ------------------------------------------------------------------ #
    # Weather-based duration factor
    # ------------------------------------------------------------------ #

    @property
    def weather_current_temp(self) -> float | None:
        """Return the current outside temperature from the configured weather entity."""
        if not self.weather_entity:
            return None
        state = self.hass.states.get(self.weather_entity)
        if state is None:
            return None
        temp = state.attributes.get("temperature")
        return float(temp) if temp is not None else None

    @property
    def weather_current_factor(self) -> float:
        """Linear factor derived from the current temperature.

        factor(reference_temp) = 1.0, factor(hot_temp) = hot_factor, extrapolated
        linearly beyond those two points and clamped to a sane range.
        """
        if not self.weather_adjustment_enabled:
            return 1.0
        temp = self.weather_current_temp
        if temp is None:
            return 1.0

        span = self.weather_hot_temp - self.weather_reference_temp
        if span == 0:
            return 1.0

        slope = (self.weather_hot_factor - 1.0) / span
        factor = 1.0 + (temp - self.weather_reference_temp) * slope
        return max(MIN_WEATHER_FACTOR, min(MAX_WEATHER_FACTOR, factor))

    # ------------------------------------------------------------------ #
    # Scheduling
    # ------------------------------------------------------------------ #

    def _schedule_daily_trigger(self) -> None:
        for unsub in self._unsub_daily_triggers:
            unsub()
        self._unsub_daily_triggers = [
            async_track_time_change(
                self.hass,
                self._handle_daily_trigger,
                hour=int(hour),
                minute=int(minute),
                second=int(second),
            )
            for hour, minute, second in (t.split(":") for t in self.start_times)
        ]

    @callback
    def _handle_daily_trigger(self, now: datetime) -> None:
        self.hass.async_create_task(self.async_start_now(triggered_by_schedule=True))

    def _is_blocked(self) -> tuple[bool, str | None]:
        if self.winter_mode:
            return True, STATE_WINTER_MODE
        if self.rain_pause_until:
            pause_until = date.fromisoformat(self.rain_pause_until)
            if date.today() < pause_until:
                return True, STATE_RAIN_PAUSE
            # Rain pause has expired: clear it lazily here instead of
            # scheduling a separate timer, since this is checked on every
            # start attempt and status read anyway.
            self.rain_pause_until = None
            self.hass.async_create_task(self._async_save())
        return False, None

    @property
    def next_run(self) -> str | None:
        blocked, _ = self._is_blocked()
        if blocked:
            return None
        now = dt_util.now()
        candidates = []
        for start_time in self.start_times:
            hour, minute, second = (int(part) for part in start_time.split(":"))
            candidate = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            candidates.append(candidate)
        return min(candidates).isoformat()

    # ------------------------------------------------------------------ #
    # Running the sequence
    # ------------------------------------------------------------------ #

    async def async_start_now(self, triggered_by_schedule: bool = False) -> None:
        if self._run_task and not self._run_task.done():
            _LOGGER.warning("Irrigation sequence is already running, ignoring start request")
            return

        if triggered_by_schedule:
            blocked, reason = self._is_blocked()
            if blocked:
                self.status = reason or STATE_IDLE
                self._notify_listeners()
                return

        if not self.zones:
            _LOGGER.warning("No zones configured, aborting start")
            return

        self._stop_requested = False
        self._run_task = self.hass.async_create_task(self._async_run_sequence())

    async def async_stop(self) -> None:
        self._stop_requested = True
        if self._run_task and not self._run_task.done():
            await self._run_task

    def _zone_duration_seconds(self, zone: dict[str, Any]) -> int:
        base_seconds = zone["duration_minutes"] * 60
        return max(1, round(base_seconds * self.weather_current_factor))

    @property
    def estimated_total_seconds(self) -> int:
        """Sequence duration estimate from the currently configured zone
        durations and pauses, without the weather factor (unknowable ahead
        of the actual run). Used for the start-times overlap check and
        exposed to the card for the same client-side check."""
        return sum(zone["duration_minutes"] * 60 for zone in self.zones) + (
            self.pause_between_zones_seconds * max(0, len(self.zones) - 1)
        )

    async def _async_run_sequence(self) -> None:
        total_seconds = sum(
            self._zone_duration_seconds(zone) for zone in self.zones
        ) + self.pause_between_zones_seconds * max(0, len(self.zones) - 1)
        self.seconds_remaining_total = total_seconds

        try:
            for index, zone in enumerate(self.zones):
                if self._stop_requested:
                    break

                self.current_zone_index = index
                self.last_zone_index = index
                self.status = STATE_RUNNING
                duration_seconds = self._zone_duration_seconds(zone)
                self.seconds_remaining_zone = duration_seconds
                self._notify_listeners()

                await self._async_set_valve(zone["entity_id"], True)
                # Tick once per second (instead of a single asyncio.sleep for
                # the whole duration) so the countdown attributes stay live
                # for the sensor/card and a stop request is picked up quickly.
                for _ in range(duration_seconds):
                    if self._stop_requested:
                        break
                    await asyncio.sleep(1)
                    self.seconds_remaining_zone -= 1
                    self.seconds_remaining_total -= 1
                    self._notify_listeners()
                await self._async_set_valve(zone["entity_id"], False)

                if self._stop_requested:
                    break

                is_last_zone = index == len(self.zones) - 1
                if not is_last_zone and self.pause_between_zones_seconds > 0:
                    self.status = STATE_PAUSED_BETWEEN_ZONES
                    self.current_zone_index = None
                    remaining = self.pause_between_zones_seconds
                    self._notify_listeners()
                    for _ in range(remaining):
                        if self._stop_requested:
                            break
                        await asyncio.sleep(1)
                        self.seconds_remaining_total -= 1
                        self._notify_listeners()
        finally:
            for zone in self.zones:
                await self._async_set_valve(zone["entity_id"], False)
            self.status = STATE_IDLE
            self.current_zone_index = None
            self.last_zone_index = None
            self.seconds_remaining_zone = 0
            self.seconds_remaining_total = 0
            self._stop_requested = False
            self._notify_listeners()

    async def _async_set_valve(self, entity_id: str, turn_on: bool) -> None:
        # Zones can be valve, switch, or light entities (the last one mostly
        # useful for testing with a lamp instead of a real relay) - each
        # domain has its own turn on/off service pair.
        domain = entity_id.split(".")[0]
        if domain == "valve":
            service = "open_valve" if turn_on else "close_valve"
            service_domain = "valve"
        elif domain == "light":
            service = "turn_on" if turn_on else "turn_off"
            service_domain = "light"
        else:
            service = "turn_on" if turn_on else "turn_off"
            service_domain = "switch"
        await self.hass.services.async_call(
            service_domain, service, {"entity_id": entity_id}, blocking=True
        )
