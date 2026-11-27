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
    for key, coverage in data.get("coverage", {}).items():
        date.fromisoformat(key)
        if not isinstance(coverage, dict) or not number(coverage["observed"]) or not number(coverage["unavailable"]):
            raise ValueError("Invalid coverage")
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
    for session in data["sessions"]:
        if not isinstance(session["app"], str) or not number(session["seconds"]):
            raise ValueError("Invalid session")
        if timestamp(session["end"]) < timestamp(session["start"]):
            raise ValueError("Invalid session timestamps")
        if not all(number(v) for v in session.get("days", {}).values()):
            raise ValueError("Invalid session days")
    return data


