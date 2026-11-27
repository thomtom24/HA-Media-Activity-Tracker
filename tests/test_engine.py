"""Pure accounting regression tests."""
import importlib.util
import pathlib
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
spec = importlib.util.spec_from_file_location("engine", pathlib.Path(__file__).parents[1]/"custom_components/media_activity_tracker/engine.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class TestEngine(unittest.TestCase):
    def setUp(self):
        self.t = datetime(2026, 11, 26, 23, 50, tzinfo=timezone.utc)
        self.e = m.Engine(None, ZoneInfo("Europe/London"), self.t)
        self.a = {"app_id": "11703", "app_name": "BBC iPlayer"}
    def change(self, minutes, state, attrs=None, allowed=True):
        self.e.transition(self.t+timedelta(minutes=minutes), state, attrs or self.a, allowed, "playing")
    def test_roku_and_midnight(self):
        self.change(0,"on",{"app_name":"Roku Dynamic Menu"})
        self.change(1,"playing")
        self.change(6,"paused")
        self.change(9,"playing")
        self.change(14,"playing",{"app_id":"12","app_name":"Netflix"})
        self.change(19,"unavailable")
        p=self.e.report(self.t+timedelta(minutes=20))
        self.assertEqual(p["periods"]["month"]["seconds"],900)
        self.assertEqual(p["periods"]["day"]["seconds"],540)
        self.assertEqual(p["periods"]["month"]["apps"]["id:12"],300)
    def test_gate(self):
        self.change(0,"playing")
        self.change(2,"playing",allowed=False)
        self.change(4,"playing")
        self.change(5,"off")
        self.assertEqual(self.e.report(self.t+timedelta(minutes=5))["periods"]["day"]["seconds"],180)
    def test_conditions(self):
        self.assertFalse(m.condition_matches("unavailable","not_equals","off"))
        self.assertTrue(m.condition_matches("home","equals","home"))
        self.assertTrue(m.condition_matches("25","above","20"))
        self.assertFalse(m.condition_matches("nan","above","20"))
    def test_restart(self):
        self.change(0,"playing")
        self.e.settle(self.t+timedelta(minutes=1))
        e=m.Engine(self.e.storage(),ZoneInfo("Europe/London"),self.t+timedelta(hours=2))
        self.assertEqual(e.report(self.t+timedelta(hours=2))["periods"]["month"]["seconds"],60)
    def test_dst(self):
        tz=ZoneInfo("Europe/London")
        start=datetime(2026,10,25,0,0,tzinfo=tz)
        end=datetime(2026,10,26,0,0,tzinfo=tz)
        e=m.Engine(None,tz,start)
        e.transition(start,"playing",self.a,True,"playing")
        e.settle(end)
        self.assertEqual(e.data["days"]["2026-10-25"]["apps"]["id:11703"],25*3600)

    def test_observed_days_include_zero_days_since_install(self):
        self.change(0, "playing")
        self.change(5, "off")
        report = self.e.report(self.t+timedelta(days=2))
        self.assertEqual(report["periods"]["30"]["observed_days"], 3)
        self.assertEqual(report["periods"]["30"]["days"], 30)
        self.assertEqual(report["periods"]["30"]["seconds"], 300)
        self.assertIsNone(report["periods"]["week"]["previous_seconds"])

    def test_like_for_like_completed_hours(self):
        start = datetime(2026, 11, 24, 0, tzinfo=timezone.utc)
        e = m.Engine(None, ZoneInfo("Europe/London"), start)
        yesterday = start + timedelta(days=1)
        today = start + timedelta(days=2)
        e.transition(yesterday+timedelta(hours=8), "playing", self.a, True, "playing")
        e.transition(yesterday+timedelta(hours=9), "off", self.a, True, "playing")
        e.transition(yesterday+timedelta(hours=20), "playing", self.a, True, "playing")
        e.transition(yesterday+timedelta(hours=22), "off", self.a, True, "playing")
        e.transition(today+timedelta(hours=8), "playing", self.a, True, "playing")
        e.transition(today+timedelta(hours=8,minutes=30), "off", self.a, True, "playing")
        e.transition(today+timedelta(hours=10), "playing", self.a, True, "playing")
        p = e.report(today+timedelta(hours=10,minutes=30))["periods"]["day"]
        self.assertEqual(p["seconds"], 3600)
        self.assertEqual(p["comparison_seconds"], 1800)
        self.assertEqual(p["previous_seconds"], 3600)

    def test_session_retention_does_not_delete_daily_totals(self):
        self.change(0, "playing")
        self.change(5, "off")
        self.e.prune(self.t+timedelta(days=3), 2)
        self.assertEqual(self.e.data["sessions"], [])
        self.assertEqual(self.e.data["days"]["2026-11-26"]["apps"]["id:11703"], 300)

    def test_clock_jump_does_not_invent_activity(self):
        self.change(0,"playing")
        self.e.transition(self.t+timedelta(hours=3),"playing",self.a,True,"playing",elapsed=1)
        self.assertEqual(self.e.report(self.t+timedelta(hours=3))["periods"]["month"]["seconds"],0)

    def test_power_exclusion(self):
        self.assertFalse(m.qualifies("on",self.a,"power",{"id:11703"}))

    def test_paused_timeout(self):
        self.change(0,"playing")
        self.change(5,"paused")
        self.change(40,"paused")
        self.assertIsNone(self.e.session)

    def test_id_fallback(self):
        self.change(0,"playing")
        self.change(1,"playing",{"app_name":"BBC iPlayer"})
        self.change(2,"off")
        self.assertEqual(self.e.data["days"]["2026-11-26"]["apps"],{"id:11703":120})

    def test_observation_coverage(self):
        self.e.transition(self.t,"off",self.a,True,"playing",observed=True)
        self.e.transition(self.t+timedelta(minutes=5),"unavailable",self.a,True,"playing",observed=False)
        self.e.transition(self.t+timedelta(minutes=7),"off",self.a,True,"playing",observed=True)
        self.assertEqual(self.e.data["coverage"]["2026-11-26"],{"observed":300,"unavailable":120})

    def test_lord_howe_fractional_dst(self):
        tz=ZoneInfo("Australia/Lord_Howe")
        start=datetime(2026,10,4,0,0,tzinfo=tz)
        end=datetime(2026,10,5,0,0,tzinfo=tz)
        e=m.Engine(None,tz,start)
        e.transition(start,"playing",self.a,True,"playing")
        e.settle(end)
        self.assertAlmostEqual(e.data["days"]["2026-10-04"]["apps"]["id:11703"],23.5*3600,places=3)

    def test_id_exclusion_when_id_disappears(self):
        self.change(0,"playing")
        self.e.transition(self.t+timedelta(minutes=1),"playing",{"app_name":"BBC iPlayer"},True,"playing",{"id:11703"})
        self.assertFalse(self.e.active)

    def test_promote_continuous_name_only_session(self):
        self.change(0, "playing", {"app_name": "BBC iPlayer"})
        self.change(2, "playing", self.a)
        self.change(4, "off")
        p = self.e.report(self.t+timedelta(minutes=4))
        self.assertEqual(p["periods"]["day"]["apps"], {"id:11703": 240})
        self.assertEqual(p["periods"]["day"]["sessions"], 1)

    def test_observation_average_and_comparison_after_change(self):
        start = datetime(2026, 11, 20, tzinfo=timezone.utc)
        e = m.Engine(None, ZoneInfo("UTC"), start)
        e.data.update(coverage_since="2026-11-20", mixed_history=True,
                      mode_changes=[{"at": start.isoformat(), "mode": "playing"}])
        e.transition(start, "playing", self.a, True, "playing", observed=True)
        e.transition(start+timedelta(hours=1), "off", self.a, True, "playing", observed=True)
        e.transition(start+timedelta(days=1), "playing", self.a, True, "playing", observed=True)
        e.transition(start+timedelta(days=1,hours=1), "off", self.a, True, "playing", observed=True)
        now = start+timedelta(days=1,hours=2)
        p = e.report(now)["periods"]["day"]
        self.assertEqual(p["previous_seconds"], 3600)
        self.assertEqual(p["observed_day_average"], 3600)
        e.transition(now, "unavailable", self.a, True, "playing", observed=False)
        p = e.report(now+timedelta(hours=2))["periods"]["day"]
        self.assertIsNone(p["previous_seconds"])
