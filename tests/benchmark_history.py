"""Synthetic ten-year history regression and timings (not a Pi benchmark)."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo
spec=importlib.util.spec_from_file_location("engine",Path(__file__).parents[1]/"custom_components/media_activity_tracker/engine.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
now=datetime(2026,11,27,tzinfo=timezone.utc)
e=m.Engine(None,ZoneInfo("UTC"),now-timedelta(days=3650))
for i in range(3650):
    day=(now-timedelta(days=i)).date().isoformat()
    e.data["days"][day]={"apps":{f"id:{a}":1800 for a in range(10)},"sessions":10,"longest":1800}
start=perf_counter()
r=e.report(now,3660)
assert len(r["history"])==3660
assert r["periods"]["30"]["seconds"]==30*10*1800
print(f"Ten-year report: {perf_counter()-start:.3f}s")
