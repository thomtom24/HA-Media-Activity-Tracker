"""Home Assistant event adapter and persistence."""
from copy import deepcopy
from datetime import timedelta
import logging
import time

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .config_flow import resolve
from .config_values import app_list, aliases as application_aliases
from .engine import Engine, HOME, condition_matches, app_identity
from .history import HistoryStore, validate

_LOGGER = logging.getLogger(__name__)


class Tracker:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.config = {**entry.data, **entry.options}
        self.store = HistoryStore(hass, f"{DOMAIN}.{entry.entry_id}")
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.unsubs = []
        self.state_unsub = None
        self.reason = "initializing"
        self.source_state = "unknown"
        self.current_app = "Unknown app"
        self.condition_results = []
        self.snapshot = None
        self.report_cache = {}
        self.observed_states = {}
        self.last_checkpoint = 0.0
        self.dirty = True
        self.stopped = False
        self.last_mono = time.monotonic()
        self.source = resolve(hass, self.config["source"])
        self.condition_entities = []
        self._conditions()

    def _conditions(self):
        registry = er.async_get(self.hass)
        self.condition_entities = [
            (resolve(self.hass, c["entity"]), c) for c in self.config.get("conditions", [])
        ]
        self.invalid_condition = any(
            (item := registry.async_get(entity_id)) is not None and item.platform == DOMAIN
            for entity_id, _ in self.condition_entities
        )

    async def start(self):
        from pathlib import Path
        # HA may rename corrupt JSON and return None; do not create replacement history.
        path = Path(self.store.path)
        existed = await self.hass.async_add_executor_job(lambda: path.exists() or any(path.parent.glob(path.name + ".corrupt.*")))
        try:
            data = await self.store.async_load()
            if data is None and existed:
                raise ValueError("Existing history unreadable")
            if data is not None:
                validate(data)
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as err:
            raise ConfigEntryError("Media Activity history is unreadable; restore a backup before retrying") from err
        now = dt_util.utcnow()
        self.engine = Engine(data, dt_util.get_time_zone(self.hass.config.time_zone), now)
        self.engine.data.setdefault("history_schema", 2)
        self.engine.data.setdefault("coverage_since", now.astimezone(self.engine.tz).date().isoformat())
        mode = self.config.get("mode", "playing")
        previous = self.engine.data.get("last_mode")
        if previous is not None and previous != mode:
            self.engine.data["mixed_history"] = True
            self.engine.data.setdefault("mode_changes", []).append({"at": now.isoformat(), "mode": mode})
        self.engine.data["last_mode"] = mode
        previous_source = self.engine.data.get("last_source")
        if previous_source is not None and previous_source != self.config["source"]:
            self.engine.data["mixed_history"] = True
            self.engine.data.setdefault("source_changes", []).append(now.isoformat())
        self.engine.data["last_source"] = self.config["source"]
        self.last_mono = time.monotonic()
        self.engine.prune(now, self.config.get("retention_days", 90))
        self.watch()
        self.unsubs.append(async_track_time_interval(self.hass, self.tick, timedelta(seconds=30)))
        self.unsubs.append(self.hass.bus.async_listen("entity_registry_updated", self.registry_changed))
        self.unsubs.append(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.shutdown))
        self.refresh()
        self.checkpoint()

    @callback
    def watch(self):
        if self.state_unsub:
            self.state_unsub()
        entities = {self.source}
        if not self.invalid_condition:
            entities.update(entity for entity, _ in self.condition_entities)
        self.observed_states = {entity: self.hass.states.get(entity) for entity in entities}
        self.state_unsub = async_track_state_change_event(self.hass, entities, self.changed)

    @callback
    def registry_changed(self, event):
        old = {self.source, *(e for e, _ in self.condition_entities)}
        if not old.intersection({event.data.get("entity_id"), event.data.get("old_entity_id")}) and not (event.data.get("action") == "create" and any("media_activity_missing_" in e for e in old)):
            return
        self.source = resolve(self.hass, self.config["source"])
        self._conditions()
        self.watch()
        self.refresh()

    @callback
    def changed(self, event):
        self.refresh(event)

    @callback
    def refresh(self, event=None):
        if self.stopped:
            return
        now = dt_util.utcnow()
        if event and self.engine.last <= event.time_fired <= now and (now-event.time_fired).total_seconds() < 5:
            now = event.time_fired
        mono = time.monotonic()
        elapsed = max(0, mono-self.last_mono)
        self.last_mono = mono
        previous_active = self.engine.active
        previous_app = self.engine.app
        if event:
            self.observed_states[event.data["entity_id"]] = event.data.get("new_state")
        else:
            self.observed_states = {entity: self.hass.states.get(entity) for entity in self.observed_states}
        def state_for(entity_id):
            return self.observed_states.get(entity_id)
        source = state_for(self.source)
        self.source_state = source.state if source else "unknown"
        attributes = source.attributes if source else {}
        self.current_app = app_identity(attributes)[1]
        self.condition_results = []
        for entity_id, condition in self.condition_entities:
            entity = state_for(entity_id)
            state = entity.state if entity else None
            matched = condition_matches(state, condition["operator"], condition["value"])
            self.condition_results.append({"operator": condition["operator"], "matched": matched,
                                           "available": state not in (None, "unknown", "unavailable")})
        results = [c["matched"] for c in self.condition_results]
        allowed = not self.invalid_condition and (not results or (all(results) if self.config.get("logic") != "or" else any(results)))
        excluded = {s.casefold() for s in app_list(self.config.get("excluded", []))}
        mode = self.config.get("mode", "playing")
        if elapsed > 120:
            # Do not infer playback across a long unobserved gap.
            elapsed = 0
        observed = self.source_state not in ("unknown", "unavailable") and not self.invalid_condition and all(c["available"] for c in self.condition_results)
        self.engine.transition(now, self.source_state, attributes, allowed, mode, excluded,
                               elapsed=elapsed, pause_timeout=self.config.get("pause_timeout", 30), observed=observed)
        self.dirty |= previous_active or self.engine.active or previous_app != self.engine.app
        if self.invalid_condition:
            self.reason = "circular_condition"
        elif self.engine.active:
            self.reason = "tracking"
        elif not allowed:
            self.reason = "condition_not_met"
        elif self.source_state in ("unknown", "unavailable"):
            self.reason = "source_unavailable"
        elif self.source_state in ("off", "standby"):
            self.reason = "source_off"
        elif self.source_state in ("paused", "buffering") and mode == "playing":
            self.reason = self.source_state
        elif app_identity(attributes)[1].casefold() in excluded or app_identity(attributes)[0].casefold() in excluded or (
            mode != "power" and app_identity(attributes)[1].casefold() in HOME
        ):
            self.reason = "app_excluded"
        else:
            self.reason = "source_not_active"
        self.report_cache.clear()
        self.snapshot = self.report(1, include_sessions=False)
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def tick(self, now):
        self.refresh()
        old = len(self.engine.data["sessions"])
        self.engine.prune(now, self.config.get("retention_days", 90))
        self.dirty |= old != len(self.engine.data["sessions"])
        if self.dirty or self.store.write_failed or time.monotonic()-self.last_checkpoint >= 300:
            self.checkpoint()

    @callback
    def checkpoint(self):
        # Snapshot on the event loop; serialise the independent copy in a worker.
        self.store.async_delay_save(lambda snapshot=deepcopy(self.engine.storage()): snapshot, 1)
        self.dirty = False
        self.last_checkpoint = time.monotonic()

    @callback
    def report(self, days=366, *, include_sessions=True):
        if include_sessions and days in self.report_cache:
            return self.report_cache[days]
        aliases = application_aliases(self.config.get("aliases", []))
        result = self.engine.report(dt_util.utcnow(), days, settle=False, include_sessions=include_sessions)
        if not include_sessions:
            result["raw_apps"] = dict(result["apps"])
        result["apps"] = {key: aliases.get(key.casefold(), aliases.get(name.casefold(), name))
                          for key, name in result["apps"].items()}
        source = self.observed_states.get(self.source)
        key, name = app_identity(source.attributes if source else {})
        app = aliases.get(key.casefold(), aliases.get(name.casefold(), name))
        result = {**result, "name": self.entry.title, "source": self.source,
                "state": self.source_state, "app": app, "reason": self.reason,
                "mode": self.config.get("mode", "playing"),
                "condition_results": self.condition_results,
                "retention_days": self.config.get("retention_days", 90),
                "storage_error": self.store.write_failed, "last_saved": self.store.last_success,
                "timezone": self.hass.config.time_zone}
        if include_sessions:
            if len(self.report_cache) >= 3:
                self.report_cache.clear()
            self.report_cache[days] = result
        return result

    async def shutdown(self, _event):
        if not self.stopped:
            self.refresh()
            await self.store.async_save(deepcopy(self.engine.storage()))

    async def stop(self):
        if self.stopped:
            return
        self.refresh()
        self.stopped = True
        self.close_subscriptions()
        self.engine.finish()
        await self.store.async_save(deepcopy(self.engine.storage()))

    @callback
    def close_subscriptions(self):
        if self.state_unsub:
            self.state_unsub()
            self.state_unsub = None
        for unsub in self.unsubs:
            unsub()
        self.unsubs.clear()
