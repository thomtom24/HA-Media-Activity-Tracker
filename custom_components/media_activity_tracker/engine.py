"""Independent playback accounting; timestamps are timezone-aware."""
from datetime import date, datetime, time, timedelta, timezone
import math

UTC = timezone.utc
HOME = {"home", "roku dynamic menu", "home screen", "screensaver"}
INACTIVE = {"off", "standby", "unknown", "unavailable", ""}
ACTIVE = {"playing", "paused", "buffering", "idle", "on"}


def app_identity(attributes):
    """Return stable key and label without recording media titles."""
    name = str(attributes.get("app_name") or attributes.get("source") or "Unknown app")
    app_id = attributes.get("app_id")
    return ("id:" + str(app_id) if app_id not in (None, "") else "name:" + name.casefold(), name)


def condition_matches(state, operator, expected):
    """Unknown values never satisfy any comparison, including inequality."""
    if state is None or state in ("unknown", "unavailable"):
        return False
    if operator == "equals":
        return state == expected
    if operator == "not_equals":
        return state != expected
    try:
        a, b = float(state), float(expected)
        return math.isfinite(a) and math.isfinite(b) and (
            (operator == "above" and a > b) or (operator == "below" and a < b)
        )
    except (ValueError, TypeError):
        return False


def qualifies(state, attributes, mode, excluded=()):
    """Evaluate the source, independently of additional conditions."""
    key, name = app_identity(attributes)
    if state in INACTIVE:
        return False
    if mode == "power":
        return state in ACTIVE
    if name.casefold() in HOME or name.casefold() in excluded or key.casefold() in excluded:
        return False
    if mode == "playing":
        return state == "playing"
    return mode == "app" and state in ACTIVE and name != "Unknown app"


class Engine:
    """Accumulate observed seconds into daily buckets and bounded sessions."""

    def __init__(self, data, tz, now):
        self.tz = tz
        self.data = data or {"days": {}, "apps": {}, "sessions": [], "started": now.isoformat()}
        self.last = now.astimezone(UTC)
        self.active = False
        self.app = None
        self.session = None

    def day(self, day):
        return self.data["days"].setdefault(day, {"apps": {}, "sessions": 0, "longest": 0.0})

    def settle(self, now):
        """Account for previous state up to now, splitting at local midnight."""
        end = now.astimezone(UTC)
        if end <= self.last:
            return
        cursor = self.last
        self.last = end
        if not self.active or self.session is None:
            return
        while cursor < end:
            local_day = cursor.astimezone(self.tz).date()
            day = local_day.isoformat()
            midnight = datetime.combine(local_day + timedelta(days=1), time.min, self.tz).astimezone(UTC)
            local = cursor.astimezone(self.tz)
            # Split by elapsed time to next local clock hour; repeated DST hours aggregate.
            hour_end = cursor + timedelta(seconds=3600-local.minute*60-local.second-local.microsecond/1_000_000)
            boundary = min(end, midnight, hour_end)
            seconds = (boundary - cursor).total_seconds()
            bucket = self.day(day)
            bucket["apps"][self.app] = bucket["apps"].get(self.app, 0.0) + seconds
            hours = bucket.setdefault("hours", {})
            hour = str(local.hour)
            hours[hour] = hours.get(hour, 0.0) + seconds
            parts = self.session["days"]
            if day not in parts:
                bucket["sessions"] += 1
                parts[day] = 0.0
            parts[day] += seconds
            bucket["longest"] = max(bucket["longest"], parts[day])
            self.session["seconds"] += seconds
            self.session["end"] = boundary.isoformat()
            cursor = boundary

    def transition(self, now, state, attributes, allowed, mode, excluded=()):
        self.settle(now)
        key, name = app_identity(attributes)
        active = allowed and qualifies(state, attributes, mode, excluded)
        # Pause/buffer retains the session for the same app; other interruptions end it.
        suspended = allowed and state in ("paused", "buffering") and key == self.app
        if self.session and (key != self.app or (not active and not suspended)):
            self.finish()
        if active:
            self.data["apps"][key] = name
            if self.session is None:
                self.session = {"app": key, "start": now.isoformat(), "end": now.isoformat(),
                                "seconds": 0.0, "days": {}}
            self.app = key
        self.active = active

    def finish(self):
        if self.session and self.session["seconds"] > 0:
            self.data["sessions"].append(self.session)
        self.session = None
        self.app = None
        self.active = False

    def prune(self, now):
        cutoff = now.astimezone(UTC) - timedelta(days=90)
        self.data["sessions"] = [s for s in self.data["sessions"]
                                 if datetime.fromisoformat(s["end"]) >= cutoff]

    def storage(self):
        # A checkpoint records only observed time. A restart opens a new session.
        return {**self.data, "sessions": self.data["sessions"] +
                ([self.session] if self.session and self.session["seconds"] > 0 else [])}

    def report(self, now, days=366):
        self.settle(now)
        today = now.astimezone(self.tz).date()
        monday = today - timedelta(days=today.weekday())
        month = today.replace(day=1)
        prev_month = (month - timedelta(days=1)).replace(day=1)
        def aggregate(start, end):
            apps = {}
            count = 0
            longest = 0.0
            for key, bucket in self.data["days"].items():
                if start.isoformat() <= key <= end.isoformat():
                    count += bucket["sessions"]
                    longest = max(longest, bucket["longest"])
                    for app, seconds in bucket["apps"].items():
                        apps[app] = apps.get(app, 0.0) + seconds
            total = sum(apps.values())
            return {"seconds": total, "apps": apps, "sessions": count,
                    "longest": longest, "days": max(1, (end-start).days+1)}
        periods = {}
        for label, start, prior_start, prior_end in (
            ("day", today, today-timedelta(days=1), today-timedelta(days=1)),
            ("week", monday, monday-timedelta(days=7), today-timedelta(days=7)),
            ("month", month, prev_month, min(month-timedelta(days=1), prev_month+timedelta(days=today.day-1))),
            ("year", today.replace(month=1, day=1), today.replace(year=today.year-1, month=1, day=1), min(today.replace(month=1, day=1)-timedelta(days=1), today.replace(year=today.year-1, month=1, day=1)+timedelta(days=(today-today.replace(month=1, day=1)).days))),
        ):
            periods[label] = aggregate(start, today)
            periods[label]["previous_seconds"] = aggregate(prior_start, prior_end)["seconds"]
        for length in (7, 30, 90, 365):
            periods[str(length)] = aggregate(today-timedelta(days=length-1), today)
        start = today-timedelta(days=days-1)
        history = [{"date": d.isoformat(), **self.data["days"].get(d.isoformat(), {"apps": {}, "sessions": 0, "longest": 0})}
                   for d in (start+timedelta(days=i) for i in range(days))]
        return {"schema": 1, "started": self.data["started"], "apps": self.data["apps"],
                "periods": periods, "history": history,
                "sessions": (self.data["sessions"] + ([self.session] if self.session else []))[-500:],
                "active": self.active, "session_seconds": self.session["seconds"] if self.session else 0}
