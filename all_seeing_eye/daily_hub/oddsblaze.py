"""OddsBlaze adapter. Credentials and availability are separate from The Odds API."""
from datetime import datetime, timezone

from .markets import BOOKS, get_json, is_pregame, key, match_events, number, utc


def parse_prices(payload: dict, games: list[dict], book: str) -> list[dict]:
    if payload.get("sportsbook", {}).get("id") != book:
        return []
    updated = utc(payload.get("updated"))
    now = datetime.now(timezone.utc)
    if updated is None or not -60 <= (now - updated).total_seconds() <= 900:
        return []
    events = [{**e, "home_team": e.get("teams", {}).get("home", {}).get("name", ""),
               "away_team": e.get("teams", {}).get("away", {}).get("name", ""),
               "commence_time": e.get("date", "")} for e in payload.get("events", []) if not e.get("live")]
    matches = match_events(games, events)
    rows = []
    for game in games:
        gid = str(game["game_id"])
        if not is_pregame(game, now):
            continue
        event = matches.get(gid)
        if not event:
            continue
        for odd in event.get("odds", []):
            selection = odd.get("selection", {})
            price = number(odd.get("price"))
            player = odd.get("player", {}).get("name")
            if (key(odd.get("market")) not in {"playerhomeruns", "batterhomeruns"}
                    or str(selection.get("side", "")).lower() != "over"
                    or number(selection.get("line")) != 0.5 or not player
                    or price is None or abs(price) < 100 or odd.get("locked")):
                continue
            rows.append({"game_id": gid, "player_key": key(player), "book": book,
                         "price": price, "event_id": event["id"], "updated": payload["updated"],
                         "provider": "oddsblaze", "selection_id": odd.get("id", "")})
    return rows


def fetch_prices(games: list[dict], api_key: str) -> tuple[list[dict], list[str]]:
    if not api_key:
        return [], ["OddsBlaze needs its own key. Your existing Odds API key is not sent to this provider."]
    rows, warnings = [], []
    for book in BOOKS:
        try:
            payload = get_json("https://odds.oddsblaze.com/", {
                "key": api_key, "sportsbook": book, "league": "mlb",
                "market_contains": "Home Run", "price": "american", "live": "false"})
            prices = parse_prices(payload, games, book)
            rows.extend(prices)
            if not prices:
                warnings.append(f"OddsBlaze: no fresh pregame HR quotes returned for {book}.")
        except RuntimeError as exc:
            warnings.append(f"OddsBlaze {book}: {exc}")
    return rows, warnings
