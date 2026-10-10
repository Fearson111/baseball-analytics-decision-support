from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd

from all_seeing_eye.daily_hub import public_odds as public
from all_seeing_eye.daily_hub.markets import prepare_market_board


class PublicOddsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.start = self.now + timedelta(hours=4)
        self.game = {"game_id": "101", "home_team": "Seattle Mariners", "away_team": "Chicago Cubs",
                     "home_abbrev": "SEA", "away_abbrev": "CHC", "status": "Preview",
                     "start_time": self.start.isoformat()}
        self.event = {"id": "mlb/42", "home_team": "Seattle Mariners", "away_team": "Chicago Cubs",
                      "commence_time": self.start.isoformat()}
        self.offer = {"available": True, "value": .5, "over": 500, "under": -750,
                      "favorite": "under", "metadata": {"over": "selection-1"}}
        self.market = {"id": "mlb.42.0.20.hr", "stat": "home runs",
                       "player": {"first_name": "Michael", "last_name": "Busch", "team": {"hashtag": "CHC"}},
                       "comparison": {"bet365": self.offer}}
        self.payload = {"event": {"sport": "mlb", "home": {"hashtag": "SEA"}, "away": {"hashtag": "CHC"}},
                        "books": {"bet365": {}, "draftkings": {}, "fanatics": {}}, "markets": [self.market]}
        self.frame = pd.DataFrame([{"player_name": "Michael Busch", "player_id": "20", "game_id": "101",
                                    "home_away": "away", "adjusted_hr_probability_percent": 20}])

    def scoreboard(self, start=None):
        return f'''<div class="event-card" id="mlb.42">
        <span data-role="localtime" data-value="{start or self.start.isoformat()}"></span>
        <tr data-side="home"><span class="team-name"><a>Mariners</a></span></tr>
        <tr data-side="away"><span class="team-name"><a>Cubs</a></span></tr></div>'''

    def jedi(self, start=None, odds=None, name="Mike Busch"):
        start = (start or self.start).astimezone(ZoneInfo("America/New_York"))
        return f'''<h1>MLB Anytime Home Run Odds</h1>
        <tr class="po-row po-game-start" data-home="SEA" data-away="CHC"
            data-pick="{name}" data-odds='{json.dumps(odds or {"dk": "+550"})}'>
        <span class="po-time">{start.strftime('%I:%M %p ET | %a, %b %d')}</span>
        <td class="po-gated">+99999</td></tr>'''

    def parse(self, payload=None):
        return public.comparison_prices(payload or self.payload, self.game, self.event, self.now.isoformat())

    def test_json_quote_and_provenance(self):
        quote = self.parse()[0]
        self.assertEqual((quote["price"], quote["book"], quote["game_id"]), (500, "bet365", "101"))
        self.assertEqual(quote["timestamp_kind"], "observed")
        self.assertEqual(quote["selection_id"], "selection-1")

    def test_only_open_full_game_over_half_hr(self):
        for changes in [{"available": False}, {"available": None}, {"value": 1.5},
                        {"value": 0}, {"over": 0}, {"over": "nan"}, {"over": 50}, {"over": None}]:
            with self.subTest(changes=changes):
                p = deepcopy(self.payload)
                p["markets"][0]["comparison"]["bet365"].update(changes)
                self.assertEqual(self.parse(p), [])
        for changes in [{"stat": "first home run"}, {"id": "mlb.42.1.20.hr"},
                        {"id": "mlb.99.0.20.hr"}, {"stat": "total bases"}]:
            p = deepcopy(self.payload)
            p["markets"][0].update(changes)
            self.assertEqual(self.parse(p), [])

    def test_no_invented_fanatics_coverage(self):
        self.assertEqual({q["book"] for q in self.parse()}, {"bet365"})
        self.market["comparison"]["fanatics"] = {**self.offer, "over": 600}
        self.assertEqual({q["book"] for q in self.parse()}, {"bet365", "fanatics"})
        self.market["comparison"]["fanduel"] = self.offer
        self.assertNotIn("fanduel", {q["book"] for q in self.parse()})

    def test_response_team_must_match_requested_event(self):
        self.payload["event"]["away"]["hashtag"] = "CWS"
        self.assertEqual(self.parse(), [])

    def test_scoreboard_exact_time_and_doubleheader(self):
        events = public.scoreboard_events(self.scoreboard(), [self.game])
        self.assertEqual(events, [self.event])
        second = {**self.game, "game_id": "102", "start_time": (self.start + timedelta(hours=4)).isoformat()}
        self.assertEqual(set(public.match_events([self.game, second], events)), {"101"})
        stale = public.scoreboard_events(self.scoreboard((self.start - timedelta(days=1)).isoformat()), [self.game])
        self.assertEqual(public.match_events([self.game], stale), {})

    def test_sox_are_not_confused(self):
        game = {**self.game, "home_team": "Boston Red Sox", "away_team": "Chicago White Sox"}
        html = self.scoreboard().replace("Mariners", "Red Sox").replace("Cubs", "White Sox")
        result = public.scoreboard_events(html, [game])[0]
        self.assertEqual(result["home_team"], "Boston Red Sox")
        self.assertEqual(result["away_team"], "Chicago White Sox")

    def test_jedi_reads_only_free_dk_json_not_blurred_cells(self):
        rows = public.jedi_prices(self.jedi(odds={"dk": "+550", "fn": "+99999", "b3": "+99999"}), [self.game], self.now.isoformat())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price"], 550)
        self.assertEqual(rows[0]["provider"], "jedibets")

    def test_jedi_missing_price_wrong_day_and_wrong_teams(self):
        for html in [self.jedi(odds={"fd": "+600"}), self.jedi(start=self.start-timedelta(days=1)),
                     self.jedi().replace('data-home="SEA"', 'data-home="CWS"')]:
            self.assertEqual(public.jedi_prices(html, [self.game], self.now.isoformat()), [])

    def test_unique_name_resolution_preserves_original_name(self):
        quote = {**self.parse()[0], "player_name": "Mike Busch", "player_key": "mikebusch"}
        result = public.align_prices([quote], self.frame, [self.game])
        self.assertEqual(result[0]["player_name"], "Michael Busch")
        self.assertEqual(result[0]["source_player_name"], "Mike Busch")
        self.assertEqual(result[0]["player_id"], "20")

    def test_merge_quote_sources_fills_missing_identity_without_overwriting(self):
        primary = [{"game_id": "101", "player_key": "michaelbusch", "book": "draftkings", "price": 550}]
        supplemental = [
            {"game_id": "101", "player_key": "michaelbusch", "book": "draftkings", "price": 600},
            {"game_id": "101", "player_key": "michaelbusch", "book": "fanatics", "price": 575},
            {"game_id": "101", "player_key": "michaelbusch", "book": "fanduel", "price": 560},
        ]
        result = public.merge_quote_sources(primary, supplemental)
        self.assertEqual([row["book"] for row in result], ["draftkings", "fanatics"])
        self.assertEqual(result[0]["price"], 550)

    def test_suffix_resolution_and_no_fuzzy_initials(self):
        frame = self.frame.copy()
        frame["player_name"] = "Ronald Acuna Jr."
        quote = {**self.parse()[0], "player_name": "Ronald Acuna"}
        self.assertEqual(len(public.align_prices([quote], frame, [self.game])), 1)
        self.assertEqual(public.align_prices([{**quote, "player_name": "R. Acuna"}], frame, [self.game]), [])

    def test_ambiguous_name_team_mismatch_or_price_conflict_is_not_guessed(self):
        quote = self.parse()[0]
        self.assertEqual(public.align_prices([quote], pd.concat([self.frame, self.frame]), [self.game]), [])
        self.assertEqual(public.align_prices([{**quote, "player_team": "SEA"}], self.frame, [self.game]), [])
        self.assertEqual(public.align_prices([quote, {**quote, "price": 900}], self.frame, [self.game]), [])

    def test_best_price_reaches_model_and_clears_disappearing_quotes(self):
        quotes = self.parse() + public.jedi_prices(self.jedi(), [self.game], self.now.isoformat())
        quotes = public.align_prices(quotes, self.frame, [self.game])
        result = prepare_market_board(self.frame, [self.game], [], quotes, [], live=True)
        row = result.iloc[0]
        self.assertTrue(row.ready)
        self.assertEqual(row.bookmaker_used, "DraftKings")
        self.assertEqual(row.dk_odds, 550)
        self.assertEqual(row["365_odds"], 500)
        self.assertEqual(row.odds_source, "jedibets")
        self.assertEqual(row.odds_timestamp_kind, "observed")
        self.assertAlmostEqual(row.edge_percent, 20-100/6.5)
        empty = prepare_market_board(result, [self.game], [], [], [], live=True).iloc[0]
        self.assertFalse(empty.ready)
        self.assertEqual(empty.odds_source, "")
        self.assertEqual(empty.book_american_odds, "")

    def test_manual_override_and_confirmed_only_still_apply(self):
        result = prepare_market_board(self.frame, [self.game], [], self.parse(),
                                      [{"game_id": "101", "player_id": "20", "odds": 600, "sportsbook": "Fanatics"}],
                                      live=True, confirmed_only=True).iloc[0]
        self.assertEqual(result.bookmaker_used, "Fanatics")
        self.assertEqual(result.odds_source, "manual")
        self.assertFalse(result.ready)

    def response(self, body="public body", status=200, seconds_old=0):
        return Mock(status_code=status, text=body,
                    headers={"Date": format_datetime(self.now-timedelta(seconds=seconds_old), usegmt=True)})

    @patch.object(public.time, "sleep")
    def test_cache_and_no_credentials_sent(self, _):
        with tempfile.TemporaryDirectory() as directory, patch.object(public.requests, "get", return_value=self.response()) as get:
            feed = public.PublicFeed(directory)
            first = feed.read(public.JEDI)
            self.assertEqual(feed.read(public.JEDI), first)
            self.assertEqual(get.call_count, 1)
            self.assertNotIn("Authorization", get.call_args.kwargs["headers"])
            self.assertIsNone(get.call_args.kwargs["params"])

    @patch.object(public.time, "sleep")
    def test_stale_response_and_http_block_are_errors_not_bypassed(self, _):
        for response in [self.response(seconds_old=1000), self.response(status=403), self.response(status=429)]:
            with patch.object(public.requests, "get", return_value=response) as get:
                with self.assertRaises(RuntimeError):
                    public.PublicFeed(None).read(public.JEDI)
                self.assertEqual(get.call_count, 1)

    @patch.object(public.time, "sleep")
    def test_expired_cache_not_reused_when_network_fails(self, _):
        with tempfile.TemporaryDirectory() as directory, patch.object(public.requests, "get", return_value=self.response()):
            feed = public.PublicFeed(directory)
            feed.read(public.JEDI)
            path = next(Path(directory).glob("*.json"))
            data = json.loads(path.read_text())
            data["observed"] = (self.now-timedelta(hours=1)).isoformat()
            path.write_text(json.dumps(data))
            with patch.object(public.requests, "get", side_effect=public.requests.ConnectionError):
                with self.assertRaises(RuntimeError):
                    feed.read(public.JEDI)

    def test_complete_fetch_uses_public_sources_and_keeps_partial_success(self):
        def read(url, params=None):
            if url == public.SCOREBOARD:
                return self.scoreboard(), self.now.isoformat()
            if url == public.COMPARISON:
                return json.dumps(self.payload), self.now.isoformat()
            return self.jedi(), self.now.isoformat()
        with patch.object(public.PublicFeed, "read", side_effect=read):
            for game in (self.game, {**self.game, "status": "Live", "detailed_status": "Warmup"}):
                quotes, warnings = public.fetch_prices([game], "must-not-be-sent")
                self.assertEqual({q["book"] for q in quotes}, {"bet365", "draftkings"})
                self.assertTrue(any("fanatics" in w for w in warnings))
        with patch.object(public.PublicFeed, "read", side_effect=lambda url, params=None:
                          (self.jedi(), self.now.isoformat()) if url == public.JEDI else (_ for _ in ()).throw(RuntimeError("HTTP 403"))):
            quotes, warnings = public.fetch_prices([self.game])
            self.assertEqual({q["book"] for q in quotes}, {"draftkings"})

    def test_no_in_play_collection(self):
        with patch.object(public.PublicFeed, "read") as read:
            self.assertEqual(public.fetch_prices([{**self.game, "status": "Live"}])[0], [])
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
