"""Tests for the self-hosted Lovelace card (no separate HACS Dashboard entry
or manual resource needed - the integration serves and registers its own
frontend module on startup)."""
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.irrigation_sequencer import _async_ensure_lovelace_resource
from custom_components.irrigation_sequencer.const import DOMAIN


async def test_card_file_is_served_over_http(hass: HomeAssistant, hass_client) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_client()
    resp = await client.get(f"/{DOMAIN}_files/irrigation-sequencer-card.js")
    assert resp.status == 200
    assert resp.headers["Cache-Control"] == "no-store"
    body = await resp.text()
    assert "irrigation-sequencer-status-card" in body
    assert "irrigation-sequencer-settings-card" in body


async def test_registers_lovelace_resource_on_setup(hass: HomeAssistant) -> None:
    """Regression coverage for switching away from add_extra_js_url(): that
    helper baked the <script> reference into the server-rendered index
    page, which a stale cached copy of that page (Home Assistant's own
    frontend service worker) kept serving without the update - the card
    stopped loading until the user manually cleared their browser/app
    cache after every single release. A Lovelace resource is instead
    fetched dynamically over the websocket connection on every dashboard
    load, so it doesn't have that staleness problem."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    from homeassistant.components.lovelace.const import LOVELACE_DATA

    items = hass.data[LOVELACE_DATA].resources.async_items()
    matches = [i for i in items if i["url"].startswith("/irrigation_sequencer_files/")]
    assert len(matches) == 1
    assert matches[0]["type"] == "module"
    assert matches[0]["url"].endswith("irrigation-sequencer-card.js?v=1.2.8")


async def test_lovelace_resource_is_updated_not_duplicated_on_version_change(
    hass: HomeAssistant,
) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    await _async_ensure_lovelace_resource(hass, "9.9.9")

    from homeassistant.components.lovelace.const import LOVELACE_DATA

    items = hass.data[LOVELACE_DATA].resources.async_items()
    matches = [i for i in items if i["url"].startswith("/irrigation_sequencer_files/")]
    assert len(matches) == 1
    assert matches[0]["url"].endswith("irrigation-sequencer-card.js?v=9.9.9")
