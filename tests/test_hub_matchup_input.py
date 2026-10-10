import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from all_seeing_eye.daily_hub import runner
from all_seeing_eye.io import load_signal_folder


class MatchupInputTests(unittest.TestCase):
    def test_assemble_keeps_matchup_rank_116_through_150(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = pd.DataFrame([{
                "player_name": "Ben Rice" if rank == 116 else f"Player {rank}",
                "rank": rank, "regression_rank": rank, "projection_rank": rank,
                "game_date": "2026-09-04",
            } for rank in range(1, 161)])
            paths = {}
            for name in runner.INPUTS:
                paths[name] = root / f"{name}.csv"
                source.to_csv(paths[name], index=False)
            market = source.assign(ready=True, start_time="2026-09-04T23:00:00Z",
                                   player_id=[str(n) for n in range(1, 161)])
            job = object.__new__(runner.Runner)
            job.day, job.mode = "2026-09-04", "saved"
            job.confirmed_only = False
            job.folder = root / "run"
            job.folder.mkdir()
            job.state = {}
            job.status = Mock()
            job.warn = Mock()
            with patch.object(runner, "source_paths", return_value=paths), \
                 patch.object(runner, "GBM", root), patch.object(runner, "HUB", root), \
                 patch.object(runner, "prepare_market_board", return_value=market):
                inputs, _, _ = job.assemble()
            matchup = pd.read_csv(inputs / runner.INPUTS["matchup"])
            self.assertEqual(len(matchup), 150)
            self.assertEqual(matchup.loc[matchup.player_name.eq("Ben Rice"), "rank"].iloc[0], 116)
            self.assertEqual(matchup["rank"].max(), 150)
            self.assertEqual(len(pd.read_csv(inputs / runner.INPUTS["gbm"])), 160)
            self.assertEqual(len(pd.read_csv(inputs / runner.INPUTS["regression"])), 160)
            self.assertEqual(len(pd.read_csv(inputs / runner.INPUTS["sequence"])), 150)
            self.assertEqual(len(pd.read_csv(paths["matchup"])), 160)
            boards = load_signal_folder(inputs, required=True)
            rice = next(row for row in boards["pitcher_batter_top80"] if row.player == "Ben Rice")
            self.assertEqual(rice.rank, 116)


if __name__ == "__main__":
    unittest.main()
