import unittest

from all_seeing_eye.boards import BoardEntry, PlayerSignal
from all_seeing_eye.scoring import (
    acceleration_score,
    rank_to_score,
    scale_acceleration_score,
    scale_eye_score,
    score_players,
)


class ScoringTests(unittest.TestCase):
    def test_rank_to_score_rewards_top_rank(self):
        self.assertEqual(rank_to_score(1, 80), 100.0)
        self.assertGreater(rank_to_score(10, 80), rank_to_score(40, 80))

    def test_eye_score_uses_soft_cap_instead_of_flat_100(self):
        self.assertLess(scale_eye_score(100), 100)
        self.assertLess(scale_eye_score(140), 100)
        self.assertGreater(scale_eye_score(140), scale_eye_score(100))

    def test_acceleration_score_uses_soft_cap_instead_of_flat_100(self):
        self.assertLess(scale_acceleration_score(120), 100)
        self.assertGreater(scale_acceleration_score(120), scale_acceleration_score(95))

    def test_static_convergence_is_supporting_context(self):
        converged = PlayerSignal(
            player="Player A",
            entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 20, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 25, {}),
                "pitcher_batter_top80": BoardEntry("pitcher_batter_top80", "Player A", 22, {}),
            },
        )
        single = PlayerSignal(
            player="Player B",
            entries={"gbm_top80": BoardEntry("gbm_top80", "Player B", 5, {})},
        )

        scored = score_players({"a": converged, "b": single})

        self.assertEqual(scored[0].player, "Player A")
        self.assertEqual(scored[0].review_priority, "Medium")

    def test_hidden_mover_gets_movement_reason(self):
        signal = PlayerSignal(
            player="Player C",
            entries={"sequence_top150": BoardEntry("sequence_top150", "Player C", 18, {})},
            previous_entries={"sequence_top150": BoardEntry("sequence_top150", "Player C", 103, {})},
        )

        scored = score_players({"c": signal})[0]

        self.assertIn("accelerated", " ".join(scored.reasoning))
        self.assertGreaterEqual(scored.eye_score, 40)

    def test_multi_board_climber_gets_high_acceleration_score(self):
        signal = PlayerSignal(
            player="Player A",
            entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 18, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 22, {}),
                "pitcher_batter_top80": BoardEntry("pitcher_batter_top80", "Player A", 12, {}),
            },
            previous_entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 78, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 117, {}),
                "pitcher_batter_top80": BoardEntry("pitcher_batter_top80", "Player A", 64, {}),
            },
            historical_entries={
                "gbm_top80": [
                    BoardEntry("gbm_top80", "Player A", 122, {}),
                    BoardEntry("gbm_top80", "Player A", 96, {}),
                    BoardEntry("gbm_top80", "Player A", 78, {}),
                ],
                "sequence_top150": [
                    BoardEntry("sequence_top150", "Player A", 140, {}),
                    BoardEntry("sequence_top150", "Player A", 128, {}),
                    BoardEntry("sequence_top150", "Player A", 117, {}),
                ],
            },
            has_previous_context=True,
            has_history_context=True,
        )

        score, reasons = acceleration_score(signal)

        self.assertGreaterEqual(score, 80)
        self.assertIn("Multi-board acceleration", " ".join(reasons))

    def test_flat_repeated_history_has_low_acceleration_score(self):
        signal = PlayerSignal(
            player="Player A",
            entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 6, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 14, {}),
            },
            previous_entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 6, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 14, {}),
            },
            historical_entries={
                "gbm_top80": [
                    BoardEntry("gbm_top80", "Player A", 5, {}),
                    BoardEntry("gbm_top80", "Player A", 6, {}),
                    BoardEntry("gbm_top80", "Player A", 6, {}),
                ],
                "sequence_top150": [
                    BoardEntry("sequence_top150", "Player A", 13, {}),
                    BoardEntry("sequence_top150", "Player A", 14, {}),
                    BoardEntry("sequence_top150", "Player A", 14, {}),
                ],
            },
            has_previous_context=True,
            has_history_context=True,
        )

        score, _ = acceleration_score(signal)

        self.assertLessEqual(score, 5)

    def test_hidden_mover_can_beat_static_obvious_convergence(self):
        static = PlayerSignal(
            player="Player A",
            entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 8, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 12, {}),
                "pitcher_batter_top80": BoardEntry("pitcher_batter_top80", "Player A", 10, {}),
            },
            previous_entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 7, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 11, {}),
                "pitcher_batter_top80": BoardEntry("pitcher_batter_top80", "Player A", 9, {}),
            },
            has_previous_context=True,
        )
        mover = PlayerSignal(
            player="Player B",
            entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player B", 42, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player B", 33, {}),
                "pitcher_batter_top80": BoardEntry("pitcher_batter_top80", "Player B", 19, {}),
            },
            previous_entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player B", 104, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player B", 133, {}),
                "pitcher_batter_top80": BoardEntry("pitcher_batter_top80", "Player B", 89, {}),
            },
            has_previous_context=True,
        )

        scored = score_players({"static": static, "mover": mover})

        self.assertEqual(scored[0].player, "Player B")
        self.assertIn("Cross-system acceleration", " ".join(scored[0].reasoning))

    def test_stable_gbm_top_anchor_is_not_penalized_by_itself(self):
        signal = PlayerSignal(
            player="Player A",
            entries={"gbm_top80": BoardEntry("gbm_top80", "Player A", 3, {})},
            previous_entries={"gbm_top80": BoardEntry("gbm_top80", "Player A", 3, {})},
            historical_entries={
                "gbm_top80": [
                    BoardEntry("gbm_top80", "Player A", 2, {}),
                    BoardEntry("gbm_top80", "Player A", 4, {}),
                    BoardEntry("gbm_top80", "Player A", 3, {}),
                ]
            },
            has_previous_context=True,
            has_history_context=True,
        )

        scored = score_players({"a": signal})[0]

        self.assertNotIn("penalty", " ".join(scored.reasoning).lower())
        self.assertEqual(scored.stale_signal_status, "fresh")

    def test_repeated_non_gbm_support_without_elite_confirmation_gets_stale_penalty(self):
        signal = PlayerSignal(
            player="Player A",
            entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 35, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 32, {}),
            },
            previous_entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 35, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 32, {}),
            },
            historical_entries={
                "gbm_top80": [
                    BoardEntry("gbm_top80", "Player A", 36, {}),
                    BoardEntry("gbm_top80", "Player A", 34, {}),
                    BoardEntry("gbm_top80", "Player A", 35, {}),
                ],
                "sequence_top150": [
                    BoardEntry("sequence_top150", "Player A", 33, {}),
                    BoardEntry("sequence_top150", "Player A", 31, {}),
                    BoardEntry("sequence_top150", "Player A", 32, {}),
                ],
            },
            has_previous_context=True,
            has_history_context=True,
        )

        scored = score_players({"a": signal})[0]

        self.assertIn("non-GBM support", " ".join(scored.reasoning))
        self.assertEqual(scored.stale_signal_status, "normal_stale_penalty")

    def test_repeated_elite_support_gets_reinforced_instead_of_buried(self):
        signal = PlayerSignal(
            player="Player A",
            entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 7, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 11, {}),
                "pitcher_batter_top80": BoardEntry("pitcher_batter_top80", "Player A", 16, {}),
            },
            previous_entries={
                "gbm_top80": BoardEntry("gbm_top80", "Player A", 7, {}),
                "sequence_top150": BoardEntry("sequence_top150", "Player A", 11, {}),
                "pitcher_batter_top80": BoardEntry("pitcher_batter_top80", "Player A", 16, {}),
            },
            historical_entries={
                "gbm_top80": [BoardEntry("gbm_top80", "Player A", 7, {}) for _ in range(3)],
                "sequence_top150": [BoardEntry("sequence_top150", "Player A", 11, {}) for _ in range(3)],
                "pitcher_batter_top80": [BoardEntry("pitcher_batter_top80", "Player A", 16, {}) for _ in range(3)],
            },
            has_previous_context=True,
            has_history_context=True,
        )

        scored = score_players({"a": signal})[0]

        self.assertEqual(scored.stale_signal_status, "persistent_elite_reinforced")
        self.assertIn("Stale elite reinforcement", " ".join(scored.reasoning))


if __name__ == "__main__":
    unittest.main()
