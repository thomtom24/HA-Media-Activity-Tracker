"""Exercise persistence and report permission failures."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.storage import Store
from custom_components.media_activity_tracker.history import HistoryStore
from custom_components.media_activity_tracker.history_schema import validate
from custom_components.media_activity_tracker import websocket_report


class SafetyTests(unittest.IsolatedAsyncioTestCase):
    def test_malformed_history_is_rejected(self):
        with self.assertRaises((KeyError,ValueError)):
            validate({"started":"2026-11-27T00:00:00+00:00","apps":{},"days":{"bad":{}},"sessions":[]})
        with self.assertRaises(ValueError):
            validate({"started":"2026-11-27T00:00:00+00:00","apps":{},"days":{},"sessions":[],"history_schema":999})

    async def test_write_error_is_visible(self):
        store=object.__new__(HistoryStore)
        store.write_failed=False
        store.last_success=None
        with patch.object(Store,"_async_write_data",new_callable=AsyncMock,side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await store._async_write_data({})
        self.assertTrue(store.write_failed)
        with patch.object(Store,"_async_write_data",new_callable=AsyncMock):
            await store._async_write_data({})
        self.assertFalse(store.write_failed)
        self.assertIsNotNone(store.last_success)

    def test_tracker_permission_required(self):
        tracker=SimpleNamespace(source="media_player.test",report=MagicMock())
        hass=SimpleNamespace(data={"media_activity_tracker":{"entry":tracker}})
        conn=MagicMock()
        conn.user.permissions.check_entity.side_effect=[True,False]
        with patch("custom_components.media_activity_tracker.er.async_get") as reg:
            reg.return_value.async_get_entity_id.return_value="sensor.test_status"
            websocket_report(hass,conn,{"id":1,"entry_id":"entry","days":1})
        conn.send_error.assert_called_once()
        tracker.report.assert_not_called()
