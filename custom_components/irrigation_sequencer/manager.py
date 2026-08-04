"""Runtime manager: state, persistence and the irrigation sequence logic."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_PAUSE_SECONDS,
    DEFAULT_START_TIME,
    DEFAULT_WEATHER_HOT_FACTOR,
    DEFAULT_WEATHER_HOT_TEMP,
    DEFAULT_WEATHER_REFERENCE_TEMP,
    DEFAULT_WEATHER_TEMP_SOURCE,
    DEFAULT_ZONE_DURATION_MINUTES,
    FORECAST_REFRESH_MINUTES,
    MAX_START_TIMES,
    MAX_WEATHER_FACTOR,
    MIN_START_TIMES,
    MIN_WEATHER_FACTOR,
    NOTIFY_MESSAGES_BY_LANGUAGE,
    STATE_IDLE,
    STATE_PAUSED_BETWEEN_ZONES,
    STATE_RAIN_PAUSE,
    STATE_RUNNING,
    STATE_WINTER_MODE,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
    WEATHER_TEMP_SOURCE_CURRENT,
    WEATHER_TEMP_SOURCE_FORECAST_HIGH,
    WEATHER_TEMP_SOURCES,
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
        # Notify service name (e.g. "mobile_app_my_phone", the part after
        # "notify.") to message after a completed run, or None to disable.
        self.notify_target: str | None = None

        self.weather_adjustment_enabled: bool = False
        self.weather_entity: str | None = None
        self.weather_reference_temp: float = DEFAULT_WEATHER_REFERENCE_TEMP
        self.weather_hot_temp: float = DEFAULT_WEATHER_HOT_TEMP
        self.weather_hot_factor: float = DEFAULT_WEATHER_HOT_FACTOR
        self.weather_temp_source: str = DEFAULT_WEATHER_TEMP_SOURCE
        # Cached daily forecast high. Fetching it needs an async service
        # call, but the factor is read from synchronous properties during a
        # run, so it can't be fetched on demand there.
        self.weather_forecast_high: float | None = None
        self._unsub_forecast_refresh: Callable[[], None] | None = None

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
        # What actually happened in the most recent run, one entry per zone,
        # appended live as each zone finishes - see _async_run_sequence.
        self.last_run_zones: list[dict[str, Any]] = []

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
            self.notify_target = data.get("notify_target")

            self.weather_adjustment_enabled = data.get("weather_adjustment_enabled", False)
            self.weather_entity = data.get("weather_entity")
            self.weather_reference_temp = data.get(
                "weather_reference_temp", DEFAULT_WEATHER_REFERENCE_TEMP
            )
            self.weather_hot_temp = data.get("weather_hot_temp", DEFAULT_WEATHER_HOT_TEMP)
            self.weather_hot_factor = data.get("weather_hot_factor", DEFAULT_WEATHER_HOT_FACTOR)
            stored_source = data.get("weather_temp_source", DEFAULT_WEATHER_TEMP_SOURCE)
            if stored_source in WEATHER_TEMP_SOURCES:
                self.weather_temp_source = stored_source

        self._schedule_daily_trigger()
        self._schedule_forecast_refresh()

        # Don't fetch during setup: weather integrations are often not up
        # yet at that point, and calling weather.get_forecasts against an
        # entity that doesn't exist yet makes Home Assistant log
        # "Referenced entities ... are missing or not currently available"
        # - our warning, in the user's log, for a fetch that was never
        # going to succeed. Wait until startup has finished instead.
        async def _initial_forecast(_hass) -> None:
            await self.async_refresh_forecast()

        async_at_started(self.hass, _initial_forecast)

    @callback
    def _schedule_forecast_refresh(self) -> None:
        if self._unsub_forecast_refresh is not None:
            self._unsub_forecast_refresh()

        async def _refresh(_now) -> None:
            await self.async_refresh_forecast()

        self._unsub_forecast_refresh = async_track_time_interval(
            self.hass, _refresh, timedelta(minutes=FORECAST_REFRESH_MINUTES)
        )

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "zones": self.zones,
                "pause_between_zones_seconds": self.pause_between_zones_seconds,
                "start_times": self.start_times,
                "winter_mode": self.winter_mode,
                "rain_pause_until": self.rain_pause_until,
                "notify_target": self.notify_target,
                "weather_adjustment_enabled": self.weather_adjustment_enabled,
                "weather_entity": self.weather_entity,
                "weather_reference_temp": self.weather_reference_temp,
                "weather_hot_temp": self.weather_hot_temp,
                "weather_hot_factor": self.weather_hot_factor,
                "weather_temp_source": self.weather_temp_source,
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
        if self._unsub_forecast_refresh is not None:
            self._unsub_forecast_refresh()
            self._unsub_forecast_refresh = None
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
            new_zones.append({**zone, "position": position})
        if len(new_zones) == len(self.zones):
            self.zones = new_zones
            await self._async_save()
            self._notify_listeners()

    async def async_set_zone_duration(self, entity_id: str, minutes: int) -> None:
        if not any(z["entity_id"] == entity_id for z in self.zones):
            return
        clamped = max(1, int(minutes))
        # Build a new list/dicts rather than mutating the existing zone dict
        # in place: extra_state_attributes hands this same list out by
        # reference on every state write, so an in-place edit left HA's
        # state-diffing unable to tell the "zones" attribute had changed at
        # all (old and new state ended up pointing at the identical,
        # already-mutated object) - the browser's status card timeline
        # silently never picked up a duration change unless something else
        # happened to change too. Scalar attributes like
        # pause_between_zones_seconds don't have this problem since
        # reassigning an int is inherently a fresh value.
        self.zones = [
            {**z, "duration_minutes": clamped} if z["entity_id"] == entity_id else z
            for z in self.zones
        ]
        await self._async_save()
        self._notify_listeners()

    async def async_set_zone_name(self, entity_id: str, name: str) -> None:
        if not any(z["entity_id"] == entity_id for z in self.zones):
            return
        stripped = name.strip()
        self.zones = [
            {**z, "name": stripped} if z["entity_id"] == entity_id else z
            for z in self.zones
        ]
        await self._async_save()
        self._notify_listeners()

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

    async def async_set_notify_target(self, target: str | None) -> None:
        self.notify_target = target or None
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
        temp_source: str | None = None,
    ) -> None:
        self.weather_adjustment_enabled = enabled
        self.weather_entity = weather_entity or None
        self.weather_reference_temp = float(reference_temp)
        self.weather_hot_temp = float(hot_temp)
        self.weather_hot_factor = float(hot_factor)
        if temp_source in WEATHER_TEMP_SOURCES:
            self.weather_temp_source = temp_source
        # The cached high belongs to the previous entity/source combination,
        # so drop it rather than briefly scaling off the wrong number.
        self.weather_forecast_high = None
        await self._async_save()
        self._notify_listeners()
        await self.async_refresh_forecast()

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

    async def async_refresh_forecast(self) -> None:
        """Cache the daily forecast high for the day the run starts in.

        Called on a timer (so the card shows a fresh number) and again
        right before a sequence starts (so the run itself never scales off
        a stale value). Entry 0 of the daily forecast is the current
        calendar day, which for the typical night/early-morning schedule is
        the day whose heat the watering is meant to cover.

        Failures are swallowed deliberately: no forecast simply means
        weather_effective_temp falls back to the current temperature, which
        is strictly better than letting a weather integration hiccup break
        the irrigation run.
        """
        if not self.weather_adjustment_enabled or not self.weather_entity:
            return
        if self.weather_temp_source != WEATHER_TEMP_SOURCE_FORECAST_HIGH:
            return
        if self.hass.states.get(self.weather_entity) is None:
            return

        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"type": "daily"},
                target={"entity_id": self.weather_entity},
                blocking=True,
                return_response=True,
            )
            forecast = (response or {}).get(self.weather_entity, {}).get("forecast") or []
            high = forecast[0].get("temperature") if forecast else None
            new_high = float(high) if high is not None else None
        except Exception as err:  # noqa: BLE001 - never break a run over this
            _LOGGER.debug("Could not fetch forecast for %s: %s", self.weather_entity, err)
            return

        if new_high != self.weather_forecast_high:
            self.weather_forecast_high = new_high
            self._notify_listeners()

    @property
    def weather_effective_temp(self) -> float | None:
        """The temperature the factor is actually derived from.

        Falls back to the current temperature when the forecast high is
        selected but unavailable (weather integration without forecast
        support, or a failed/not-yet-completed fetch)."""
        if self.weather_temp_source == WEATHER_TEMP_SOURCE_FORECAST_HIGH:
            if self.weather_forecast_high is not None:
                return self.weather_forecast_high
        return self.weather_current_temp

    @property
    def weather_current_factor(self) -> float:
        """The factor applied to every zone's duration.

        factor(reference_temp) = 1.0, factor(hot_temp) = hot_factor, extrapolated
        linearly beyond those two points and clamped to a sane range.
        Derived from weather_effective_temp - despite the attribute name,
        that is not necessarily the *current* temperature (see
        WEATHER_TEMP_SOURCE_* in const.py).
        """
        if not self.weather_adjustment_enabled:
            return 1.0
        temp = self.weather_effective_temp
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

    @property
    def scaled_total_seconds(self) -> int:
        """Run time with the weather factor applied - what the sequence will
        really take, and what the card's timeline shows. Deliberately
        separate from estimated_total_seconds, which stays unscaled because
        the start-time overlap check is validated against it and must not
        shift with the weather."""
        return sum(self._zone_duration_seconds(zone) for zone in self.zones) + (
            self.pause_between_zones_seconds * max(0, len(self.zones) - 1)
        )

    def _zone_seconds_for(self, entity_id: str) -> int:
        """Currently configured (weather-scaled) run time for a zone, looked
        up fresh by entity id. The running sequence re-reads this every tick
        instead of freezing it at zone start, so a duration changed from the
        card takes effect on the zone that is running right now."""
        for zone in self.zones:
            if zone["entity_id"] == entity_id:
                return self._zone_duration_seconds(zone)
        return 0

    def _remaining_after(self, index: int, head_seconds: int, include_next_pause: bool) -> int:
        """Total seconds left: whatever is left of the current phase plus
        every zone and pause still to come, priced at the *current*
        configuration so the countdown never contradicts the timeline."""
        later = self.zones[index + 1 :]
        rest = sum(self._zone_duration_seconds(zone) for zone in later)
        pauses = self.pause_between_zones_seconds * (
            len(later) if include_next_pause else max(0, len(later) - 1)
        )
        return head_seconds + rest + pauses

    async def _async_run_sequence(self) -> None:
        # Never scale the run off a stale forecast.
        await self.async_refresh_forecast()
        # Snapshot the order so the iteration stays stable, but always look
        # durations up by entity id - self.zones is replaced wholesale on
        # every change.
        planned = list(self.zones)
        self.seconds_remaining_total = self._remaining_after(-1, 0, include_next_pause=False)
        run_elapsed = 0
        self.last_run_zones = []
        _LOGGER.info(
            "Irrigation run starting: %d zone(s), weather_adjustment_enabled=%s "
            "factor=%.3f effective_temp=%s forecast_high=%s current_temp=%s",
            len(planned),
            self.weather_adjustment_enabled,
            self.weather_current_factor,
            self.weather_effective_temp,
            self.weather_forecast_high,
            self.weather_current_temp,
        )

        try:
            for index, planned_zone in enumerate(planned):
                if self._stop_requested:
                    break

                entity_id = planned_zone["entity_id"]
                self.current_zone_index = index
                self.last_zone_index = index
                self.status = STATE_RUNNING
                zone_elapsed = 0
                target_at_start = self._zone_seconds_for(entity_id)
                factor_at_start = self.weather_current_factor
                self.seconds_remaining_zone = target_at_start
                self.seconds_remaining_total = self._remaining_after(
                    index, self.seconds_remaining_zone, include_next_pause=True
                )
                self._notify_listeners()
                _LOGGER.info(
                    "Zone %s starting: base=%dmin factor=%.3f effective_temp=%s target=%ds",
                    entity_id,
                    planned_zone["duration_minutes"],
                    factor_at_start,
                    self.weather_effective_temp,
                    target_at_start,
                )

                await self._async_set_valve(entity_id, True)
                expected_on_state = "open" if entity_id.startswith("valve.") else "on"
                external_off_at: int | None = None
                # Tick once per second (instead of one long sleep) so the
                # countdown stays live, a stop request is picked up quickly,
                # and - re-reading the target every pass - a duration edited
                # mid-run applies immediately, ending the zone at once if the
                # new value is already behind us.
                final_target = target_at_start
                while not self._stop_requested:
                    final_target = self._zone_seconds_for(entity_id)
                    if zone_elapsed >= final_target:
                        break
                    await asyncio.sleep(1)
                    zone_elapsed += 1
                    run_elapsed += 1
                    # We only ever *command* this entity here - nothing reads
                    # its live state back, so a device that switches itself
                    # off on its own (e.g. a relay's own auto-off timer)
                    # would otherwise go completely unnoticed: the loop just
                    # keeps counting against a device that's already off.
                    if external_off_at is None:
                        live_state = self.hass.states.get(entity_id)
                        if live_state is not None and live_state.state != expected_on_state:
                            external_off_at = zone_elapsed
                            _LOGGER.warning(
                                "Zone %s reports state '%s' after %ds even though this "
                                "sequence still expects it %s for %ds more - the device "
                                "may be turning itself off on its own (e.g. a built-in "
                                "auto-off timer), independent of this integration.",
                                entity_id,
                                live_state.state,
                                zone_elapsed,
                                expected_on_state,
                                final_target - zone_elapsed,
                            )
                    self.seconds_remaining_zone = max(
                        0, self._zone_seconds_for(entity_id) - zone_elapsed
                    )
                    self.seconds_remaining_total = self._remaining_after(
                        index, self.seconds_remaining_zone, include_next_pause=True
                    )
                    self._notify_listeners()
                await self._async_set_valve(entity_id, False)
                _LOGGER.info(
                    "Zone %s finished: elapsed=%ds target_at_start=%ds target_at_finish=%ds "
                    "external_off_detected_at=%s stopped_early=%s",
                    entity_id,
                    zone_elapsed,
                    target_at_start,
                    final_target,
                    external_off_at,
                    self._stop_requested,
                )
                self.last_run_zones.append(
                    {
                        "entity_id": entity_id,
                        "duration_minutes": planned_zone["duration_minutes"],
                        "factor_at_start": factor_at_start,
                        "target_seconds_at_start": target_at_start,
                        "target_seconds_at_finish": final_target,
                        "actual_elapsed_seconds": zone_elapsed,
                        "external_off_detected_at_seconds": external_off_at,
                        "stopped_early": self._stop_requested,
                    }
                )
                self._notify_listeners()

                if self._stop_requested:
                    break

                is_last_zone = index == len(planned) - 1
                if not is_last_zone and self.pause_between_zones_seconds > 0:
                    self.status = STATE_PAUSED_BETWEEN_ZONES
                    self.current_zone_index = None
                    pause_elapsed = 0
                    self._notify_listeners()
                    while not self._stop_requested:
                        target = self.pause_between_zones_seconds
                        if pause_elapsed >= target:
                            break
                        await asyncio.sleep(1)
                        pause_elapsed += 1
                        run_elapsed += 1
                        pause_left = max(0, self.pause_between_zones_seconds - pause_elapsed)
                        self.seconds_remaining_total = self._remaining_after(
                            index, pause_left, include_next_pause=False
                        )
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
            # Count the seconds actually spent running rather than deriving
            # them from a planned total - the plan can change mid-run now.
            await self._async_send_completion_notification(run_elapsed)

    async def _async_send_completion_notification(self, elapsed_seconds: int) -> None:
        """Best-effort notify.<target> call after a run - never lets a
        notification failure affect the irrigation run itself, which has
        already fully finished by the time this runs."""
        if not self.notify_target:
            return
        language = self.hass.config.language
        texts = NOTIFY_MESSAGES_BY_LANGUAGE.get(language, NOTIFY_MESSAGES_BY_LANGUAGE["en"])
        minutes = max(1, round(elapsed_seconds / 60))
        try:
            await self.hass.services.async_call(
                "notify",
                self.notify_target,
                {
                    "title": texts["title"],
                    "message": texts["message"].format(minutes=minutes),
                },
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - best-effort, must not raise
            _LOGGER.warning(
                "Failed to send irrigation-finished notification to notify.%s: %s",
                self.notify_target,
                err,
            )

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
