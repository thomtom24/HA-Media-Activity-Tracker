"""Test bundled card registration without mutating real dashboard storage."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection

from custom_components.media_activity_tracker.card_resource import (
    CARD_PATH, CARD_URL, CARD_VERSION, async_ensure_resource, async_register_card,
)


def collection(items=(), loaded=True):
    resources = MagicMock(spec=ResourceStorageCollection)
    resources.loaded = loaded
    resources.async_items.return_value = list(items)
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()
    resources.async_get_info = AsyncMock()
    return resources


class ResourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_load_before_write_and_preserve_other_resources(self):
        resources = collection([{"id": "other", "url": "/local/other.js", "type": "module"}], False)
        async def load():
            resources.loaded = True
        resources.async_get_info.side_effect = load
        await async_ensure_resource(resources)
        resources.async_get_info.assert_awaited_once()
        resources.async_create_item.assert_awaited_once_with({"res_type": "module", "url": CARD_URL})
        resources.async_update_item.assert_not_awaited()

    async def test_never_write_unloaded_collection(self):
        resources = collection(loaded=False)
        await async_ensure_resource(resources)
        resources.async_items.assert_not_called()
        resources.async_create_item.assert_not_awaited()

    async def test_version_update_and_idempotence(self):
        resources = collection([{"id": "ours", "url": CARD_PATH + "?v=0.1.1", "type": "module"}])
        await async_ensure_resource(resources)
        resources.async_update_item.assert_awaited_once_with("ours", {"res_type": "module", "url": CARD_URL})
        resources.async_update_item.reset_mock()
        resources.async_items.return_value = [{"id": "ours", "url": CARD_URL, "type": "module"}]
        await async_ensure_resource(resources)
        resources.async_update_item.assert_not_awaited()
        resources.async_create_item.assert_not_awaited()

    async def test_legacy_resource_not_changed_or_duplicated(self):
        for url in ("/hacsfiles/HA-Media-Activity-Card/ha-media-activity-card.js?hacstag=123",
                    "/local/community/HA-Media-Activity-Card/ha-media-activity-card.js",
                    "/local/ha-media-activity-card.js"):
            with self.subTest(url=url):
                resources = collection([{"id": "old", "url": url, "type": "module"}])
                await async_ensure_resource(resources)
                resources.async_create_item.assert_not_awaited()
                resources.async_update_item.assert_not_awaited()

    async def test_static_path_and_read_only_yaml(self):
        resources = MagicMock()
        hass = SimpleNamespace(http=SimpleNamespace(async_register_static_paths=AsyncMock()),
                               data={LOVELACE_DATA: SimpleNamespace(resources=resources)})
        await async_register_card(hass)
        paths = hass.http.async_register_static_paths.await_args.args[0]
        self.assertEqual(paths[0].url_path, CARD_PATH)
        self.assertTrue(Path(paths[0].path).is_file())
        resources.async_create_item.assert_not_called()

    def test_versions_and_asset(self):
        root = Path(__file__).resolve().parents[1] / "custom_components" / "media_activity_tracker"
        self.assertEqual(json.loads((root / "manifest.json").read_text())["version"], CARD_VERSION)
        self.assertIn("Media Activity Card " + CARD_VERSION, (root / "www" / "ha-media-activity-card.js").read_text())
