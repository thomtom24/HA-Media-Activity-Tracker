"""GUI setup and options, including arbitrary entity conditions."""
import math
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector
from .const import DOMAIN, MODES, OPERATORS


def entity_ref(hass, entity_id):
    entry = er.async_get(hass).async_get(entity_id)
    return entry.id if entry else entity_id


def resolve(hass, ref):
    registry = er.async_get(hass)
    return er.async_get_entity_id(hass, ref) or ref


def choice(values):
    return selector.SelectSelector(selector.SelectSelectorConfig(options=values, mode=selector.SelectSelectorMode.DROPDOWN))


class Settings:
    """Shared setup/options steps."""

    async def settings(self, user_input, step_id, defaults):
        old = defaults.get("conditions", [])
        if user_input is not None:
            self.settings_data = dict(user_input)
            self.pending = self.settings_data.pop("condition_entities", [])
            self.conditions = []
            self.old_conditions = {resolve(self.hass, c["entity"]): c for c in old}
            return await self.async_step_condition()
        return self.async_show_form(step_id=step_id, data_schema=vol.Schema({
            vol.Required("mode", default=defaults.get("mode", "playing")): choice(MODES),
            vol.Required("logic", default=defaults.get("logic", "and")): choice(["and", "or"]),
            vol.Optional("condition_entities", default=[resolve(self.hass, c["entity"]) for c in old]): selector.EntitySelector(selector.EntitySelectorConfig(multiple=True)),
            vol.Optional("excluded", default=defaults.get("excluded", "")): selector.TextSelector(),
        }))

    async def async_step_condition(self, user_input=None):
        if not self.pending:
            return self.complete({**self.settings_data, "conditions": self.conditions})
        entity = self.pending[0]
        errors = {}
        if user_input is not None:
            op, value = user_input["operator"], user_input["value"]
            if op in ("above", "below"):
                try:
                    if not math.isfinite(float(value)):
                        raise ValueError
                except ValueError:
                    errors["value"] = "invalid_number"
            if not errors:
                self.conditions.append({"entity": entity_ref(self.hass, entity), "operator": op, "value": value})
                self.pending = self.pending[1:]
                return await self.async_step_condition()
        previous = user_input or self.old_conditions.get(entity, {})
        return self.async_show_form(step_id="condition", description_placeholders={"entity": entity},
            data_schema=vol.Schema({
                vol.Required("operator", default=previous.get("operator", "equals")): choice(OPERATORS),
                vol.Required("value", default=previous.get("value", "on")): selector.TextSelector(),
            }), errors=errors)


class ConfigFlow(Settings, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input:
            self.source = entity_ref(self.hass, user_input["entity"])
            await self.async_set_unique_id(self.source)
            self._abort_if_unique_id_configured()
            self.name = user_input["name"]
            return await self.async_step_settings()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player")),
        }))

    async def async_step_settings(self, user_input=None):
        return await self.settings(user_input, "settings", {})

    def complete(self, settings):
        return self.async_create_entry(title=self.name, data={"source": self.source, **settings})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return Options()


class Options(Settings, config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        return await self.settings(user_input, "init", {**self.config_entry.data, **self.config_entry.options})

    def complete(self, settings):
        return self.async_create_entry(title="", data=settings)
