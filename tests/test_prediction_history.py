from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from all_seeing_eye.daily_hub.prediction_history import identify, retain_day


def external_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PredictionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.games = [dict(game_id="1", start_time="2026-09-11T17:00:00Z"),
                      dict(game_id="2", start_time="2026-09-12T01:00:00Z")]

    def frames(self, rows):
        return {m: pd.DataFrame(rows) for m in ("gbm", "regression", "sequence", "matchup")}

    def saved(self, name, rows, stamp):
        folder = self.root / name
        (folder / "incoming").mkdir(parents=True)
        (folder / "status.json").write_text(json.dumps(dict(status="complete", mode="full", finished=stamp)))
        (folder / "games.json").write_text(json.dumps(self.games))
        for model, frame in self.frames(rows).items():
            frame.to_csv(folder / "incoming" / f"{model}.csv", index=False)

    def test_finished_game_preserved_in_all_four_models_without_postgame_rescoring(self):
        early = dict(player_name="Early", player_id="11", game_id="1", score=60, rank=1)
        late = dict(player_name="Late", player_id="22", game_id="2", score=50, rank=2)
        self.saved("morning", [early, late], "2026-09-11T14:00:00Z")
        current = self.frames([{**early, "score": 999}, {**late, "score": 55}])
        result = retain_day(self.root, self.root / "current", current, self.games, "2026-09-11T22:00:00Z")
        for frame in result.values():
            self.assertEqual(set(frame.player_name), {"Early", "Late"})
            self.assertEqual(float(frame.set_index("player_name").loc["Early", "score"]), 60)
            self.assertEqual(float(frame.set_index("player_name").loc["Late", "score"]), 55)

    def test_missing_early_rows_recovered_and_future_runs_excluded(self):
        early = dict(player_name="Early", player_id="11", game_id="1", score=60, rank=1)
        late = dict(player_name="Late", player_id="22", game_id="2", score=50, rank=2)
        self.saved("morning", [early, late], "2026-09-11T14:00:00Z")
        self.saved("future", [{**late, "score": 999}], "2026-09-11T23:00:00Z")
        result = retain_day(self.root, self.root / "current", self.frames([late]), self.games,
                            "2026-09-11T22:00:00Z", cutoff="2026-09-11T22:00:00Z")
        self.assertEqual(result["matchup"].score.astype(float).tolist(), [60, 50])

    def test_doubleheader_ambiguous_rows_are_not_assigned_to_wrong_game(self):
        rows = pd.DataFrame([dict(player_name="Same Player", game_id="1", player_id="11"),
                             dict(player_name="Same Player", game_id="2", player_id="11")])
        frame = identify(pd.DataFrame([dict(player_name="Same Player")]), rows, self.games)
        self.assertNotIn("game_id", frame.columns)
        exact = identify(rows, rows, self.games)
        self.assertEqual(exact.game_id.tolist(), ["1", "2"])

    def test_legacy_matchup_rows_use_earlier_gbm_identity_after_that_game_disappears(self):
        early = dict(player_name="Early", player_id="11", game_id="1", score=60, rank=1)
        late = dict(player_name="Late", player_id="22", game_id="2", score=50, rank=2)
        self.saved("morning", [early, late], "2026-09-11T14:00:00Z")
        current = self.frames([late])
        current["matchup"] = pd.DataFrame([dict(player_name="Early", score=999, rank=1), late])
        result = retain_day(self.root, self.root / "current", current, self.games, "2026-09-11T22:00:00Z")
        early_rows = result["matchup"].query("player_name == 'Early'")
        self.assertEqual(len(early_rows), 1)
        self.assertEqual(float(early_rows.score.iloc[0]), 60)


class UpstreamHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from all_seeing_eye.paths import GBM, MATCHUP
        cls.matchup_root = MATCHUP
        if not (MATCHUP / "scripts/daily_board_history.py").exists() or not (GBM / "scripts/projection_history.py").exists():
            raise unittest.SkipTest("Linked upstream model repositories are not installed")
        cls.matchup = external_module("daily_board_history", MATCHUP / "scripts/daily_board_history.py")
        cls.gbm = external_module("projection_history", GBM / "scripts/projection_history.py")

    def test_matchup_normalization_does_not_change_when_other_players_leave(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reference.json"
            initial = self.matchup.daily_zscore(pd.Series([1., 5., 9.]), path, "power")
            frozen = path.read_bytes()
            later = self.matchup.daily_zscore(pd.Series([5.]), path, "power")
            self.assertEqual(initial.iloc[1], later.iloc[0])
            self.assertEqual(path.read_bytes(), frozen)
            changed = self.matchup.daily_zscore(pd.Series([6.]), path, "power")
            self.assertGreater(changed.iloc[0], later.iloc[0])

    def test_lineup_parser_excludes_substitutes(self):
        module = external_module("matchup_daily_menu", self.matchup_root / "scripts/daily_optimizer_menu.py")
        self.assertEqual(module.parse_batting_order("100"), 1)
        self.assertEqual(module.parse_batting_order("900"), 9)
        self.assertIsNone(module.parse_batting_order("101"))
        self.assertIsNone(module.parse_batting_order("902"))

    def test_gbm_and_regression_freeze_finished_rows_and_keep_full_slate_ranks(self):
        with tempfile.TemporaryDirectory() as folder:
            schedule = pd.DataFrame([dict(game_id=1, status="Scheduled", start_time="2026-09-11T17:00:00Z"),
                                     dict(game_id=2, status="Scheduled", start_time="2026-09-12T01:00:00Z")])
            rows = pd.DataFrame([dict(game_id=1, player_id=11, score=60), dict(game_id=2, player_id=22, score=50)])
            path = Path(folder) / "board.csv"
            self.gbm.save_projection(rows, path, schedule, "score", "rank", datetime(2026, 9, 11, 14, tzinfo=timezone.utc))
            schedule.loc[0, "status"] = "Final"
            late = self.gbm.save_projection(rows.iloc[1:], path, schedule, "score", "rank",
                                            datetime(2026, 9, 11, 22, tzinfo=timezone.utc))
            self.assertEqual(late.player_id.tolist(), [11, 22])
            self.assertEqual(late["rank"].tolist(), [1, 2])
            self.assertEqual(len(list((path.parent / "snapshots" / path.stem).glob("*.csv"))), 3)

    def test_matchup_keeps_finished_rows_and_does_not_add_postgame_predictions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "board.csv"
            early = dict(player_name="Early", game_id="1", player_id=11, team_abbrev="A", opponent_abbrev="B",
                         game_status="Scheduled", start_time="2026-09-11T17:00:00Z", score=60)
            self.matchup.save_board(pd.DataFrame([early]), path, datetime(2026, 9, 11, 14, tzinfo=timezone.utc))
            later = self.matchup.save_board(pd.DataFrame([{**early, "score": 999, "game_status": "Final"},
                                           {**early, "player_name": "Substitute", "game_status": "Final"}]), path,
                                            datetime(2026, 9, 11, 22, tzinfo=timezone.utc))
            self.assertEqual(later.player_name.tolist(), ["Early"])
            self.assertEqual(float(later.score.iloc[0]), 60)


if __name__ == "__main__":
    unittest.main()
