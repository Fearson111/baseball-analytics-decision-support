import unittest

from pathlib import Path

from all_seeing_eye.menu import parse_path, parse_ranked_line


class MenuParsingTests(unittest.TestCase):
    def test_parses_rank_comma_player(self):
        self.assertEqual(parse_ranked_line("1, Kyle Schwarber"), ("Kyle Schwarber", 1))

    def test_parses_player_comma_rank(self):
        self.assertEqual(parse_ranked_line("Kyle Schwarber, 1"), ("Kyle Schwarber", 1))

    def test_parses_rank_space_player(self):
        self.assertEqual(parse_ranked_line("12 Shohei Ohtani"), ("Shohei Ohtani", 12))

    def test_skips_header(self):
        self.assertIsNone(parse_ranked_line("player,rank"))

    def test_parses_quoted_path_with_spaces(self):
        self.assertEqual(
            parse_path('"/tmp/Sample project/file.csv"'),
            Path("/tmp/Sample project/file.csv"),
        )

    def test_parses_escaped_path_with_spaces(self):
        self.assertEqual(
            parse_path("/tmp/Sample\\ project/file.csv"),
            Path("/tmp/Sample project/file.csv"),
        )


if __name__ == "__main__":
    unittest.main()
