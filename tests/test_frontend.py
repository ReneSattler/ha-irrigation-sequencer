"""Tests for the self-hosted Lovelace card (no separate HACS Dashboard entry
or manual resource needed - the integration serves and registers its own
frontend module on startup)."""
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.irrigation_sequencer.const import DOMAIN


async def test_card_file_is_served_over_http(hass: HomeAssistant, hass_client) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    client = await hass_client()
    resp = await client.get(f"/{DOMAIN}_files/irrigation-sequencer-card.js")
    assert resp.status == 200
    body = await resp.text()
    assert "irrigation-sequencer-status-card" in body
    assert "irrigation-sequencer-settings-card" in body
