import csv
import tempfile
import unittest
from pathlib import Path

from all_seeing_eye.edge_buckets import (
    build_edge_bucket_active_rows,
    build_edge_bucket_base_history_rows,
    build_edge_bucket_history_rows,
    build_edge_bucket_summary_rows,
)


class EdgeBucketTests(unittest.TestCase):
    def test_top25_is_chosen_before_book_edge_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projections = root / "projections"
            results = root / "results"
            projections.mkdir()
            results.mkdir()
            rows = []
            for index in range(1, 27):
                rows.append(
                    {
                        "rank": str(index),
                        "game_date": "2026-08-17",
                        "game_id": "G1",
                        "player_id": str(index),
                        "player_name": f"Player {index}",
                        "american_betting_odds": str(100 + index),
                        "book_american_odds": "+450" if index != 1 else "",
                        "edge_percent": "1" if index != 1 else "",
                        "adjusted_hr_probability_percent": "20",
                    }
                )
            rows[25]["book_american_odds"] = "+450"
            rows[25]["edge_percent"] = "1"
            write_csv(projections / "daily_hr_projections_2026-08-17.csv", rows)
            write_csv(
                results / "daily_results_2026-08-17.csv",
                [
                    {"game_id": "G1", "player_id": str(index), "player_name": f"Player {index}", "actual_hr_binary": "0"}
                    for index in range(1, 27)
                ],
            )

            active = build_edge_bucket_active_rows("2026-08-17", projections)
            base = build_edge_bucket_base_history_rows(projections, results, end_date="2026-08-17")

            self.assertFalse(any(row["player"] == "Player 26" for row in active))
            self.assertFalse(any(row["player"] == "Player 26" for row in base))
            self.assertTrue(any(row["player"] == "Player 2" for row in active))

    def test_history_and_summaries_grade_edge_bucket_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projections = root / "projections"
            results = root / "results"
            projections.mkdir()
            results.mkdir()
            write_csv(
                projections / "daily_hr_projections_2026-08-17.csv",
                [
                    projection_row(1, "Primary Winner", "+300", "+450", "1", "1"),
                    projection_row(2, "Tiny Winner", "+320", "+1200", "11", "2"),
                    projection_row(3, "Rank Edge", "+340", "+350", "3", "3"),
                ],
            )
            write_csv(
                results / "daily_results_2026-08-17.csv",
                [
                    result_row("1", "Primary Winner", "1"),
                    result_row("2", "Tiny Winner", "1"),
                    result_row("3", "Rank Edge", "0"),
                ],
            )

            history = build_edge_bucket_history_rows(projections, results, end_date="2026-08-17")
            summary = build_edge_bucket_summary_rows(history)
            primary = next(row for row in history if row["signal"] == "Primary Mid-Price Edge Rule")
            primary_summary = next(row for row in summary if row["bucket"] == "Primary Mid-Price Edge Rule")
            self.assertEqual(primary["player"], "Primary Winner")
            self.assertEqual(primary["profit_1u"], 4.5)
            self.assertFalse(any(row["signal"] == "Edge >10: Tiny Trust" for row in history))
            self.assertEqual(primary_summary["n"], 1)


    def test_base_history_voids_pinch_hit_one_ab_without_starting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projections = root / "projections"
            results = root / "results"
            projections.mkdir()
            results.mkdir()
            write_csv(
                projections / "daily_hr_projections_2026-08-17.csv",
                [projection_row(1, "Pinch Edge", "+300", "+450", "1", "1")],
            )
            write_csv(
                results / "daily_results_2026-08-17.csv",
                [
                    {
                        "game_id": "G1",
                        "player_id": "1",
                        "player_name": "Pinch Edge",
                        "lineup_position": "PH",
                        "actual_pa": "1",
                        "actual_ab": "1",
                        "actual_hr_binary": "0",
                    }
                ],
            )

            base = build_edge_bucket_base_history_rows(projections, results, end_date="2026-08-17")

            self.assertEqual(base[0]["result"], "Void")
            self.assertEqual(base[0]["is_void"], "1")
            self.assertEqual(base[0]["void_reason"], "Pinch-hit one AB without starting")
            self.assertEqual(base[0]["profit_1u"], 0.0)


def projection_row(rank: int, player: str, model_odds: str, book_odds: str, edge: str, player_id: str) -> dict[str, str]:
    return {
        "rank": str(rank),
        "game_date": "2026-08-17",
        "game_id": "G1",
        "player_id": player_id,
        "player_name": player,
        "american_betting_odds": model_odds,
        "book_american_odds": book_odds,
        "edge_percent": edge,
        "adjusted_hr_probability_percent": "20",
    }


def result_row(player_id: str, player: str, actual_hr: str) -> dict[str, str]:
    return {"game_id": "G1", "player_id": player_id, "player_name": player, "actual_hr_binary": actual_hr}


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
