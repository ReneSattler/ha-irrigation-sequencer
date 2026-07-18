"""Start/stop buttons for manually controlling the sequence."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
            IrrigationSequencerStartButton(manager, entry),
            IrrigationSequencerStopButton(manager, entry),
        ]
    )


class _BaseButton(ButtonEntity):
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


class IrrigationSequencerStartButton(_BaseButton):
    _attr_translation_key = "start_now"
    _attr_icon = "mdi:play"

    def __init__(self, manager: IrrigationSequencerManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, "start_now")

    async def async_press(self) -> None:
        await self._manager.async_start_now()


class IrrigationSequencerStopButton(_BaseButton):
    _attr_translation_key = "stop"
    _attr_icon = "mdi:stop"

    def __init__(self, manager: IrrigationSequencerManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, "stop")

    async def async_press(self) -> None:
        await self._manager.async_stop()
