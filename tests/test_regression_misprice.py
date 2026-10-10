import csv
import tempfile
import unittest
from pathlib import Path

from all_seeing_eye.regression_misprice import (
    build_regression_misprice_from_run,
    build_regression_misprice_history_from_archives,
    build_regression_misprice_history_rows,
)


class RegressionMispriceTests(unittest.TestCase):
    def test_builds_daily_regression_misprice_zones_from_progression_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "8", "player": "Primary Bat", "gbm_rank": "20"},
                    {"eye_rank": "18", "player": "Secondary Bat", "gbm_rank": "44"},
                    {"eye_rank": "28", "player": "Aggressive Bat", "gbm_rank": "60"},
                    {"eye_rank": "35", "player": "No Signal", "gbm_rank": "70"},
                ],
            )
            write_csv(
                inputs / "gbm_progression_top80.csv",
                [
                    {"regression_rank": "1", "player_name": "Primary Bat", "positive_regression_score": "41", "book_american_odds": "+300", "edge_percent": "-1"},
                    {"regression_rank": "2", "player_name": "Secondary Bat", "positive_regression_score": "39", "book_american_odds": "+420", "edge_percent": "8"},
                    {"regression_rank": "3", "player_name": "Aggressive Bat", "positive_regression_score": "43", "book_american_odds": "+475", "edge_percent": "9"},
                    {"regression_rank": "4", "player_name": "No Signal", "positive_regression_score": "37", "book_american_odds": "+475", "edge_percent": "-8"},
                ],
            )

            paths = build_regression_misprice_from_run(board, inputs, root / "regression")

            primary = read_csv(paths["primary_watch"])
            aggressive = read_csv(paths["aggressive_flag"])
            main_watch = read_csv(paths["main_watch_rule"])
            no_edge = read_csv(paths["main_watch_rule_no_edge"])
            premium = read_csv(paths["premium_signal"])
            combined = read_csv(paths["combined"])

            self.assertEqual([row["player"] for row in primary], ["Primary Bat"])
            self.assertNotIn("secondary_value", paths)
            self.assertEqual([row["player"] for row in aggressive], ["Aggressive Bat"])
            self.assertEqual([row["player"] for row in main_watch], ["Aggressive Bat", "Primary Bat", "Secondary Bat"])
            self.assertEqual([row["player"] for row in no_edge], ["Primary Bat"])
            self.assertEqual([row["player"] for row in premium], ["Primary Bat"])
            self.assertFalse(any(row["zone"] == "Secondary Value Zone" for row in combined))
            self.assertEqual(len(combined), 7)


    def test_archive_history_uses_frozen_regression_targets_and_daily_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            targets = root / "projections"
            results = root / "daily_results"
            targets.mkdir()
            results.mkdir()
            write_csv(
                targets / "daily_positive_regression_targets_2026-06-27.csv",
                [
                    {"regression_rank": "1", "player_id": "1", "player_name": "Archive Premium", "positive_regression_score": "41", "book_american_odds": "+300", "edge_percent": "-1", "adjusted_hr_probability_percent": "22"},
                    {"regression_rank": "2", "player_id": "2", "player_name": "Archive Main", "positive_regression_score": "39", "book_american_odds": "+420", "edge_percent": "8", "adjusted_hr_probability_percent": "18"},
                    {"regression_rank": "3", "player_id": "3", "player_name": "Missing Odds", "positive_regression_score": "42", "book_american_odds": "", "edge_percent": "-5"},
                    {"regression_rank": "11", "player_id": "4", "player_name": "Outside Rank", "positive_regression_score": "44", "book_american_odds": "+300", "edge_percent": "-5"},
                ],
            )
            write_csv(
                results / "daily_results_2026-06-27.csv",
                [
                    {"player_id": "1", "player_name": "Archive Premium", "team_abbrev": "AAA", "batting_order": "2", "actual_hr_binary": "1"},
                    {"player_id": "2", "player_name": "Archive Main", "team_abbrev": "BBB", "batting_order": "4", "actual_hr_binary": "0"},
                    {"player_id": "3", "player_name": "Missing Odds", "team_abbrev": "CCC", "batting_order": "5", "actual_hr_binary": "1"},
                    {"player_id": "4", "player_name": "Outside Rank", "team_abbrev": "DDD", "batting_order": "6", "actual_hr_binary": "1"},
                ],
            )

            history = build_regression_misprice_history_from_archives(targets, results)

            main_watch = [row for row in history if row["zone"] == "Main Watch Rule"]
            no_edge = [row for row in history if row["zone"] == "Main Watch Rule No Edge"]
            premium = [row for row in history if row["zone"] == "Premium Signal"]
            self.assertEqual([row["player"] for row in main_watch], ["Archive Premium", "Archive Main"])
            self.assertEqual([row["player"] for row in no_edge], ["Archive Premium"])
            self.assertEqual([row["player"] for row in premium], ["Archive Premium"])
            self.assertEqual(premium[0]["profit_1u"], 3.0)
            self.assertEqual(premium[0]["team_abbrev"], "AAA")

    def test_archive_history_voids_pinch_hit_one_ab_without_starting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            targets = root / "projections"
            results = root / "daily_results"
            targets.mkdir()
            results.mkdir()
            write_csv(
                targets / "daily_positive_regression_targets_2026-06-27.csv",
                [
                    {
                        "regression_rank": "1",
                        "player_id": "1",
                        "player_name": "Pinch Regression",
                        "positive_regression_score": "41",
                        "book_american_odds": "+300",
                        "edge_percent": "-1",
                    }
                ],
            )
            write_csv(
                results / "daily_results_2026-06-27.csv",
                [
                    {
                        "player_id": "1",
                        "player_name": "Pinch Regression",
                        "lineup_position": "PH",
                        "actual_pa": "1",
                        "actual_ab": "1",
                        "actual_hr_binary": "0",
                    }
                ],
            )

            history = build_regression_misprice_history_from_archives(targets, results)

            premium = next(row for row in history if row["zone"] == "Premium Signal")
            self.assertEqual(premium["result"], "Void")
            self.assertEqual(premium["is_void"], "1")
            self.assertEqual(premium["void_reason"], "Pinch-hit one AB without starting")
            self.assertEqual(premium["profit_1u"], 0.0)

    def test_history_grades_regression_misprice_zones(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs" / "manual_20260815_1000"
            inputs.mkdir(parents=True)
            write_csv(
                inputs / "gbm_progression_top80.csv",
                [
                    {"regression_rank": "1", "player_name": "Primary Bat", "positive_regression_score": "41", "book_american_odds": "+300", "edge_percent": "-1"},
                    {"regression_rank": "2", "player_name": "Secondary Bat", "positive_regression_score": "39", "book_american_odds": "+420", "edge_percent": "8"},
                ],
            )
            rows = [
                {"game_date": "2026-08-15", "eye_rank": "8", "player": "Primary Bat", "actual_hr": "1"},
                {"game_date": "2026-08-15", "eye_rank": "18", "player": "Secondary Bat", "actual_hr": "0"},
            ]

            history = build_regression_misprice_history_rows(rows, root / "inputs")

            primary = next(row for row in history if row["zone"] == "Primary Watch Zone")
            self.assertFalse(any(row["zone"] == "Secondary Value Zone" for row in history))
            main_watch = [row for row in history if row["zone"] == "Main Watch Rule"]
            no_edge = [row for row in history if row["zone"] == "Main Watch Rule No Edge"]
            premium = [row for row in history if row["zone"] == "Premium Signal"]
            self.assertEqual(primary["result"], "HR")
            self.assertEqual(primary["profit_1u"], 3.0)
            self.assertEqual([row["player"] for row in main_watch], ["Primary Bat", "Secondary Bat"])
            self.assertEqual([row["player"] for row in no_edge], ["Primary Bat"])
            self.assertEqual([row["player"] for row in premium], ["Primary Bat"])


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
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
