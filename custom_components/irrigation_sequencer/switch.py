"""Switch entities: winter mode (fully disables irrigation) and weather-based
duration adjustment (on/off)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .manager import IrrigationSequencerManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager: IrrigationSequencerManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            IrrigationSequencerWinterModeSwitch(manager, entry),
            IrrigationSequencerWeatherAdjustmentSwitch(manager, entry),
            IrrigationSequencerAutoOffUnexpectedSwitch(manager, entry),
            IrrigationSequencerFrostProtectionSwitch(manager, entry),
            IrrigationSequencerRainDelaySwitch(manager, entry),
        ]
    )


class _BaseSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: IrrigationSequencerManager, entry: ConfigEntry, key: str) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "ha-irrigation-sequencer",
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._manager.async_add_listener(self.async_write_ha_state))


class IrrigationSequencerWinterModeSwitch(_BaseSwitch):
    """Switch to fully disable irrigation for the winter season."""

    _attr_translation_key = "winter_mode"
    _attr_icon = "mdi:snowflake"

    def __init__(self, manager: IrrigationSequencerManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, "winter_mode")

    @property
    def is_on(self) -> bool:
        return self._manager.winter_mode

    async def async_turn_on(self, **kwargs) -> None:
        await self._manager.async_set_winter_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._manager.async_set_winter_mode(False)


class IrrigationSequencerWeatherAdjustmentSwitch(_BaseSwitch):
    """Switch to enable/disable temperature-based duration adjustment."""

    _attr_translation_key = "weather_adjustment"
    _attr_icon = "mdi:weather-partly-cloudy"

    def __init__(self, manager: IrrigationSequencerManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, "weather_adjustment")

    @property
    def is_on(self) -> bool:
        return self._manager.weather_adjustment_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self._manager.async_set_weather_adjustment(
            True,
            self._manager.weather_entity,
            self._manager.weather_reference_temp,
            self._manager.weather_hot_temp,
            self._manager.weather_hot_factor,
        )

    async def async_turn_off(self, **kwargs) -> None:
        await self._manager.async_set_weather_adjustment(
            False,
            self._manager.weather_entity,
            self._manager.weather_reference_temp,
            self._manager.weather_hot_temp,
            self._manager.weather_hot_factor,
        )


class IrrigationSequencerAutoOffUnexpectedSwitch(_BaseSwitch):
    """Switch controlling whether a zone that came on outside a run gets
    closed again.

    Turn it off if you also water manually from the valve vendor's own app:
    that is indistinguishable from the device switching itself on, so the
    guard would otherwise shut the water off under you. Reporting (log,
    attribute, notification) happens either way."""

    _attr_translation_key = "auto_off_unexpected"
    _attr_icon = "mdi:water-alert"

    def __init__(self, manager: IrrigationSequencerManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, "auto_off_unexpected")

    @property
    def is_on(self) -> bool:
        return self._manager.auto_off_unexpected_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self._manager.async_set_auto_off_unexpected(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._manager.async_set_auto_off_unexpected(False)


class IrrigationSequencerFrostProtectionSwitch(_BaseSwitch):
    """Switch blocking scheduled runs near freezing - a milder, automatic
    sibling of winter mode for cold spring/autumn nights."""

    _attr_translation_key = "frost_protection"
    _attr_icon = "mdi:snowflake-alert"

    def __init__(self, manager: IrrigationSequencerManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, "frost_protection")

    @property
    def is_on(self) -> bool:
        return self._manager.frost_protection_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self._manager.async_set_frost_protection(
            True, self._manager.frost_threshold_temp
        )

    async def async_turn_off(self, **kwargs) -> None:
        await self._manager.async_set_frost_protection(
            False, self._manager.frost_threshold_temp
        )


class IrrigationSequencerRainDelaySwitch(_BaseSwitch):
    """Switch for the automatic, forecast-based rain delay - strictly
    opt-in, so an instance that never enables it behaves exactly as
    before this feature existed."""

    _attr_translation_key = "rain_delay"
    _attr_icon = "mdi:weather-rainy"

    def __init__(self, manager: IrrigationSequencerManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, "rain_delay")

    @property
    def is_on(self) -> bool:
        return self._manager.rain_delay_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self._manager.async_set_rain_delay(
            True, self._manager.rain_delay_threshold_mm
        )

    async def async_turn_off(self, **kwargs) -> None:
        await self._manager.async_set_rain_delay(
            False, self._manager.rain_delay_threshold_mm
        )
