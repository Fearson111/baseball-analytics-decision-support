import csv
import tempfile
import unittest
from pathlib import Path

from all_seeing_eye.menu import normalize_american_odds, resolve_missing_book_odds


class MissingOddsMenuTests(unittest.TestCase):
    def test_resolve_missing_book_odds_adds_odds_and_removes_outs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            reasoning = root / "all_seeing_eye_reasoning.md"
            write_csv(
                board,
                [
                    base_row("1", "Keep Missing", ""),
                    base_row("2", "Remove Missing", ""),
                    base_row("3", "Already Priced", "+350"),
                ],
            )
            answers = iter(["450", "out"])

            added, removed = resolve_missing_book_odds(board, reasoning, prompt_func=lambda _: next(answers))

            rows = read_csv(board)
            self.assertEqual((added, removed), (1, 1))
            self.assertEqual([row["player"] for row in rows], ["Keep Missing", "Already Priced"])
            self.assertEqual(rows[0]["book_american_odds"], "+450")
            self.assertEqual(rows[0]["bookmaker_used"], "Manual")
            self.assertEqual([row["eye_rank"] for row in rows], ["1", "2"])
            self.assertIn("Keep Missing", reasoning.read_text())
            self.assertNotIn("Remove Missing", reasoning.read_text())

    def test_normalize_american_odds_accepts_common_shapes(self):
        self.assertEqual(normalize_american_odds("450"), "+450")
        self.assertEqual(normalize_american_odds("+450"), "+450")
        self.assertEqual(normalize_american_odds("-120"), "-120")
        self.assertIsNone(normalize_american_odds("out"))


def base_row(rank: str, player: str, odds: str) -> dict[str, str]:
    return {
        "eye_rank": rank,
        "player": player,
        "eye_score": "90",
        "accel_score": "80",
        "game_date": "2026-08-16",
        "player_id": "",
        "team_abbrev": "AAA",
        "opponent_abbrev": "BBB",
        "lineup_status": "",
        "batting_order": "",
        "model_hr_probability_percent": "",
        "model_american_odds": "",
        "bookmaker_used": "",
        "book_american_odds": odds,
        "edge_percent": "",
        "odds_source": "",
        "odds_last_update": "",
        "review_priority": "High",
        "layers_present": "gbm",
        "gbm_rank": rank,
        "gbm_progression_rank": "",
        "sequence_rank": "",
        "pitcher_batter_rank": "",
        "movement_summary": "",
        "reasoning": "test reason",
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
