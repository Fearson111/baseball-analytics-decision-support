from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from all_seeing_eye.daily_hub import runner
from all_seeing_eye.daily_hub.corrections import apply_correction


class QuickCorrectionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hub = self.root / "hub"
        self.patch = patch.object(runner, "HUB", self.hub)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.day = date.today().isoformat()
        self.base = self.hub / "runs" / self.day / "original"
        self.out = self.base / self.day
        self.out.mkdir(parents=True)
        (self.base / "incoming").mkdir()
        now = datetime.now(timezone.utc)
        self.state = dict(date=self.day, mode="refresh", status="complete", limit=77,
                          output=str(self.out), started=now.isoformat(), confirmed_only=False)
        runner.atomic_json(self.base / "status.json", self.state)
        runner.atomic_json(self.hub / "latest.json", self.state)
        runner.atomic_json(self.hub / "status.json", self.state)
        game = dict(game_id="1", home_abbrev="SEA", away_abbrev="CHC", status="Preview",
                    start_time=(now + timedelta(hours=4)).isoformat())
        runner.atomic_json(self.base / "games.json", [game])
        starters = [dict(game_id="1", player_id="10", team_abbrev="SEA", batting_order=1),
                    dict(game_id="1", player_id="20", team_abbrev="CHC", batting_order=2)]
        runner.atomic_json(self.base / "starters.json", starters)
        rows = [dict(player_name=name, player_id=pid, game_id="1", game_date=self.day,
                     team_abbrev=team, rank=i, regression_rank=i, projection_rank=i,
                     adjusted_hr_probability_percent=20, opposing_pitcher="Pitcher")
                for i, (name, pid, team) in enumerate([("Player One", "10", "SEA"), ("Player Two", "20", "CHC")], 1)]
        for name in runner.INPUTS:
            pd.DataFrame(rows).to_csv(self.base / "incoming" / f"{name}.csv", index=False)
        quotes = [dict(game_id="1", player_key=name, book="draftkings", price=500,
                       updated=now.isoformat(), event_id="event") for name in ("playerone", "playertwo")]
        runner.atomic_json(self.base / "market_quotes.json", quotes)
        market = runner.prepare_market_board(pd.DataFrame(rows), [game], starters, quotes, [], live=True)
        market.to_csv(self.base / "market_board.csv", index=False)
        self.correction = dict(game_id="1", player_id="10", out=True, odds=None, sportsbook="DraftKings")

    def run_correction(self, correction=None, clear=False):
        def score(job, inputs, market):
            self.assertEqual(job.limit, 77)
            path = job.folder / job.day
            path.mkdir()
            return path
        with patch.object(runner.Runner, "score", score), patch.object(runner.Runner, "exports"), \
                patch.object(runner.Runner, "models", side_effect=AssertionError("upstream models called")), \
                patch.object(runner, "fetch_context", side_effect=AssertionError("network called")), \
                patch.object(runner, "fetch_prices", side_effect=AssertionError("odds fetch called")), \
                patch("all_seeing_eye.daily_hub.ledger.capture", side_effect=AssertionError("history changed")):
            return apply_correction(self.out, correction or self.correction, clear=clear)

    def test_scratch_removes_all_model_inputs_and_clear_restores_without_network(self):
        state = self.run_correction()
        folder = Path(state["output"]).parent
        market = pd.read_csv(folder / "market_board.csv")
        self.assertFalse(market.iloc[0].ready)
        for filename in runner.INPUTS.values():
            self.assertEqual(list(pd.read_csv(folder / "inputs" / filename).player_name), ["Player Two"])
        restored = self.run_correction(clear=True)
        restored_folder = Path(restored["output"]).parent
        self.assertTrue(pd.read_csv(restored_folder / "market_board.csv").ready.all())
        self.assertEqual(len(pd.read_csv(restored_folder / "inputs" / runner.INPUTS["gbm"])), 2)
        self.assertEqual(len(pd.read_csv(self.base / "incoming" / "gbm.csv")), 2)

    def test_manual_odds_and_clear_restore_original_quote_and_timestamp(self):
        correction = {**self.correction, "out": False, "odds": 750, "sportsbook": "Fanatics", "updated": "manual"}
        state = self.run_correction(correction)
        row = pd.read_csv(Path(state["output"]).parent / "market_board.csv").iloc[0]
        self.assertEqual(row.book_american_odds, 750)
        self.assertEqual(row.bookmaker_used, "Fanatics")
        self.assertAlmostEqual(row.edge_percent, 20 - 100/8.5)
        state = self.run_correction(clear=True)
        row = pd.read_csv(Path(state["output"]).parent / "market_board.csv").iloc[0]
        self.assertEqual(row.book_american_odds, 500)
        original = pd.read_csv(self.base / "market_board.csv").iloc[0]
        self.assertEqual(row.odds_last_update, original.odds_last_update)

    def test_running_worker_status_not_replaced(self):
        runner.atomic_json(self.hub / "status.json", {"status": "running", "pid": 123})
        self.run_correction()
        self.assertEqual(runner.read_json(self.hub / "status.json"), {"status": "running", "pid": 123})

    def test_failure_retains_latest_snapshot_but_saves_override(self):
        with patch.object(runner.Runner, "assemble", side_effect=ValueError("bad input")):
            with self.assertRaisesRegex(RuntimeError, "previous lists were retained"):
                apply_correction(self.out, self.correction)
        self.assertEqual(runner.read_json(self.hub / "latest.json"), self.state)
        self.assertTrue(runner.read_json(self.hub / "overrides" / f"{self.day}.json")[0]["out"])

    def test_unknown_game_rejected_before_saving(self):
        with self.assertRaisesRegex(ValueError, "not in the latest snapshot"):
            self.run_correction({**self.correction, "game_id": "2"})
        self.assertFalse((self.hub / "overrides" / f"{self.day}.json").exists())

    def test_snapshots_preserve_original_eligibility_time(self):
        state = self.run_correction()
        self.assertEqual(state["market_as_of"], self.state["started"])
        self.assertEqual(runner.read_json(self.base / "status.json"), self.state)

    def test_legacy_snapshot_without_starters_can_rebuild(self):
        (self.base / "starters.json").unlink()
        self.assertEqual(self.run_correction()["status"], "complete")


if __name__ == "__main__":
    unittest.main()
