from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from all_seeing_eye.financial_system import history, results


DAY = "2026-09-06"


def row(pid="10", gid="1", day=DAY):
    return dict(date=day, player="Player " + pid, player_key="player" + pid, player_id=pid,
                game_id=gid, start_time="2099-01-01T00:00:00Z", decision="BET", american_odds=370,
                recommended_units=1)


def box(hr=1, pa=4, ab=4, order="100", position="DH", extra_positions=()):
    teams = {}
    for side, pid in [("home", "10"), ("away", "20")]:
        hits = hr if side == "home" else 0
        teams[side] = dict(teamStats={"batting": {"plateAppearances": pa, "homeRuns": hits}}, players={
            "ID" + pid: dict(person={"id": int(pid), "fullName": "Player " + pid},
                             battingOrder=order, position={"abbreviation": position},
                             allPositions=[{"abbreviation": p} for p in extra_positions],
                             gameStatus={"isSubstitute": order != "100", "isOnBench": False},
                             stats={"batting": {"plateAppearances": pa, "atBats": ab, "homeRuns": hits}})
        })
    return {"teams": teams}


class FinancialResultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.saved = history.capture(self.root, [row()], "run")[0]
        history.record(self.root, self.saved["snapshot_id"], 1, 370)
        self.calls = []

    def fetch(self, url, params=None):
        self.calls.append((url, params))
        if "schedule" in url:
            return {"dates": [{"games": [{"gamePk": 1, "status": {"abstractGameState": "Final"}}]}]}
        return box()

    def test_fetch_only_tracked_games_and_grade_once(self):
        report = results.scan_day(self.root, DAY, self.fetch)
        self.assertEqual(report["newly_graded"], 1)
        self.assertEqual(report["pending_players"], 0)
        self.assertEqual(self.calls[0][1]["gamePks"], "1")
        self.assertEqual(len(self.calls), 2)
        report = results.scan_day(self.root, DAY, self.fetch)
        self.assertEqual(report["newly_graded"], 0)
        self.assertEqual(report["unchanged"], 1)
        wager = history.read(self.root, True).iloc[0]
        self.assertEqual(wager.result, "HR")
        self.assertAlmostEqual(wager.profit_units, 3.7)
        with history.database(self.root) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM outcomes").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM wagers").fetchone()[0], 1)

    def test_unfinished_game_stays_pending_without_box_fetch(self):
        def fetch(url, params):
            self.assertIn("schedule", url)
            return {"dates": [{"games": [{"gamePk": 1, "status": {"abstractGameState": "Live"}}]}]}
        report = results.scan_day(self.root, DAY, fetch)
        self.assertEqual(report["final_games"], 0)
        self.assertEqual(report["pending_players"], 1)

    def test_incomplete_box_does_not_infer_loss(self):
        def fetch(url, params):
            return self.fetch(url, params) if "schedule" in url else {"teams": {}}
        report = results.scan_day(self.root, DAY, fetch)
        self.assertTrue(report["errors"])
        self.assertEqual(history.read(self.root, True).iloc[0].result, "Pending")

    def test_team_totals_guard_against_partial_player_results(self):
        incomplete = box()
        incomplete["teams"]["home"]["teamStats"]["batting"]["plateAppearances"] = 99
        with self.assertRaises(ValueError): results.box_results(incomplete, "1", DAY)

    def test_missing_player_remains_pending(self):
        missing = box()
        missing["teams"]["home"]["players"]["ID10"]["person"]["id"] = 99
        report = results.scan_day(self.root, DAY, lambda u,p: self.fetch(u,p) if "schedule" in u else missing)
        self.assertEqual(report["pending_players"], 1)
        self.assertTrue(report["errors"])

    def test_nonstarter_pinch_hit_one_ab_void_but_starter_not_void(self):
        ph = results.box_results(box(hr=1, pa=1, ab=1, order="101", position="RF", extra_positions=["PH","RF"]), "1", DAY)
        self.assertEqual(history.outcome_from_result(ph["10"]), "Void")
        starter = results.box_results(box(hr=1, pa=1, ab=1), "1", DAY)
        self.assertEqual(history.outcome_from_result(starter["10"]), "HR")

    def test_explicit_nonappearance_is_void(self):
        payload = box()
        payload["teams"]["home"]["players"]["ID11"] = dict(person={"id":11}, gameStatus={"isOnBench":True}, stats={"batting":{}})
        parsed = results.box_results(payload,"1",DAY)
        self.assertEqual(history.outcome_from_result(parsed["11"]), "Void")

    def test_saved_csv_cannot_overwrite_fetched_result(self):
        results.scan_day(self.root, DAY, self.fetch)
        folder = self.root / "saved"
        folder.mkdir()
        path = folder / f"daily_results_{DAY}.csv"
        pd.DataFrame([dict(game_id="1",player_id="10",actual_hr=0,actual_pa=4,actual_ab=4)]).to_csv(path,index=False)
        before = path.read_bytes()
        changed = history.settle(self.root, folder, DAY, lambda d:self.fetch("schedule",None))
        self.assertEqual(changed, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(history.read(self.root,True).iloc[0].result, "HR")

    def test_official_correction_updates_same_outcome(self):
        results.scan_day(self.root, DAY, self.fetch)
        report = results.scan_day(self.root, DAY, lambda u,p:self.fetch(u,p) if "schedule" in u else box(hr=0))
        self.assertEqual(report["corrected"], 1)
        self.assertEqual(history.read(self.root,True).iloc[0].profit_units, -1)

    def test_failure_does_not_discard_previous_result(self):
        results.scan_day(self.root, DAY, self.fetch)
        def fail(url, params): raise RuntimeError("offline")
        report = results.scan_day(self.root, DAY, fail)
        self.assertTrue(report["errors"])
        self.assertEqual(report["pending_players"], 0)
        self.assertEqual(history.read(self.root,True).iloc[0].result, "HR")

    def test_simultaneous_scans_do_not_duplicate(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            reports = list(pool.map(lambda _:results.scan_day(self.root, DAY, self.fetch), range(2)))
        self.assertEqual(sum(r["newly_graded"] for r in reports), 1)
        self.assertEqual(sum(r["unchanged"] for r in reports), 1)

    def test_morning_checks_yesterday_and_older_unresolved_only(self):
        history.capture(self.root,[row("30", "3", "2026-09-05")],"older")
        history.capture(self.root,[row("40", "4", "2026-09-04")],"old-settled")
        history.capture(self.root,[row("50", "5", "2026-09-07")],"future")
        with history.database(self.root) as db:
            history.write_outcome(db,"4","40",dict(actual_hr=0,actual_pa=4,actual_ab=4))
        with patch.object(results,"scan_day",return_value={}) as scan:
            results.refresh_due(self.root,DAY)
        self.assertEqual([call.args[1] for call in scan.call_args_list],["2026-09-05",DAY])

    def test_selected_day_no_positions_needs_no_network(self):
        def fail(url, params): raise AssertionError("No request expected")
        report = results.scan_day(self.root,"2026-08-01",fail)
        self.assertEqual(report["games_checked"], 0)

    def live_fetch(self, url, params=None, hr=1):
        self.calls.append((url, params))
        if "schedule" in url:
            return {"dates":[{"games":[{"gamePk":1,"status":{"abstractGameState":"Live"}}]}]}
        return box(hr=hr, pa=1, ab=1)

    def test_live_hr_credits_profit_and_removes_active_bar(self):
        from all_seeing_eye.financial_system import metrics
        report = results.scan_day(self.root, DAY, self.live_fetch, include_live=True)
        actual = history.read(self.root, True)
        self.assertEqual(report["live_games"], 1)
        self.assertEqual(report["newly_graded"], 1)
        self.assertEqual(actual.iloc[0].result, "HR")
        self.assertTrue(actual.iloc[0].result_provisional)
        self.assertAlmostEqual(actual.iloc[0].profit_units, 3.7)
        self.assertEqual(metrics.portfolio_positions([], actual.to_dict("records")), [])

    def test_live_zero_hr_never_becomes_loss_or_void(self):
        report = results.scan_day(self.root, DAY, lambda u,p:self.live_fetch(u,p,0), include_live=True)
        self.assertEqual(report["pending_players"], 1)
        self.assertEqual(history.read(self.root, True).iloc[0].result, "Pending")

    def test_live_hr_correction_restores_pending_and_reverses_credit(self):
        results.scan_day(self.root, DAY, self.live_fetch, include_live=True)
        report = results.scan_day(self.root, DAY, lambda u,p:self.live_fetch(u,p,0), include_live=True)
        self.assertEqual(report["corrected"], 1)
        actual = history.read(self.root, True).iloc[0]
        self.assertEqual(actual.result, "Pending")
        self.assertFalse(actual.result_provisional)
        self.assertIsNone(actual.profit_units)

    def test_final_confirmation_clears_provisional_flag_without_double_credit(self):
        results.scan_day(self.root, DAY, self.live_fetch, include_live=True)
        report = results.scan_day(self.root, DAY, self.fetch, include_live=True)
        self.assertEqual(report["finalized"], 1)
        self.assertEqual(report["newly_graded"], 0)
        self.assertFalse(history.read(self.root, True).iloc[0].result_provisional)
        self.assertAlmostEqual(history.read(self.root, True).iloc[0].profit_units, 3.7)

    def test_final_loss_can_correct_live_hr(self):
        results.scan_day(self.root, DAY, self.live_fetch, include_live=True)
        report = results.scan_day(self.root, DAY, lambda u,p:self.fetch(u,p) if "schedule" in u else box(hr=0), include_live=True)
        self.assertEqual(report["corrected"], 1)
        self.assertEqual(history.read(self.root, True).iloc[0].profit_units, -1)
        self.assertFalse(history.read(self.root, True).iloc[0].result_provisional)

    def test_stale_live_schedule_cannot_downgrade_final_result(self):
        results.scan_day(self.root, DAY, self.fetch)
        results.scan_day(self.root, DAY, lambda u,p:self.live_fetch(u,p,0), include_live=True)
        self.assertEqual(history.read(self.root, True).iloc[0].result, "HR")
        self.assertFalse(history.read(self.root, True).iloc[0].result_provisional)

    def test_poll_throttle_shares_result_across_sessions_without_repeated_changes(self):
        first = results.scan_day(self.root, DAY, self.live_fetch, include_live=True, recorded_only=True, min_interval_seconds=30)
        second = results.scan_day(self.root, DAY, self.live_fetch, include_live=True, recorded_only=True, min_interval_seconds=30)
        self.assertEqual(first["newly_graded"], 1)
        self.assertEqual(second["newly_graded"], 0)
        self.assertEqual(len(self.calls), 2)

    def test_poll_only_fetches_recorded_wager_games(self):
        history.capture(self.root, [row("30", "3")], "another-model-recommendation")
        results.scan_day(self.root, DAY, self.live_fetch, include_live=True, recorded_only=True)
        self.assertEqual(self.calls[0][1]["gamePks"], "1")

    def test_live_cache_is_not_treated_as_official_final_by_saved_grader(self):
        results.scan_day(self.root, DAY, self.live_fetch, include_live=True)
        history.settle(self.root, self.root / "no-results", DAY, lambda d:self.fetch("schedule",None))
        self.assertTrue(history.read(self.root, True).iloc[0].result_provisional)


if __name__ == "__main__":
    unittest.main()
