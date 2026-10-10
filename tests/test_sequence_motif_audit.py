import unittest

import numpy as np
import pandas as pd

from scripts.sequence_motif_audit import (
    TARGET, bh, block_interval, composition_key, guarded_excess, unique_game_rows, validate_forecast_alignment,
)


class SequenceMotifAuditTests(unittest.TestCase):
    def test_bh_restores_original_order(self):
        np.testing.assert_allclose(bh([.04, .001, .02]), [.04, .003, .03])

    def test_empty_bootstrap_samples_are_not_zero_outcomes(self):
        ci = block_interval([1., 1.], pd.to_datetime(["2026-07-01", "2026-09-01"]), reps=2000)
        self.assertEqual(ci["low"], 1.)
        self.assertEqual(ci["high"], 1.)

    def test_rare_zero_hits_do_not_create_certain_negative_edge(self):
        ci = guarded_excess([0, 0], .1, ["2026-08-25"]*2, [1, 2], reps=1000)
        self.assertGreater(ci["high"], 0)
        self.assertEqual(ci["p_two_sided"], 1)
        self.assertFalse(ci["eligible"])

    def test_one_player_does_not_meet_motif_support_gate(self):
        ci = guarded_excess([1]*60, .1, pd.date_range("2026-06-01", periods=60), [1]*60, reps=1000)
        self.assertFalse(ci["eligible"])
        self.assertEqual(ci["p_two_sided"], 1)

    def test_composition_ignores_order_but_preserves_counts_and_mode(self):
        self.assertEqual(composition_key("exact:K>2B>K>K"), composition_key("exact:2B>K>K>K"))
        self.assertNotEqual(composition_key("exact:K>2B>K>K"), composition_key("exact:K>2B>2B>K"))
        self.assertNotEqual(composition_key("exact:K>K>K>K"), composition_key("pressure:K>K>K>K"))

    def test_strict_game_cohort_excludes_repeated_future_target_and_same_day_window(self):
        base = dict(player_id=1, next_game_id=10, next_game_date="2026-09-11", **{TARGET:1})
        rows = [dict(base, prediction_date="2026-09-10", sequence_window_end="2026-09-09"),
                dict(base, prediction_date="2026-09-11", sequence_window_end="2026-09-10"),
                dict(base, player_id=2, prediction_date="2026-09-11", sequence_window_end="2026-09-11"),
                dict(base, player_id=3, prediction_date="2026-09-12", next_game_date="2026-09-12", sequence_window_end="2026-09-11")]
        result = unique_game_rows(pd.DataFrame(rows))
        self.assertEqual(len(result), 1)
        self.assertEqual(result.player_id.iloc[0], 1)

    def test_duplicate_actual_player_game_fails_loudly(self):
        row = dict(player_id=1, next_game_id=10, prediction_date="2026-09-11",
                   next_game_date="2026-09-11", sequence_window_end="2026-09-10", **{TARGET:0})
        with self.assertRaises(ValueError):
            unique_game_rows(pd.DataFrame([row, row]))

    def test_cached_forecasts_cannot_silently_join_different_players(self):
        f = pd.DataFrame(dict(prediction_date=pd.to_datetime(["2026-09-11"]),
                              player_id=[1], next_game_id=[10], **{TARGET:[0]}))
        validate_forecast_alignment(f, f.copy())
        with self.assertRaises(AssertionError):
            validate_forecast_alignment(f, f.assign(player_id=2))


if __name__ == "__main__":
    unittest.main()
