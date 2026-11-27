"""Pure history validation and schema migration; safe for offline tools."""
from datetime import date, datetime
import math

def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Naive timestamp")
    return result


def validate(data):
    """Reject malformed history rather than replacing it with empty history."""
    if not isinstance(data, dict):
        raise ValueError("Invalid history root")
    timestamp(data["started"])
    if data.get("history_schema", 1) not in (1, 2):
        raise ValueError("Unsupported history schema")
    if "coverage_since" in data:
        date.fromisoformat(data["coverage_since"])
    for field in ("mode_changes", "source_changes"):
        if not isinstance(data.get(field, []), list):
            raise ValueError("Invalid change history")
    for item in data.get("mode_changes", []):
        timestamp(item["at"])
        if item["mode"] not in ("playing", "app", "power"):
            raise ValueError("Invalid historical mode")
    for item in data.get("source_changes", []):
        timestamp(item)
    if "comparison_reset" in data:
        timestamp(data["comparison_reset"])
    for key, coverage in data.get("coverage", {}).items():
        date.fromisoformat(key)
        if not isinstance(coverage, dict) or not number(coverage["observed"]) or not number(coverage["unavailable"]):
            raise ValueError("Invalid coverage")
        hours = coverage.get("hours", {})
        for hour, values in hours.items():
            if hour not in {str(h) for h in range(24)} or not all(number(values[k]) for k in ("observed", "unavailable")):
                raise ValueError("Invalid hourly coverage")
        for field in ("observed", "unavailable"):
            if sum(values[field] for values in hours.values()) > coverage[field] + 0.01:
                raise ValueError("Hourly coverage exceeds daily coverage")
    if not isinstance(data["apps"], dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in data["apps"].items()):
        raise ValueError("Invalid application names")
    if not isinstance(data["days"], dict) or not isinstance(data["sessions"], list):
        raise ValueError("Invalid history collections")
    for key, day in data["days"].items():
        date.fromisoformat(key)
        if not isinstance(day, dict) or not isinstance(day["apps"], dict):
            raise ValueError("Invalid daily bucket")
        if not all(isinstance(k, str) and number(v) for k,v in day["apps"].items()):
            raise ValueError("Invalid app duration")
        if not number(day["sessions"]) or not number(day["longest"]):
            raise ValueError("Invalid session totals")
        if not all(k in {str(h) for h in range(24)} and number(v) for k,v in day.get("hours", {}).items()):
            raise ValueError("Invalid hourly duration")
        total = sum(day["apps"].values())
        if day["longest"] > total + 0.01 or sum(day.get("hours", {}).values()) > total + 0.01:
            raise ValueError("Daily durations are inconsistent")
    for session in data["sessions"]:
        if not isinstance(session["app"], str) or not number(session["seconds"]):
            raise ValueError("Invalid session")
        if timestamp(session["end"]) < timestamp(session["start"]):
            raise ValueError("Invalid session timestamps")
        for day, seconds in session.get("days", {}).items():
            date.fromisoformat(day)
            if not number(seconds):
                raise ValueError("Invalid session days")
        if session.get("days") and abs(sum(session["days"].values()) - session["seconds"]) > 0.01:
            raise ValueError("Session totals are inconsistent")
    return data


