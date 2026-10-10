from datetime import datetime, timedelta, timezone
import unittest

from all_seeing_eye.daily_hub.markets import is_pregame
from all_seeing_eye.daily_hub.public_odds import active_games


class PregameStatusTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 11, 22, 21, tzinfo=timezone.utc)
        self.game = dict(status="Live", detailed_status="Warmup", start_time="2026-09-11T22:40:00Z")

    def test_warmup_before_first_pitch_is_pregame(self):
        self.assertTrue(is_pregame(self.game, self.now))
        self.assertEqual(active_games([self.game], self.now), [self.game])

    def test_at_or_after_scheduled_start_is_not_pregame_even_if_still_warmup(self):
        start = datetime.fromisoformat(self.game["start_time"])
        for now in (start, start + timedelta(seconds=1)):
            self.assertFalse(is_pregame(self.game, now))
            self.assertEqual(active_games([self.game], now), [])

    def test_started_postponed_and_unknown_games_stay_excluded(self):
        for status, detail in (("Live", "In Progress"), ("Live", ""), ("Live", "Delayed"),
                               ("Final", "Final"), ("Preview", "Postponed"),
                               ("Preview", "Suspended"), ("", "")):
            with self.subTest(status=status, detail=detail):
                self.assertFalse(is_pregame({**self.game, "status": status, "detailed_status": detail}, self.now))

    def test_regular_pregame_states_and_missing_start(self):
        for detail in ("", "Scheduled", "Pre-Game"):
            self.assertTrue(is_pregame({**self.game, "status": "Preview", "detailed_status": detail}, self.now))
        self.assertFalse(is_pregame({**self.game, "start_time": ""}, self.now))


if __name__ == "__main__":
    unittest.main()
