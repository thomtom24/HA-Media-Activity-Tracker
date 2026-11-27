"""GUI setup and options, including arbitrary entity conditions."""
import math
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector
from .const import DOMAIN, MODES, OPERATORS
from .config_values import app_list, alias_rows, valid_application_settings


def entity_ref(hass, entity_id):
    entry = er.async_get(hass).async_get(entity_id)
    return entry.id if entry else entity_id


def resolve(hass, ref):
    registry = er.async_get(hass)
    if "." in ref:
        return ref
    # Registry IDs remain stable across entity renames.
    if entry := registry.async_get(ref):
        return entry.entity_id
    return f"sensor.media_activity_missing_{ref}"


def choice(values):
    return selector.SelectSelector(selector.SelectSelectorConfig(options=values, mode=selector.SelectSelectorMode.DROPDOWN))


class Settings:
    """Shared setup/options steps."""

    async def settings(self, user_input, step_id, defaults):
        old = defaults.get("conditions", [])
        errors = {}
        if user_input is not None:
            selected = user_input.get("condition_entities", [])
            registry = er.async_get(self.hass)
            if any((item := registry.async_get(e)) is not None and item.platform == DOMAIN for e in selected):
                errors["condition_entities"] = "circular_condition"
            elif not valid_application_settings(user_input):
                errors["base"] = "invalid_text"
            elif len(selected) > 20:
                errors["condition_entities"] = "too_many_conditions"
            else:
                self.settings_data = dict(user_input)
                self.pending = self.settings_data.pop("condition_entities", [])
                self.conditions = []
                self.old_conditions = {resolve(self.hass, c["entity"]): c for c in old}
                return await self.async_step_condition()
        return self.async_show_form(step_id=step_id, data_schema=vol.Schema({
            vol.Required("mode", default=defaults.get("mode", "playing")): choice(MODES),
            vol.Required("logic", default=defaults.get("logic", "and")): choice(["and", "or"]),
            vol.Optional("condition_entities", default=[resolve(self.hass, c["entity"]) for c in old]): selector.EntitySelector(selector.EntitySelectorConfig(multiple=True)),
            vol.Optional("retention_days", default=defaults.get("retention_days", 90)): vol.All(vol.Coerce(int), vol.Range(min=1, max=3650)),
            vol.Optional("pause_timeout", default=defaults.get("pause_timeout", 30)): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            vol.Optional("excluded", default=app_list(defaults.get("excluded", []))): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
            vol.Optional("aliases", default=alias_rows(defaults.get("aliases", []))): selector.ObjectSelector(selector.ObjectSelectorConfig(multiple=True, label_field="key", fields={"key": {"label": "App name or ID", "selector": selector.TextSelector(), "required": True}, "label": {"label": "Display name", "selector": selector.TextSelector(), "required": True}})),
            vol.Optional("app_sensors", default=app_list(defaults.get("app_sensors", []))): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
        }), errors=errors)

    async def async_step_condition(self, user_input=None):
        if not self.pending:
            return self.complete({**self.settings_data, "conditions": self.conditions})
        entity = self.pending[0]
        errors = {}
        if user_input is not None:
            op, value = user_input["operator"], user_input["value"]
            if not isinstance(value, str) or not value.strip() or len(value) > 255:
                errors["value"] = "invalid_value"
            elif op in ("above", "below"):
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
        errors = {}
        if user_input and (not user_input["name"].strip() or len(user_input["name"]) > 128):
            errors["name"] = "invalid_name"
        elif user_input:
            self._media_source_ref = entity_ref(self.hass, user_input["entity"])
            await self.async_set_unique_id(self._media_source_ref)
            self._abort_if_unique_id_configured()
            self._tracker_name = user_input["name"]
            return await self.async_step_settings()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player")),
        }), errors=errors)

    async def async_step_settings(self, user_input=None):
        return await self.settings(user_input, "settings", {})

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            ref = entity_ref(self.hass, user_input["entity"])
            if any(e.entry_id != entry.entry_id and e.unique_id == ref for e in self.hass.config_entries.async_entries(DOMAIN)):
                errors["entity"] = "already_configured"
            elif not user_input.get("retain_history"):
                errors["retain_history"] = "confirm_history"
            else:
                return self.async_update_reload_and_abort(entry, unique_id=ref, data_updates={"source": ref})
        return self.async_show_form(step_id="reconfigure", data_schema=vol.Schema({
            vol.Required("entity", default=resolve(self.hass, entry.data["source"])): selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player")),
            vol.Required("retain_history", default=False): selector.BooleanSelector(),
        }), errors=errors)

    def complete(self, settings):
        return self.async_create_entry(title=self._tracker_name, data={"source": self._media_source_ref, **settings})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return Options()


class Options(Settings, config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        return await self.settings(user_input, "init", {**self.config_entry.data, **self.config_entry.options})

    def complete(self, settings):
        return self.async_create_entry(title="", data=settings)
