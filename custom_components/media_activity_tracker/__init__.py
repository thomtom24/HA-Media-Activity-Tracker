"""Media Activity Tracker."""
import logging
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.core import callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN
from .tracker import Tracker

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})
    websocket_api.async_register_command(hass, websocket_report)
    try:
        from .card_resource import async_register_card
        await async_register_card(hass)
    except Exception:
        _LOGGER.exception("Optional dashboard setup failed; media tracking remains available")
    return True


@websocket_api.websocket_command({vol.Required("type"): DOMAIN + "/report",
                                vol.Required("entry_id"): str,
                                vol.Optional("days", default=366): vol.All(int, vol.Range(min=1, max=3660))})
@callback
def websocket_report(hass, connection, msg):
    tracker = hass.data[DOMAIN].get(msg["entry_id"])
    if not tracker:
        connection.send_error(msg["id"], "not_found", "Tracker not loaded")
        return
    if not connection.user.permissions.check_entity(tracker.source, POLICY_READ):
        connection.send_error(msg["id"], "unauthorized", "Source entity access denied")
        return
    connection.send_result(msg["id"], tracker.report(msg["days"]))


async def async_setup_entry(hass, entry):
    tracker = Tracker(hass, entry)
    await tracker.start()
    entry.runtime_data = tracker
    hass.data[DOMAIN][entry.entry_id] = tracker
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, ["sensor"]):
        return False
    await entry.runtime_data.stop()
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def async_remove_entry(hass, entry):
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
