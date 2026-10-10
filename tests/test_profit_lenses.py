import csv
import tempfile
import unittest
from pathlib import Path

from all_seeing_eye.profit_lenses import build_profit_lenses, build_profit_lenses_from_run


class ProfitLensTests(unittest.TestCase):
    def test_builds_daily_capped_and_sharper_lenses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            write_csv(
                board,
                [
                    {
                        "eye_rank": "8",
                        "player": "Broad Fit",
                        "book_american_odds": "+650",
                        "model_hr_probability_percent": "15",
                        "edge_percent": "2.1",
                        "gbm_rank": "88",
                        "pitcher_batter_rank": "18",
                    },
                    {
                        "eye_rank": "21",
                        "player": "Sharper Fit",
                        "book_american_odds": "+550",
                        "model_hr_probability_percent": "14",
                        "edge_percent": "4.2",
                        "gbm_rank": "55",
                        "pitcher_batter_rank": "7",
                    },
                    {
                        "eye_rank": "4",
                        "player": "Too Short",
                        "book_american_odds": "+320",
                        "model_hr_probability_percent": "20",
                        "edge_percent": "8",
                        "gbm_rank": "12",
                        "pitcher_batter_rank": "2",
                    },
                ],
            )

            paths = build_profit_lenses(board, root / "profit_lenses")

            broad = read_csv(paths["daily_capped_eye_top1"])
            self.assertEqual([row["player"] for row in broad], ["Broad Fit"])

            sharper = read_csv(paths["sharper_pitchfit"])
            self.assertEqual([row["player"] for row in sharper], ["Sharper Fit"])

            combined = read_csv(paths["combined"])
            self.assertEqual({row["player"] for row in combined}, {"Broad Fit", "Sharper Fit"})

    def test_enriches_missing_market_fields_from_input_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            write_csv(
                board,
                [
                    {
                        "eye_rank": "12",
                        "player": "Input Odds Fit",
                        "gbm_rank": "70",
                        "pitcher_batter_rank": "6",
                    }
                ],
            )
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                inputs / "gbm_top80.csv",
                [
                    {
                        "player_name": "Input Odds Fit",
                        "book_american_odds": "+575",
                        "adjusted_hr_probability_percent": "14.5",
                        "edge_percent": "3.0",
                    }
                ],
            )

            paths = build_profit_lenses_from_run(board, inputs, root / "profit_lenses")

            sharper = read_csv(paths["sharper_pitchfit"])
            self.assertEqual(sharper[0]["player"], "Input Odds Fit")
            self.assertEqual(sharper[0]["book_american_odds"], "+575")


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
