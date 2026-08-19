"""Unit tests for IrrigationSequencerManager's core logic."""
import asyncio
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.irrigation_sequencer.manager import IrrigationSequencerManager


_real_sleep = asyncio.sleep


async def _instant_sleep(_seconds):
    """Collapse the sequence's 1-second ticks so a multi-minute run is
    testable, while still yielding so other tasks (like a duration change
    arriving mid-run) can interleave exactly as they would in reality."""
    await _real_sleep(0)


def make_manager(hass: HomeAssistant, zone_entities=None) -> IrrigationSequencerManager:
    zone_entities = zone_entities if zone_entities is not None else ["switch.zone_1", "switch.zone_2"]
    return IrrigationSequencerManager(hass, "test_entry", zone_entities)


# --------------------------------------------------------------------- #
# Zones
# --------------------------------------------------------------------- #


async def test_initial_zones_have_default_name_and_duration(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    assert [z["entity_id"] for z in manager.zones] == ["switch.zone_1", "switch.zone_2"]
    assert all(z["name"] == "" for z in manager.zones)
    assert all(z["duration_minutes"] == 10 for z in manager.zones)
    assert [z["position"] for z in manager.zones] == [0, 1]


async def test_set_zone_order(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_zone_order(["switch.zone_2", "switch.zone_1"])
    assert [z["entity_id"] for z in manager.zones] == ["switch.zone_2", "switch.zone_1"]
    assert [z["position"] for z in manager.zones] == [0, 1]


async def test_set_zone_order_ignores_mismatched_entity_list(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    original = list(manager.zones)
    # Missing a zone entirely - the whole reorder is rejected rather than
    # silently dropping a zone.
    await manager.async_set_zone_order(["switch.zone_1"])
    assert manager.zones == original


async def test_set_zone_duration_clamped_to_minimum_one(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_zone_duration("switch.zone_1", -5)
    assert manager.zones[0]["duration_minutes"] == 1


async def test_set_zone_duration_unknown_entity_is_noop(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    original = list(manager.zones)
    await manager.async_set_zone_duration("switch.does_not_exist", 20)
    assert manager.zones == original


async def test_set_zone_name_strips_whitespace(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_zone_name("switch.zone_1", "  Front lawn  ")
    assert manager.zones[0]["name"] == "Front lawn"


async def test_set_zone_duration_does_not_mutate_previously_returned_zones(
    hass: HomeAssistant,
) -> None:
    """Regression test: extra_state_attributes hands out manager.zones by
    reference on every state write. If a change mutated the existing
    list/dicts in place instead of producing new ones, a reference captured
    before the change (as HA's previous State object holds) would show the
    new value too, making the "zones" attribute look unchanged to HA's
    state-diffing - the status card's timeline silently never updated."""
    manager = make_manager(hass)
    zones_before = manager.zones
    zone_before = manager.zones[0]
    await manager.async_set_zone_duration("switch.zone_1", 15)
    assert zones_before[0]["duration_minutes"] != 15
    assert zone_before["duration_minutes"] != 15
    assert manager.zones[0]["duration_minutes"] == 15


async def test_set_zone_name_does_not_mutate_previously_returned_zones(
    hass: HomeAssistant,
) -> None:
    manager = make_manager(hass)
    zones_before = manager.zones
    zone_before = manager.zones[0]
    await manager.async_set_zone_name("switch.zone_1", "Front lawn")
    assert zones_before[0]["name"] != "Front lawn"
    assert zone_before["name"] != "Front lawn"
    assert manager.zones[0]["name"] == "Front lawn"


# --------------------------------------------------------------------- #
# Pause between zones
# --------------------------------------------------------------------- #


async def test_set_pause_between_zones_clamped_to_minimum_zero(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_pause_between_zones(-10)
    assert manager.pause_between_zones_seconds == 0


async def test_estimated_total_seconds(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_zone_duration("switch.zone_1", 5)
    await manager.async_set_zone_duration("switch.zone_2", 8)
    await manager.async_set_pause_between_zones(90)
    # (5 + 8) minutes * 60 + one pause of 90s between the two zones
    assert manager.estimated_total_seconds == 13 * 60 + 90


async def test_estimated_total_seconds_single_zone_has_no_pause(hass: HomeAssistant) -> None:
    manager = make_manager(hass, zone_entities=["switch.zone_1"])
    await manager.async_set_pause_between_zones(90)
    assert manager.estimated_total_seconds == 10 * 60


# --------------------------------------------------------------------- #
# Start times: validation + overlap detection
# --------------------------------------------------------------------- #


async def test_set_start_times_accepts_one_to_three(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_start_times(["05:00:00", "12:00:00", "20:00:00"])
    assert manager.start_times == ["05:00:00", "12:00:00", "20:00:00"]


async def test_set_start_times_sorts_input(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_start_times(["20:00:00", "05:00:00"])
    assert manager.start_times == ["05:00:00", "20:00:00"]


async def test_set_start_times_rejects_zero_entries(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    with pytest.raises(ServiceValidationError):
        await manager.async_set_start_times([])


async def test_set_start_times_rejects_more_than_three(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    with pytest.raises(ServiceValidationError):
        await manager.async_set_start_times(["01:00:00", "02:00:00", "03:00:00", "04:00:00"])


async def test_set_start_times_rejects_overlap(hass: HomeAssistant) -> None:
    # Two zones of 10 min each + no pause -> ~20 min sequence.
    manager = make_manager(hass)
    with pytest.raises(ServiceValidationError):
        # 10 minutes apart is well under the ~20 minute sequence duration.
        await manager.async_set_start_times(["05:00:00", "05:10:00"])
    # Rejected calls must not mutate state.
    assert manager.start_times == ["05:00:00"]


async def test_set_start_times_accepts_sufficiently_spaced_times(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_start_times(["05:00:00", "18:00:00"])
    assert manager.start_times == ["05:00:00", "18:00:00"]


async def test_set_start_times_detects_wraparound_overlap_past_midnight(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    # Sequence takes ~20 min; 23:50 -> 00:05 wraps past midnight and is only
    # 15 minutes apart, which must still be caught.
    with pytest.raises(ServiceValidationError):
        await manager.async_set_start_times(["23:50:00", "00:05:00"])


# --------------------------------------------------------------------- #
# Winter mode / rain pause blocking
# --------------------------------------------------------------------- #


async def test_winter_mode_blocks_sequence(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_winter_mode(True)
    blocked, reason = manager._is_blocked()  # noqa: SLF001 - testing internal gate directly
    assert blocked is True
    assert reason == "winter_mode"


async def test_winter_mode_off_does_not_block(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_winter_mode(False)
    blocked, _ = manager._is_blocked()  # noqa: SLF001
    assert blocked is False


async def test_rain_pause_blocks_sequence_while_active(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_rain_pause(3)
    blocked, reason = manager._is_blocked()  # noqa: SLF001
    assert blocked is True
    assert reason == "rain_pause"
    assert manager.rain_pause_until == (date.today() + timedelta(days=3)).isoformat()


async def test_clear_rain_pause(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_rain_pause(3)
    await manager.async_clear_rain_pause()
    assert manager.rain_pause_until is None
    blocked, _ = manager._is_blocked()  # noqa: SLF001
    assert blocked is False


async def test_expired_rain_pause_is_lazily_cleared(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    manager.rain_pause_until = (date.today() - timedelta(days=1)).isoformat()
    blocked, reason = manager._is_blocked()  # noqa: SLF001
    assert blocked is False
    assert reason is None
    assert manager.rain_pause_until is None


# --------------------------------------------------------------------- #
# Weather-based duration factor
# --------------------------------------------------------------------- #


async def test_weather_factor_defaults_to_one_when_disabled(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    manager.weather_adjustment_enabled = False
    assert manager.weather_current_factor == 1.0


async def test_weather_factor_defaults_to_one_without_entity_state(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    manager.weather_adjustment_enabled = True
    manager.weather_entity = "weather.does_not_exist"
    assert manager.weather_current_factor == 1.0


async def test_weather_factor_linear_interpolation(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    manager.weather_adjustment_enabled = True
    manager.weather_entity = "weather.home"
    manager.weather_reference_temp = 20.0
    manager.weather_hot_temp = 30.0
    manager.weather_hot_factor = 2.0
    hass.states.async_set("weather.home", "sunny", {"temperature": 25.0})

    # Halfway between reference and hot temp -> halfway between factor 1.0 and 2.0.
    assert manager.weather_current_factor == pytest.approx(1.5)


async def test_weather_factor_clamped_to_max(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    manager.weather_adjustment_enabled = True
    manager.weather_entity = "weather.home"
    manager.weather_reference_temp = 20.0
    manager.weather_hot_temp = 30.0
    manager.weather_hot_factor = 2.0
    # Far beyond hot_temp - the raw linear extrapolation would exceed
    # MAX_WEATHER_FACTOR (3.0) and must be clamped.
    hass.states.async_set("weather.home", "sunny", {"temperature": 80.0})

    assert manager.weather_current_factor == pytest.approx(3.0)


async def test_weather_factor_clamped_to_min(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    manager.weather_adjustment_enabled = True
    manager.weather_entity = "weather.home"
    manager.weather_reference_temp = 20.0
    manager.weather_hot_temp = 30.0
    manager.weather_hot_factor = 2.0
    # Far below reference_temp - the raw linear extrapolation would go
    # negative and must be clamped to MIN_WEATHER_FACTOR (0.1).
    hass.states.async_set("weather.home", "sunny", {"temperature": -50.0})

    assert manager.weather_current_factor == pytest.approx(0.1)


# --------------------------------------------------------------------- #
# Notify target / completion notification
# --------------------------------------------------------------------- #


async def test_set_notify_target(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_notify_target("mobile_app_test_phone")
    assert manager.notify_target == "mobile_app_test_phone"


async def test_set_notify_target_empty_string_clears_it(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    await manager.async_set_notify_target("mobile_app_test_phone")
    await manager.async_set_notify_target("")
    assert manager.notify_target is None


async def test_completion_notification_not_sent_when_no_target(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    calls = []
    hass.services.async_register("notify", "mobile_app_test_phone", lambda call: calls.append(call.data))

    await manager._async_send_completion_notification(300)  # noqa: SLF001

    assert calls == []


async def test_completion_notification_sent_in_english(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    manager.notify_target = "mobile_app_test_phone"
    hass.config.language = "en"
    calls = []
    hass.services.async_register("notify", "mobile_app_test_phone", lambda call: calls.append(call.data))

    await manager._async_send_completion_notification(300)  # noqa: SLF001

    assert len(calls) == 1
    assert calls[0]["title"] == "Irrigation finished"
    assert calls[0]["message"] == "Ran for 5 minutes."


async def test_completion_notification_sent_in_german(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    manager.notify_target = "mobile_app_test_phone"
    hass.config.language = "de"
    calls = []
    hass.services.async_register("notify", "mobile_app_test_phone", lambda call: calls.append(call.data))

    await manager._async_send_completion_notification(300)  # noqa: SLF001

    assert calls[0]["title"] == "Bewässerung abgeschlossen"
    assert calls[0]["message"] == "Lief 5 Minuten."


async def test_completion_notification_failure_does_not_raise(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    # No notify.mobile_app_missing service registered - the call should
    # fail internally and be swallowed, not propagate.
    manager.notify_target = "mobile_app_missing"

    await manager._async_send_completion_notification(60)  # noqa: SLF001


# --------------------------------------------------------------------- #
# Weather temperature source (forecast high vs current)
# --------------------------------------------------------------------- #


async def test_factor_uses_forecast_high_not_current_temp(hass: HomeAssistant) -> None:
    """The whole point of the feature: a run scheduled for 01:00 must scale
    off how hot the *day* gets, not off the cold night it starts in. With
    the defaults (1.0 at 20 deg, 2.0 at 30 deg) an 18 deg night would give
    0.8x while the 37 deg day calls for 2.7x - watering least on the
    hottest days, the exact inverse of the intent."""
    manager = make_manager(hass)
    hass.states.async_set("weather.home", "sunny", {"temperature": 18})
    await manager.async_set_weather_adjustment(
        True, "weather.home", 20.0, 30.0, 2.0, "forecast_high"
    )
    manager.weather_forecast_high = 37.0

    assert manager.weather_effective_temp == 37.0
    assert manager.weather_current_factor == pytest.approx(2.7)


async def test_factor_uses_current_temp_when_source_is_current(
    hass: HomeAssistant,
) -> None:
    manager = make_manager(hass)
    hass.states.async_set("weather.home", "sunny", {"temperature": 18})
    await manager.async_set_weather_adjustment(
        True, "weather.home", 20.0, 30.0, 2.0, "current"
    )
    manager.weather_forecast_high = 37.0

    assert manager.weather_effective_temp == 18
    assert manager.weather_current_factor == pytest.approx(0.8)


async def test_falls_back_to_current_temp_without_forecast(hass: HomeAssistant) -> None:
    """Weather integrations without daily forecast support must still get a
    sensible factor rather than none at all."""
    manager = make_manager(hass)
    hass.states.async_set("weather.home", "sunny", {"temperature": 25})
    await manager.async_set_weather_adjustment(
        True, "weather.home", 20.0, 30.0, 2.0, "forecast_high"
    )
    manager.weather_forecast_high = None

    assert manager.weather_effective_temp == 25
    assert manager.weather_current_factor == pytest.approx(1.5)


async def test_forecast_high_defaults_to_forecast_source(hass: HomeAssistant) -> None:
    manager = make_manager(hass)
    assert manager.weather_temp_source == "forecast_high"


async def test_scaled_total_applies_factor_but_estimate_does_not(
    hass: HomeAssistant,
) -> None:
    """The card shows the scaled total, while the start-time overlap check
    validates against the unscaled estimate - that check must not shift
    with the weather, or previously accepted start times could silently
    become invalid on a hot day."""
    manager = make_manager(hass)  # 2 zones x 10 min, 120 s pause
    hass.states.async_set("weather.home", "sunny", {"temperature": 18})
    await manager.async_set_weather_adjustment(
        True, "weather.home", 20.0, 30.0, 2.0, "forecast_high"
    )
    manager.weather_forecast_high = 30.0  # factor 2.0

    assert manager.estimated_total_seconds == 10 * 60 * 2 + 120
    assert manager.scaled_total_seconds == 10 * 60 * 2 * 2 + 120


# --------------------------------------------------------------------- #
# Changing a zone's duration while that zone is running
# --------------------------------------------------------------------- #


async def test_shortening_a_running_zone_ends_it_immediately(
    hass: HomeAssistant,
) -> None:
    """Reported live: a zone was running on its planned 18 minutes and the
    duration was changed to 1 minute from the card. The run used to freeze
    the target at zone start, so the valve kept going on the old value
    while the timeline already showed the new one - countdown and bar
    contradicting each other. The target is now re-read every tick, so a
    duration already behind us ends the zone at once."""
    manager = make_manager(hass, ["switch.zone_1"])
    manager.zones[0]["duration_minutes"] = 18

    calls = []

    async def fake_set_valve(entity_id, on):
        calls.append((entity_id, on))

    manager._async_set_valve = fake_set_valve

    async def shorten_after_a_moment():
        await asyncio.sleep(0.05)
        await manager.async_set_zone_duration("switch.zone_1", 1)

    with patch("asyncio.sleep", _instant_sleep):
        run = asyncio.create_task(manager._async_run_sequence())
        await shorten_after_a_moment()
        await asyncio.wait_for(run, timeout=5)

    # It stopped well short of the original 18 minutes.
    assert manager.status == "idle"
    assert ("switch.zone_1", False) in calls


async def test_lengthening_a_running_zone_extends_it(hass: HomeAssistant) -> None:
    """The mirror case: raising the duration mid-run keeps the zone going
    rather than ending it on the value captured at start."""
    manager = make_manager(hass, ["switch.zone_1"])
    manager.zones[0]["duration_minutes"] = 1

    assert manager._zone_seconds_for("switch.zone_1") == 60
    await manager.async_set_zone_duration("switch.zone_1", 5)
    assert manager._zone_seconds_for("switch.zone_1") == 300


async def test_remaining_total_reflects_current_config(hass: HomeAssistant) -> None:
    """The countdown is priced at the current configuration, so it can
    never disagree with what the timeline draws."""
    manager = make_manager(hass, ["switch.zone_1", "switch.zone_2"])
    manager.zones[0]["duration_minutes"] = 10
    manager.zones[1]["duration_minutes"] = 10
    manager.pause_between_zones_seconds = 120

    # Standing at the start of zone 0 with its full 10 minutes left.
    assert manager._remaining_after(0, 600, include_next_pause=True) == 600 + 600 + 120

    await manager.async_set_zone_duration("switch.zone_2", 5)
    assert manager._remaining_after(0, 600, include_next_pause=True) == 600 + 300 + 120


async def test_last_run_zones_persists_across_reload(hass: HomeAssistant) -> None:
    """The runs worth inspecting last_run_zones for are the automatic,
    scheduled ones - typically at night, with nobody watching. It has to
    survive a restart that happens to land between that run finishing and
    someone actually checking the attribute, not just live in memory."""
    manager = make_manager(hass, ["switch.zone_1"])
    manager.zones[0]["duration_minutes"] = 1

    async def fake_set_valve(entity_id, on):
        pass

    manager._async_set_valve = fake_set_valve

    with patch("asyncio.sleep", _instant_sleep):
        await asyncio.wait_for(manager._async_run_sequence(), timeout=5)

    assert len(manager.last_run_zones) == 1
    assert manager.last_run_zones[0]["entity_id"] == "switch.zone_1"
    assert manager.last_run_zones[0]["actual_elapsed_seconds"] == 60

    reloaded = make_manager(hass, ["switch.zone_1"])
    await reloaded.async_load()
    assert reloaded.last_run_zones == manager.last_run_zones


# --------------------------------------------------------------------- #
# Zones switching on outside a run
# --------------------------------------------------------------------- #


async def _watching_manager(hass: HomeAssistant, entity_id="switch.zone_1"):
    """A loaded manager watching one zone, with the valve calls captured.

    Starts the zone off and settles startup so the tests below control
    exactly which activation the manager gets to see."""
    hass.states.async_set(entity_id, "off")
    manager = make_manager(hass, [entity_id])
    await manager.async_load()
    await hass.async_block_till_done()

    calls = []

    async def fake_set_valve(eid, on):
        calls.append((eid, on))

    manager._async_set_valve = fake_set_valve
    return manager, calls


async def test_device_side_activation_is_recorded_and_switched_off(
    hass: HomeAssistant,
) -> None:
    """A relay that comes up on its own - its built-in timer, the vendor
    app, or a power cut with "turn on when powered" configured - waters the
    garden with nothing in Home Assistant having asked for it. The context
    on such a state change carries neither a user nor a parent."""
    manager, calls = await _watching_manager(hass)

    hass.states.async_set("switch.zone_1", "on")
    await hass.async_block_till_done()

    assert calls == [("switch.zone_1", False)]
    assert len(manager.unexpected_zone_activations) == 1
    record = manager.unexpected_zone_activations[0]
    assert record["entity_id"] == "switch.zone_1"
    assert record["source"] == "outside_home_assistant"
    assert record["turned_off"] is True


async def test_manual_switch_on_from_the_ui_is_recorded_but_left_running(
    hass: HomeAssistant,
) -> None:
    """Turning a zone on by hand to water something extra is a legitimate
    thing to do - shutting it off under the user would be worse than the
    problem this guards against. It is still recorded, so it stays possible
    to tell afterwards that a watering wasn't the schedule's doing."""
    manager, calls = await _watching_manager(hass)

    hass.states.async_set(
        "switch.zone_1", "on", context=Context(user_id="a-real-person")
    )
    await hass.async_block_till_done()

    assert calls == []
    assert len(manager.unexpected_zone_activations) == 1
    record = manager.unexpected_zone_activations[0]
    assert record["source"] == "ha_user"
    assert record["turned_off"] is False


async def test_switch_on_by_another_automation_is_recorded_and_named(
    hass: HomeAssistant,
) -> None:
    """Another automation opening a valve is deliberate, so it is left
    running - but "a zone came on" is only half an answer while
    troubleshooting; which automation did it is the useful half."""
    manager, calls = await _watching_manager(hass)

    trigger = Context()
    hass.states.async_set(
        "automation.old_garden_script",
        "on",
        {"friendly_name": "Old garden script"},
        context=trigger,
    )
    hass.states.async_set(
        "switch.zone_1", "on", context=Context(parent_id=trigger.id)
    )
    await hass.async_block_till_done()

    assert calls == []
    assert len(manager.unexpected_zone_activations) == 1
    record = manager.unexpected_zone_activations[0]
    assert record["source"] == "other_automation"
    assert record["actor"] == "Old garden script"
    assert record["turned_off"] is False


async def test_auto_off_disabled_reports_but_leaves_the_valve_open(
    hass: HomeAssistant,
) -> None:
    """Someone who waters from the vendor's own app needs the reporting
    without the guard closing the valve under them - the two are
    indistinguishable to Home Assistant."""
    manager, calls = await _watching_manager(hass)
    await manager.async_set_auto_off_unexpected(False)

    hass.states.async_set("switch.zone_1", "on")
    await hass.async_block_till_done()

    assert calls == []
    assert len(manager.unexpected_zone_activations) == 1
    assert manager.unexpected_zone_activations[0]["turned_off"] is False


async def test_auto_off_setting_persists_across_reload(hass: HomeAssistant) -> None:
    manager, _ = await _watching_manager(hass)
    assert manager.auto_off_unexpected_enabled is True

    await manager.async_set_auto_off_unexpected(False)

    reloaded = make_manager(hass, ["switch.zone_1"])
    await reloaded.async_load()
    assert reloaded.auto_off_unexpected_enabled is False


async def test_activation_during_a_run_is_not_flagged(hass: HomeAssistant) -> None:
    """The sequence turns zones on itself; that must never be mistaken for
    an unexpected activation and switched back off mid-run."""
    manager, calls = await _watching_manager(hass)
    manager.zones[0]["duration_minutes"] = 1

    async def turn_on_midway():
        await asyncio.sleep(0.05)
        hass.states.async_set("switch.zone_1", "on")
        await hass.async_block_till_done()

    with patch("asyncio.sleep", _instant_sleep):
        run = asyncio.create_task(manager._async_run_sequence())
        await turn_on_midway()
        await asyncio.wait_for(run, timeout=5)

    assert manager.unexpected_zone_activations == []


async def test_rapid_repeat_is_still_turned_off_but_reported_once(
    hass: HomeAssistant,
) -> None:
    """Found live: a zone coming back on 2 s after being closed was left
    running, because one cooldown throttled the reporting *and* the
    turn-off together. Water must never be the thing that gets rate
    limited - only the push messages and history entries are."""
    manager, calls = await _watching_manager(hass)

    for _ in range(3):
        hass.states.async_set("switch.zone_1", "on")
        await hass.async_block_till_done()
        hass.states.async_set("switch.zone_1", "off")
        await hass.async_block_till_done()

    # Closed every single time...
    assert calls == [("switch.zone_1", False)] * 3
    # ...but the user isn't told about the same flapping zone three times.
    assert len(manager.unexpected_zone_activations) == 1


async def test_device_that_keeps_switching_itself_on_is_given_up_on(
    hass: HomeAssistant,
) -> None:
    """Not throttling the turn-off means a device that insists on coming
    back would otherwise trade service calls with us forever. After a
    bounded number of attempts it stops and says so - which is the far
    more useful outcome, since it names a problem the user has to fix on
    the device itself."""
    manager, calls = await _watching_manager(hass)

    for _ in range(8):
        hass.states.async_set("switch.zone_1", "on")
        await hass.async_block_till_done()
        hass.states.async_set("switch.zone_1", "off")
        await hass.async_block_till_done()

    assert len(calls) == 5  # MAX_AUTO_OFF_ATTEMPTS, then it stops trying
    giving_up = [r for r in manager.unexpected_zone_activations if r.get("gave_up")]
    assert len(giving_up) == 1
    assert giving_up[0]["turned_off"] is False


async def test_overlapping_activations_do_not_race_the_turn_off_call(
    hass: HomeAssistant,
) -> None:
    """Reported live against a real Tuya-backed zone: a slow cloud round
    trip on the first turn-off call left it still in flight when a second
    activation of the same zone arrived. Firing a second, concurrent
    turn_off at the same device let the downstream integration drop one of
    them - the zone was found stuck on with no error logged anywhere.
    A second activation must wait for the first's call to actually finish
    rather than racing it."""
    manager, _ = await _watching_manager(hass)

    call_log: list[str] = []
    release_first = asyncio.Event()

    async def slow_then_fast_set_valve(entity_id, on):
        call_log.append(f"start:{on}")
        if len(call_log) == 1:
            # The first call blocks until the test explicitly lets it
            # through, standing in for the observed 5+ s cloud latency.
            await release_first.wait()
        call_log.append(f"end:{on}")

    manager._async_set_valve = slow_then_fast_set_valve

    hass.states.async_set("switch.zone_1", "on")
    # Let the first task start and block on the call. Deliberately not
    # hass.async_block_till_done() here - that waits for *every* pending
    # task, including this one, which is intentionally still parked.
    for _ in range(3):
        await asyncio.sleep(0)

    # Simulate the device flapping back on while the first turn-off is
    # still stuck mid-flight - the exact ordering observed live.
    hass.states.async_set("switch.zone_1", "off")
    await asyncio.sleep(0)
    hass.states.async_set("switch.zone_1", "on")
    for _ in range(3):
        await asyncio.sleep(0)

    # The second activation's task must be waiting on the lock, not
    # already having made (and possibly lost) its own concurrent call.
    assert call_log == ["start:False"]

    release_first.set()
    await hass.async_block_till_done()

    # Only now does the second call get to start - strictly after the
    # first one's call finished, never overlapping it.
    assert call_log == ["start:False", "end:False", "start:False", "end:False"]


async def test_a_hung_turn_off_call_times_out_instead_of_blocking_forever(
    hass: HomeAssistant,
) -> None:
    """Reported live: after the lock fix, one turn-off call to a real
    (Tuya-backed) device never returned - no exception, nothing in the
    log - while an independent, freshly issued turn_off for the same
    entity succeeded immediately. Nothing here was blocking the device;
    our own queued call just never came back. Without a timeout, that
    hangs the per-zone lock forever, wedging every future activation of
    that zone behind it until Home Assistant restarts."""
    manager, _ = await _watching_manager(hass)

    async def hangs_forever(entity_id, on):
        await asyncio.Event().wait()  # never set - simulates no response ever coming

    manager._async_set_valve = hangs_forever

    with patch(
        "custom_components.irrigation_sequencer.manager.AUTO_OFF_CALL_TIMEOUT_SECONDS",
        0.05,
    ):
        hass.states.async_set("switch.zone_1", "on")
        # Not async_block_till_done() - the hung call is deliberately left
        # running past the timeout, so waiting for every pending task would
        # wait on the very thing this test says we stop waiting for.
        await asyncio.sleep(0.2)

    record = manager.unexpected_zone_activations[-1]
    assert record["turned_off"] is False
    assert "timed out" in record["error"]

    # The lock must have been released despite the timeout - a second
    # activation (now with a working turn-off) is not stuck behind it, and
    # gets its own fresh call rather than joining the still-hung one.
    calls = []

    async def working_set_valve(entity_id, on):
        calls.append((entity_id, on))

    manager._async_set_valve = working_set_valve
    hass.states.async_set("switch.zone_1", "off")
    await asyncio.sleep(0.05)
    hass.states.async_set("switch.zone_1", "on")
    await asyncio.sleep(0.2)

    assert calls == [("switch.zone_1", False)]

    for task in list(manager._orphaned_off_tasks):
        task.cancel()
    await hass.async_block_till_done()


async def test_timeout_holds_even_when_the_call_swallows_cancellation(
    hass: HomeAssistant,
) -> None:
    """Reported live after the timeout was already in place: a zone sat at
    phase "calling_off" for minutes, far past the timeout, so the timeout
    plainly wasn't bounding anything. Awaiting the call directly means
    asyncio.timeout has to cancel *that await*, and the cancellation has
    to propagate back out through Home Assistant's service-call machinery
    and the device integration underneath it - which it did not. Running
    the call as its own shielded task makes giving up on waiting purely
    our own decision, independent of whether anything downstream honours
    cancellation at all."""
    manager, _ = await _watching_manager(hass)

    async def ignores_cancellation(entity_id, on):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Swallowed rather than re-raised, exactly as observed
            # downstream. Only the timeout's cancellation is absorbed; the
            # test's own cleanup cancel below still ends the task.
            await asyncio.Event().wait()

    manager._async_set_valve = ignores_cancellation

    with patch(
        "custom_components.irrigation_sequencer.manager.AUTO_OFF_CALL_TIMEOUT_SECONDS",
        0.05,
    ):
        hass.states.async_set("switch.zone_1", "on")
        await asyncio.sleep(0.2)

    # The handler moved on regardless, rather than sitting at "calling_off".
    assert manager.unexpected_activation_phase["switch.zone_1"] == "timed_out"
    record = manager.unexpected_zone_activations[-1]
    assert record["turned_off"] is False
    assert "timed out" in record["error"]

    for task in list(manager._orphaned_off_tasks):
        task.cancel()
    await asyncio.sleep(0)


async def test_phase_attribute_tracks_an_in_flight_attempt_live(
    hass: HomeAssistant,
) -> None:
    """The Python logger's level can be silently overridden outside this
    integration's control (a `logger:` block, some other component),
    making log-based diagnosis unreliable. This attribute uses the same
    state-attribute mechanism as everything else here instead, so which
    phase a stuck attempt is in is visible even when logs aren't."""
    manager, _ = await _watching_manager(hass)

    entered_call = asyncio.Event()
    release_call = asyncio.Event()

    async def pausable_set_valve(entity_id, on):
        entered_call.set()
        await release_call.wait()

    manager._async_set_valve = pausable_set_valve

    hass.states.async_set("switch.zone_1", "on")
    await asyncio.wait_for(entered_call.wait(), timeout=2)

    # Caught mid-flight: the phase must say so, and clearly enough to
    # know it's the call itself and not still waiting on the lock.
    assert manager.unexpected_activation_phase["switch.zone_1"] == "calling_off"

    release_call.set()
    await hass.async_block_till_done()

    # Settled again - nothing left in-flight for this zone.
    assert "switch.zone_1" not in manager.unexpected_activation_phase


async def test_attempt_counter_resets_after_a_quiet_window(hass: HomeAssistant) -> None:
    """Giving up must not be permanent - a zone that behaves for a while
    and then comes on again weeks later is a fresh incident, not the
    continuation of an old one."""
    manager, calls = await _watching_manager(hass)

    for _ in range(6):
        hass.states.async_set("switch.zone_1", "on")
        await hass.async_block_till_done()
        hass.states.async_set("switch.zone_1", "off")
        await hass.async_block_till_done()
    assert len(calls) == 5

    # Pretend the burst happened a couple of minutes ago.
    manager._auto_off_attempts = {}
    manager._unexpected_reported_at = {}
    manager._gave_up_announced = set()

    hass.states.async_set("switch.zone_1", "on")
    await hass.async_block_till_done()
    assert len(calls) == 6


async def test_unexpected_activations_persist_across_reload(hass: HomeAssistant) -> None:
    """The power-cut case takes Home Assistant down with it, so this has to
    still be there after it comes back up."""
    manager, _ = await _watching_manager(hass)

    hass.states.async_set("switch.zone_1", "on")
    await hass.async_block_till_done()
    assert len(manager.unexpected_zone_activations) == 1

    # The valve really does close as a result, so a manager coming up after
    # the restart finds it off and has nothing new of its own to report.
    hass.states.async_set("switch.zone_1", "off")
    await hass.async_block_till_done()

    reloaded = make_manager(hass, ["switch.zone_1"])
    await reloaded.async_load()
    await hass.async_block_till_done()
    assert reloaded.unexpected_zone_activations == manager.unexpected_zone_activations


async def test_zone_already_on_at_startup_is_flagged(hass: HomeAssistant) -> None:
    """A power cut that flips a relay on usually takes Home Assistant down
    too, so the state change happens with nothing listening - checking once
    after startup is what catches it at all."""
    # Deliberately no listener: the point is a zone that was already on
    # before this integration was watching anything at all.
    hass.states.async_set("switch.zone_1", "on")
    manager = make_manager(hass, ["switch.zone_1"])
    calls = []

    async def fake_set_valve(eid, on):
        calls.append((eid, on))

    manager._async_set_valve = fake_set_valve

    await manager._async_check_zones_on_at_startup()

    assert calls == [("switch.zone_1", False)]
    assert len(manager.unexpected_zone_activations) == 1
    assert manager.unexpected_zone_activations[0]["source"] == "already_on_at_startup"
