from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from all_seeing_eye.daily_hub.markets import match_events, prepare_market_board, key
from all_seeing_eye.daily_hub.presentation import posting_frame, table_html, png_bytes
from all_seeing_eye.daily_hub.ledger import capture, history, grade
from all_seeing_eye.daily_hub.history import stats


class DailyHubTests(unittest.TestCase):
    def setUp(self):
        start = datetime.now(timezone.utc) + timedelta(days=1)
        self.games = [{"game_id": str(i), "home_team": "Seattle Mariners", "away_team": "Chicago Cubs",
                       "home_abbrev": "SEA", "away_abbrev": "CHC", "status": "Preview", "game_number": i,
                       "start_time": (start + timedelta(hours=(i - 1) * 4)).isoformat()} for i in [1, 2]]
        self.frame = pd.DataFrame([{"rank": i, "player_id": "10", "player_name": "A Player", "game_id": str(i),
                                    "home_away": "home", "adjusted_hr_probability_percent": 20,
                                    "book_american_odds": 900} for i in [1, 2]])
        self.starters = [{"game_id": str(i), "player_id": "10", "team_abbrev": "SEA", "batting_order": 2} for i in [1, 2]]

    def test_doubleheader_has_separate_events_and_no_reuse(self):
        events = [{"id": f"e{i}", "home_team": "Seattle Mariners", "away_team": "Chicago Cubs",
                   "commence_time": g["start_time"]} for i, g in enumerate(self.games)]
        matches = match_events(self.games, events)
        self.assertEqual(matches["1"]["id"], "e0")
        self.assertEqual(matches["2"]["id"], "e1")
        self.assertEqual(set(match_events(self.games, events[:1])), {"1"})

    def test_wrong_day_event_never_attaches(self):
        event = {"id": "old", "home_team": "Seattle Mariners", "away_team": "Chicago Cubs", "commence_time": "2020-01-01T12:00:00Z"}
        self.assertEqual(match_events(self.games, [event]), {})

    def test_best_book_and_missing_market_do_not_reuse_old_odds(self):
        quotes = [{"game_id": "1", "player_key": key("A Player"), "book": b, "price": p, "updated": "now", "event_id": "e0"}
                  for b, p in [("draftkings", 450), ("fanatics", 600), ("bet365", 500)]]
        result = prepare_market_board(self.frame, self.games, self.starters, quotes, [], live=True)
        first, second = result.iloc[0], result.iloc[1]
        self.assertTrue(first["ready"])
        self.assertEqual(first["bookmaker_used"], "Fanatics")
        self.assertEqual(first["book_american_odds"], 600)
        self.assertAlmostEqual(first["edge_percent"], 20 - 100 / 7)
        self.assertFalse(second["ready"])
        self.assertEqual(second["book_american_odds"], "")

    def test_doubleheader_override_is_game_specific(self):
        overrides = [{"game_id": "2", "player_id": "10", "odds": 500, "sportsbook": "DraftKings"}]
        result = prepare_market_board(self.frame, self.games, self.starters, [], overrides, live=True)
        self.assertFalse(result.iloc[0]["ready"])
        self.assertTrue(result.iloc[1]["ready"])

    def test_unconfirmed_and_scratched_stay_pending(self):
        override = [{"game_id": "1", "player_id": "10", "odds": 500}]
        result = prepare_market_board(self.frame, self.games, [], [], override, live=True, confirmed_only=True)
        self.assertFalse(result.iloc[0]["ready"])
        self.assertIn("lineup", result.iloc[0]["pending_reason"])
        override[0]["out"] = True
        result = prepare_market_board(self.frame, self.games, self.starters, [], override, live=True)
        self.assertFalse(result.iloc[0]["ready"])

    def test_formatting_groups_names_without_changing_research_rows(self):
        raw = pd.DataFrame([{"signal": s, "player": "A Player", "odds": 600, "signal_stats": "2 bets, 1 HR, +5.00u, +250.00% ROI", "team": "SEA"}
                            for s in ["B", "A"]])
        view = posting_frame(raw, "Straight Bets", 0)
        rendered = table_html(view)
        self.assertEqual(rendered.count("A Player"), 1)
        self.assertIn("#005C5C", rendered)
        self.assertEqual(view["player"].tolist(), ["A Player", "A Player"])
        from PIL import Image
        image = Image.open(BytesIO(png_bytes(view)))
        self.assertGreater(image.width, 200)
        self.assertGreater(image.height, 80)
        self.assertEqual(image.getpixel((0, 0)), (255, 195, 160))
        self.assertEqual(image.getpixel((image.width - 1, image.height - 1)), (255, 195, 160))
        self.assertIn((0, 92, 92), {color for _, color in image.getcolors(image.width * image.height)})

    def test_png_background_matches_peach_theme_for_all_posting_views(self):
        from PIL import Image, ImageColor
        from all_seeing_eye.daily_hub.presentation import VIEWS
        from all_seeing_eye.theme import PEACH
        raw = pd.DataFrame([{"player": "A Player", "player_name": "A Player", "rank": 1, "signal": "Signal"}])
        for title in [*VIEWS, "Parlays"]:
            with self.subTest(title=title):
                image = Image.open(BytesIO(png_bytes(posting_frame(raw, title))))
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.getpixel((0, 0)), ImageColor.getrgb(PEACH))
                self.assertEqual(image.getpixel((8, 45)), (255, 195, 160))

    def test_frozen_capture_and_void_parlay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite3"
            market = pd.DataFrame([{"ready": True, "player_name": n, "player_id": str(i), "game_id": "1", "bookmaker_used": "Fanatics"}
                                   for i, n in [(10, "A Player"), (11, "B Player")]])
            straight = pd.DataFrame([{"signal": "Signal", "player": "A Player", "odds": 500, "sportsbook": "Fanatics"}])
            parlay = pd.DataFrame([{"parlay_test_group": "active_2leg", "leg1": "A Player", "odds1": 500,
                                   "leg2": "B Player", "odds2": 500, "parlay_odds": 3500}])
            capture(path, "2026-09-01", "first", straight, parlay, market)
            straight.loc[0, "odds"] = 900
            capture(path, "2026-09-01", "second", straight, parlay, market)
            frozen = history(path)
            self.assertEqual(len(frozen), 1)
            self.assertEqual(frozen.iloc[0]["book_american_odds"], 500)
            pd.DataFrame([{"game_id": "1", "player_id": "10", "actual_pa": 1, "actual_ab": 1,
                           "lineup_position": "PH", "actual_hr": 0},
                          {"game_id": "1", "player_id": "11", "actual_pa": 4, "actual_ab": 4,
                           "lineup_position": "CF", "actual_hr": 1}]).to_csv(Path(directory) / "daily_results_2026-09-01.csv", index=False)
            with patch("all_seeing_eye.daily_hub.ledger.get_json", return_value={"dates": [{"games": [{"gamePk": 1, "status": {"abstractGameState": "Final"}}]}]}):
                self.assertEqual(grade(path, Path(directory), "2026-09-02"), 2)
            self.assertEqual(history(path).iloc[0]["result"], "Void")
            self.assertTrue(history(path, "parlay").empty)
            self.assertIn("0 bets, 0 HR", stats(history(path))["Signal"])


    def test_oddsblaze_only_accepts_fresh_full_game_hr_quotes(self):
        from all_seeing_eye.daily_hub.oddsblaze import parse_prices
        odd = {"id": "quote1", "market": "Player Home Runs", "price": "+600",
               "selection": {"side": "Over", "line": 0.5}, "player": {"name": "A Player"}}
        payload = {"updated": datetime.now(timezone.utc).isoformat(), "sportsbook": {"id": "draftkings"},
                   "events": [{"id": "g1", "date": self.games[0]["start_time"], "live": False,
                               "teams": {"home": {"name": "Seattle Mariners"}, "away": {"name": "Chicago Cubs"}},
                               "odds": [odd, {**odd, "market": "Player Hits"}, {**odd, "selection": {"side": "Over", "line": 1.5}},
                                        {**odd, "locked": True}]}]}
        quotes = parse_prices(payload, self.games, "draftkings")
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["game_id"], "1")
        self.assertEqual(quotes[0]["price"], 600)
        self.assertEqual(parse_prices(payload, self.games, "fanatics"), [])
        payload["updated"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.assertEqual(parse_prices(payload, self.games, "draftkings"), [])

    def test_provider_credentials_are_isolated(self):
        from all_seeing_eye.daily_hub.credentials import read_key
        with patch.dict("os.environ", {"ODDS_API_KEY": "original", "ODDSBLAZE_API_KEY": "alternative"}, clear=True):
            self.assertEqual(read_key(), "original")
            self.assertEqual(read_key("oddsblaze"), "alternative")

        with patch.dict("os.environ", {"ODDSPAPI_API_KEY": "oddspapi"}, clear=True):
            self.assertEqual(read_key("odds_papi"), "oddspapi")

    def test_signal_stats_grade_actual_rows_not_static_backtest_notes(self):
        frame = pd.DataFrame([{"signal": "Sequence", "result": "HR" if i < 5 else "No HR",
                               "profit_1u": 4 if i < 5 else -1} for i in range(17)] +
                             [{"signal": "Sequence", "result": "Void", "profit_1u": 0},
                              {"signal": "Sequence", "result": "Pending", "profit_1u": None}])
        self.assertEqual(stats(frame)["Sequence"], "17 bets, 5 HR, +8.00u, +47.06% ROI")



    def test_publish_preserves_existing_daily_inputs(self):
        from all_seeing_eye.daily_hub import runner as module
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "MODEL4_DAILY_READS" / "2026-09-04").mkdir(parents=True)
            prior = root / "inputs" / "manual_20260904_original"
            prior.mkdir(parents=True)
            job = object.__new__(module.Runner)
            job.day, job.mode, job.folder = "2026-09-04", "full", root / "run"
            job.warn = Mock()
            with patch.object(module, "ROOT", root), patch.object(module, "HUB", root / "hub"), \
                    patch.object(module.pd, "read_csv", return_value=pd.DataFrame()), \
                    patch("all_seeing_eye.daily_hub.ledger.capture"), patch.object(module.shutil, "copytree") as copy:
                job.publish(root / "output", root / "new-inputs")
                copy.assert_not_called()
            self.assertTrue(prior.exists())



    def test_morning_default_allows_unconfirmed_with_odds_but_not_missing_odds(self):
        override = [{"game_id": "1", "player_id": "10", "odds": 500, "sportsbook": "DraftKings"}]
        result = prepare_market_board(self.frame, self.games, [], [], override, live=True)
        self.assertTrue(result.iloc[0]["ready"])
        self.assertEqual(result.iloc[0]["lineup_status"], "not_confirmed")
        self.assertFalse(result.iloc[1]["ready"])
        self.assertEqual(result.iloc[1]["pending_reason"], "Waiting for sportsbook odds")

    def test_morning_default_still_excludes_announced_nonstarter_and_manual_out(self):
        starters = [{"game_id": "1", "player_id": "99", "team_abbrev": "SEA", "batting_order": 2}]
        override = [{"game_id": "1", "player_id": "10", "odds": 500}]
        result = prepare_market_board(self.frame, self.games, starters, [], override, live=True)
        self.assertFalse(result.iloc[0]["ready"])
        self.assertIn("Not starting", result.iloc[0]["pending_reason"])
        override[0]["out"] = True
        result = prepare_market_board(self.frame, self.games, [], [], override, live=True)
        self.assertFalse(result.iloc[0]["ready"])

    def test_background_launcher_defaults_to_morning_mode(self):
        from all_seeing_eye.daily_hub import runner as module
        import inspect
        self.assertFalse(inspect.signature(module.Runner).parameters["confirmed_only"].default)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(module, "HUB", Path(directory)), patch.object(module.subprocess, "Popen") as start:
                module.start_run("2026-09-04", "saved")
                self.assertNotIn("--confirmed-only", start.call_args.args[0])
                module.start_run("2026-09-04", "saved", confirmed_only=True)
                self.assertIn("--confirmed-only", start.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
