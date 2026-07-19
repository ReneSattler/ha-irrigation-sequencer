"""Status sensor: current zone, progress, schedule and weather factor – the
main data source for the Lovelace card."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_CURRENT_ZONE_ENTITY_ID,
    ATTR_CURRENT_ZONE_INDEX,
    ATTR_LAST_ZONE_INDEX,
    ATTR_NEXT_RUN,
    ATTR_PAUSE_BETWEEN_ZONES_SECONDS,
    ATTR_RAIN_PAUSE_UNTIL,
    ATTR_SECONDS_REMAINING_TOTAL,
    ATTR_SECONDS_REMAINING_ZONE,
    ATTR_START_TIMES,
    ATTR_WEATHER_ADJUSTMENT_ENABLED,
    ATTR_WEATHER_CURRENT_FACTOR,
    ATTR_WEATHER_CURRENT_TEMP,
    ATTR_WEATHER_ENTITY,
    ATTR_WEATHER_HOT_FACTOR,
    ATTR_WEATHER_HOT_TEMP,
    ATTR_WEATHER_REFERENCE_TEMP,
    ATTR_WINTER_MODE,
    ATTR_ZONES,
    DOMAIN,
)
from .manager import IrrigationSequencerManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager: IrrigationSequencerManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IrrigationSequencerStatusSensor(manager, entry)])


class IrrigationSequencerStatusSensor(Entity):
    """Exposes the full sequence status and configuration as state attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "status"
    _attr_should_poll = False
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, manager: IrrigationSequencerManager, entry: ConfigEntry) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "ha-irrigation-sequencer",
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._manager.async_add_listener(self.async_write_ha_state))

    @property
    def state(self) -> str:
        return self._manager.status

    @property
    def extra_state_attributes(self) -> dict:
        current_zone_entity_id = None
        if self._manager.current_zone_index is not None:
            current_zone_entity_id = self._manager.zones[self._manager.current_zone_index][
                "entity_id"
            ]

        return {
            "entry_id": self._manager.entry_id,
            ATTR_ZONES: self._manager.zones,
            ATTR_PAUSE_BETWEEN_ZONES_SECONDS: self._manager.pause_between_zones_seconds,
            ATTR_START_TIMES: self._manager.start_times,
            ATTR_WINTER_MODE: self._manager.winter_mode,
            ATTR_RAIN_PAUSE_UNTIL: self._manager.rain_pause_until,
            ATTR_CURRENT_ZONE_INDEX: self._manager.current_zone_index,
            ATTR_LAST_ZONE_INDEX: self._manager.last_zone_index,
            ATTR_CURRENT_ZONE_ENTITY_ID: current_zone_entity_id,
            ATTR_SECONDS_REMAINING_ZONE: self._manager.seconds_remaining_zone,
            ATTR_SECONDS_REMAINING_TOTAL: self._manager.seconds_remaining_total,
            ATTR_NEXT_RUN: self._manager.next_run,
            ATTR_WEATHER_ADJUSTMENT_ENABLED: self._manager.weather_adjustment_enabled,
            ATTR_WEATHER_ENTITY: self._manager.weather_entity,
            ATTR_WEATHER_REFERENCE_TEMP: self._manager.weather_reference_temp,
            ATTR_WEATHER_HOT_TEMP: self._manager.weather_hot_temp,
            ATTR_WEATHER_HOT_FACTOR: self._manager.weather_hot_factor,
            ATTR_WEATHER_CURRENT_TEMP: self._manager.weather_current_temp,
            ATTR_WEATHER_CURRENT_FACTOR: self._manager.weather_current_factor,
        }
