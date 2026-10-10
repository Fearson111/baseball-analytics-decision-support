from contextlib import ExitStack
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from all_seeing_eye.daily_hub import runner
from all_seeing_eye.financial_system import bet_log, config, data, decisions, engine, history, page


def financial_page(root, out):
    from pathlib import Path
    from all_seeing_eye.financial_system.page import render
    render(Path(root), Path(out))


class FinancialWagerRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.day = date.today().isoformat()
        self.out = self.root / "run" / self.day
        self.out.mkdir(parents=True)
        for path in (self.out.parent / "market_board.csv", self.out / "straight_bets.csv",
                     self.out / f"MODEL4_{self.day}_BOARD.csv"):
            pd.DataFrame([{"player": "Luis Garcia Jr."}]).to_csv(path, index=False)
        self.folder = self.out / "FINANCIAL_SYSTEM"
        self.cfg = config.Config()
        now = datetime.now(timezone.utc)
        row = data.enrich(dict(date=self.day, player="Luis Garcia Jr.", player_key="luisgarciajr",
                              game_id="123", player_id="456", team="NYY", opponent="NYM",
                              american_odds=385, base_model_probability=.3, lineup_status="confirmed",
                              start_time=(now + timedelta(hours=5)).isoformat(), odds_observed=now.isoformat(),
                              signal_labels=["Pitch-Fit Longshot + Best Eye Rank"]), self.cfg)
        row.update(estimated_hr_probability=.3, posterior_lower=.22, posterior_upper=.38,
                   p_positive_ev=.96, historical_bets=80, historical_hr_rate=.3,
                   probability_edge_pp=9.38, expected_value_per_unit=.455, decision="BET", reasons=[])
        self.row = row
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(runner, "HUB", self.root / "DAILY_BASEBALL"))
        self.stack.enter_context(patch("all_seeing_eye.daily_hub.history.straight_history", return_value=pd.DataFrame()))
        self.stack.enter_context(patch.object(data, "history_players", return_value=pd.DataFrame()))
        self.stack.enter_context(patch.object(data, "candidates", return_value=pd.DataFrame([row])))
        self.stack.enter_context(patch.object(engine, "synthesize", side_effect=self.synthesize))

    def synthesize(self, candidates, training, cfg, model=None, bankroll=None, existing=()):
        rows = decisions.allocate([deepcopy(self.row)], cfg, bankroll or 100, existing)
        return rows, {"version": "test"}

    def build(self):
        return engine.build(self.root, self.out, config=self.cfg, persist=False)[0]

    def records(self):
        return history.read(self.root, actual=True).to_dict("records")

    def record(self, units=.5, odds=500, replace=False):
        bet_log.log_bet(self.root, self.day, self.row["player"], units, odds, "DraftKings Boost",
                        context={"prediction": self.row}, replace=replace)

    def test_record_invalidates_older_snapshot_and_rebuild_marks_already_recorded(self):
        self.assertEqual(self.build()[0]["decision"], "BET")
        self.assertFalse(engine.wagers_changed(self.folder, []))
        self.record()
        self.assertTrue(engine.wagers_changed(self.folder, self.records()))
        row = self.build()[0]
        self.assertEqual(row["decision"], "PASS")
        self.assertEqual(row["recommended_units"], 0)
        self.assertIn("ALREADY_RECORDED", row["reasons"])
        self.assertFalse(engine.wagers_changed(self.folder, self.records()))

    def test_updates_and_removal_invalidate_allocations(self):
        self.record()
        self.build()
        self.record(units=1., odds=550, replace=True)
        self.assertTrue(engine.wagers_changed(self.folder, self.records()))
        self.build()
        self.assertFalse(engine.wagers_changed(self.folder, self.records()))
        history.remove_record(self.root, self.day + ":luisgarciajr")
        self.assertTrue(engine.wagers_changed(self.folder, []))
        self.assertEqual(self.build()[0]["decision"], "BET")

    def test_legacy_manifest_refreshes_once_and_signature_ignores_row_order(self):
        self.folder.mkdir()
        (self.folder / "manifest.json").write_text("{}")
        self.assertTrue(engine.wagers_changed(self.folder, []))
        self.build()
        self.assertFalse(engine.wagers_changed(self.folder, []))
        rows = [dict(player_key="a", actual_units_bet=.5), dict(player_key="b", actual_units_bet=1.)]
        self.assertEqual(engine.wager_signature(rows), engine.wager_signature(rows[::-1]))

    def test_display_filter_does_not_mutate_snapshot_or_remove_other_players(self):
        rows = [dict(self.row), {**self.row, "player_key": "another", "player": "Another Player"}]
        before = deepcopy(rows)
        visible = decisions.unrecorded_decisions(rows, [self.row])
        self.assertEqual([r["player_key"] for r in visible], ["another"])
        self.assertEqual(rows, before)
        self.assertNotIn("luisgarciajr", engine.decision_export(visible).player_key.tolist())

    def test_page_detects_bet_from_another_session_without_rebuild_flag(self):
        self.build()
        for name in ("live_result_monitor", "record_bet_control", "inspector", "evidence_view", "exposure_view",
                     "portfolio_performance", "history_charts", "diagnostics", "config_view"):
            self.stack.enter_context(patch.object(page, name))
        app = AppTest.from_function(financial_page, args=(str(self.root), str(self.out))).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.metric[0].value, "1")
        self.record()
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.metric[0].value, "0")
        self.assertTrue(any(exp.label == "BET · 0" for exp in app.expander))
        self.assertTrue(any(exp.label == "PASS · 0" for exp in app.expander))
        cached = json.loads((self.folder / "decisions.json").read_text())
        self.assertEqual(cached[0]["primary_reason"], "ALREADY_RECORDED")
        self.assertFalse(engine.wagers_changed(self.folder, self.records()))

    def test_page_shows_recorded_stake_and_remaining_daily_budget(self):
        self.cfg = config.Config(max_daily=4, max_family=4)
        config.save(self.root, self.cfg)
        self.record(units=3.5)
        self.build()
        for name in ("live_result_monitor", "record_bet_control", "inspector", "evidence_view", "exposure_view",
                     "portfolio_performance", "history_charts", "diagnostics", "config_view"):
            self.stack.enter_context(patch.object(page, name))
        app = AppTest.from_function(financial_page, args=(str(self.root), str(self.out))).run()
        self.assertEqual(len(app.exception), 0)
        by_label = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(by_label["Recorded stake"], "3.50u")
        self.assertNotIn("Daily cap", by_label)
        self.assertEqual(by_label["Remaining budget"], "0.50u")


if __name__ == "__main__":
    unittest.main()
