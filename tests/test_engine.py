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
