"""Unit tests for IrrigationSequencerManager's core logic."""
import asyncio
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
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
