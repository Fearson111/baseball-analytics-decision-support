"""Read public pregame comparison feeds without accounts or protected endpoints.

ScoresAndOdds exposes its Odds Compare widget as JSON. JediBets exposes four
free books as JSON data attributes; member-only/blurred cells are never read.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import requests

from .markets import BOOKS, is_pregame, key, match_events, number, utc

SCOREBOARD = "https://www.scoresandodds.com/mlb"
COMPARISON = "https://rga51lus77.execute-api.us-east-1.amazonaws.com/prod/market-comparison"
JEDI = "https://jedibets.com/odds/mlb/home-runs"
CACHE = Path(__file__).resolve().parents[2] / "DAILY_BASEBALL" / "odds_cache"
TEAM_ALIASES = {"AZ": "ARI", "ATH": "OAK", "CHW": "CWS", "WSN": "WSH", "KCR": "KC", "SDP": "SD", "SFG": "SF", "TBR": "TB"}


def team_key(value):
    value = str(value).upper()
    return TEAM_ALIASES.get(value, value)


def active_games(games, now):
    return [g for g in games if is_pregame(g, now)]


def scoreboard_events(html, games):
    soup = BeautifulSoup(html, "html.parser")
    teams = {key(g[f"{side}_team"].split()[-1]): g[f"{side}_team"]
             for g in games for side in ("home", "away")}
    # Sox names need both words to distinguish Chicago and Boston.
    teams.update({"redsox": "Boston Red Sox", "whitesox": "Chicago White Sox",
                  "bluejays": "Toronto Blue Jays", "athletics": "Athletics"})
    events = []
    for card in soup.select(".event-card[id^='mlb.']"):
        stamp = card.select_one('[data-role="localtime"][data-value]')
        event = {"id": card.get("id", "").replace(".", "/", 1),
                 "commence_time": stamp.get("data-value", "") if stamp else ""}
        for side in ("home", "away"):
            label = card.select_one(f'[data-side="{side}"] .team-name a')
            name = key(label.get_text(" ", strip=True)) if label else ""
            event[f"{side}_team"] = teams.get(name, "")
        if all(event.values()) and re.fullmatch(r"mlb/\d+", event["id"]):
            events.append(event)
    return events


def comparison_prices(payload, game, event, observed):
    """A book listing alone is not evidence of coverage: require an open O0.5 quote."""
    source_game = payload.get("event") or {}
    if source_game.get("sport") != "mlb":
        return []
    for side in ("home", "away"):
        source_team = source_game.get(side, {})
        if team_key(source_team.get("hashtag", source_team.get("key", ""))) != team_key(game.get(f"{side}_abbrev", "")):
            return []
    rows = []
    for market in payload.get("markets", []):
        # Period 0 is the full game, not first-inning HR or an alternate threshold.
        parts = str(market.get("id", "")).split(".")
        if (len(parts) != 5 or "/".join(parts[:2]) != event["id"] or parts[2] != "0"
                or market.get("stat") != "home runs" or parts[4] != "hr"):
            continue
        player = market.get("player") or {}
        name = " ".join(str(player.get(k) or "").strip() for k in ("first_name", "last_name")).strip()
        if not name or not player.get("last_name"):
            continue
        for book, offer in (market.get("comparison") or {}).items():
            price = number(offer.get("over"))
            if (book not in BOOKS or book not in payload.get("books", {})
                    or offer.get("available") is not True or number(offer.get("value")) != .5
                    or price is None or abs(price) < 100):
                continue
            rows.append({"game_id": str(game["game_id"]), "player_key": key(name), "player_name": name,
                         "player_team": team_key((player.get("team") or {}).get("hashtag", "")),
                         "book": book, "price": price, "event_id": event["id"],
                         "updated": observed, "timestamp_kind": "observed", "provider": "scoresandodds",
                         "selection_id": (offer.get("metadata") or {}).get("over", ""),
                         "source_url": SCOREBOARD + "/props/home-runs"})
    return rows


def jedi_prices(html, games, observed):
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one("h1")
    if (not heading or "mlbanytimehomerunodds" not in key(heading.get_text(" ", strip=True))
            or not soup.select_one(".po-row[data-odds]")):
        return []
    now = utc(observed)
    groups, current = [], None
    for row in soup.select(".po-row"):
        if "po-game-start" in row.get("class", []):
            current = None
            stamp = row.select_one(".po-time")
            if stamp:
                # The public board prints month/day and ET; bind to the observed year.
                label = stamp.get_text(" ", strip=True).replace("\u00b7", "|")
                try:
                    parsed = datetime.strptime(f"{now.year} {label}", "%Y %I:%M %p ET | %a, %b %d")
                    start = parsed.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
                    current = {"start": start, "home": team_key(row.get("data-home")),
                               "away": team_key(row.get("data-away")), "rows": []}
                    groups.append(current)
                except ValueError:
                    pass
        if current is not None and team_key(row.get("data-home")) == current["home"] and team_key(row.get("data-away")) == current["away"]:
            current["rows"].append(row)
    events = []
    for i, group in enumerate(groups):
        matching = [g for g in games if team_key(g.get("home_abbrev")) == group["home"]
                    and team_key(g.get("away_abbrev")) == group["away"]]
        if matching:
            events.append({"id": f"jedi:{i}", "home_team": matching[0]["home_team"],
                           "away_team": matching[0]["away_team"], "commence_time": group["start"].isoformat(), "group": group})
    rows = []
    for gid, event in match_events(games, events).items():
        for row in event["group"]["rows"]:
            try:
                prices = json.loads(row.get("data-odds", "{}"))
            except (ValueError, TypeError):
                continue
            # Only DK belongs to our allowlist among the four explicitly free books.
            price = number(prices.get("dk")) if isinstance(prices, dict) else None
            name = row.get("data-pick", "").strip()
            if name and price is not None and abs(price) >= 100:
                rows.append({"game_id": gid, "player_key": key(name), "player_name": name,
                             "book": "draftkings", "price": price,
                             "event_id": f"{event['home_team']}:{event['away_team']}:{event['commence_time']}",
                             "updated": observed, "timestamp_kind": "observed", "provider": "jedibets",
                             "source_url": JEDI})
    return rows


# Explicit spelling/nickname equivalents observed across the public boards and GBM.
NAME_ALIASES = {"mikebusch": "michaelbusch", "cameronsmith": "camsmith",
                "mikemassey": "michaelmassey", "michaelgasper": "mickeygasper",
                "benjaminjosephmalgeri": "benmalgeri"}


def identity_name(value):
    normalized = key(value)
    normalized = re.sub(r"(jr|sr|iii|ii|iv)$", "", normalized)
    return NAME_ALIASES.get(normalized, normalized)


def align_prices(prices, frame, games):
    """Resolve only unique roster identities within one game; never fuzzy-match initials."""
    game_index = {str(g["game_id"]): g for g in games}
    roster = {}
    for player in frame.fillna("").to_dict("records"):
        gid = str(player.get("game_id", "")).removesuffix(".0")
        game = game_index.get(gid, {})
        team = player.get("team_abbrev") or game.get(f"{player.get('home_away')}_abbrev", "")
        identity = (gid, identity_name(player.get("player_name", "")))
        roster.setdefault(identity, []).append((player, team_key(team)))
    output, identities = [], {}
    for quote in prices:
        candidates = roster.get((str(quote["game_id"]), identity_name(quote.get("player_name", ""))), [])
        if quote.get("player_team"):
            candidates = [c for c in candidates if c[1] == team_key(quote["player_team"])]
        if len(candidates) != 1:
            continue
        player = candidates[0][0]
        row = {**quote, "source_player_name": quote.get("player_name", ""),
               "player_key": key(player["player_name"]), "player_name": player["player_name"],
               "player_id": str(player["player_id"]).removesuffix(".0")}
        identity = (row["game_id"], row["player_key"], row["book"])
        identities.setdefault(identity, []).append(row)
    for values in identities.values():
        # Conflicting alias prices from a single snapshot require review, not optimism.
        if len({v["price"] for v in values}) == 1:
            output.append(values[0])
    return output


def merge_quote_sources(primary: list[dict], supplemental: list[dict]) -> list[dict]:
    """Append supplemental quotes only when that exact game/player/book is absent."""
    output = list(primary)
    seen = {(str(row.get("game_id")), row.get("player_key"), row.get("book")) for row in output}
    for quote in supplemental:
        identity = (str(quote.get("game_id")), quote.get("player_key"), quote.get("book"))
        if quote.get("book") not in BOOKS or identity in seen:
            continue
        output.append(quote)
        seen.add(identity)
    return output


class PublicFeed:
    def __init__(self, cache_dir=CACHE):
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.last_request = 0.

    def read(self, url, params=None):
        import hashlib
        cache_key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / f"{cache_key}.json" if self.cache_dir else None
        now = datetime.now(timezone.utc)
        if path and path.exists():
            try:
                cached = json.loads(path.read_text())
                stamp = utc(cached["observed"])
                if stamp and 0 <= (now - stamp).total_seconds() < 300:
                    return cached["body"], cached["observed"]
            except (OSError, ValueError, KeyError, TypeError):
                pass
        time.sleep(max(0., 1. - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        try:
            response = requests.get(url, params=params, timeout=(10, 30),
                                    headers={"User-Agent": "Model4-DailyBaseball/1.0 (public odds comparison)"})
        except requests.RequestException:
            raise RuntimeError("Public odds connection failed; no old quotes were substituted.") from None
        if response.status_code != 200:
            raise RuntimeError(f"Public odds returned HTTP {response.status_code}; no access-bypass retry attempted.")
        try:
            server_time = parsedate_to_datetime(response.headers["Date"])
            age = float(response.headers.get("Age", 0))
            if not -60 <= (datetime.now(timezone.utc) - server_time).total_seconds() <= 900 or not 0 <= age <= 900:
                raise ValueError("stale")
        except (KeyError, ValueError, TypeError, OverflowError):
            raise RuntimeError("Public odds response has missing or stale timestamp metadata.") from None
        observed = server_time.isoformat()
        body = response.text
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps({"body": body, "observed": observed}))
            temp.replace(path)
        return body, observed


def fetch_prices(games, api_key="", *, cache_dir=CACHE):
    # api_key is accepted only for the provider interface; it is never sent anywhere.
    games = active_games(games, datetime.now(timezone.utc))
    if not games:
        return [], ["Public comparison: no remaining pregame MLB events on this slate."]
    feed = PublicFeed(cache_dir)
    rows, warnings = [], []
    try:
        html, _ = feed.read(SCOREBOARD)
        events = scoreboard_events(html, games)
        matches = match_events(games, events)
        if not matches:
            warnings.append("ScoresAndOdds: no unambiguous current-slate events found.")
        for game in games:
            event = matches.get(str(game["game_id"]))
            if not event:
                continue
            try:
                body, observed = feed.read(COMPARISON, {"event": event["id"], "market": "home runs"})
                payload = json.loads(body)
                if not isinstance(payload, dict) or not isinstance(payload.get("markets"), list):
                    raise ValueError("Unexpected comparison schema")
                rows.extend(comparison_prices(payload, game, event, observed))
            except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
                warnings.append(f"ScoresAndOdds {game['game_id']}: {exc}")
                if "HTTP 429" in str(exc) or "HTTP 403" in str(exc):
                    break
    except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
        warnings.append(f"ScoresAndOdds: {exc}")
    try:
        html, observed = feed.read(JEDI)
        # Prefer a JSON comparison quote when that book/game/player is already present.
        seen = {(r["game_id"], r["player_key"], r["book"]) for r in rows}
        rows.extend(r for r in jedi_prices(html, games, observed)
                    if (r["game_id"], r["player_key"], r["book"]) not in seen)
    except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
        warnings.append(f"JediBets: {exc}")
    for book in BOOKS:
        if not any(r["book"] == book for r in rows):
            warnings.append(f"Public comparison: {book} HR prices unavailable; no substitute book or estimated odds used.")
    warnings.append("Public comparison timestamps show when the feed was observed, not when the sportsbook last changed its price. Confirm the price in the book before betting.")
    return rows, warnings
