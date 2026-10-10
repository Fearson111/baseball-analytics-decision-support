import unittest

from all_seeing_eye.boards import BoardEntry
from all_seeing_eye.closer import score_closer_candidate


class CloserTests(unittest.TestCase):
    def test_strong_actionable_profile_becomes_bet_candidate(self):
        row = {
            "eye_rank": "4",
            "player": "Player A",
            "eye_score": "84",
            "movement_summary": "Cross-system acceleration detected on 2 boards",
            "reasoning": "",
        }
        entries = {
            "gbm_top80": BoardEntry(
                "gbm_top80",
                "Player A",
                6,
                {
                    "adjusted_hr_probability_percent": "18",
                    "batting_order": "2",
                    "lineup_status": "confirmed",
                    "projected_pa": "4.7",
                    "edge_percent": "6",
                    "american_betting_odds": "+520",
                },
            ),
            "sequence_top150": BoardEntry("sequence_top150", "Player A", 18, {"hr_probability": "0.20"}),
            "pitcher_batter_top80": BoardEntry(
                "pitcher_batter_top80",
                "Player A",
                10,
                {"hr_edge_score": "80"},
            ),
        }

        candidate = score_closer_candidate(row, entries)

        self.assertEqual(candidate.decision, "BET_CANDIDATE")
        self.assertGreaterEqual(candidate.conviction_score, 78)

    def test_no_gbm_support_is_cautioned(self):
        row = {
            "eye_rank": "1",
            "player": "Player B",
            "eye_score": "92",
            "movement_summary": "New entrant on Sequence Top 150 at rank 1",
            "reasoning": "",
        }
        entries = {
            "sequence_top150": BoardEntry("sequence_top150", "Player B", 1, {"hr_probability": "0.25"}),
        }

        candidate = score_closer_candidate(row, entries)

        self.assertIn("No GBM base-board support", " ".join(candidate.reasons))
        self.assertNotEqual(candidate.decision, "BET_CANDIDATE")


if __name__ == "__main__":
    unittest.main()

