"""Tests for the options flow that lets users change zones after setup.

Regression coverage for a real bug: manually assigning self.config_entry in
OptionsFlow.__init__ (the old pattern) used to just be deprecated but now
raises on current HA core, breaking "Configure" with a 500 error."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.irrigation_sequencer.const import CONF_ZONE_ENTITIES, DOMAIN


async def test_options_flow_adds_a_second_zone(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ZONE_ENTITIES: ["light.stehlampe"]}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ZONE_ENTITIES: ["light.stehlampe", "light.wohnzimmer"]},
    )
    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_ZONE_ENTITIES] == ["light.stehlampe", "light.wohnzimmer"]
