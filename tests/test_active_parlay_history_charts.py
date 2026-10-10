import unittest

import pandas as pd

from all_seeing_eye.profit_lens_app import active_parlay_history_groups, parlay_profit_curve
from all_seeing_eye.profit_parlays import (
    parlay_specs, three_leg_parlay_specs, four_leg_parlay_specs,
    reinforced_parlay_specs, movement_parlay_specs,
)


class ActiveParlayHistoryChartTests(unittest.TestCase):
    def test_whole_group_totals_exclude_reinforced_and_movement(self):
        history = pd.DataFrame([
            dict(parlay=parlay_specs()[0].title, game_date="2026-09-01", profit_1u=10),
            dict(parlay=parlay_specs()[1].title, game_date="2026-09-02", profit_1u=-1),
            dict(parlay=three_leg_parlay_specs()[0].title, game_date="2026-09-01", profit_1u=20),
            dict(parlay=four_leg_parlay_specs()[0].title, game_date="2026-09-01", profit_1u=40),
            dict(parlay=reinforced_parlay_specs()[0].title, game_date="2026-09-01", profit_1u=100),
            dict(parlay=movement_parlay_specs()[0].title, game_date="2026-09-01", profit_1u=200),
        ])
        groups = active_parlay_history_groups(history)
        self.assertEqual([title for title, _ in groups], [
            "Active 2-Leg Cumulative P/L", "Active 3-Leg Cumulative P/L", "Active 4-Leg Cumulative P/L"])
        self.assertEqual([len(group) for _, group in groups], [2, 1, 1])
        self.assertEqual([parlay_profit_curve(group).iloc[-1]["Cumulative P/L (u)"] for _, group in groups], [9, 20, 40])

    def test_empty_history(self):
        groups = active_parlay_history_groups(pd.DataFrame())
        self.assertEqual(len(groups), 3)
        self.assertTrue(all(group.empty for _, group in groups))
