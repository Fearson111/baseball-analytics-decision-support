import unittest

from all_seeing_eye.parlay_odds import correlated_parlay_odds


class ParlayOddsTests(unittest.TestCase):
    def test_same_team_two_leg_parlay_gets_grouped_sgp_price(self):
        odds = correlated_parlay_odds(
            [
                {"player": "Bleday", "book_american_odds": "+370", "team_abbrev": "ATH", "opponent_abbrev": "KC"},
                {"player": "Stewart", "book_american_odds": "+400", "team_abbrev": "ATH", "opponent_abbrev": "KC"},
            ]
        )

        self.assertEqual(odds["independent_parlay_decimal_odds"], 23.5)
        self.assertAlmostEqual(odds["parlay_decimal_odds"], 18.095)
        self.assertEqual(odds["correlation_factor"], 0.77)
        self.assertIn("same-team correlated SGP", odds["correlation_note"])

    def test_same_game_different_team_gets_mixed_sgp_price(self):
        odds = correlated_parlay_odds(
            [
                {"player": "Home Bat", "book_american_odds": "+400", "team_abbrev": "NYY", "opponent_abbrev": "BOS"},
                {"player": "Away Bat", "book_american_odds": "+500", "team_abbrev": "BOS", "opponent_abbrev": "NYY"},
            ]
        )

        self.assertEqual(odds["independent_parlay_decimal_odds"], 30.0)
        self.assertAlmostEqual(odds["parlay_decimal_odds"], 34.2)
        self.assertEqual(odds["correlation_factor"], 1.14)
        self.assertIn("mixed-team same-game SGP", odds["correlation_note"])

    def test_same_game_pair_inside_three_leg_parlay_groups_then_multiplies_odd_man_out(self):
        odds = correlated_parlay_odds(
            [
                {"player": "Team Bat 1", "book_american_odds": "+370", "team_abbrev": "ATH", "opponent_abbrev": "KC"},
                {"player": "Team Bat 2", "book_american_odds": "+400", "team_abbrev": "ATH", "opponent_abbrev": "KC"},
                {"player": "Other Game", "book_american_odds": "+300", "team_abbrev": "LAD", "opponent_abbrev": "SF"},
            ]
        )

        self.assertEqual(odds["independent_parlay_decimal_odds"], 94.0)
        self.assertAlmostEqual(odds["parlay_decimal_odds"], 72.38)
        self.assertEqual(odds["correlation_factor"], 0.77)

    def test_two_separate_same_team_blocks_are_each_grouped_then_multiplied(self):
        odds = correlated_parlay_odds(
            [
                {"player": "Wilyer Abreu", "book_american_odds": "+420", "team_abbrev": "BOS", "opponent_abbrev": "AZ"},
                {"player": "Elly De La Cruz", "book_american_odds": "+410", "team_abbrev": "CIN", "opponent_abbrev": "STL"},
                {"player": "Willson Contreras", "book_american_odds": "+525", "team_abbrev": "BOS", "opponent_abbrev": "AZ"},
                {"player": "Tyler Stephenson", "book_american_odds": "+575", "team_abbrev": "CIN", "opponent_abbrev": "STL"},
            ]
        )

        self.assertEqual(odds["independent_parlay_decimal_odds"], 1118.8125)
        self.assertAlmostEqual(odds["parlay_decimal_odds"], 663.3439)
        self.assertEqual(odds["correlation_factor"], 0.5929)
        self.assertIn("AZ/BOS SGP block", odds["correlation_note"])
        self.assertIn("CIN/STL SGP block", odds["correlation_note"])

    def test_mixed_three_leg_game_block_matches_observed_sgp_shape(self):
        odds = correlated_parlay_odds(
            [
                {"player": "Pete Crow-Armstrong", "book_american_odds": "+260", "team_abbrev": "CHC", "opponent_abbrev": "SEA"},
                {"player": "Josh Naylor", "book_american_odds": "+750", "team_abbrev": "SEA", "opponent_abbrev": "CHC"},
                {"player": "Dominic Canzone", "book_american_odds": "+510", "team_abbrev": "SEA", "opponent_abbrev": "CHC"},
                {"player": "Jose Ramirez", "book_american_odds": "+350", "team_abbrev": "CLE", "opponent_abbrev": "COL"},
            ]
        )

        self.assertEqual(odds["independent_parlay_decimal_odds"], 839.97)
        self.assertAlmostEqual(odds["parlay_decimal_odds"], 1129.9276)
        self.assertEqual(odds["correlation_factor"], 1.3452)

    def test_different_games_are_not_adjusted(self):
        odds = correlated_parlay_odds(
            [
                {"player": "A", "book_american_odds": "+400", "team_abbrev": "NYY", "opponent_abbrev": "BOS"},
                {"player": "B", "book_american_odds": "+500", "team_abbrev": "LAD", "opponent_abbrev": "SF"},
            ]
        )

        self.assertEqual(odds["independent_parlay_decimal_odds"], 30.0)
        self.assertEqual(odds["parlay_decimal_odds"], 30.0)
        self.assertEqual(odds["correlation_factor"], 1.0)


if __name__ == "__main__":
    unittest.main()
