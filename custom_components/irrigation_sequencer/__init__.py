"""Irrigation Sequencer – multi-zone irrigation control with sequencing,
pauses, night start, winter mode, rain pause and weather-based duration
adjustment."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ZONE_ENTITIES,
    DOMAIN,
    MAX_RAIN_PAUSE_DAYS,
    MIN_RAIN_PAUSE_DAYS,
    PLATFORMS,
    SERVICE_CLEAR_RAIN_PAUSE,
    SERVICE_SET_PAUSE_BETWEEN_ZONES,
    SERVICE_SET_RAIN_PAUSE,
    SERVICE_SET_START_TIME,
    SERVICE_SET_WEATHER_ADJUSTMENT,
    SERVICE_SET_ZONE_DURATION,
    SERVICE_SET_ZONE_NAME,
    SERVICE_SET_ZONE_ORDER,
    SERVICE_START_NOW,
    SERVICE_STOP,
)
from .manager import IrrigationSequencerManager

SET_ZONE_ORDER_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("zones"): vol.All(cv.ensure_list, [cv.entity_id]),
    }
)
SET_ZONE_DURATION_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
    }
)
SET_ZONE_NAME_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("name"): cv.string,
    }
)
SET_PAUSE_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("seconds"): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
    }
)
SET_START_TIME_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("start_time"): cv.time,
    }
)
SET_RAIN_PAUSE_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("days"): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_RAIN_PAUSE_DAYS, max=MAX_RAIN_PAUSE_DAYS)
        ),
    }
)
SET_WEATHER_ADJUSTMENT_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("enabled"): cv.boolean,
        vol.Optional("weather_entity"): vol.Any(cv.entity_id, None),
        vol.Required("reference_temp"): vol.Coerce(float),
        vol.Required("hot_temp"): vol.Coerce(float),
        vol.Required("hot_factor"): vol.Coerce(float),
    }
)
ENTRY_ID_ONLY_SCHEMA = vol.Schema({vol.Required("entry_id"): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    zone_entities = entry.data[CONF_ZONE_ENTITIES]
    manager = IrrigationSequencerManager(hass, entry.entry_id, zone_entities)
    await manager.async_load()
    hass.data[DOMAIN][entry.entry_id] = manager

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its zone selection changes via the options flow."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager: IrrigationSequencerManager = hass.data[DOMAIN][entry.entry_id]
    await manager.async_unload()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _get_manager(hass: HomeAssistant, entry_id: str) -> IrrigationSequencerManager:
    manager = hass.data.get(DOMAIN, {}).get(entry_id)
    if manager is None:
        raise ValueError(f"Unknown Irrigation Sequencer entry_id: {entry_id}")
    return manager


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_ZONE_ORDER):
        return

    async def handle_set_zone_order(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_set_zone_order(call.data["zones"])

    async def handle_set_zone_duration(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_set_zone_duration(call.data["entity_id"], call.data["minutes"])

    async def handle_set_zone_name(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_set_zone_name(call.data["entity_id"], call.data["name"])

    async def handle_set_pause(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_set_pause_between_zones(call.data["seconds"])

    async def handle_set_start_time(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_set_start_time(str(call.data["start_time"]))

    async def handle_set_rain_pause(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_set_rain_pause(call.data["days"])

    async def handle_clear_rain_pause(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_clear_rain_pause()

    async def handle_set_weather_adjustment(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_set_weather_adjustment(
            call.data["enabled"],
            call.data.get("weather_entity"),
            call.data["reference_temp"],
            call.data["hot_temp"],
            call.data["hot_factor"],
        )

    async def handle_start_now(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_start_now()

    async def handle_stop(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_stop()

    hass.services.async_register(
        DOMAIN, SERVICE_SET_ZONE_ORDER, handle_set_zone_order, schema=SET_ZONE_ORDER_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ZONE_DURATION,
        handle_set_zone_duration,
        schema=SET_ZONE_DURATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_ZONE_NAME, handle_set_zone_name, schema=SET_ZONE_NAME_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_PAUSE_BETWEEN_ZONES, handle_set_pause, schema=SET_PAUSE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_START_TIME, handle_set_start_time, schema=SET_START_TIME_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_RAIN_PAUSE, handle_set_rain_pause, schema=SET_RAIN_PAUSE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_RAIN_PAUSE,
        handle_clear_rain_pause,
        schema=ENTRY_ID_ONLY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_WEATHER_ADJUSTMENT,
        handle_set_weather_adjustment,
        schema=SET_WEATHER_ADJUSTMENT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_START_NOW, handle_start_now, schema=ENTRY_ID_ONLY_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_STOP, handle_stop, schema=ENTRY_ID_ONLY_SCHEMA)
