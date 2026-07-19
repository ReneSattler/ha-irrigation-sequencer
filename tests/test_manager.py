"""Unit tests for IrrigationSequencerManager's core logic."""
from datetime import date, timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.irrigation_sequencer.manager import IrrigationSequencerManager


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
