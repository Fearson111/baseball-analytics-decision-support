from datetime import datetime, timedelta, timezone
import unittest

from all_seeing_eye.daily_hub.odds_papi import parse_prices


class OddsPapiTests(unittest.TestCase):
    def test_parses_active_draftkings_anytime_hr_and_normalizes_name(self):
        start = datetime.now(timezone.utc) + timedelta(hours=4)
        payload = {"bookmakerOdds": {"draftkings": {"markets": {"131663": {"outcomes": {
            "131664": {"players": {
                "42": {"playerName": "Busch, Michael", "priceAmerican": "+550", "active": True},
                "43": {"playerName": "Inactive, Player", "priceAmerican": "+900", "active": False},
            }},
            "131665": {"players": {
                "44": {"playerName": "Other, Player", "priceAmerican": "+1200", "active": True},
            }}}}}}}}
        rows = parse_prices(payload, {"game_id": "101"},
                            {"game_id": "101", "event_id": "fixture-1", "commence_time": start.isoformat()})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["player_name"], "Michael Busch")
        self.assertEqual(rows[0]["player_key"], "michaelbusch")
        self.assertEqual(rows[0]["price"], 550)
        self.assertEqual(rows[0]["book"], "draftkings")

    def test_decimal_price_fallback_and_missing_market(self):
        payload = {"bookmakerOdds": {"draftkings": {"markets": {"131663": {"outcomes": {
            "131664": {"players": {
                "42": {"playerName": "A Player", "price": 6.5, "active": True},
            }}}}}}}}
        rows = parse_prices(payload, {"game_id": "101"},
                            {"game_id": "101", "event_id": "fixture-1", "commence_time": ""})
        self.assertEqual(rows[0]["price"], 550)
        self.assertEqual(parse_prices({}, {"game_id": "101"}, {"game_id": "101", "event_id": "fixture-1"}), [])


if __name__ == "__main__":
    unittest.main()
