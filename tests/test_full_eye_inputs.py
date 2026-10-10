from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from all_seeing_eye.cli import main as score_main
from all_seeing_eye.daily_hub import runner
from all_seeing_eye.io import load_signal_folder, merge_player_signals, player_key
from all_seeing_eye.scoring import score_player


class FullEyeInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hub = self.root / "hub"
        for name, value in (("ROOT", self.root), ("HUB", self.hub)):
            mocked = patch.object(runner, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.day = date.today().isoformat()
        now = datetime.now(timezone.utc)
        self.base = self.hub / "runs" / self.day / "original"
        (self.base / "incoming").mkdir(parents=True)
        runner.atomic_json(self.base / "status.json", dict(
            date=self.day, status="complete", mode="full", started=now.isoformat(),
            market_as_of=now.isoformat(), model_inputs_as_of=now.isoformat()))
        runner.atomic_json(self.base / "games.json", [dict(
            game_id="1", home_abbrev="SEA", away_abbrev="CHC", status="Preview",
            start_time=(now + timedelta(hours=4)).isoformat())])
        runner.atomic_json(self.base / "starters.json", [])
        runner.atomic_json(self.base / "market_quotes.json", [])
        for name, count in (("gbm", 350), ("regression", 220), ("sequence", 170), ("matchup", 185)):
            rows = [dict(player_name=f"Player {i}", player_id=str(i), game_id="1",
                         game_date=self.day, team_abbrev="SEA", opposing_pitcher="Pitcher",
                         **{("regression_rank" if name == "regression" else
                             "projection_rank" if name == "sequence" else "rank"): i},
                         adjusted_hr_probability_percent=30 - i * .01,
                         positive_regression_score=400 - i, hr_probability=.3 - i * .0001,
                         score=400 - i) for i in range(1, count + 1)]
            pd.DataFrame(rows).to_csv(self.base / "incoming" / f"{name}.csv", index=False)

    def test_full_lists_reach_scorer_with_original_ranks_and_output_limit_is_separate(self):
        job = runner.Runner(self.day, "uncapped", "correction", limit=20)
        job.base_folder = self.base
        with patch.object(runner, "fetch_context", side_effect=AssertionError("network called")):
            inputs, _, _ = job.assemble()
        self.assertEqual(job.state["eye_input_rows"], dict(gbm=350, regression=220, sequence=150, matchup=150))
        boards = load_signal_folder(inputs, required=True)
        players = merge_player_signals(boards)
        self.assertEqual(players[player_key("Player 350")].entries["gbm_top80"].rank, 350)
        self.assertEqual(players[player_key("Player 220")].entries["gbm_progression_top80"].rank, 220)
        tail = score_player(players[player_key("Player 220")])
        self.assertEqual(tail.ranks["gbm_top80"], 220)
        self.assertEqual(tail.ranks["gbm_progression_top80"], 220)
        self.assertIn("gbm", tail.layers_present)
        capped = {name: entries[:80] if name.startswith("gbm") else entries for name, entries in boards.items()}
        old = merge_player_signals(capped)
        self.assertNotIn(player_key("Player 220"), old)
        self.assertNotEqual(score_player(players[player_key("Player 100")]).eye_score,
                            score_player(old[player_key("Player 100")]).eye_score)
        out = job.folder / "test_score"
        score_main(["--today", str(inputs), "--out", str(out), "--limit", "350"])
        result = pd.read_csv(out / "all_seeing_eye_board.csv")
        self.assertEqual(len(result), 350)
        self.assertEqual(result.loc[result.player.eq("Player 350"), "gbm_rank"].item(), 350)
        score_main(["--today", str(inputs), "--out", str(out), "--limit", "20"])
        self.assertEqual(len(pd.read_csv(out / "all_seeing_eye_board.csv")), 20)
        self.assertEqual(len(pd.read_csv(inputs / runner.INPUTS["gbm"])), 350)

    def test_scratch_filter_still_applies_without_compressing_remaining_ranks(self):
        runner.atomic_json(self.hub / "overrides" / f"{self.day}.json", [
            dict(game_id="1", player_id="100", out=True)])
        job = runner.Runner(self.day, "scratch", "correction")
        job.base_folder = self.base
        inputs, _, _ = job.assemble()
        boards = load_signal_folder(inputs, required=True)
        self.assertEqual(len(boards["gbm_top80"]), 349)
        self.assertEqual(len(boards["gbm_progression_top80"]), 219)
        for name in ("gbm_top80", "gbm_progression_top80"):
            entries = {e.player: e.rank for e in boards[name]}
            self.assertNotIn("Player 100", entries)
            self.assertEqual(entries["Player 101"], 101)


class FullStateInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "manual_20260911_hub"
        self.target = self.root / "history_copy"
        self.runs = self.root / "runs" / "2026-09-11"
        self.run = self.runs / "original"
        self.source.mkdir()
        self.target.mkdir()
        (self.run / "inputs").mkdir(parents=True)
        runner.atomic_json(self.run / "status.json", {"status": "complete"})
        self.originals = {}
        for name, filename in runner.INPUTS.items():
            frame = pd.DataFrame({"player": [f"Player {i}" for i in range(1, 221)], "rank": range(1, 221)})
            frame.to_csv(self.run / f"{name}_full.csv", index=False)
            archived = frame.head(80 if name in {"gbm", "regression"} else 150)
            archived.to_csv(self.source / filename, index=False)
            archived.to_csv(self.run / "inputs" / filename, index=False)
            self.originals[filename] = (self.source / filename).read_bytes()

    def test_expands_only_exact_snapshot_and_preserves_all_original_archives(self):
        paths = runner.copy_state_inputs(self.source, self.target, self.runs)
        for name, filename in runner.INPUTS.items():
            self.assertEqual((self.source / filename).read_bytes(), self.originals[filename])
            self.assertEqual((self.run / "inputs" / filename).read_bytes(), self.originals[filename])
            if name in {"gbm", "regression"}:
                self.assertEqual(len(pd.read_csv(self.target / filename)), 220)
                self.assertEqual(paths[name], str(self.run / f"{name}_full.csv"))
            else:
                self.assertEqual((self.target / filename).read_bytes(), self.originals[filename])

    def test_different_intraday_snapshot_cannot_replace_history(self):
        (self.run / "inputs" / runner.INPUTS["sequence"]).write_text("player,rank\nChanged,1\n")
        runner.copy_state_inputs(self.source, self.target, self.runs)
        for filename in runner.INPUTS.values():
            self.assertEqual((self.target / filename).read_bytes(), self.originals[filename])

    def test_missing_run_leaves_manual_inputs_intact(self):
        runner.copy_state_inputs(self.source, self.target, self.root / "missing")
        for filename in runner.INPUTS.values():
            self.assertEqual((self.target / filename).read_bytes(), self.originals[filename])

    def test_finder_metadata_and_other_files_are_not_treated_as_runs(self):
        (self.runs / ".DS_Store").write_bytes(b"Finder metadata")
        (self.runs / "000_notes.txt").write_text("Not a run")
        with patch.object(runner, "read_json", wraps=runner.read_json) as read:
            paths = runner.copy_state_inputs(self.source, self.target, self.runs)
        self.assertEqual([call.args[0] for call in read.call_args_list], [self.run / "status.json"])
        self.assertEqual(paths["gbm"], str(self.run / "gbm_full.csv"))
        self.assertEqual(len(pd.read_csv(self.target / runner.INPUTS["gbm"])), 220)
        self.assertTrue((self.runs / ".DS_Store").is_file())

    def test_json_reader_tolerates_non_directory_parent_or_directory_file(self):
        metadata = self.runs / ".DS_Store"
        metadata.write_bytes(b"Finder metadata")
        self.assertEqual(runner.read_json(metadata / "status.json"), {})
        self.assertEqual(runner.read_json(metadata / "status.json", default=[]), [])
        self.assertEqual(runner.read_json(self.run), {})

    def test_full_output_must_have_exact_archived_prefix(self):
        full = self.run / "gbm_full.csv"
        frame = pd.read_csv(full)
        frame.loc[0, "rank"] = 99
        frame.to_csv(full, index=False)
        runner.copy_state_inputs(self.source, self.target, self.runs)
        filename = runner.INPUTS["gbm"]
        self.assertEqual((self.target / filename).read_bytes(), self.originals[filename])
        self.assertEqual(len(pd.read_csv(self.target / runner.INPUTS["regression"])), 220)

    def test_failed_run_cannot_supply_history(self):
        runner.atomic_json(self.run / "status.json", {"status": "failed"})
        runner.copy_state_inputs(self.source, self.target, self.runs)
        for filename in runner.INPUTS.values():
            self.assertEqual((self.target / filename).read_bytes(), self.originals[filename])


if __name__ == "__main__":
    unittest.main()
