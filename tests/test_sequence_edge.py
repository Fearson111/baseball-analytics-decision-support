import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from all_seeing_eye.sequence_edge import SIGNAL_301_500_NEG_EDGE, summary_rows
from all_seeing_eye import profit_lens_app


class SequenceEdgeTests(unittest.TestCase):
    def test_summary_prefers_live_history_over_research_note(self):
        active = pd.DataFrame([{"signal": SIGNAL_301_500_NEG_EDGE}])
        history = pd.DataFrame(
            [
                {"signal": SIGNAL_301_500_NEG_EDGE, "result": "HR", "profit_1u": 3.2},
                {"signal": SIGNAL_301_500_NEG_EDGE, "result": "No HR", "profit_1u": -1.0},
            ]
        )

        summary = summary_rows(active, history)

        row = summary[summary["signal"].eq(SIGNAL_301_500_NEG_EDGE)].iloc[0]
        self.assertEqual(row["n"], 2)
        self.assertEqual(row["hr"], 1)
        self.assertEqual(row["profit_1u"], 2.2)
        self.assertEqual(row["read"], "2 bets, 1 HR, +2.20u, +110.00% ROI")

    def test_straight_bet_export_prefers_sequence_history_stats_over_summary(self):
        active = pd.DataFrame(
            [
                {
                    "signal": SIGNAL_301_500_NEG_EDGE,
                    "player": "Active Bat",
                    "bookmaker_used": "DraftKings",
                    "book_american_odds": 320,
                    "dk_odds": 330,
                    "signal_note": "Research read: 6 bets, 4 HR, +15.49u, +258.17% ROI.",
                }
            ]
        )
        history = pd.DataFrame(
            [
                {"signal": SIGNAL_301_500_NEG_EDGE, "result": "HR", "actual_hr": 1, "profit_1u": 3.2},
                {"signal": SIGNAL_301_500_NEG_EDGE, "result": "No HR", "actual_hr": 0, "profit_1u": -1.0},
            ]
        )
        stale_summary = pd.DataFrame(
            [
                {
                    "signal": SIGNAL_301_500_NEG_EDGE,
                    "n": 6,
                    "hr": 4,
                    "profit_1u": 15.49,
                }
            ]
        )

        with patch.object(profit_lens_app, "build_sequence_edge_frames", return_value=(active, history, stale_summary)):
            rows = profit_lens_app.active_sequence_edge_export_rows(Path("/tmp/project"), Path("/tmp/day"))

        self.assertEqual(rows[0]["signal_stats"], "2 bets, 1 HR, +2.20u, +110.00% ROI")
        self.assertEqual(rows[0]["sportsbook"], "DK")
        self.assertEqual(rows[0]["odds"], "330")


if __name__ == "__main__":
    unittest.main()
