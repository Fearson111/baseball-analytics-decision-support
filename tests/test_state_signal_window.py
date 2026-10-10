from datetime import date
import os
from pathlib import Path
import tempfile
import unittest

from all_seeing_eye.daily_hub.runner import INPUTS, rolling_state_history


class StateSignalWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def folder(self, day, suffix="run", complete=True, timestamp=1):
        path = self.root / f"manual_{day}_{suffix}"
        path.mkdir()
        for name in list(INPUTS.values())[:4 if complete else 3]:
            (path / name).write_text("player,rank\nExample,1\n")
        os.utime(path, (timestamp, timestamp))
        return path

    def test_three_prior_days_excludes_today_and_future(self):
        for day in range(1, 8):
            self.folder(f"202609{day:02d}")
        result = rolling_state_history(self.root, date(2026, 9, 5))
        self.assertEqual([d.isoformat() for d, _ in result], ["2026-09-02", "2026-09-03", "2026-09-04"])
        self.assertEqual(len(list(self.root.iterdir())), 7)

    def test_next_morning_rolls_forward(self):
        for day in range(1, 6):
            self.folder(f"202609{day:02d}")
        result = rolling_state_history(self.root, date(2026, 9, 6))
        self.assertEqual([d.isoformat() for d, _ in result], ["2026-09-03", "2026-09-04", "2026-09-05"])

    def test_multiple_runs_count_as_one_day_and_incomplete_latest_is_ignored(self):
        original = self.folder("20260904", "first", timestamp=1)
        newest = self.folder("20260904", "second", timestamp=2)
        self.folder("20260904", "incomplete", complete=False, timestamp=3)
        result = rolling_state_history(self.root, date(2026, 9, 5))
        self.assertEqual(result, [(date(2026, 9, 4), newest)])
        self.assertTrue(original.exists())

    def test_missing_days_use_three_available_input_days_not_duplicate_snapshots(self):
        for day in (1, 3, 4):
            self.folder(f"202609{day:02d}")
        result = rolling_state_history(self.root, date(2026, 9, 5))
        self.assertEqual([d.day for d, _ in result], [1, 3, 4])

    def test_empty_partial_invalid_and_undated_inputs_do_not_enter_history(self):
        self.folder("20260904", complete=False)
        self.folder("invalid")
        (self.root / "yesterday").mkdir()
        self.assertEqual(rolling_state_history(self.root, date(2026, 9, 5)), [])


if __name__ == "__main__":
    unittest.main()
