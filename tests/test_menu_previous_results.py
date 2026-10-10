import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from all_seeing_eye.menu import auto_update_previous_results


class PreviousResultsPreflightTests(unittest.TestCase):
    def test_skips_when_yesterday_board_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch("all_seeing_eye.menu.refresh_completed_results") as refresh, patch(
                "all_seeing_eye.menu.run_rank_tracker"
            ) as tracker:
                result = auto_update_previous_results(
                    board_root=root / "MODEL4_DAILY_READS",
                    input_root=root / "inputs",
                    output_folder=root / "tracking",
                    results_dir=root / "results",
                    statcast_dir=root / "statcast",
                    target_date=date(2026, 8, 15),
                )

            self.assertFalse(result)
            refresh.assert_not_called()
            tracker.assert_not_called()

    def test_refreshes_yesterday_then_rebuilds_full_tracker_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board_root = root / "MODEL4_DAILY_READS"
            board_dir = board_root / "2026-08-15"
            board_dir.mkdir(parents=True)
            (board_dir / "MODEL4_2026-08-15_BOARD.csv").write_text("eye_rank,player\n1,Player A\n")
            fake_outputs = SimpleNamespace(graded_rows=420, graded_days=55)

            with patch("all_seeing_eye.menu.refresh_completed_results", return_value=[date(2026, 8, 15)]) as refresh, patch(
                "all_seeing_eye.menu.run_rank_tracker", return_value=fake_outputs
            ) as tracker:
                result = auto_update_previous_results(
                    board_root=board_root,
                    input_root=root / "inputs",
                    output_folder=root / "tracking",
                    results_dir=root / "results",
                    statcast_dir=root / "statcast",
                    target_date=date(2026, 8, 15),
                )

            self.assertTrue(result)
            refresh.assert_called_once_with(board_root, start_date=date(2026, 8, 15), end_date=date(2026, 8, 15))
            tracker.assert_called_once()
            _, kwargs = tracker.call_args
            self.assertNotIn("start_date", kwargs)
            self.assertNotIn("end_date", kwargs)
            self.assertEqual(kwargs["board_root"], board_root)
            self.assertEqual(kwargs["output_folder"], root / "tracking")

    def test_preflight_failure_does_not_block_today_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board_root = root / "MODEL4_DAILY_READS"
            board_dir = board_root / "2026-08-15"
            board_dir.mkdir(parents=True)
            (board_dir / "MODEL4_2026-08-15_BOARD.csv").write_text("eye_rank,player\n1,Player A\n")

            with patch("all_seeing_eye.menu.refresh_completed_results", side_effect=RuntimeError("boom")):
                result = auto_update_previous_results(
                    board_root=board_root,
                    input_root=root / "inputs",
                    output_folder=root / "tracking",
                    results_dir=root / "results",
                    statcast_dir=root / "statcast",
                    target_date=date(2026, 8, 15),
                )

            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
