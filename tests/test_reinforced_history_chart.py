import unittest

import pandas as pd

from all_seeing_eye.profit_lens_app import parlay_profit_curve


class ReinforcedHistoryChartTests(unittest.TestCase):
    def test_daily_totals_opening_zero_and_gaps(self):
        frame = pd.DataFrame([
            dict(game_date="2026-09-03", profit_1u=-1),
            dict(game_date="2026-09-01", profit_1u=5),
            dict(game_date="2026-09-01", profit_1u=-1),
        ])
        curve = parlay_profit_curve(frame)
        self.assertEqual(curve["Cumulative P/L (u)"].tolist(), [0, 4, 4, 3])
        self.assertEqual(str(curve.iloc[0]["Date"].date()), "2026-08-31")
        self.assertEqual(curve.iloc[-1]["Cumulative P/L (u)"], frame.profit_1u.sum())

    def test_filtered_history_does_not_use_other_rules_running_totals(self):
        frame = pd.DataFrame([
            dict(parlay="a", game_date="2026-09-01", profit_1u=5),
            dict(parlay="b", game_date="2026-09-01", profit_1u=-1),
        ])
        self.assertEqual(parlay_profit_curve(frame[frame.parlay.eq("b")]).iloc[-1]["Cumulative P/L (u)"], -1)

    def test_empty_or_invalid_history(self):
        self.assertTrue(parlay_profit_curve(pd.DataFrame()).empty)
        self.assertTrue(parlay_profit_curve(pd.DataFrame([dict(game_date="bad", profit_1u=4)])).empty)
