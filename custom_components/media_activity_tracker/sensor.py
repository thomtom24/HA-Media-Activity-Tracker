"""Compact, automation-friendly sensors."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import callback
from .const import DOMAIN

SENSORS = {
    "today": ("Playing time today", "day", "seconds"),
    "week": ("Playing time this week", "week", "seconds"),
    "month": ("Playing time this month", "month", "seconds"),
    "year": ("Playing time this year", "year", "seconds"),
    "average_7": ("Daily average 7 days", "7", "average"),
    "average_30": ("Daily average 30 days", "30", "average"),
    "average_90": ("Daily average 90 days", "90", "average"),
    "top_today": ("Most used app today", "day", "top"),
    "top_week": ("Most used app this week", "week", "top"),
    "top_month": ("Most used app this month", "month", "top"),
    "sessions": ("Sessions today", "day", "sessions"),
    "longest": ("Longest session today", "day", "longest"),
    "session": ("Current session duration", None, "session"),
    "current_app": ("Current app", None, "app"),
    "status": ("Tracking status", None, "reason"),
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ActivitySensor(entry.runtime_data, key, spec) for key, spec in SENSORS.items()])


class ActivitySensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, tracker, key, spec):
        self.tracker = tracker
        self.key, (self._attr_name, self.period, self.metric) = key, spec
        self._attr_unique_id = f"{tracker.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, tracker.entry.entry_id)}, name=tracker.entry.title)
        if self.metric in ("seconds", "average", "longest", "session"):
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:television-play"

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, self.tracker.signal, self.updated))
        self.updated()

    @callback
    def updated(self):
        report = self.tracker.report(1)
        p = report["periods"].get(self.period, {})
        if self.metric == "average":
            value = p["seconds"] / p["days"] / 60
        elif self.metric == "top":
            top = max(p["apps"], key=p["apps"].get, default=None)
            value = report["apps"].get(top, "None")
        elif self.metric == "session":
            value = report["session_seconds"] / 60
        elif self.metric in ("seconds", "longest"):
            value = p[self.metric] / 60
        elif self.period:
            value = p[self.metric]
        else:
            value = report[self.metric]
        self._attr_native_value = round(value, 2) if isinstance(value, float) else value
        if self.key == "status":
            self._attr_extra_state_attributes = {"tracker_entry_id": self.tracker.entry.entry_id,
                "source_entity": report["source"], "source_state": report["state"], "tracking_mode": report["mode"]}
        self.async_write_ha_state()
