import csv
import tempfile
import unittest
from pathlib import Path

from all_seeing_eye.tracker import parse_homer_name, profit_for_1u, run_rank_tracker


class TrackerTests(unittest.TestCase):
    def test_profit_for_positive_american_odds(self):
        self.assertEqual(profit_for_1u(350, True), 3.5)
        self.assertEqual(profit_for_1u(350, False), -1.0)

    def test_parse_homer_name_from_statcast_description(self):
        self.assertEqual(
            parse_homer_name("Alex Bregman homers (14) on a fly ball to left field."),
            "Alex Bregman",
        )

    def test_tracker_grades_rank_slots_and_profit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board_dir = root / "MODEL4_DAILY_READS" / "2026-08-14"
            board_dir.mkdir(parents=True)
            write_csv(
                board_dir / "MODEL4_2026-08-14_BOARD.csv",
                [
                    {
                        "eye_rank": "1",
                        "player": "Player A",
                        "eye_score": "91",
                        "accel_score": "82",
                        "book_american_odds": "+300",
                    },
                    {
                        "eye_rank": "2",
                        "player": "Player B",
                        "eye_score": "88",
                        "accel_score": "54",
                        "book_american_odds": "+500",
                    },
                ],
            )
            results_dir = root / "results"
            results_dir.mkdir()
            write_csv(
                results_dir / "daily_results_2026-08-14.csv",
                [
                    {"player_name": "Player A", "actual_hr": "1"},
                    {"player_name": "Player B", "actual_hr": "0"},
                ],
            )

            outputs = run_rank_tracker(
                board_root=root / "MODEL4_DAILY_READS",
                input_root=root / "inputs",
                output_folder=root / "MODEL4_RANK_TRACKING",
                results_dir=results_dir,
                statcast_dir=root / "statcast",
            )

            self.assertEqual(outputs.graded_rows, 2)
            summary = read_csv(outputs.summary_path)
            self.assertEqual(summary[0]["eye_rank"], "1")
            self.assertEqual(summary[0]["hit_rate_percent"], "100.0")
            self.assertEqual(summary[0]["profit_1u_flat"], "3.0")
            self.assertEqual(summary[1]["profit_1u_flat"], "-1.0")

    def test_tracker_voids_player_missing_from_completed_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board_dir = root / "MODEL4_DAILY_READS" / "2026-08-14"
            board_dir.mkdir(parents=True)
            write_csv(
                board_dir / "MODEL4_2026-08-14_BOARD.csv",
                [
                    {"eye_rank": "1", "player": "Player A", "book_american_odds": "+300"},
                    {"eye_rank": "2", "player": "Scratched Bat", "book_american_odds": "+500"},
                ],
            )
            results_dir = root / "results"
            results_dir.mkdir()
            write_csv(
                results_dir / "daily_results_2026-08-14.csv",
                [
                    {"player_name": "Player A", "actual_pa": "4", "actual_ab": "4", "actual_hr": "1"},
                ],
            )

            outputs = run_rank_tracker(
                board_root=root / "MODEL4_DAILY_READS",
                input_root=root / "inputs",
                output_folder=root / "MODEL4_RANK_TRACKING",
                results_dir=results_dir,
                statcast_dir=root / "statcast",
            )

            detail = read_csv(outputs.detail_path)
            scratched = next(row for row in detail if row["player"] == "Scratched Bat")
            self.assertEqual(scratched["result"], "Void")
            self.assertEqual(scratched["is_void"], "1")
            self.assertEqual(scratched["profit_1u"], "0.0")
            summary = read_csv(outputs.summary_path)
            self.assertEqual([row["eye_rank"] for row in summary], ["1"])

    def test_tracker_voids_pinch_hit_one_ab_without_starting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board_dir = root / "MODEL4_DAILY_READS" / "2026-08-14"
            board_dir.mkdir(parents=True)
            write_csv(
                board_dir / "MODEL4_2026-08-14_BOARD.csv",
                [
                    {"eye_rank": "1", "player": "Starter Bat", "book_american_odds": "+300"},
                    {"eye_rank": "2", "player": "Pinch Bat", "book_american_odds": "+500"},
                ],
            )
            results_dir = root / "results"
            results_dir.mkdir()
            write_csv(
                results_dir / "daily_results_2026-08-14.csv",
                [
                    {"player_name": "Starter Bat", "actual_pa": "4", "actual_ab": "4", "actual_hr": "1"},
                    {
                        "player_name": "Pinch Bat",
                        "lineup_position": "PH",
                        "actual_pa": "1",
                        "actual_ab": "1",
                        "actual_hr": "0",
                    },
                ],
            )

            outputs = run_rank_tracker(
                board_root=root / "MODEL4_DAILY_READS",
                input_root=root / "inputs",
                output_folder=root / "MODEL4_RANK_TRACKING",
                results_dir=results_dir,
                statcast_dir=root / "statcast",
            )

            detail = read_csv(outputs.detail_path)
            pinch = next(row for row in detail if row["player"] == "Pinch Bat")
            self.assertEqual(pinch["result"], "Void")
            self.assertEqual(pinch["is_void"], "1")
            self.assertEqual(pinch["void_reason"], "Pinch-hit one AB without starting")
            self.assertEqual(pinch["profit_1u"], "0.0")
            summary = read_csv(outputs.summary_path)
            self.assertEqual([row["eye_rank"] for row in summary], ["1"])


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
