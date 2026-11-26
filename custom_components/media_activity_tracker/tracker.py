"""HA event adapter and persistence."""
from datetime import timedelta
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from .const import DOMAIN
from .config_flow import resolve
from .engine import Engine, condition_matches, app_identity


class Tracker:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.config = {**entry.data, **entry.options}
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.unsubs = []
        self.reason = "initializing"
        self.source_state = "unknown"
        self.current_app = "Unknown app"

    @property
    def source(self):
        return resolve(self.hass, self.config["source"])

    async def start(self):
        self.engine = Engine(await self.store.async_load(), dt_util.get_time_zone(self.hass.config.time_zone), dt_util.utcnow())
        self.watch()
        self.unsubs.append(async_track_time_interval(self.hass, self.tick, timedelta(seconds=30)))
        self.unsubs.append(self.hass.bus.async_listen("entity_registry_updated", self.registry_changed))
        self.refresh()

    @callback
    def watch(self):
        if getattr(self, "state_unsub", None):
            self.state_unsub()
        entities = {self.source, *(resolve(self.hass, c["entity"]) for c in self.config.get("conditions", []))}
        self.state_unsub = async_track_state_change_event(self.hass, entities, self.changed)

    @callback
    def registry_changed(self, event):
        if event.data.get("action") in ("update", "remove", "create"):
            self.watch()
            self.refresh()

    @callback
    def changed(self, event):
        self.refresh()

    @callback
    def refresh(self):
        now = dt_util.utcnow()
        source = self.hass.states.get(self.source)
        self.source_state = source.state if source else "unknown"
        attributes = source.attributes if source else {}
        self.current_app = app_identity(attributes)[1]
        results = []
        for condition in self.config.get("conditions", []):
            entity = self.hass.states.get(resolve(self.hass, condition["entity"]))
            results.append(condition_matches(entity.state if entity else None, condition["operator"], condition["value"]))
        allowed = not results or (all(results) if self.config.get("logic") != "or" else any(results))
        excluded = {s.strip().casefold() for s in self.config.get("excluded", "").split(",") if s.strip()}
        self.engine.transition(now, self.source_state, attributes, allowed, self.config.get("mode", "playing"), excluded)
        self.reason = "tracking" if self.engine.active else "condition_not_met" if not allowed else "source_not_active"
        self.notify()

    @callback
    def tick(self, now):
        self.refresh()
        self.engine.prune(now)

    @callback
    def notify(self):
        self.store.async_delay_save(self.engine.storage, 5)
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def report(self, days=366):
        return {**self.engine.report(dt_util.utcnow(), days), "name": self.entry.title,
                "source": self.source, "state": self.source_state, "app": self.current_app,
                "reason": self.reason, "mode": self.config.get("mode", "playing")}

    async def stop(self):
        self.state_unsub()
        for unsub in self.unsubs:
            unsub()
        self.engine.settle(dt_util.utcnow())
        self.engine.finish()
        await self.store.async_save(self.engine.storage())
