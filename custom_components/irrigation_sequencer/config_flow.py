"""Config flow: select the irrigation zones (1-10 valves/smart plugs).

Also provides an options flow so the zone selection can be changed later via
Settings -> Devices & Services -> Irrigation Sequencer -> Configure. All
other settings (order, duration, pauses, start time, winter mode, rain
pause, weather adjustment) are runtime settings controlled through the
Lovelace card or services, not through this dialog - see the README.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
)

from .const import CONF_ZONE_ENTITIES, DOMAIN, MAX_ZONES, MIN_ZONES


class IrrigationSequencerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Irrigation Sequencer."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        errors: dict[str, str] = {}

        if user_input is not None:
            zone_entities = user_input[CONF_ZONE_ENTITIES]
            if len(zone_entities) < MIN_ZONES:
                errors["base"] = "too_few_zones"
            elif len(zone_entities) > MAX_ZONES:
                errors["base"] = "too_many_zones"
            else:
                await self.async_set_unique_id(f"{DOMAIN}_{user_input['name']}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input["name"],
                    data={
                        CONF_ZONE_ENTITIES: zone_entities,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required("name", default="Lawn Irrigation"): TextSelector(),
                vol.Required(CONF_ZONE_ENTITIES): EntitySelector(
                    EntitySelectorConfig(domain=["valve", "switch", "light"], multiple=True)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "IrrigationSequencerOptionsFlow":
        return IrrigationSequencerOptionsFlow(config_entry)


class IrrigationSequencerOptionsFlow(OptionsFlow):
    """Lets the user change the zone entities after the initial setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        errors: dict[str, str] = {}

        if user_input is not None:
            zone_entities = user_input[CONF_ZONE_ENTITIES]
            if len(zone_entities) < MIN_ZONES:
                errors["base"] = "too_few_zones"
            elif len(zone_entities) > MAX_ZONES:
                errors["base"] = "too_many_zones"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_ZONE_ENTITIES: zone_entities},
                )
                return self.async_create_entry(title="", data={})

        current_zones = self.config_entry.data.get(CONF_ZONE_ENTITIES, [])
        schema = vol.Schema(
            {
                vol.Required(CONF_ZONE_ENTITIES, default=current_zones): EntitySelector(
                    EntitySelectorConfig(domain=["valve", "switch", "light"], multiple=True)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
