import csv
import tempfile
import unittest
from pathlib import Path

from all_seeing_eye.profit_parlays import build_profit_parlays_from_run, build_parlay_history_rows


class ProfitParlayTests(unittest.TestCase):
    def test_builds_active_parlay_from_rank_bands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "12", "player": "Mid A", "pitcher_batter_rank": "4"},
                    {"eye_rank": "18", "player": "Mid B", "pitcher_batter_rank": "5"},
                ],
            )
            write_csv(
                inputs / "gbm_top80.csv",
                [
                    {"player_name": "Mid A", "book_american_odds": "+450"},
                    {"player_name": "Mid B", "book_american_odds": "+600"},
                ],
            )

            paths = build_profit_parlays_from_run(board, inputs, root / "parlays")

            rows = read_csv(paths["mid_board_pitch_11_15_16_20"])
            self.assertEqual(rows[0]["leg1_player"], "Mid A")
            self.assertEqual(rows[0]["leg2_player"], "Mid B")

    def test_builds_rank_one_deep_comp_best_eye_parlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "1", "player": "Anchor", "book_american_odds": "+350"},
                    {"eye_rank": "41", "player": "Deep Best", "book_american_odds": "+550", "sequence_rank": "25", "edge_percent": "1"},
                    {"eye_rank": "45", "player": "Deep Worse", "book_american_odds": "+700", "sequence_rank": "12", "edge_percent": "2"},
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Anchor"}, {"player_name": "Deep Best"}, {"player_name": "Deep Worse"}])

            paths = build_profit_parlays_from_run(board, inputs, root / "parlays")

            rows = read_csv(paths["anchor_deep_comp_best_eye"])
            self.assertEqual(rows[0]["leg1_player"], "Anchor")
            self.assertEqual(rows[0]["leg2_player"], "Deep Best")

    def test_builds_rank_one_pitch15_best_sequence_parlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "1", "player": "Anchor", "book_american_odds": "+350"},
                    {"eye_rank": "20", "player": "Seq Best", "book_american_odds": "+475", "pitcher_batter_rank": "14", "sequence_rank": "3"},
                    {"eye_rank": "12", "player": "Pitch Best", "book_american_odds": "+650", "pitcher_batter_rank": "2", "sequence_rank": "24"},
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Anchor"}, {"player_name": "Seq Best"}, {"player_name": "Pitch Best"}])

            paths = build_profit_parlays_from_run(board, inputs, root / "parlays")

            rows = read_csv(paths["anchor_pitch15_best_sequence"])
            self.assertEqual(rows[0]["leg1_player"], "Anchor")
            self.assertEqual(rows[0]["leg2_player"], "Seq Best")

    def test_builds_rank_one_deep_pitch15_three_leg_parlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "1", "player": "Anchor", "book_american_odds": "+350"},
                    {"eye_rank": "41", "player": "Deep Best", "book_american_odds": "+550", "sequence_rank": "25", "edge_percent": "1"},
                    {"eye_rank": "20", "player": "Seq Best", "book_american_odds": "+475", "pitcher_batter_rank": "14", "sequence_rank": "3"},
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Anchor"}, {"player_name": "Deep Best"}, {"player_name": "Seq Best"}])

            paths = build_profit_parlays_from_run(board, inputs, root / "parlays")

            rows = read_csv(paths["three_leg_anchor_deep_pitch15_sequence"])
            self.assertEqual(rows[0]["leg1_player"], "Anchor")
            self.assertEqual(rows[0]["leg2_player"], "Deep Best")
            self.assertEqual(rows[0]["leg3_player"], "Seq Best")

    def test_builds_mid_pitch_sharper_three_leg_parlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "12", "player": "Mid A", "book_american_odds": "+450", "pitcher_batter_rank": "4"},
                    {"eye_rank": "18", "player": "Mid B", "book_american_odds": "+600", "pitcher_batter_rank": "5"},
                    {"eye_rank": "8", "player": "Sharp C", "book_american_odds": "+540", "gbm_rank": "93", "pitcher_batter_rank": "4"},
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Mid A"}, {"player_name": "Mid B"}, {"player_name": "Sharp C"}])

            paths = build_profit_parlays_from_run(board, inputs, root / "parlays")

            rows = read_csv(paths["three_leg_11_15_16_20_sharper_eye"])
            self.assertEqual(rows[0]["leg1_player"], "Mid A")
            self.assertEqual(rows[0]["leg2_player"], "Mid B")
            self.assertEqual(rows[0]["leg3_player"], "Sharp C")

    def test_history_grades_three_leg_profit(self):
        rows = [
            {
                "game_date": "2026-08-15",
                "eye_rank": "1",
                "player": "Anchor",
                "book_american_odds": "+350",
                "actual_hr": "1",
            },
            {
                "game_date": "2026-08-15",
                "eye_rank": "41",
                "player": "Deep Best",
                "book_american_odds": "+500",
                "sequence_rank": "25",
                "edge_percent": "1",
                "actual_hr": "1",
            },
            {
                "game_date": "2026-08-15",
                "eye_rank": "20",
                "player": "Seq Best",
                "book_american_odds": "+700",
                "pitcher_batter_rank": "14",
                "sequence_rank": "3",
                "actual_hr": "1",
            },
        ]

        history = build_parlay_history_rows(rows)

        row = next(item for item in history if item["parlay"] == "Eye #1 + Deep Comp Best Eye + Pitch<=15 Best Sequence")
        self.assertEqual(row["parlay_result"], "Hit")
        self.assertEqual(row["leg3_player"], "Seq Best")
        self.assertEqual(row["profit_1u"], 215.0)

    def test_history_grades_two_leg_profit(self):
        rows = [
            {
                "game_date": "2026-08-15",
                "eye_rank": "12",
                "player": "Mid A",
                "pitcher_batter_rank": "4",
                "book_american_odds": "+450",
                "actual_hr": "1",
            },
            {
                "game_date": "2026-08-15",
                "eye_rank": "18",
                "player": "Mid B",
                "pitcher_batter_rank": "5",
                "book_american_odds": "+600",
                "actual_hr": "1",
            },
        ]

        history = build_parlay_history_rows(rows)

        row = next(item for item in history if item["parlay"] == "Ranks 11-15 Pitch + Ranks 16-20 Pitch")
        self.assertEqual(row["parlay_result"], "Hit")
        self.assertEqual(row["profit_1u"], 37.5)

    def test_builds_four_leg_mid_pitch_ladder_parlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "12", "player": "Mid A", "book_american_odds": "+450", "pitcher_batter_rank": "4"},
                    {"eye_rank": "18", "player": "Mid B", "book_american_odds": "+600", "pitcher_batter_rank": "5"},
                    {"eye_rank": "22", "player": "Mid C", "book_american_odds": "+650", "pitcher_batter_rank": "6"},
                    {"eye_rank": "8", "player": "Sharp D", "book_american_odds": "+540", "gbm_rank": "93", "pitcher_batter_rank": "4"},
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Mid A"}, {"player_name": "Mid B"}, {"player_name": "Mid C"}, {"player_name": "Sharp D"}])

            paths = build_profit_parlays_from_run(board, inputs, root / "parlays")

            rows = read_csv(paths["four_leg_mid_pitch_ladder_sharper_eye"])
            self.assertEqual(rows[0]["leg1_player"], "Mid A")
            self.assertEqual(rows[0]["leg2_player"], "Mid B")
            self.assertEqual(rows[0]["leg3_player"], "Mid C")
            self.assertEqual(rows[0]["leg4_player"], "Sharp D")

    def test_history_grades_four_leg_profit(self):
        rows = [
            {"game_date": "2026-08-15", "eye_rank": "12", "player": "Mid A", "book_american_odds": "+400", "pitcher_batter_rank": "4", "actual_hr": "1"},
            {"game_date": "2026-08-15", "eye_rank": "18", "player": "Mid B", "book_american_odds": "+500", "pitcher_batter_rank": "5", "actual_hr": "1"},
            {"game_date": "2026-08-15", "eye_rank": "22", "player": "Mid C", "book_american_odds": "+600", "pitcher_batter_rank": "6", "actual_hr": "1"},
            {"game_date": "2026-08-15", "eye_rank": "8", "player": "Sharp D", "book_american_odds": "+700", "gbm_rank": "93", "pitcher_batter_rank": "4", "actual_hr": "1"},
        ]

        history = build_parlay_history_rows(rows)

        row = next(item for item in history if item["parlay"] == "Ranks 11-15 Pitch + Ranks 16-20 Pitch + Ranks 21-25 Pitch + Sharper Best Eye")
        self.assertEqual(row["parlay_result"], "Hit")
        self.assertEqual(row["leg4_player"], "Sharp D")
        self.assertEqual(row["profit_1u"], 1679.0)


    def test_builds_movement_progression_pitch_sequence_parlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "8", "player": "Prog Jump", "book_american_odds": "+450", "movement_summary": "GBM Progression Top 80 accelerated from rank 92 to 44"},
                    {"eye_rank": "14", "player": "Burst Jump", "book_american_odds": "+575", "movement_summary": "Pitcher/Batter Top 80 accelerated from rank 70 to 20"},
                    {"eye_rank": "18", "player": "Other", "book_american_odds": "+500", "movement_summary": "GBM Top 80 accelerated from rank 80 to 70"},
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Prog Jump"}, {"player_name": "Burst Jump"}, {"player_name": "Other"}])

            paths = build_profit_parlays_from_run(board, inputs, root / "parlays")

            rows = read_csv(paths["movement_progression_pitch_sequence_burst"])
            self.assertEqual(rows[0]["leg1_player"], "Prog Jump")
            self.assertEqual(rows[0]["leg2_player"], "Burst Jump")

    def test_builds_three_leg_best_movement_sequence_parlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "6", "player": "Move A", "book_american_odds": "+500", "movement_summary": "GBM Top 80 accelerated from rank 160 to 70; Sequence Top 150 accelerated from rank 120 to 70"},
                    {"eye_rank": "9", "player": "Move B", "book_american_odds": "+550", "movement_summary": "Pitcher/Batter Top 80 accelerated from rank 85 to 15; GBM Progression Top 80 accelerated from rank 90 to 55"},
                    {"eye_rank": "22", "player": "Seq C", "book_american_odds": "+600", "movement_summary": "Sequence Top 150 accelerated from rank 130 to 35"},
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Move A"}, {"player_name": "Move B"}, {"player_name": "Seq C"}])

            paths = build_profit_parlays_from_run(board, inputs, root / "parlays")

            rows = read_csv(paths["movement_best_best_sequence_accel"])
            self.assertEqual(rows[0]["leg1_player"], "Move A")
            self.assertEqual(rows[0]["leg2_player"], "Move B")
            self.assertEqual(rows[0]["leg3_player"], "Seq C")

    def test_history_grades_movement_eye_riser_parlay(self):
        rows = [
            {"game_date": "2026-08-14", "eye_rank": "20", "player": "Eye Pop", "book_american_odds": "", "gbm_rank": "120", "actual_hr": "0", "movement_summary": ""},
            {"game_date": "2026-08-14", "eye_rank": "30", "player": "GBM Jump", "book_american_odds": "", "gbm_rank": "155", "actual_hr": "0", "movement_summary": ""},
            {"game_date": "2026-08-15", "eye_rank": "11", "player": "GBM Jump", "book_american_odds": "+500", "gbm_rank": "88", "actual_hr": "1", "movement_summary": "GBM Top 80 accelerated from rank 155 to 88"},
            {"game_date": "2026-08-15", "eye_rank": "5", "player": "Eye Pop", "book_american_odds": "+600", "gbm_rank": "110", "actual_hr": "1", "movement_summary": "Sequence Top 150 accelerated from rank 120 to 80"},
        ]

        history = build_parlay_history_rows(rows)

        row = next(item for item in history if item["parlay"] == "Movement: GBM Accel + Eye Riser")
        self.assertEqual(row["parlay_result"], "Hit")
        self.assertEqual(row["leg1_player"], "GBM Jump")
        self.assertEqual(row["leg2_player"], "Eye Pop")
        self.assertEqual(row["profit_1u"], 41.0)


    def test_builds_reinforced_basket_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "35", "player": "Deep Elite", "book_american_odds": "+250", "gbm_rank": "7", "sequence_rank": "11", "pitcher_batter_rank": "16"},
                    {"eye_rank": "6", "player": "Prog A", "book_american_odds": "+430", "gbm_progression_rank": "8"},
                    {"eye_rank": "7", "player": "Prog B", "book_american_odds": "+440", "gbm_progression_rank": "6"},
                    {"eye_rank": "25", "player": "Prog C", "book_american_odds": "+420", "gbm_progression_rank": "4"},
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Deep Elite"}, {"player_name": "Prog A"}, {"player_name": "Prog B"}, {"player_name": "Prog C"}])

            paths = build_profit_parlays_from_run(board, inputs, root / "parlays")

            rows = read_csv(paths["reinforced_deep_3model_elite_top3_progression_top10"])
            self.assertEqual(len(rows), 3)
            self.assertEqual({row["leg1_player"] for row in rows}, {"Deep Elite"})
            self.assertEqual([row["leg2_player"] for row in rows], ["Prog A", "Prog B", "Prog C"])


    def test_low_odds_two_leg_is_no_play_in_active_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "all_seeing_eye_board.csv"
            inputs = root / "inputs"
            inputs.mkdir()
            write_csv(
                board,
                [
                    {"eye_rank": "12", "player": "Short A", "pitcher_batter_rank": "4", "book_american_odds": "+150"},
                    {"eye_rank": "18", "player": "Short B", "pitcher_batter_rank": "5", "book_american_odds": "+150"},
                ],
            )
            write_csv(inputs / "gbm_top80.csv", [{"player_name": "Short A"}, {"player_name": "Short B"}])

            paths = build_profit_parlays_from_run(board, inputs, root / "parlays")

            rows = read_csv(paths["mid_board_pitch_11_15_16_20"])
            self.assertEqual(rows, [])

    def test_low_odds_two_leg_is_no_play_in_history(self):
        rows = [
            {
                "game_date": "2026-08-15",
                "eye_rank": "12",
                "player": "Short A",
                "pitcher_batter_rank": "4",
                "book_american_odds": "+150",
                "actual_hr": "1",
            },
            {
                "game_date": "2026-08-15",
                "eye_rank": "18",
                "player": "Short B",
                "pitcher_batter_rank": "5",
                "book_american_odds": "+150",
                "actual_hr": "1",
            },
        ]

        history = build_parlay_history_rows(rows)

        self.assertFalse(
            any(item["parlay"] == "Ranks 11-15 Pitch + Ranks 16-20 Pitch" for item in history)
        )


    def test_history_voids_parlay_ticket_with_scratched_leg_without_replacement(self):
        rows = [
            {
                "game_date": "2026-08-15",
                "eye_rank": "12",
                "player": "Scratched Mid",
                "book_american_odds": "+400",
                "pitcher_batter_rank": "4",
                "result": "Void",
                "is_void": "1",
                "actual_hr": "",
            },
            {
                "game_date": "2026-08-15",
                "eye_rank": "18",
                "player": "Mid B",
                "book_american_odds": "+500",
                "pitcher_batter_rank": "5",
                "actual_hr": "1",
            },
            {
                "game_date": "2026-08-15",
                "eye_rank": "19",
                "player": "Replacement Mid",
                "book_american_odds": "+600",
                "pitcher_batter_rank": "6",
                "actual_hr": "1",
            },
        ]

        history = build_parlay_history_rows(rows)

        self.assertFalse(
            any(item["parlay"] == "Ranks 11-15 Pitch + Ranks 16-20 Pitch" for item in history)
        )


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
