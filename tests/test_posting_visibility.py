import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from all_seeing_eye.daily_hub.visibility import PostingVisibility, posting_scope, filter_posting_rows, with_lineups


class PostingVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.market = pd.DataFrame([
            {"player_name": "Ben Rice", "player_id": "1", "game_id": "10", "team_abbrev": "NYY",
             "lineup_status": "confirmed", "ready": True},
            {"player_name": "Dominic Canzone", "player_id": "2", "game_id": "20", "team_abbrev": "SEA",
             "lineup_status": "not_confirmed", "ready": True},
            {"player_name": "CJ Abrams", "player_id": "3", "game_id": "30", "team_abbrev": "WSH",
             "lineup_status": "out", "ready": False},
        ])
        self.visibility = PostingVisibility(self.market)

    def test_toggle_restores_complete_board_without_reranking_or_mutating(self):
        board = pd.DataFrame({"eye_rank": [1, 2, 3], "player": ["Dominic Canzone", "Ben Rice", "CJ Abrams"]})
        original = board.copy(deep=True)
        with posting_scope(self.visibility):
            shown = filter_posting_rows(board)
            self.assertEqual(shown["player"].tolist(), ["Ben Rice"])
            self.assertEqual(shown["eye_rank"].tolist(), [2])
        pd.testing.assert_frame_equal(filter_posting_rows(board), original)
        pd.testing.assert_frame_equal(board, original)

    def test_all_signal_rows_for_unconfirmed_player_are_hidden(self):
        signals = pd.DataFrame({"signal": ["A", "B", "C"], "player": ["Dominic Canzone", "Dominic Canzone", "Ben Rice"]})
        self.assertEqual(self.visibility.filter(signals)["signal"].tolist(), ["C"])

    def test_entire_parlay_is_hidden_when_any_leg_is_unconfirmed(self):
        for first, second in [("leg1", "leg2"), ("leg1_player", "leg2_player")]:
            tickets = pd.DataFrame([{first: "Ben Rice", second: "Dominic Canzone", "parlay_odds": "+2500"}])
            self.assertTrue(self.visibility.filter(tickets).empty)
            self.assertEqual(tickets.iloc[0][second], "Dominic Canzone")

    def test_doubleheader_confirmation_does_not_bleed_into_other_game(self):
        market = pd.concat([self.market, pd.DataFrame([{"player_name": "Ben Rice", "player_id": "1",
                                                      "game_id": "11", "lineup_status": "not_confirmed", "ready": False}])])
        gate = PostingVisibility(market)
        self.assertFalse(gate.confirmed("Ben Rice", "11"))
        self.assertTrue(gate.confirmed("Ben Rice", "10"))
        self.assertTrue(gate.confirmed("Ben Rice"))
        market.loc[market["player_name"].eq("Ben Rice"), "ready"] = False
        self.assertFalse(PostingVisibility(market).confirmed("Ben Rice"))

    def test_lineup_overlay_does_not_change_prices_or_snapshot(self):
        market = self.market.assign(book_american_odds=[400, 500, 600])
        original = market.copy(deep=True)
        changed = with_lineups(market, [{"game_id": "10"}, {"game_id": "20"}, {"game_id": "30"}],
                               [{"game_id": "20", "player_id": "2", "team_abbrev": "SEA"}])
        self.assertEqual(changed.loc[changed.player_name.eq("Dominic Canzone"), "lineup_status"].iloc[0], "confirmed")
        self.assertEqual(changed["book_american_odds"].tolist(), [400, 500, 600])
        pd.testing.assert_frame_equal(market, original)
        out = with_lineups(market, [{"game_id": "20"}],
                           [{"game_id": "20", "player_id": "2", "team_abbrev": "SEA"}],
                           [{"game_id": "20", "player_id": "2", "out": True}])
        self.assertEqual(out.iloc[1]["lineup_status"], "out")

    def test_native_active_reader_is_filtered_only_inside_posting_context(self):
        from all_seeing_eye.profit_lens_app import read_active_parlay_frame
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ticket.csv"
            pd.DataFrame([{"leg1_player": "Ben Rice", "leg2_player": "Dominic Canzone"}]).to_csv(path, index=False)
            original = path.read_bytes()
            with posting_scope(self.visibility):
                self.assertTrue(read_active_parlay_frame(path).empty)
            self.assertEqual(len(read_active_parlay_frame(path)), 1)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
