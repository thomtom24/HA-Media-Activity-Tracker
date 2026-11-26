"""Minimal diagnostics; omit entity identifiers and viewing history."""
async def async_get_config_entry_diagnostics(hass, entry):
    tracker = entry.runtime_data
    return {"mode": tracker.config.get("mode"), "logic": tracker.config.get("logic"),
            "condition_count": len(tracker.config.get("conditions", [])),
            "source_state": tracker.source_state, "tracking_reason": tracker.reason,
            "recorded_days": len(tracker.engine.data["days"])}
