"""Validate persisted analytics and detect failed atomic writes."""
from datetime import date, datetime
import math

from homeassistant.helpers.storage import Store
from .history_schema import validate


class HistoryStore(Store):
    """Report write outcome even though HA Store logs and swallows write errors."""

    def __init__(self, hass, key):
        super().__init__(hass, 1, key, private=True, atomic_writes=True, serialize_in_event_loop=False)
        self.write_failed = False
        self.last_success = None

    async def _async_write_data(self, data):
        from homeassistant.util import dt as dt_util
        try:
            await super()._async_write_data(data)
        except Exception:
            self.write_failed = True
            raise
        else:
            self.write_failed = False
            self.last_success = dt_util.utcnow().isoformat()
