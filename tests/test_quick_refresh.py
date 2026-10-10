from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from all_seeing_eye.daily_hub import public_odds, runner


class QuickRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hub = self.root / "DAILY_BASEBALL"
        for name, value in (("ROOT", self.root), ("HUB", self.hub)):
            mocked = patch.object(runner, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.day = date.today().isoformat()
        self.now = datetime.now(timezone.utc)
        self.base = self.hub / "runs" / self.day / "original"
        (self.base / "incoming").mkdir(parents=True)
        (self.base / self.day).mkdir()
        self.state = dict(date=self.day, run_id="original", mode="full", status="complete",
                          started=(self.now - timedelta(hours=2)).isoformat(),
                          finished=(self.now - timedelta(hours=1)).isoformat(),
                          output=str(self.base / self.day))
        runner.atomic_json(self.base / "status.json", self.state)
        runner.atomic_json(self.hub / "latest.json", self.state)
        self.games = [dict(game_id="1", home_abbrev="SEA", away_abbrev="CHC", status="Preview",
                           start_time=(self.now + timedelta(hours=2)).isoformat())]
        self.starters = [dict(game_id="1", player_id="10", team_abbrev="SEA", batting_order=2)]
        rows = [dict(player_name=name, player_id=pid, game_id="1", game_date=self.day,
                     team_abbrev="SEA", rank=i, regression_rank=i, projection_rank=i,
                     adjusted_hr_probability_percent=20, opposing_pitcher="Pitcher",
                     lineup_status="not_confirmed", book_american_odds=500)
                for i, (name, pid) in enumerate((("Player One", "10"), ("Player Two", "20")), 1)]
        for name in runner.INPUTS:
            pd.DataFrame(rows).to_csv(self.base / "incoming" / f"{name}.csv", index=False)
        self.prices = [dict(game_id="1", player_key="playerone", player_name="Player One", book="draftkings", price=750,
                            updated=self.now.isoformat(), event_id="event")]

    def refresh(self, run_id="refresh"):
        def score(job, inputs, market):
            out = job.folder / job.day
            out.mkdir()
            return out

        with patch.dict("os.environ", DAILY_BASEBALL_ODDS_PROVIDER="public_comparison"), \
                patch.object(runner.Runner, "models", side_effect=AssertionError("Models reran")) as models, \
                patch.object(runner.Runner, "previous_results", side_effect=AssertionError("History reran")), \
                patch.object(runner, "source_paths", side_effect=AssertionError("Mutable upstream files used")), \
                patch.object(runner, "fetch_context", return_value=(self.games, self.starters)) as context, \
                patch.object(public_odds, "fetch_prices", return_value=(self.prices, [])) as prices, \
                patch.object(runner.Runner, "score", score), \
                patch.object(runner.Runner, "exports") as exports, \
                patch.object(runner.Runner, "publish"):
            job = runner.Runner(self.day, run_id, "refresh", confirmed_only=True)
            job.run()
        models.assert_not_called()
        return job, context, prices, exports

    def test_refresh_reuses_raw_inputs_but_updates_lineups_prices_and_exports(self):
        originals = {name: (self.base / "incoming" / f"{name}.csv").read_bytes() for name in runner.INPUTS}
        job, context, prices, exports = self.refresh()
        self.assertEqual(job.state["status"], "complete", job.state.get("error"))
        context.assert_called_once_with(self.day)
        prices.assert_called_once()
        exports.assert_called_once()
        self.assertEqual(job.state["base_run"], str(self.base))
        self.assertEqual(job.state["model_inputs_as_of"], self.state["finished"])
        self.assertGreater(job.state["market_as_of"], self.state["finished"])
        for name, raw in originals.items():
            self.assertEqual((job.folder / "incoming" / f"{name}.csv").read_bytes(), raw)
            self.assertEqual((self.base / "incoming" / f"{name}.csv").read_bytes(), raw)
            frame = pd.read_csv(job.folder / "inputs" / runner.INPUTS[name])
            self.assertEqual(frame.player_name.tolist(), ["Player One"])
            self.assertEqual(frame.book_american_odds.iloc[0], 750)
        market = pd.read_csv(job.folder / "market_board.csv")
        self.assertEqual(market.lineup_status.tolist(), ["confirmed", "out"])
        self.assertEqual(market.ready.tolist(), [True, False])
        self.assertAlmostEqual(market.edge_percent.iloc[0], 20 - 100 / 8.5)

    def test_missing_prices_are_not_carried_forward(self):
        self.prices = []
        job, _, _, _ = self.refresh()
        self.assertEqual(job.state["status"], "complete", job.state.get("error"))
        market = pd.read_csv(job.folder / "market_board.csv")
        self.assertTrue(market.book_american_odds.isna().all())
        self.assertFalse(market.ready.any())

    def test_lineup_timeout_retries_then_uses_explicit_empty_same_day_file(self):
        gbm = self.root / "Homerun_Predictor"
        with patch.object(runner, "GBM", gbm):
            job = runner.Runner(self.day, "lineup-fallback", "full")
            with patch.object(job, "command", side_effect=RuntimeError("lineup feed timed out")) as command:
                job.lineups()
        self.assertEqual(command.call_count, 3)
        output = gbm / "data/raw/daily" / f"lineups_{self.day}.csv"
        self.assertTrue(output.exists())
        self.assertEqual(pd.read_csv(output).columns.tolist(), [
            "game_id", "home_away", "team_id", "team", "team_abbrev", "player_id",
            "player_name", "batting_order", "lineup_position", "lineup_status"])
        self.assertEqual(job.state["stages"]["pull daily lineups"], "unavailable")
        self.assertIn("continuing with unconfirmed lineups", job.state["warnings"][0])

    def test_started_games_are_not_ready(self):
        self.games[0]["status"] = "Live"
        job, _, _, _ = self.refresh()
        self.assertEqual(job.state["status"], "complete", job.state.get("error"))
        self.assertFalse(pd.read_csv(job.folder / "market_board.csv").ready.any())

    def test_warmup_keeps_odds_on_gbm_and_regression_boards(self):
        self.games[0].update(status="Live", detailed_status="Warmup")
        job, _, _, _ = self.refresh()
        self.assertEqual(job.state["status"], "complete", job.state.get("error"))
        self.assertTrue(pd.read_csv(job.folder / "market_board.csv").ready.iloc[0])
        for name in ("gbm", "regression"):
            row = pd.read_csv(job.folder / f"{name}_full.csv").iloc[0]
            self.assertEqual(row.book_american_odds, 750)

    def test_manual_corrections_remain_in_effect(self):
        runner.atomic_json(self.hub / "overrides" / f"{self.day}.json", [
            dict(game_id="1", player_id="10", odds=600, sportsbook="Manual", updated=self.now.isoformat())])
        job, _, _, _ = self.refresh()
        self.assertEqual(job.state["status"], "complete", job.state.get("error"))
        row = pd.read_csv(job.folder / "market_board.csv").iloc[0]
        self.assertEqual(row.book_american_odds, 600)
        self.assertEqual(row.odds_source, "manual")

    def test_repeated_refresh_keeps_original_model_age_and_can_restore_starter(self):
        first, _, _, _ = self.refresh("first")
        self.starters.append(dict(game_id="1", player_id="20", team_abbrev="SEA", batting_order=3))
        second, _, _, _ = self.refresh("second")
        self.assertEqual(second.state["status"], "complete", second.state.get("error"))
        self.assertEqual(second.state["base_run"], str(first.folder))
        self.assertEqual(second.state["model_inputs_as_of"], self.state["finished"])
        self.assertEqual(len(pd.read_csv(second.folder / "inputs" / runner.INPUTS["gbm"])), 2)

    def test_saved_or_previous_day_snapshot_cannot_seed_live_refresh(self):
        for changes in ({"mode": "saved"}, {"date": "2000-01-01"}, {"status": "failed"}):
            with self.subTest(changes=changes):
                runner.atomic_json(self.base / "status.json", {**self.state, **changes})
                job, context, prices, exports = self.refresh(str(len(changes)) + str(next(iter(changes))))
                self.assertEqual(job.state["status"], "failed")
                self.assertIn("Run Daily Predictions first", job.state["error"])
                context.assert_not_called()
                prices.assert_not_called()
                exports.assert_not_called()
        self.assertEqual(runner.read_json(self.hub / "latest.json"), self.state)

    def test_incomplete_latest_inputs_fail_without_falling_back(self):
        (self.base / "incoming" / "sequence.csv").unlink()
        job, context, _, _ = self.refresh()
        self.assertEqual(job.state["status"], "failed")
        self.assertIn("incomplete model inputs", job.state["error"])
        context.assert_not_called()
        self.assertEqual(runner.read_json(self.hub / "latest.json"), self.state)

    def test_wrong_date_in_cached_csv_fails_before_market_fetch(self):
        path = self.base / "incoming" / "gbm.csv"
        frame = pd.read_csv(path)
        frame["game_date"] = "2000-01-01"
        frame.to_csv(path, index=False)
        job, context, _, _ = self.refresh()
        self.assertEqual(job.state["status"], "failed")
        self.assertIn("different date", job.state["error"])
        context.assert_not_called()

    def test_full_prediction_run_still_runs_models_and_previous_results(self):
        with patch.object(runner.Runner, "models") as models, \
                patch.object(runner.Runner, "previous_results") as previous, \
                patch.object(runner.Runner, "reuse_model_inputs") as reuse, \
                patch.object(runner.Runner, "build_snapshot") as build:
            job = runner.Runner(self.day, "full", "full")
            job.run()
        models.assert_called_once()
        previous.assert_called_once()
        build.assert_called_once()
        reuse.assert_not_called()


if __name__ == "__main__":
    unittest.main()
