"""Test bundled card registration without mutating real dashboard storage."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp.test_utils import TestClient, TestServer
from homeassistant.components.http import HomeAssistantHTTP, KEY_ALLOW_CONFIGURED_CORS

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

    async def test_real_ha_http_serves_only_bundled_file(self):
        async def executor(func, *args):
            return await asyncio.to_thread(func, *args)
        hass = SimpleNamespace(data={}, async_add_executor_job=executor)
        hass.http = HomeAssistantHTTP(hass, None, None, None, None, 0, [], "modern")
        hass.http.app[KEY_ALLOW_CONFIGURED_CORS] = lambda _: None
        await async_register_card(hass)
        await async_register_card(hass)  # no duplicate routes on repeated setup
        async with TestClient(TestServer(hass.http.app)) as client:
            response = await client.get(CARD_URL)
            self.assertEqual(response.status, 200)
            self.assertIn("javascript", response.headers["Content-Type"])
            self.assertIn("Media Activity Card " + CARD_VERSION, await response.text())
            self.assertEqual((await client.get("/media_activity_tracker/manifest.json")).status, 404)

    async def test_multiple_entries_share_single_card_registration(self):
        from custom_components.media_activity_tracker import async_setup, async_setup_entry
        from custom_components.media_activity_tracker.const import DOMAIN
        hass = SimpleNamespace(data={}, http=SimpleNamespace(async_register_static_paths=AsyncMock()),
                               config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock()))
        entries = [SimpleNamespace(entry_id="a"), SimpleNamespace(entry_id="b")]
        with patch("custom_components.media_activity_tracker.websocket_api.async_register_command"), \
             patch("custom_components.media_activity_tracker.Tracker") as tracker:
            tracker.side_effect = [SimpleNamespace(start=AsyncMock()), SimpleNamespace(start=AsyncMock())]
            self.assertTrue(await async_setup(hass, {}))
            for entry in entries:
                self.assertTrue(await async_setup_entry(hass, entry))
            self.assertEqual(set(hass.data[DOMAIN]), {"a", "b"})
            self.assertIsNot(hass.data[DOMAIN]["a"], hass.data[DOMAIN]["b"])
            hass.http.async_register_static_paths.assert_awaited_once()

    async def test_static_registration_failure_is_nonfatal(self):
        hass = SimpleNamespace(data={}, http=SimpleNamespace(async_register_static_paths=AsyncMock(side_effect=RuntimeError("test"))))
        with self.assertLogs("custom_components.media_activity_tracker.card_resource", level="ERROR"):
            await async_register_card(hass)
