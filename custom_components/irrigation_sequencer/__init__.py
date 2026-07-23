"""Irrigation Sequencer – multi-zone irrigation control with sequencing,
pauses, night start, winter mode, rain pause and weather-based duration
adjustment."""
from __future__ import annotations

from pathlib import Path

import voluptuous as vol
from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    CONF_ZONE_ENTITIES,
    DOMAIN,
    MAX_RAIN_PAUSE_DAYS,
    MAX_START_TIMES,
    MAX_ZONE_DURATION_MINUTES,
    MIN_RAIN_PAUSE_DAYS,
    MIN_START_TIMES,
    PLATFORMS,
    SERVICE_CLEAR_RAIN_PAUSE,
    SERVICE_SET_PAUSE_BETWEEN_ZONES,
    SERVICE_SET_RAIN_PAUSE,
    SERVICE_SET_START_TIMES,
    SERVICE_SET_NOTIFY_TARGET,
    SERVICE_SET_WEATHER_ADJUSTMENT,
    SERVICE_SET_WINTER_MODE,
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
        vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_ZONE_DURATION_MINUTES)),
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
SET_START_TIMES_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("start_times"): vol.All(
            cv.ensure_list, [cv.time], vol.Length(min=MIN_START_TIMES, max=MAX_START_TIMES)
        ),
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
SET_WINTER_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("enabled"): cv.boolean,
    }
)
SET_NOTIFY_TARGET_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Optional("target"): vol.Any(cv.string, None),
    }
)
ENTRY_ID_ONLY_SCHEMA = vol.Schema({vol.Required("entry_id"): cv.string})

FRONTEND_URL_BASE = f"/{DOMAIN}_files"
CARD_FILENAME = "irrigation-sequencer-card.js"


class _CardFileView(HomeAssistantView):
    """Serves the self-hosted card with an explicit no-store Cache-Control
    header - HA's built-in static-path helper only offers a choice between
    a 1-month "public, max-age=..." header or no Cache-Control header at
    all (the latter leaves browsers free to heuristically cache the
    response based on its Last-Modified date). The resource URL already
    carries a `?v=<integration version>` query string that changes on
    every release, so a stale cached copy of an old version's URL was
    never actually a problem - this exists purely as defense in depth."""

    url = f"{FRONTEND_URL_BASE}/{CARD_FILENAME}"
    name = f"{DOMAIN}:card_file"
    requires_auth = False

    def __init__(self, content: bytes) -> None:
        self._content = content

    async def get(self, request: web.Request) -> web.Response:
        return web.Response(
            body=self._content,
            content_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )


async def _async_ensure_lovelace_resource(hass: HomeAssistant, version: str) -> None:
    """Register (or update, on a version change) a Lovelace resource entry
    for the card, instead of the frontend.add_extra_js_url() helper this
    used before v1.2.8.

    add_extra_js_url() bakes the <script> reference directly into the
    server-rendered index page. A stale cached copy of that page (Home
    Assistant's frontend is a PWA with its own service worker, which a
    custom integration can't control) kept serving without the new
    reference after every single update, requiring the user to manually
    clear their browser/app cache each time - not something we could fix
    while using that mechanism.

    A Lovelace resource, by contrast, is stored server-side and the URL
    list is fetched dynamically over the websocket connection on every
    dashboard load rather than baked into any static, cacheable page -
    the same delivery mechanism every other HACS frontend card relies on,
    which doesn't have this staleness problem. Skips silently if this
    instance manages resources via YAML (resource_mode: yaml in
    configuration.yaml) - that collection is read-only from here, and a
    user in that mode is already managing resources by hand.
    """
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None or not isinstance(
        lovelace_data.resources, ResourceStorageCollection
    ):
        return

    resources = lovelace_data.resources
    await resources.async_get_info()  # ensures the collection is loaded

    base_url = f"{FRONTEND_URL_BASE}/{CARD_FILENAME}"
    new_url = f"{base_url}?v={version}"
    existing = next(
        (item for item in resources.async_items() if item["url"].startswith(base_url)),
        None,
    )
    if existing is None:
        await resources.async_create_item({"res_type": "module", "url": new_url})
    elif existing["url"] != new_url:
        await resources.async_update_item(existing["id"], {"url": new_url})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Self-host the Lovelace card so it loads automatically - no separate
    HACS "Dashboard" download or manual resource registration needed."""
    integration = await async_get_integration(hass, DOMAIN)
    card_path = Path(integration.file_path) / "frontend" / CARD_FILENAME
    content = await hass.async_add_executor_job(card_path.read_bytes)
    hass.http.register_view(_CardFileView(content))
    await _async_ensure_lovelace_resource(hass, integration.version)
    return True


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
    # Services are registered per-domain, not per-entry, but this function
    # runs once per config entry - skip if a previous entry already
    # registered them so a second irrigation system doesn't duplicate/reset
    # the handlers.
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

    async def handle_set_start_times(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_set_start_times([str(t) for t in call.data["start_times"]])

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

    async def handle_set_winter_mode(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_set_winter_mode(call.data["enabled"])

    async def handle_set_notify_target(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["entry_id"])
        await manager.async_set_notify_target(call.data.get("target"))

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
        DOMAIN, SERVICE_SET_START_TIMES, handle_set_start_times, schema=SET_START_TIMES_SCHEMA
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
        DOMAIN, SERVICE_SET_WINTER_MODE, handle_set_winter_mode, schema=SET_WINTER_MODE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_NOTIFY_TARGET,
        handle_set_notify_target,
        schema=SET_NOTIFY_TARGET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_START_NOW, handle_start_now, schema=ENTRY_ID_ONLY_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_STOP, handle_stop, schema=ENTRY_ID_ONLY_SCHEMA)
