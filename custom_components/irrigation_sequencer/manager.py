"""Runtime manager: state, persistence and the irrigation sequence logic."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_AUTO_OFF_UNEXPECTED,
    DEFAULT_PAUSE_SECONDS,
    DEFAULT_START_TIME,
    DEFAULT_WEATHER_HOT_FACTOR,
    DEFAULT_WEATHER_HOT_TEMP,
    DEFAULT_WEATHER_REFERENCE_TEMP,
    DEFAULT_WEATHER_TEMP_SOURCE,
    DEFAULT_ZONE_DURATION_MINUTES,
    FORECAST_REFRESH_MINUTES,
    MAX_START_TIMES,
    MAX_UNEXPECTED_ACTIVATIONS_KEPT,
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
    AUTO_OFF_ATTEMPT_WINDOW_SECONDS,
    AUTO_OFF_CALL_TIMEOUT_SECONDS,
    AUTO_OFF_VERIFY_POLL_SECONDS,
    AUTO_OFF_VERIFY_SECONDS,
    MAX_AUTO_OFF_ATTEMPTS,
    UNEXPECTED_ACTIVATION_MESSAGES_BY_LANGUAGE,
    UNEXPECTED_ACTIVATION_REPORT_COOLDOWN_SECONDS,
    UNEXPECTED_SOURCE_AUTOMATION,
    UNEXPECTED_SOURCE_DEVICE,
    UNEXPECTED_SOURCE_STARTUP,
    UNEXPECTED_SOURCE_USER,
    ZONE_SAFETY_SWEEP_SECONDS,
    WEATHER_TEMP_SOURCE_CURRENT,
    WEATHER_TEMP_SOURCE_FORECAST_HIGH,
    WEATHER_TEMP_SOURCES,
)

_LOGGER = logging.getLogger(__name__)


def _on_state_for(entity_id: str) -> str:
    """The state string that means "water is flowing" for this entity.

    Valves report open/closed; switches and lights report on/off."""
    return "open" if entity_id.startswith("valve.") else "on"


def _on_since(state) -> str:
    """Identity of one "switched on" episode, shared by both detection
    paths so neither handles what the other already did.

    last_changed only moves when the state itself does, so it stays put
    across attribute updates and names this particular switch-on until the
    zone goes off again."""
    return state.last_changed.isoformat()


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
        # Set by the sequence itself rather than inferred from _run_task,
        # which is assigned by the caller and so isn't reliably set for
        # every path into _async_run_sequence.
        self._sequence_running = False
        self._stop_requested = False
        self._unsub_daily_triggers: list[Callable[[], None]] = []
        self._listeners: list[Callable[[], None]] = []
        # What actually happened in the most recent run, one entry per zone,
        # appended live as each zone finishes - see _async_run_sequence.
        self.last_run_zones: list[dict[str, Any]] = []
        # Zones seen switching on while no sequence was running, newest
        # last - see _handle_zone_state_event.
        self.unexpected_zone_activations: list[dict[str, Any]] = []
        self.auto_off_unexpected_enabled: bool = DEFAULT_AUTO_OFF_UNEXPECTED
        self._unsub_zone_watch: Callable[[], None] | None = None
        # Live phase marker per zone entity for whatever is currently
        # in-flight ("waiting_for_lock" / "lock_acquired" / "calling_off" /
        # "off_call_returned" / "timed_out" / "error:<msg>" / None once
        # settled), refreshed on the state machine the same way every other
        # attribute here is - independent of Python logging entirely, since
        # a log level can be silently overridden (a `logger:` block in
        # configuration.yaml, some other integration, etc.) in ways that
        # are invisible and unfixable from here. Diagnostic only; not
        # persisted.
        self.unexpected_activation_phase: dict[str, str] = {}
        # Timestamp (isoformat) the state-change listener last *saw* a raw
        # event for a zone entity, written before any early return in
        # _handle_zone_state_event - including ones filtered out as
        # attribute-only updates or a running sequence. Exists purely to
        # answer "did the listener fire at all" when unexpected_activation_
        # phase never moves, since that question turned out to not be
        # answerable any other way. Diagnostic only; not persisted.
        self.last_zone_event_seen: dict[str, str] = {}
        # When the safety sweep last ran, and the "on since" timestamp of
        # the activation already handled per zone. The latter is what makes
        # the sweep and the listener idempotent with each other: both
        # identify an activation by the state's last_changed, so whichever
        # notices it first handles it and the other skips it.
        self.last_zone_safety_sweep: str | None = None
        self._handled_on_since: dict[str, str] = {}
        self._unsub_safety_sweep: Callable[[], None] | None = None
        # Last time an activation of this entity was *reported* (record,
        # log, notification). Closing the valve is not throttled by this.
        self._unexpected_reported_at: dict[str, float] = {}
        # Turn-offs that did not close the zone, per entity, as
        # (count, first_at) - so a device that will not respond can be
        # given up on instead of traded service calls with forever. Only
        # failures count: a zone that closes every time it is asked is
        # working no matter how often it is switched on.
        self._auto_off_failures: dict[str, tuple[int, float]] = {}
        # One lock per zone entity, created on first use. A second
        # activation for a zone already being handled waits for the first
        # to finish its turn-off call before making its own, instead of
        # both racing a service call at the same device concurrently -
        # observed live to make a downstream integration (Tuya) drop one
        # of the two when the first was still in flight on a slow cloud
        # round trip.
        self._unexpected_locks: dict[str, asyncio.Lock] = {}
        # Strong references to turn-off calls still running, so a task that
        # outlived the timeout waiting on it is neither garbage collected
        # mid-flight nor left with its exception uncollected. Entries drop
        # out as they finish - see _on_off_task_done.
        self._orphaned_off_tasks: set[asyncio.Task] = set()
        # Entities we've already announced giving up on in the current
        # burst - saying it once is the point; saying it on every
        # subsequent flap would be the message flood this avoids.
        self._gave_up_announced: set[str] = set()

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

            # Survives a restart deliberately: the runs worth inspecting this
            # for are the automatic, scheduled ones, and there's no
            # guarantee nobody restarts HA (an update, a crash) between one
            # finishing and someone actually checking the attribute.
            self.last_run_zones = data.get("last_run_zones", [])
            self.unexpected_zone_activations = data.get("unexpected_zone_activations", [])
            self.auto_off_unexpected_enabled = data.get(
                "auto_off_unexpected_enabled", DEFAULT_AUTO_OFF_UNEXPECTED
            )

        self._schedule_daily_trigger()
        self._schedule_forecast_refresh()
        self._schedule_zone_watch()
        self._schedule_zone_safety_sweep()

        # Don't fetch during setup: weather integrations are often not up
        # yet at that point, and calling weather.get_forecasts against an
        # entity that doesn't exist yet makes Home Assistant log
        # "Referenced entities ... are missing or not currently available"
        # - our warning, in the user's log, for a fetch that was never
        # going to succeed. Wait until startup has finished instead.
        async def _after_start(_hass) -> None:
            await self.async_refresh_forecast()
            # A power cut that flips a relay on ("turn on when powered")
            # usually takes Home Assistant down with it, so the state
            # change that turned the zone on happens while nothing is
            # listening. Checking once after startup is what catches that
            # case at all - the live listener never sees it.
            await self._async_check_zones_on_at_startup()

        async_at_started(self.hass, _after_start)

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
                "last_run_zones": self.last_run_zones,
                "unexpected_zone_activations": self.unexpected_zone_activations,
                "auto_off_unexpected_enabled": self.auto_off_unexpected_enabled,
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
        if self._unsub_zone_watch is not None:
            self._unsub_zone_watch()
            self._unsub_zone_watch = None
        if self._unsub_safety_sweep is not None:
            self._unsub_safety_sweep()
            self._unsub_safety_sweep = None
        if self._run_task and not self._run_task.done():
            self._stop_requested = True
            await self._run_task

    # ------------------------------------------------------------------ #
    # Watching for zones switching on outside a run
    # ------------------------------------------------------------------ #

    @property
    def _sequence_active(self) -> bool:
        """True while a run owns the valves.

        Deliberately not keyed off self.status: the run starts by
        refreshing the forecast, which can take a moment, and status is
        still "idle" for that stretch - a zone turned on right then is the
        sequence's own doing and must not be flagged."""
        return self._sequence_running or (
            self._run_task is not None and not self._run_task.done()
        )

    @callback
    def _schedule_zone_watch(self) -> None:
        """Watch the zone entities for switching on while nothing here asked
        them to.

        The sequence only ever *commands* the valves; without this, anything
        that turns one on behind Home Assistant's back - the device's own
        timer, the vendor app, a physical button, or a power-loss reboot
        with "turn on when powered" configured - just silently waters the
        garden, and the only trace is an entry in the entity's history that
        looks much like any other."""
        if self._unsub_zone_watch is not None:
            self._unsub_zone_watch()
            self._unsub_zone_watch = None

        entity_ids = [zone["entity_id"] for zone in self.zones]
        if not entity_ids:
            return

        self._unsub_zone_watch = async_track_state_change_event(
            self.hass, entity_ids, self._handle_zone_state_event
        )

    @callback
    def _handle_zone_state_event(self, event) -> None:
        watched_entity_id = event.data.get("entity_id")
        if watched_entity_id is not None:
            self.last_zone_event_seen[watched_entity_id] = dt_util.now().isoformat()
            self._notify_listeners()

        if self._sequence_active:
            return

        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return

        entity_id = new_state.entity_id
        on_state = _on_state_for(entity_id)
        if new_state.state != on_state:
            return
        # Only react to the transition into "on". Attribute-only updates
        # (power readings on a metering relay, for instance) arrive as
        # state changes too and would otherwise re-trigger on every tick.
        if old_state is not None and old_state.state == on_state:
            return

        self._handled_on_since[entity_id] = _on_since(new_state)
        context = new_state.context
        source = self._classify_activation(context)
        self.hass.async_create_task(
            self._async_handle_unexpected_activation(entity_id, source, context)
        )

    @callback
    def _schedule_zone_safety_sweep(self) -> None:
        """Poll the zones' real states as a backstop for the listener.

        Live evidence made this necessary: after one activation was handled
        end to end, the state-change listener stopped delivering events for
        that entity entirely - the zone's own history shows it going off
        and back on with nothing reaching us - so a zone switched on again
        seconds later stayed on with no trace. An event that never arrives
        cannot be waited for; reading the state directly cannot be missed
        the same way."""
        if self._unsub_safety_sweep is not None:
            self._unsub_safety_sweep()
            self._unsub_safety_sweep = None

        self._unsub_safety_sweep = async_track_time_interval(
            self.hass,
            self._async_zone_safety_sweep,
            timedelta(seconds=ZONE_SAFETY_SWEEP_SECONDS),
        )

    async def _async_zone_safety_sweep(self, _now=None) -> None:
        self.last_zone_safety_sweep = dt_util.now().isoformat()
        if self._sequence_active:
            self._notify_listeners()
            return

        for zone in list(self.zones):
            entity_id = zone["entity_id"]
            state = self.hass.states.get(entity_id)
            if state is None or state.state != _on_state_for(entity_id):
                continue

            source = self._classify_activation(state.context)
            wants_turn_off = (
                source in (UNEXPECTED_SOURCE_DEVICE, UNEXPECTED_SOURCE_STARTUP)
                and self.auto_off_unexpected_enabled
            )
            already_handled = self._handled_on_since.get(entity_id) == _on_since(state)
            # A zone we deliberately leave running (a person's or another
            # automation's doing) is recorded once and then left alone. One
            # we should be closing is retried while it is still open, since
            # "still on" means the last attempt did not take - the attempt
            # counter is what stops that from going on forever.
            if already_handled and not wants_turn_off:
                continue

            self._handled_on_since[entity_id] = _on_since(state)
            await self._async_handle_unexpected_activation(
                entity_id, source, state.context
            )

        self._notify_listeners()

    @callback
    def _classify_activation(self, context) -> str:
        """Work out who turned a zone on from the state change's context.

        Home Assistant stamps every state change with one, and its shape is
        the only thing that distinguishes a person clicking in the UI from
        a relay that came up on its own."""
        if context is None:
            return UNEXPECTED_SOURCE_DEVICE
        if getattr(context, "user_id", None) is not None:
            return UNEXPECTED_SOURCE_USER
        if getattr(context, "parent_id", None) is not None:
            return UNEXPECTED_SOURCE_AUTOMATION
        return UNEXPECTED_SOURCE_DEVICE

    async def _async_check_zones_on_at_startup(self) -> None:
        """Catch zones that were already on when Home Assistant came up."""
        if self._sequence_active:
            return
        for zone in self.zones:
            entity_id = zone["entity_id"]
            state = self.hass.states.get(entity_id)
            if state is not None and state.state == _on_state_for(entity_id):
                self._handled_on_since[entity_id] = _on_since(state)
                await self._async_handle_unexpected_activation(
                    entity_id, UNEXPECTED_SOURCE_STARTUP, None
                )

    async def _async_describe_actor(self, context) -> str | None:
        """Name whoever inside Home Assistant caused this, if anyone did.

        "A zone came on" is only half an answer during troubleshooting -
        which person, or which of your automations, is the half that
        actually tells you where to go looking."""
        if context is None:
            return None

        user_id = getattr(context, "user_id", None)
        if user_id is not None:
            try:
                user = await self.hass.auth.async_get_user(user_id)
            except Exception:  # noqa: BLE001 - naming is a nicety, never fatal
                return user_id
            return user.name if user is not None and user.name else user_id

        parent_id = getattr(context, "parent_id", None)
        if parent_id is not None:
            # The automation/script that ran stamped its own entity state
            # with the parent context, so matching on it names the culprit.
            # Same heuristic the logbook uses for "triggered by".
            for state in self.hass.states.async_all():
                if state.domain not in ("automation", "script", "scene"):
                    continue
                if state.context.id == parent_id:
                    return state.attributes.get("friendly_name") or state.entity_id
        return None

    async def _async_handle_unexpected_activation(
        self, entity_id: str, source: str, context=None
    ) -> None:
        """Record it, and - only if it came from outside Home Assistant -
        report it and close the valve again.

        A zone switched on from inside Home Assistant, by a person or by
        another automation, is deliberate: it gets recorded with whoever
        did it, and is otherwise left alone."""
        now = time.monotonic()
        actor = await self._async_describe_actor(context)

        # Anything Home Assistant itself initiated - a person clicking, or
        # another automation - is left running: it was deliberate, and
        # closing the valve under whoever opened it would be worse than the
        # problem this guards against. Only a switch-on that reached us
        # from outside Home Assistant entirely is treated as one to undo.
        from_outside_ha = source in (UNEXPECTED_SOURCE_DEVICE, UNEXPECTED_SOURCE_STARTUP)
        wants_turn_off = from_outside_ha and self.auto_off_unexpected_enabled

        # Closing the valve happens on every single activation, never
        # throttled: it is one idempotent service call, and skipping it
        # because the same zone came on a moment ago left water running -
        # the exact failure this guard exists to prevent.
        turned_off = False
        gave_up = False
        first_give_up = False
        error: str | None = None
        if wants_turn_off:
            # A second activation for this zone waits here for the first's
            # turn-off call to actually finish, rather than firing its own
            # concurrently - see _unexpected_locks. Logged at info (not
            # debug) unconditionally, one line per phase, so which of these
            # three stages an attempt got stuck at is visible without
            # needing debug logging enabled ahead of time.
            lock = self._unexpected_locks.setdefault(entity_id, asyncio.Lock())
            _LOGGER.info("Zone %s: waiting for its turn-off lock", entity_id)
            self.unexpected_activation_phase[entity_id] = "waiting_for_lock"
            self._notify_listeners()
            async with lock:
                _LOGGER.info("Zone %s: lock acquired", entity_id)
                self.unexpected_activation_phase[entity_id] = "lock_acquired"
                self._notify_listeners()
                failures, window_start = self._auto_off_failures_in_window(
                    entity_id, now
                )
                if failures >= MAX_AUTO_OFF_ATTEMPTS:
                    gave_up = True
                    first_give_up = entity_id not in self._gave_up_announced
                    self._gave_up_announced.add(entity_id)
                    self.unexpected_activation_phase[entity_id] = "gave_up"
                    self._notify_listeners()
                else:
                    try:
                        _LOGGER.info(
                            "Zone %s: calling turn-off (%d failed attempt(s) so "
                            "far, timeout %ds)",
                            entity_id,
                            failures,
                            AUTO_OFF_CALL_TIMEOUT_SECONDS,
                        )
                        self.unexpected_activation_phase[entity_id] = "calling_off"
                        self._notify_listeners()

                        # The call is run as its own task and awaited behind
                        # asyncio.shield rather than awaited directly: a
                        # live case showed the timeout below did not bound
                        # a hung call as intended, because the cancellation
                        # asyncio.timeout sends never made it back out
                        # through Home Assistant's/the device integration's
                        # own service-call machinery. Shielding means the
                        # timeout only gives up on *waiting*, never depends
                        # on the call honouring cancellation. A timed-out
                        # call is left running rather than cancelled, since
                        # it may still land - but it is not waited on again:
                        # live, a freshly issued call to the same device
                        # went through immediately while an earlier one was
                        # still hung, so the next activation must get its
                        # own call rather than join the stuck one.
                        off_task = self.hass.async_create_task(
                            self._async_set_valve(entity_id, False)
                        )
                        self._orphaned_off_tasks.add(off_task)
                        off_task.add_done_callback(
                            lambda task, eid=entity_id: self._on_off_task_done(
                                eid, task
                            )
                        )

                        async with asyncio.timeout(AUTO_OFF_CALL_TIMEOUT_SECONDS):
                            await asyncio.shield(off_task)
                        _LOGGER.info("Zone %s: turn-off call returned", entity_id)

                        # A returned call is not a closed valve - live, the
                        # two came apart repeatedly. Only the zone's own
                        # state settles it.
                        self.unexpected_activation_phase[entity_id] = "verifying"
                        self._notify_listeners()
                        turned_off = await self._async_wait_until_off(entity_id)
                        if turned_off:
                            self.unexpected_activation_phase.pop(entity_id, None)
                        else:
                            error = (
                                "the turn-off call reported success but the "
                                f"zone was still on {AUTO_OFF_VERIFY_SECONDS}s "
                                "later"
                            )
                            self.unexpected_activation_phase[entity_id] = "still_on"
                            _LOGGER.error(
                                "Zone %s did not go off within %ds of a turn-off "
                                "call that reported success - the command was "
                                "accepted but the device did not act on it.",
                                entity_id,
                                AUTO_OFF_VERIFY_SECONDS,
                            )
                        self._notify_listeners()
                    except TimeoutError:
                        error = f"timed out after {AUTO_OFF_CALL_TIMEOUT_SECONDS}s"
                        self.unexpected_activation_phase[entity_id] = "timed_out"
                        self._notify_listeners()
                        _LOGGER.error(
                            "Turning zone %s off did not complete within %ds - "
                            "giving up on waiting for this attempt so the "
                            "zone isn't blocked for future ones. The call "
                            "itself is left running in the background in "
                            "case it eventually goes through.",
                            entity_id,
                            AUTO_OFF_CALL_TIMEOUT_SECONDS,
                        )
                    except Exception as err:  # noqa: BLE001 - reporting matters more
                        error = str(err)
                        self.unexpected_activation_phase[entity_id] = f"error:{error}"
                        self._notify_listeners()
                        _LOGGER.error(
                            "Could not turn zone %s back off: %s", entity_id, err
                        )

                    # Only a zone that would not close counts towards giving
                    # up. A zone that closes every time it is asked is not
                    # fighting anyone, however often it is switched on - and
                    # counting those was enough to trip the guard during
                    # ordinary manual testing.
                    self._record_auto_off_outcome(
                        entity_id, failures, window_start, turned_off
                    )

        # Having already given up is not news. The sweep keeps coming back
        # to a zone it gave up on so the attempt window can re-arm and try
        # again later, and every one of those visits would otherwise write
        # its own "gave up" entry.
        if gave_up and not first_give_up:
            return

        # Reporting is what gets rate-limited instead, so a flapping device
        # can't bury the user in push messages or fill the history with one
        # incident. Giving up is always worth saying out loud.
        last_reported = self._unexpected_reported_at.get(entity_id)
        should_report = (
            first_give_up
            or last_reported is None
            or now - last_reported >= UNEXPECTED_ACTIVATION_REPORT_COOLDOWN_SECONDS
        )
        if not should_report:
            return
        self._unexpected_reported_at[entity_id] = now

        record = {
            "entity_id": entity_id,
            "zone_name": self._zone_display_name(entity_id),
            "source": source,
            "actor": actor,
            "at": dt_util.now().isoformat(),
            "turned_off": turned_off,
            "gave_up": gave_up,
        }
        if error is not None:
            record["error"] = error

        if gave_up:
            _LOGGER.error(
                "Zone %s has switched itself back on more than %d times in %d s "
                "despite being turned off - giving up. It may still be running; "
                "check the device's own settings (auto-on timer, state after power "
                "loss) and its vendor app.",
                entity_id,
                MAX_AUTO_OFF_ATTEMPTS,
                AUTO_OFF_ATTEMPT_WINDOW_SECONDS,
            )
        elif from_outside_ha:
            _LOGGER.warning(
                "Zone %s switched on while no sequence was running, from outside "
                "Home Assistant (%s)%s. Nothing in Home Assistant asked for it - if "
                "this repeats, check the device's own settings (auto-on timer, state "
                "after power loss) and its vendor app.",
                entity_id,
                source,
                " - turned it back off" if turned_off else "",
            )
        else:
            _LOGGER.info(
                "Zone %s was switched on outside a run by %s (%s) - recorded, "
                "left running",
                entity_id,
                actor or "someone in Home Assistant",
                source,
            )

        self.unexpected_zone_activations = (
            self.unexpected_zone_activations + [record]
        )[-MAX_UNEXPECTED_ACTIVATIONS_KEPT:]
        await self._async_save()
        self._notify_listeners()
        if from_outside_ha:
            await self._async_send_unexpected_activation_notification(record)

    async def _async_wait_until_off(self, entity_id: str) -> bool:
        """Whether the zone actually went off, not whether the call said so.

        Live, these came apart repeatedly: turn-off calls returned success
        while the zone sat on "on" with its last_changed never moving, and
        the history then recorded "turned off" for a zone that was still
        watering."""
        on_state = _on_state_for(entity_id)
        deadline = time.monotonic() + AUTO_OFF_VERIFY_SECONDS
        while True:
            state = self.hass.states.get(entity_id)
            if state is None or state.state != on_state:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(AUTO_OFF_VERIFY_POLL_SECONDS, remaining))

    @callback
    def _on_off_task_done(self, entity_id: str, task: asyncio.Task) -> None:
        """Runs once a turn-off call finishes, however late.

        Only relevant after a timeout already moved on without waiting for
        it: retrieves the task's result/exception so it isn't logged as
        never collected, and if nothing newer has since taken over this
        entity's slot, reports the belated outcome and clears the stale
        "timed_out" phase so a call that quietly succeeded doesn't keep
        looking stuck."""
        self._orphaned_off_tasks.discard(task)

        if task.cancelled():
            return
        err = task.exception()
        if err is not None:
            _LOGGER.error(
                "Zone %s: turn-off call that had already timed out failed: %s",
                entity_id,
                err,
            )
            return

        _LOGGER.info(
            "Zone %s: turn-off call that had already timed out finished "
            "successfully",
            entity_id,
        )
        if self.unexpected_activation_phase.get(entity_id) == "timed_out":
            self.unexpected_activation_phase.pop(entity_id, None)
            self._notify_listeners()

    def _auto_off_failures_in_window(
        self, entity_id: str, now: float
    ) -> tuple[int, float]:
        """Failed turn-offs for this zone in the current burst, and when
        that burst started.

        Failures, not attempts: a zone that closes whenever it is asked is
        working, however many times someone switches it on. Counting those
        was enough to trip the give-up guard during ordinary manual
        testing, which then left the zone open. A burst that goes quiet for
        a full window starts over, so an unrelated repeat weeks later is
        never read as a continuation of an old one."""
        failures, first_at = self._auto_off_failures.get(entity_id, (0, now))
        if now - first_at > AUTO_OFF_ATTEMPT_WINDOW_SECONDS:
            failures, first_at = 0, now
            self._gave_up_announced.discard(entity_id)
            self._auto_off_failures.pop(entity_id, None)
        return failures, first_at

    def _record_auto_off_outcome(
        self, entity_id: str, failures: int, window_start: float, turned_off: bool
    ) -> None:
        """A close that worked clears the slate; one that didn't counts."""
        if turned_off:
            self._auto_off_failures.pop(entity_id, None)
            self._gave_up_announced.discard(entity_id)
        else:
            self._auto_off_failures[entity_id] = (failures + 1, window_start)

    def _zone_display_name(self, entity_id: str) -> str:
        """The zone's custom name if it has one, else whatever Home
        Assistant calls the entity - the notification should name the zone
        the way the user does, not by entity id."""
        for zone in self.zones:
            if zone["entity_id"] == entity_id and zone.get("name"):
                return zone["name"]
        state = self.hass.states.get(entity_id)
        if state is not None:
            return state.attributes.get("friendly_name") or entity_id
        return entity_id

    async def _async_send_unexpected_activation_notification(
        self, record: dict[str, Any]
    ) -> None:
        """Best-effort notify - the valve is already closed by this point,
        so a failure here must not surface as an error."""
        if not self.notify_target:
            return
        language = self.hass.config.language
        texts = UNEXPECTED_ACTIVATION_MESSAGES_BY_LANGUAGE.get(
            language, UNEXPECTED_ACTIVATION_MESSAGES_BY_LANGUAGE["en"]
        )
        source_label = texts["sources"].get(record["source"], record["source"])
        if record.get("gave_up"):
            title = texts["title_giving_up"]
            message = texts["message_giving_up"].format(
                zone=record["zone_name"], attempts=MAX_AUTO_OFF_ATTEMPTS
            )
        else:
            title = texts["title"]
            message = texts[
                "message_turned_off" if record["turned_off"] else "message_left_on"
            ].format(zone=record["zone_name"], source=source_label)
        try:
            await self.hass.services.async_call(
                "notify",
                self.notify_target,
                {
                    "title": title,
                    "message": message,
                },
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - best-effort, must not raise
            _LOGGER.warning(
                "Failed to send unexpected-activation notification to notify.%s: %s",
                self.notify_target,
                err,
            )

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

    async def async_set_auto_off_unexpected(self, enabled: bool) -> None:
        self.auto_off_unexpected_enabled = bool(enabled)
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
        # Claim the valves before anything else, so the zone watchdog knows
        # every switch-on from here until the finally block is ours.
        self._sequence_running = True
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
                expected_on_state = _on_state_for(entity_id)
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
                await self._async_save()
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
            # Everything is closed; from here on a zone going on again is
            # somebody else's doing and the watchdog should say so.
            self._sequence_running = False
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
