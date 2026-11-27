"""Independent playback accounting; timestamps are timezone-aware."""
from datetime import date, datetime, time, timedelta, timezone
import math

UTC = timezone.utc
HOME = {"home", "roku dynamic menu", "home screen", "screensaver"}
INACTIVE = {"off", "standby", "unknown", "unavailable", ""}
ACTIVE = {"playing", "paused", "buffering", "idle", "on"}


def app_identity(attributes):
    """Return stable key and label without recording media titles."""
    name = str(attributes.get("app_name") or attributes.get("source") or "Unknown app")[:255]
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
    if name.casefold() in excluded or key.casefold() in excluded:
        return False
    if mode == "power":
        return state in ACTIVE
    if name.casefold() in HOME:
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
        self.suspended_since = None
        self.active = False
        self.app = None
        self.session = None
        self.observed = None

    def day(self, day):
        return self.data["days"].setdefault(day, {"apps": {}, "sessions": 0, "longest": 0.0})

    def settle(self, now, elapsed=None):
        """Account for previous state up to now, splitting at local midnight."""
        end = now.astimezone(UTC)
        if end <= self.last:
            if end < self.last:
                self.finish()
                self.last = end
            return
        cursor = self.last
        self.last = end
        if elapsed is not None and abs((end-cursor).total_seconds()-elapsed) > 5:
            # A wall-clock correction or unobserved suspend is not confirmed activity.
            self.finish()
            return
        if (not self.active or self.session is None) and self.observed is None:
            return
        while cursor < end:
            local_day = cursor.astimezone(self.tz).date()
            day = local_day.isoformat()
            midnight = datetime.combine(local_day + timedelta(days=1), time.min, self.tz).astimezone(UTC)
            local = cursor.astimezone(self.tz)
            # Split by elapsed time to next local clock hour; repeated DST hours aggregate.
            hour_end = cursor + timedelta(seconds=3600-local.minute*60-local.second-local.microsecond/1_000_000)
            boundary = min(end, midnight, hour_end)
            if boundary <= cursor:
                boundary = min(end, cursor + timedelta(minutes=1))
            # A fractional-hour offset change can precede the next nominal hour.
            if (boundary-timedelta(microseconds=1)).astimezone(self.tz).utcoffset() != local.utcoffset():
                low, high = cursor, boundary
                while (high-low).total_seconds() > .000001:
                    mid = low + (high-low)/2
                    if mid.astimezone(self.tz).utcoffset() == local.utcoffset():
                        low = mid
                    else:
                        high = mid
                boundary = high
            seconds = (boundary - cursor).total_seconds()
            if self.observed is not None:
                coverage = self.data.setdefault("coverage", {}).setdefault(day, {"observed": 0.0, "unavailable": 0.0})
                category = "observed" if self.observed else "unavailable"
                coverage[category] += seconds
                hourly = coverage.setdefault("hours", {}).setdefault(str(local.hour), {"observed": 0.0, "unavailable": 0.0})
                hourly[category] += seconds
            if not self.active or self.session is None:
                cursor = boundary
                continue
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

    def transition(self, now, state, attributes, allowed, mode, excluded=(), elapsed=None, pause_timeout=30, observed=None):
        self.settle(now, elapsed)
        self.observed = observed
        key, name = app_identity(attributes)
        # Reuse an unambiguous known ID when the source temporarily omits it.
        if key.startswith("name:") and name != "Unknown app":
            matches = [k for k,v in self.data["apps"].items() if k.startswith("id:") and v.casefold() == name.casefold()]
            if len(matches) == 1:
                key = matches[0]
        # Promote only the continuous session; older same-name records could
        # refer to different applications and are deliberately retained.
        fallback = "name:" + name.casefold()
        if (key.startswith("id:") and name != "Unknown app" and self.app == fallback
                and self.session and not self.data.get("mixed_history")
                and not any(k.startswith("id:") and k != key and v.casefold() == name.casefold()
                            for k, v in self.data["apps"].items())):
            for day, seconds in self.session["days"].items():
                apps = self.data["days"][day]["apps"]
                remaining = apps[fallback] - seconds
                if remaining <= 0.000001:
                    apps.pop(fallback)
                else:
                    apps[fallback] = remaining
                apps[key] = apps.get(key, 0.0) + seconds
            self.session["app"] = key
            self.app = key
            if not any(fallback in bucket["apps"] for bucket in self.data["days"].values()):
                self.data["apps"].pop(fallback, None)
        if name == "Unknown app" and key in self.data["apps"]:
            name = self.data["apps"][key]
        active = allowed and key.casefold() not in excluded and name.casefold() not in excluded and qualifies(state, attributes, mode, excluded)
        # Pause/buffer retains the session for the same app; other interruptions end it.
        suspended = allowed and key.casefold() not in excluded and name.casefold() not in excluded and state in ("paused", "buffering") and key == self.app
        if suspended and not active:
            self.suspended_since = self.suspended_since or now
            suspended = (now-self.suspended_since).total_seconds() < pause_timeout*60
        else:
            self.suspended_since = None
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
        self.suspended_since = None

    def prune(self, now, retention_days=90):
        cutoff = now.astimezone(UTC) - timedelta(days=retention_days)
        self.data["sessions"] = [s for s in self.data["sessions"]
                                 if datetime.fromisoformat(s["end"]) >= cutoff][-10000:]

    def storage(self):
        # A checkpoint records only observed time. A restart opens a new session.
        return {**self.data, "sessions": self.data["sessions"] +
                ([self.session] if self.session and self.session["seconds"] > 0 else [])}

    def report(self, now, days=366, *, settle=True, include_sessions=True):
        if settle:
            self.settle(now)
        today = now.astimezone(self.tz).date()
        local_now = now.astimezone(self.tz)
        recorded_since = datetime.fromisoformat(self.data["started"]).astimezone(self.tz)
        recorded_day = recorded_since.date()
        monday = today - timedelta(days=today.weekday())
        month = today.replace(day=1)
        prev_month = (month - timedelta(days=1)).replace(day=1)
        coverage = self.data.get("coverage", {})
        coverage_since = self.data.get("coverage_since")
        changes = [datetime.fromisoformat(item["at"]) for item in self.data.get("mode_changes", [])]
        changes += [datetime.fromisoformat(item) for item in self.data.get("source_changes", [])]
        if self.data.get("comparison_reset"):
            changes.append(datetime.fromisoformat(self.data["comparison_reset"]))
        latest_change = max(changes, default=None)

        def mixed(start):
            if not self.data.get("mixed_history"):
                return False
            return latest_change is None or datetime.combine(start, time.min, self.tz) < latest_change

        def aggregate(start, end):
            apps = {}
            count = 0
            longest = 0.0
            for offset in range(max(0, (end-start).days+1)):
                key = (start+timedelta(days=offset)).isoformat()
                bucket = self.data["days"].get(key)
                if bucket:
                    count += bucket["sessions"]
                    longest = max(longest, bucket["longest"])
                    for app, seconds in bucket["apps"].items():
                        apps[app] = apps.get(app, 0.0) + seconds
            total = sum(apps.values())
            known_days = 0
            observed_seconds = 0.0
            observed_activity = 0.0
            for offset in range(max(0, (end-start).days+1)):
                key = (start+timedelta(days=offset)).isoformat()
                if coverage_since and key >= coverage_since:
                    observed = coverage.get(key, {}).get("observed", 0)
                    if observed > 0:
                        known_days += 1
                        observed_seconds += observed
                        observed_activity += sum(self.data["days"].get(key, {}).get("apps", {}).values())
            return {"seconds": total, "apps": apps, "sessions": count,
                    "longest": longest, "days": max(1, (end-start).days+1),
                    "observed_days": max(0, (end-max(start, recorded_day)).days+1),
                    "days_with_observation": known_days,
                    "observed_seconds": observed_seconds,
                    "observed_day_average": observed_activity / known_days if known_days else None,
                    "mixed_history": mixed(start)}
        def comparable(start, prior_start, prior_end):
            """Compare common completed local days and completed clock hours.

            Never assume pre-installation history is zero. Exclude the current
            partial hour on both sides; cap shorter calendar periods equally.
            """
            common = min((today-start).days+1, (prior_end-prior_start).days+1)
            if common <= 0 or mixed(prior_start) or recorded_since > datetime.combine(prior_start, time.min, self.tz):
                return {"comparison_seconds": None, "previous_seconds": None}
            current_last = start + timedelta(days=common-1)
            prior_last = prior_start + timedelta(days=common-1)
            # Require complete observed coverage, including the completed
            # clock hours on the last day of each period.
            def complete(start_day, last_day, partial):
                if not coverage_since:
                    return True
                for offset in range((last_day-start_day).days+1):
                    day = start_day+timedelta(days=offset)
                    key = day.isoformat()
                    if key < coverage_since:
                        return False
                    bucket = coverage.get(key, {})
                    midnight = datetime.combine(day, time.min, self.tz).astimezone(UTC)
                    end = datetime.combine(day+timedelta(days=1), time.min, self.tz).astimezone(UTC)
                    if partial and day == last_day:
                        end = datetime.combine(day, time(local_now.hour), self.tz).astimezone(UTC)
                        observed = sum(v["observed"] for h,v in bucket.get("hours", {}).items()
                                       if int(h) < local_now.hour)
                    else:
                        observed = bucket.get("observed", 0)
                    expected = (end-midnight).total_seconds()
                    if abs(observed-expected) > 5:
                        return False
                return True
            partial = current_last == today
            if not complete(start, current_last, partial) or not complete(prior_start, prior_last, partial):
                return {"comparison_seconds": None, "previous_seconds": None}
            if current_last < today:
                return {"comparison_seconds": aggregate(start, current_last)["seconds"],
                        "previous_seconds": aggregate(prior_start, prior_last)["seconds"]}
            def completed(start_day, last_day):
                full = aggregate(start_day, last_day-timedelta(days=1))["seconds"]
                bucket = self.data["days"].get(last_day.isoformat(), {})
                # Old or incomplete hour breakdown cannot support a partial-day comparison.
                if bucket.get("apps") and "hours" not in bucket:
                    return None
                return full + sum(v for h, v in bucket.get("hours", {}).items()
                                  if int(h) < local_now.hour)
            current = completed(start, current_last)
            previous = completed(prior_start, prior_last)
            if current is None or previous is None or (common == 1 and local_now.hour == 0):
                return {"comparison_seconds": None, "previous_seconds": None}
            return {"comparison_seconds": current, "previous_seconds": previous}
        periods = {}
        for label, start, prior_start, prior_end in (
            ("day", today, today-timedelta(days=1), today-timedelta(days=1)),
            ("week", monday, monday-timedelta(days=7), today-timedelta(days=7)),
            ("month", month, prev_month, min(month-timedelta(days=1), prev_month+timedelta(days=today.day-1))),
            ("year", today.replace(month=1, day=1), today.replace(year=today.year-1, month=1, day=1), min(today.replace(month=1, day=1)-timedelta(days=1), today.replace(year=today.year-1, month=1, day=1)+timedelta(days=(today-today.replace(month=1, day=1)).days))),
        ):
            periods[label] = aggregate(start, today)
            periods[label].update(comparable(start, prior_start, prior_end))
        for length in (7, 30, 90, 365):
            periods[str(length)] = aggregate(today-timedelta(days=length-1), today)
        start = today-timedelta(days=days-1)
        coverage = self.data.get("coverage", {})
        coverage_since = self.data.get("coverage_since")
        history = [{"date": d.isoformat(), **self.data["days"].get(d.isoformat(), {"apps": {}, "sessions": 0, "longest": 0}),
                    "coverage": coverage.get(d.isoformat(), {"observed": 0, "unavailable": 0}) if coverage_since and d.isoformat() >= coverage_since else None}
                   for d in (start+timedelta(days=i) for i in range(days))]
        return {"schema": 1, "started": self.data["started"], "recorded_since": recorded_day.isoformat(), "apps": self.data["apps"],
                "periods": periods, "history": history,
                "sessions": (self.data["sessions"][-499:] + [self.session] if self.session else self.data["sessions"][-500:]) if include_sessions else [],
                "mixed_history": self.data.get("mixed_history", False),
                "mode_changes": self.data.get("mode_changes", []),
                "coverage_since": coverage_since,
                "active": self.active, "session_seconds": self.session["seconds"] if self.session else 0}
