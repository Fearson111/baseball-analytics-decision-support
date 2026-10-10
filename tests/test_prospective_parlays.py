import csv
import tempfile
import unittest
from pathlib import Path

from all_seeing_eye.prospective_parlays import (
    add_meta_features,
    build_prospective_history_rows,
    build_prospective_parlays_from_run,
    normalized_strength,
)


class ProspectiveParlayTests(unittest.TestCase):
    def test_normalizes_actual_model_list_lengths(self):
        self.assertEqual(normalized_strength("1", 80), 1.0)
        self.assertAlmostEqual(normalized_strength("80", 80), 0.0)
        self.assertAlmostEqual(normalized_strength("76", 150), 0.4966, places=4)

    def test_builds_consensus_ticket_with_different_games_and_expected_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    candidate("Anchor A", 1, 2, 3, 7, 2, "+400", "NYY", "BOS"),
                    candidate("Anchor B", 2, 3, 4, 8, 3, "+500", "LAD", "SF"),
                    candidate("Same Game", 3, 4, 5, 9, 4, "+600", "BOS", "NYY"),
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Anchor A"}, {"player_name": "Anchor B"}, {"player_name": "Same Game"}])

            paths = build_prospective_parlays_from_run(board, inputs, root / "prospective")

            rows = read_csv(paths["CONSENSUS_2L_V1"])
            self.assertEqual(rows[0]["criteria_id"], "CONSENSUS_2L_V1")
            self.assertEqual(rows[0]["leg1_player"], "Anchor A")
            self.assertEqual(rows[0]["leg2_player"], "Anchor B")
            self.assertEqual(rows[0]["same_game_allowed"], "False")
            self.assertEqual(rows[0]["record_locked_before_games"], "1")
            self.assertAlmostEqual(float(rows[0]["expected_wins"]), 0.033333, places=6)

    def test_builds_anchor_specialist_with_separate_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    candidate("Low Disagree Anchor", 1, 4, 5, 6, 7, "+350", "NYM", "PHI"),
                    candidate("State Specialist", 8, 22, 30, 2, 2, "+650", "SEA", "TEX"),
                    candidate("Loose Specialist", 9, 60, 60, 1, 2, "+700", "ARI", "COL"),
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Low Disagree Anchor"}, {"player_name": "State Specialist"}, {"player_name": "Loose Specialist"}])

            paths = build_prospective_parlays_from_run(board, inputs, root / "prospective")

            rows = read_csv(paths["ANCHOR_SPECIALIST_2L_V1"])
            self.assertEqual(rows[0]["leg1_role"], "Consensus Anchor")
            self.assertEqual(rows[0]["leg1_player"], "Low Disagree Anchor")
            self.assertEqual(rows[0]["leg2_role"], "Specialist")
            self.assertEqual(rows[0]["leg2_player"], "State Specialist")

    def test_history_uses_saved_forward_tickets_and_tracker_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "MODEL4_DAILY_READS" / "2026-08-16" / "PROSPECTIVE_PARLAYS"
            folder.mkdir(parents=True)
            write_csv(
                folder / "prospective_parlays_combined.csv",
                [
                    {
                        "ticket_id": "2026-08-16_CONSENSUS_2L_V1",
                        "slate_date": "2026-08-16",
                        "criteria_id": "CONSENSUS_2L_V1",
                        "criteria_version": "1",
                        "criteria_title": "Consensus x Consensus V1",
                        "leg1_player": "Player A",
                        "leg1_book_american_odds": "+400",
                        "leg2_player": "Player B",
                        "leg2_book_american_odds": "+500",
                        "expected_wins": "0.033333",
                        "parlay_decimal_odds": "30.0",
                    }
                ],
            )
            tracking = root / "MODEL4_RANK_TRACKING"
            tracking.mkdir()
            write_csv(
                tracking / "model4_rank_results.csv",
                [
                    {"game_date": "2026-08-16", "player": "Player A", "result_available": "1", "actual_hr": "1"},
                    {"game_date": "2026-08-16", "player": "Player B", "result_available": "1", "actual_hr": "1"},
                ],
            )

            history = build_prospective_history_rows(root)

            self.assertEqual(history[0]["ticket_hit"], "1")
            self.assertEqual(history[0]["profit_units"], 29.0)
            self.assertEqual(history[0]["leg1_result"], "HR")
            self.assertEqual(history[0]["leg2_result"], "HR")


def candidate(player, eye, gbm, prog, seq, pitch, odds, team, opp):
    return {
        "eye_rank": str(eye),
        "player": player,
        "gbm_rank": str(gbm),
        "gbm_progression_rank": str(prog),
        "sequence_rank": str(seq),
        "pitcher_batter_rank": str(pitch),
        "book_american_odds": odds,
        "team_abbrev": team,
        "opponent_abbrev": opp,
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
