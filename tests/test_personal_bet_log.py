import tempfile
import unittest
from pathlib import Path
import json
import pandas as pd

from all_seeing_eye.financial_system import bet_log, history, metrics


class PersonalBetLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_watch_player_after_game_can_be_logged_with_actual_price(self):
        context = dict(game_id="123", player_id="456", team="CIN", opponent="CHC",
                       start_time="2020-01-01T00:00:00Z",
                       prediction=dict(decision="MARGINAL / WATCH", estimated_hr_probability=.2,
                                       probability_method="Reference", signal_families=["eye"], model_families=["Eye"]))
        bet_log.log_bet(self.root, "2020-01-01", "Elly De La Cruz", .5, 450, "Fanatics", context=context)
        actual = history.read(self.root, actual=True)
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual.iloc[0].actual_units_bet, .5)
        self.assertEqual(actual.iloc[0].actual_sportsbook, "Fanatics")
        self.assertEqual(actual.iloc[0].decision, "MARGINAL / WATCH")
        self.assertTrue(history.read(self.root).empty)
        with history.database(self.root) as db:
            history.write_outcome(db, "123", "456", dict(actual_hr=1, actual_pa=4, actual_ab=4))
        self.assertEqual(history.read(self.root, actual=True).iloc[0].profit_units, 2.25)

    def test_typed_player_without_predictions_does_not_break_accounting(self):
        bet_log.log_bet(self.root, "2026-09-07", "New Player", .5, 450, "Fanatics")
        raw = history.read(self.root, actual=True)
        row = raw.iloc[0]
        with history.database(self.root) as db:
            history.write_outcome(db, row.game_id, row.player_id, dict(actual_hr=0, actual_pa=4, actual_ab=4))
        f = metrics.strategy(history.read(self.root, actual=True), "actual")
        self.assertEqual(f.profit.iloc[0], -.5)
        self.assertTrue(f.p.isna().all())
        summary = metrics.summary(f)
        self.assertEqual(summary["profit"], -.5)
        self.assertIsNone(summary["expected_profit"])
        curve = metrics.portfolio_curve(f)
        self.assertEqual(curve.realized.iloc[-1], -.5)
        self.assertTrue(curve.expected.isna().iloc[-1])

    def test_expected_curve_keeps_full_range_with_partial_model_coverage(self):
        frame = pd.DataFrame([
            dict(date="2026-09-01", result="No HR", profit=-1., expected_profit=.4, return_1u=-1., stake=1.),
            dict(date="2026-09-02", result="HR", profit=2., expected_profit=float("nan"), return_1u=2., stake=1.),
            dict(date="2026-09-03", result="No HR", profit=-1., expected_profit=.2, return_1u=-1., stake=1.),
        ])
        curve = metrics.portfolio_curve(frame)
        self.assertEqual(len(curve), 4)
        for actual, expected in zip(curve.expected.tolist(), [0., .4, .4, .6]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(curve.expected_positions.iloc[-1], 2)
        self.assertTrue(history.read(self.root).empty)

    def test_existing_bet_updates_in_place_only_when_requested(self):
        bet_log.log_bet(self.root, "2026-09-07", "Elly", .5, 450, "Fanatics")
        with self.assertRaises(ValueError):
            bet_log.log_bet(self.root, "2026-09-07", "Elly", 1, 500, "DraftKings")
        bet_log.log_bet(self.root, "2026-09-07", "Elly", 1, 500, "DraftKings", replace=True)
        raw = history.read(self.root, actual=True)
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw.iloc[0].actual_units_bet, 1)
        self.assertEqual(raw.iloc[0].actual_american_odds, 500)
        with history.database(self.root) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM wager_edits").fetchone()[0], 1)

    def test_invalid_stake_price_and_blank_player_are_not_saved(self):
        for player, units, odds in [("",1,450), ("A",0,450), ("A",float("nan"),450), ("A",1,0)]:
            with self.subTest(player=player, units=units), self.assertRaises(ValueError):
                bet_log.log_bet(self.root, "2026-09-07", player, units, odds)
        self.assertTrue(history.read(self.root, actual=True).empty)

    def test_options_include_non_bet_players(self):
        row = dict(player="Elly", player_key="elly", date="2026-09-07", game_id="123",
                   player_id="456", decision="PASS", start_time="2026-09-07T23:00:00Z",
                   estimated_hr_probability=.2, probability_method="Reference")
        with history.database(self.root) as db:
            db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)",
                       ("source","2026-09-07","elly",json.dumps(row),"2026-09-07T15:00:00Z"))
        options = bet_log.player_options(self.root, "2026-09-07")
        self.assertEqual(options[0]["player"], "Elly")
        self.assertEqual(options[0]["prediction"]["decision"], "PASS")


if __name__ == "__main__":
    unittest.main()
