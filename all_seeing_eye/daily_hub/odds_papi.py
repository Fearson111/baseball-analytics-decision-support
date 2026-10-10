"""OddsPapi adapter for current DraftKings MLB home-run props."""
from datetime import datetime, timedelta, timezone
import time

from .markets import get_json, is_pregame, key, match_events, number, utc


BASE_URL = "https://api.oddspapi.io/v4"
SPORT_ID = 13
HOME_RUN_MARKET_ID = "131663"
ANYTIME_HOME_RUN_OUTCOME_ID = "131664"


def _items(payload, *names):
    if isinstance(payload, list):
        return payload
    for name in names:
        value = payload.get(name) if isinstance(payload, dict) else None
        if isinstance(value, list):
            return value
    return []


def _player_name(value):
    text = str(value or "").strip()
    if "," not in text:
        return text
    last, first = (part.strip() for part in text.split(",", 1))
    return " ".join(part for part in (first, last) if part)


def _american(value):
    direct = number(value.get("priceAmerican")) if isinstance(value, dict) else None
    if direct is not None and abs(direct) >= 100:
        return direct
    decimal = number(value.get("price")) if isinstance(value, dict) else None
    if decimal is None or decimal <= 1:
        return None
    return round((decimal - 1) * 100) if decimal >= 2 else round(-100 / (decimal - 1))


def _is_anytime_home_run(label):
    normalized = "".join(str(label or "").lower().split())
    return normalized in {"1+", "1+hr", "1+homerun", "1+homeruns", "anytimehr"}


def _fixture_events(payload):
    events = []
    for fixture in _items(payload, "data", "fixtures", "events"):
        if fixture.get("tournamentName") not in {None, "MLB"}:
            continue
        if fixture.get("hasOdds") is False:
            continue
        event_id = fixture.get("fixtureId") or fixture.get("id")
        home = fixture.get("participant1Name") or fixture.get("homeTeam") or fixture.get("home_team")
        away = fixture.get("participant2Name") or fixture.get("awayTeam") or fixture.get("away_team")
        commence = (fixture.get("startTime") or fixture.get("commenceTime") or fixture.get("commence_time")
                    or fixture.get("startTimestamp"))
        if event_id and home and away and commence:
            events.append({"id": str(event_id), "home_team": home, "away_team": away,
                           "commence_time": commence, "fixture": fixture})
    return events


def parse_prices(payload, games, event):
    bookmaker_odds = payload.get("bookmakerOdds", {}) if isinstance(payload, dict) else {}
    book = bookmaker_odds.get("draftkings", {})
    markets = book.get("markets", {}) if isinstance(book, dict) else {}
    market = markets.get(HOME_RUN_MARKET_ID) or markets.get(int(HOME_RUN_MARKET_ID))
    if not isinstance(market, dict):
        return []
    rows = []
    gid = str(event["game_id"])
    for outcome_id, outcome in (market.get("outcomes", {}) or {}).items():
        label = outcome.get("outcomeName") or outcome.get("name") or outcome.get("label", "")
        if str(outcome_id) != ANYTIME_HOME_RUN_OUTCOME_ID and not _is_anytime_home_run(label):
            continue
        for player in (outcome.get("players", {}) or {}).values():
            if not isinstance(player, dict) or player.get("active") is False:
                continue
            name = _player_name(player.get("playerName") or player.get("name"))
            price = _american(player)
            if not name or price is None or abs(price) < 100:
                continue
            rows.append({"game_id": gid, "player_key": key(name), "player_name": name,
                         "book": "draftkings", "price": price,
                         "event_id": str(event["event_id"]),
                         "updated": player.get("changedAt") or market.get("lastUpdate") or event.get("commence_time"),
                         "timestamp_kind": "book_updated", "provider": "oddspapi",
                         "selection_id": player.get("bookmakerOutcomeId") or player.get("id", "")})
    return rows


def fetch_prices(games, api_key):
    if not api_key:
        return [], ["OddsPapi needs its own key. Your existing Odds API key is not sent to this provider."]
    now = datetime.now(timezone.utc)
    day = min((utc(game.get("start_time")) or now).date() for game in games) if games else now.date()
    fixtures_payload = get_json(f"{BASE_URL}/fixtures", {
        "apiKey": api_key, "sportId": SPORT_ID,
        "from": (day - timedelta(days=1)).isoformat(),
        "to": (day + timedelta(days=2)).isoformat()})
    fixture_events = _fixture_events(fixtures_payload)
    matches = match_events(games, fixture_events)
    rows, warnings = [], []
    for index, game in enumerate(games):
        if not is_pregame(game, now):
            continue
        matched = matches.get(str(game["game_id"]))
        if not matched:
            warnings.append(f"OddsPapi: no unambiguous MLB fixture for game {game['game_id']}.")
            continue
        if index:
            time.sleep(0.3)
        try:
            for attempt in range(3):
                try:
                    payload = get_json(f"{BASE_URL}/odds", {
                        "apiKey": api_key, "fixtureId": matched["id"], "bookmakers": "draftkings"})
                    break
                except RuntimeError as exc:
                    if "HTTP 429" not in str(exc) or attempt == 2:
                        raise
                    time.sleep(0.4 * (attempt + 1))
        except RuntimeError as exc:
            warnings.append(f"OddsPapi game {game['game_id']}: {exc}")
            continue
        before = len(rows)
        rows.extend(parse_prices(payload, {"game_id": game["game_id"]},
                                 {"game_id": game["game_id"], "event_id": matched["id"],
                                  "commence_time": matched["commence_time"]}))
        if len(rows) == before:
            warnings.append(f"OddsPapi: no active DraftKings 1+ HR quotes for game {game['game_id']}.")
    if not rows:
        warnings.append("OddsPapi returned no current DraftKings MLB home-run props.")
    return rows, warnings
