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
