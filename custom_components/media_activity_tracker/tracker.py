"""HA event adapter and persistence."""
from datetime import timedelta
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from .const import DOMAIN
from .config_flow import resolve
from .engine import Engine, HOME, condition_matches, app_identity


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
        self.condition_results = []

    @property
    def source(self):
        return resolve(self.hass, self.config["source"])

    async def start(self):
        self.engine = Engine(await self.store.async_load(), dt_util.get_time_zone(self.hass.config.time_zone), dt_util.utcnow())
        self.engine.prune(dt_util.utcnow(), self.config.get("retention_days", 90))
        self.watch()
        self.unsubs.append(async_track_time_interval(self.hass, self.tick, timedelta(seconds=30)))
        self.unsubs.append(self.hass.bus.async_listen("entity_registry_updated", self.registry_changed))
        self.refresh()
        self.store.async_delay_save(self.engine.storage, 1)

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
        self.condition_results = []
        for condition in self.config.get("conditions", []):
            entity = self.hass.states.get(resolve(self.hass, condition["entity"]))
            state = entity.state if entity else None
            matched = condition_matches(state, condition["operator"], condition["value"])
            results.append(matched)
            self.condition_results.append({"operator": condition["operator"], "matched": matched,
                                           "available": state not in (None, "unknown", "unavailable")})
        allowed = not results or (all(results) if self.config.get("logic") != "or" else any(results))
        excluded = {s.strip().casefold() for s in self.config.get("excluded", "").split(",") if s.strip()}
        self.engine.transition(now, self.source_state, attributes, allowed, self.config.get("mode", "playing"), excluded)
        aliases = {}
        for item in self.config.get("aliases", "").split(","):
            key, sep, label = item.partition("=")
            if sep and key.strip() and label.strip():
                aliases[key.strip().casefold()] = label.strip()
        for key, name in list(self.engine.data["apps"].items()):
            self.engine.data["apps"][key] = aliases.get(key.casefold(), aliases.get(name.casefold(), name))
        self.current_app = aliases.get(app_identity(attributes)[0].casefold(), aliases.get(self.current_app.casefold(), self.current_app))
        if self.engine.active:
            self.reason = "tracking"
        elif not allowed:
            self.reason = "condition_not_met"
        elif self.source_state in ("unknown", "unavailable"):
            self.reason = "source_unavailable"
        elif self.source_state in ("off", "standby"):
            self.reason = "source_off"
        elif self.source_state in ("paused", "buffering") and self.config.get("mode", "playing") == "playing":
            self.reason = self.source_state
        elif self.config.get("mode", "playing") != "power" and (
            app_identity(attributes)[1].casefold() in HOME | excluded
            or app_identity(attributes)[0].casefold() in excluded
        ):
            self.reason = "app_excluded"
        else:
            self.reason = "source_not_active"
        self.notify()

    @callback
    def tick(self, now):
        self.refresh()
        self.engine.prune(now, self.config.get("retention_days", 90))
        self.store.async_delay_save(self.engine.storage, 1)

    @callback
    def notify(self):
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def report(self, days=366):
        return {**self.engine.report(dt_util.utcnow(), days), "name": self.entry.title,
                "source": self.source, "state": self.source_state, "app": self.current_app,
                "reason": self.reason, "mode": self.config.get("mode", "playing"),
                "condition_results": self.condition_results, "retention_days": self.config.get("retention_days", 90)}

    async def stop(self):
        self.state_unsub()
        for unsub in self.unsubs:
            unsub()
        self.engine.settle(dt_util.utcnow())
        self.engine.finish()
        await self.store.async_save(self.engine.storage())
