"""Exercise the actual offline backup/restore command in disposable storage."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "test_entry"
KEY = "media_activity_tracker." + ENTRY


class BackupTests(unittest.TestCase):
    def test_export_restore_and_reject_wrong_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            storage = config / ".storage"
            storage.mkdir()
            target = storage / KEY
            data = {"version": 1, "minor_version": 1, "key": KEY,
                    "data": {"started": "2026-01-01T00:00:00+00:00",
                             "apps": {}, "days": {}, "sessions": []}}
            target.write_text(json.dumps(data))
            backup = config / "backup.json"
            def run(action, *extra):
                return subprocess.run([sys.executable, str(ROOT/"tools/history_backup.py"),
                                       action, str(config), ENTRY, str(backup), *extra],
                                      capture_output=True, text=True)
            self.assertEqual(run("export").returncode, 0)
            self.assertEqual(json.loads(backup.read_text()), data)
            self.assertNotEqual(run("export").returncode, 0)
            target.write_text("corrupt original")
            self.assertNotEqual(run("restore").returncode, 0)
            self.assertEqual(run("restore", "--confirm-stopped").returncode, 0)
            self.assertEqual(json.loads(target.read_text()), data)
            self.assertEqual((storage/(KEY+".before-restore")).read_text(), "corrupt original")
            self.assertEqual(target.stat().st_mode & 0o077, 0)
            wrong = {**data, "key":"another"}
            backup.write_text(json.dumps(wrong))
            self.assertNotEqual(run("restore", "--confirm-stopped").returncode, 0)
            self.assertEqual(json.loads(target.read_text()), data)
