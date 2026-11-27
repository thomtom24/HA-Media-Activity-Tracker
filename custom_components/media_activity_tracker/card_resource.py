"""Serve and register the bundled dashboard card once per HA process."""
import logging
from pathlib import Path
from urllib.parse import urlsplit

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection

_LOGGER = logging.getLogger(__name__)
CARD_VERSION = "0.2.0"
REGISTERED = "media_activity_tracker.card_registered"
CARD_FILENAME = "ha-media-activity-card.js"
CARD_PATH = f"/media_activity_tracker/{CARD_FILENAME}"
CARD_URL = f"{CARD_PATH}?v={CARD_VERSION}"
LEGACY_PATHS = {
    f"/hacsfiles/ha-media-activity-card/{CARD_FILENAME}",
    f"/local/community/ha-media-activity-card/{CARD_FILENAME}",
    f"/local/{CARD_FILENAME}",
}


def resource_path(url):
    """Compare resource paths independently of query strings and fragments."""
    return urlsplit(url).path.rstrip("/")


async def async_register_card(hass):
    """Expose only the card file, then safely register a storage-mode resource."""
    if hass.data.get(REGISTERED):
        return
    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig(CARD_PATH, str(Path(__file__).parent / "www" / CARD_FILENAME), False)
        ])
    except Exception:
        _LOGGER.exception("Unable to serve Media Activity Card; tracking remains available")
        return

    hass.data[REGISTERED] = True
    lovelace = hass.data.get(LOVELACE_DATA)
    resources = getattr(lovelace, "resources", None)
    if not isinstance(resources, ResourceStorageCollection):
        # YAML resources are read-only; document the manual module URL.
        _LOGGER.debug("No writable dashboard resources; use %s if needed", CARD_URL)
        return
    try:
        await async_ensure_resource(resources)
    except (HomeAssistantError, OSError, RuntimeError, ValueError):
        _LOGGER.exception("Unable to register Media Activity Card; add %s manually", CARD_URL)


async def async_ensure_resource(resources):
    """Load persisted resources before inspecting or updating our own URL."""
    if not resources.loaded:
        await resources.async_get_info()
    if not resources.loaded:
        _LOGGER.warning("Dashboard resources not loaded; leaving them untouched")
        return
    items = resources.async_items()
    if any(resource_path(item.get("url", "")).lower() in LEGACY_PATHS for item in items):
        _LOGGER.warning(
            "Standalone Media Activity Card resource found. Uninstall the old card, "
            "remove its old dashboard resource if present and restart HA to activate the bundled card"
        )
        return
    ours = [item for item in items if resource_path(item.get("url", "")) == CARD_PATH]
    if not ours:
        await resources.async_create_item({"res_type": "module", "url": CARD_URL})
        return
    # Update only our own resource. Do not delete any user-managed resource.
    item = ours[0]
    if item["url"] != CARD_URL or item.get("type") != "module":
        await resources.async_update_item(item["id"], {"res_type": "module", "url": CARD_URL})
    if len(ours) > 1:
        _LOGGER.warning("Multiple bundled Media Activity Card resources; remove duplicates in Settings > Dashboards > Resources")
