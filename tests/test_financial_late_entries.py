import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from all_seeing_eye.financial_system import history


class LateEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.row = dict(date="2026-09-07", player_key="player", player="Player", player_id="10",
                        game_id="1", start_time="2026-09-07T18:00:00Z", decision="BET",
                        sportsbook="DraftKings", snapshot_id="morning")
        self.insert(self.row, "2026-09-07T15:00:00+00:00")
        with history.database(self.root) as db:
            db.execute("INSERT INTO cohort(identity,snapshot_id) VALUES(?,?)", (history.identity(self.row), "morning"))
        clock = patch.object(history, "datetime", wraps=datetime)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        self.clock.now.return_value = datetime(2026, 9, 8, 2, tzinfo=timezone.utc)

    def insert(self, row, captured):
        with history.database(self.root) as db:
            db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)",
                       (row["snapshot_id"], row["date"], row["player_key"], json.dumps(row), captured))

    def save(self, placed="2026-09-07T10:00:00-06:00"):
        return history.record_earlier(self.root, "2026-09-07", "player", placed, .5, 450, "Fanatics")

    def test_pregame_wager_can_be_logged_after_game_without_rewriting_cohort(self):
        with history.database(self.root) as db:
            before = db.execute("SELECT * FROM snapshots").fetchall()
            db.execute("INSERT INTO outcomes VALUES(?,?,?,?)", ("1", "10", "HR", "2026-09-08"))
        self.save()
        actual = history.read(self.root, actual=True).iloc[0]
        self.assertEqual(actual.entry_method, "Logged later")
        self.assertEqual(actual.placed_at, "2026-09-07T16:00:00+00:00")
        self.assertEqual(actual.recorded, "2026-09-08T02:00:00+00:00")
        self.assertEqual(actual.actual_sportsbook, "Fanatics")
        self.assertEqual(actual.profit_units, 2.25)
        self.assertEqual(actual.actual_units_bet, .5)
        with history.database(self.root) as db:
            self.assertEqual(before, db.execute("SELECT * FROM snapshots").fetchall())
            self.assertEqual(db.execute("SELECT snapshot_id FROM cohort").fetchone()[0], "morning")

    def test_duplicate_is_rejected(self):
        self.save()
        with self.assertRaisesRegex(ValueError, "already"):
            self.save()
        with history.database(self.root) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM wagers").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM wager_entries").fetchone()[0], 1)

    def test_ordinary_recording_still_locks_at_start(self):
        with self.assertRaisesRegex(ValueError, "game has started"):
            history.record(self.root, "morning", 1, 400)

    def test_live_placement_and_pre_snapshot_time_are_rejected(self):
        for placed in ["2026-09-07T18:00:00Z", "2026-09-07T19:00:00Z", "2026-09-07T14:00:00Z"]:
            with self.subTest(placed=placed), self.assertRaises(ValueError):
                self.save(placed)
        self.assertTrue(history.read(self.root, actual=True).empty)

    def test_unknown_timezone_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.save("2026-09-07T16:00:00")

    def test_future_placement_is_rejected(self):
        row = dict(self.row, snapshot_id="tomorrow", start_time="2026-09-09T18:00:00Z")
        self.insert(row, "2026-09-07T16:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "future"):
            self.save("2026-09-09T17:00:00Z")

    def test_no_postgame_snapshot_or_watch_can_be_backfilled(self):
        self.insert(dict(self.row, snapshot_id="after"), "2026-09-07T19:00:00+00:00")
        self.insert(dict(self.row, snapshot_id="watch", decision="WATCH"), "2026-09-07T15:30:00+00:00")
        self.assertEqual([r["snapshot_id"] for r in history.bet_snapshots(self.root)], ["morning"])
        for sid in ["after", "watch"]:
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                history.record(self.root, sid, 1, 400, placed_at="2026-09-07T17:00:00Z", late_entry=True)

    def test_snapshot_selection_uses_only_information_available_at_placement(self):
        self.insert(dict(self.row, snapshot_id="later"), "2026-09-07T17:00:00+00:00")
        self.assertEqual(self.save(), "morning")

    def test_missing_placement_time_and_unmarked_backdating_rejected(self):
        with self.assertRaises(ValueError):
            history.record(self.root, "morning", 1, 400, late_entry=True)
        with self.assertRaises(ValueError):
            history.record(self.root, "morning", 1, 400, placed_at="2026-09-07T16:00:00Z")

    def test_legacy_pregame_entries_remain_readable(self):
        with history.database(self.root) as db:
            db.execute("INSERT INTO wagers VALUES(?,?,?,?,?)",
                       (history.identity(self.row), "morning", 1, 400, "2026-09-07T16:00:00+00:00"))
        actual = history.read(self.root, actual=True).iloc[0]
        self.assertEqual(actual.entry_method, "Recorded pregame")
        self.assertEqual(actual.placed_at, actual.recorded)

    def test_normal_record_and_removal_keep_audit_in_sync(self):
        self.clock.now.return_value = datetime(2026, 9, 7, 16, tzinfo=timezone.utc)
        history.record(self.root, "morning", 1, 400)
        self.assertEqual(history.read(self.root, actual=True).iloc[0].entry_method, "Recorded pregame")
        history.remove_record(self.root, history.identity(self.row))
        with history.database(self.root) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM wager_entries").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

