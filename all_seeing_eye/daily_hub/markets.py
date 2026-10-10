from __future__ import annotations

from datetime import datetime, timezone
import math
import re
import unicodedata

import pandas as pd


BOOKS = {"draftkings": "dk_odds", "fanatics": "fan_odds", "bet365": "365_odds"}
BOOK_NAMES = {"draftkings": "DraftKings", "fanatics": "Fanatics", "bet365": "Bet365"}


def key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]", "", text.encode("ascii", "ignore").decode().lower())


def number(value: object) -> float | None:
    try:
        result = float(str(value).replace("+", "").replace("%", ""))
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def utc(value: object) -> datetime | None:
    try:
        return pd.Timestamp(value).to_pydatetime().astimezone(timezone.utc) if value else None
    except (ValueError, TypeError):
        return None


def is_pregame(game: dict, now: datetime) -> bool:
    status, detail = game.get("status"), game.get("detailed_status", "")
    # MLB reports Warmup under the Live umbrella before the scheduled first pitch.
    pregame = ((status == "Preview" and detail in {"", "Scheduled", "Pre-Game", "Warmup"})
               or (status == "Live" and detail == "Warmup"))
    return pregame and (utc(game.get("start_time")) or now) > now


def get_json(url: str, params: dict | None = None) -> dict | list:
    import requests
    # Never include the request URL in exceptions: query strings contain API keys.
    try:
        response = requests.get(url, params=params, timeout=(10, 40))
        if response.status_code != 200:
            raise RuntimeError(f"Data provider returned HTTP {response.status_code}")
        return response.json()
    except requests.RequestException:
        raise RuntimeError("Data provider connection failed; retry the refresh.") from None


def fetch_context(day: str) -> tuple[list[dict], list[dict]]:
    payload = get_json("https://statsapi.mlb.com/api/v1/schedule", {"sportId": 1, "date": day, "hydrate": "team"})
    games, starters = [], []
    for entry in payload.get("dates", []):
        for game in entry.get("games", []):
            teams = game["teams"]
            record = {"game_id": str(game["gamePk"]), "game_date": day,
                      "start_time": game.get("gameDate", ""), "game_number": game.get("gameNumber", 1),
                      "status": game.get("status", {}).get("abstractGameState", ""),
                      "detailed_status": game.get("status", {}).get("detailedState", "")}
            for side in ("home", "away"):
                team = teams[side]["team"]
                record[f"{side}_team"] = team["name"]
                record[f"{side}_abbrev"] = team.get("abbreviation", "")
                record[f"{side}_id"] = str(team["id"])
            games.append(record)
            box = get_json(f"https://statsapi.mlb.com/api/v1/game/{game['gamePk']}/boxscore")
            for side in ("home", "away"):
                roster = box.get("teams", {}).get(side, {})
                for player in roster.get("players", {}).values():
                    order = str(player.get("battingOrder", ""))
                    # Substitutes use 101, 102 etc.; only the original starter ends in 00.
                    if not (order.isdigit() and int(order) % 100 == 0 and 100 <= int(order) <= 900):
                        continue
                    starters.append({"game_id": record["game_id"], "player_id": str(player["person"]["id"]),
                                     "team_abbrev": record[f"{side}_abbrev"], "batting_order": int(order) // 100})
    return games, starters


def match_events(games: list[dict], events: list[dict]) -> dict[str, dict]:
    """Match independently identified games, refusing ambiguous doubleheader events."""
    proposals = []
    for game in games:
        pair = {key(game["home_team"]), key(game["away_team"])}
        start = utc(game.get("start_time"))
        if start is None:
            continue
        candidates = []
        for event in events:
            if {key(event.get("home_team")), key(event.get("away_team"))} != pair:
                continue
            other = utc(event.get("commence_time"))
            if other is not None:
                distance = abs((other - start).total_seconds())
                if distance <= 5400:
                    candidates.append((distance, event))
        candidates.sort(key=lambda item: item[0])
        if candidates and (len(candidates) == 1 or candidates[1][0] - candidates[0][0] > 900):
            proposals.append((candidates[0][0], str(game["game_id"]), candidates[0][1]))
    matches, used = {}, set()
    for _, game_id, event in sorted(proposals, key=lambda item: item[0]):
        if event["id"] not in used:
            matches[game_id] = event
            used.add(event["id"])
    return matches


def fetch_prices(games: list[dict], api_key: str) -> tuple[list[dict], list[str]]:
    if not api_key:
        return [], ["Odds API key is unavailable. Saved prices remain visible; live posting requires a fresh quote or manual odds."]
    base = "https://api.the-odds-api.com/v4/sports/baseball_mlb"
    events = get_json(base + "/events", {"apiKey": api_key})
    matches = match_events(games, events)
    rows, warnings = [], []
    now = datetime.now(timezone.utc)
    for game in games:
        game_id = str(game["game_id"])
        if not is_pregame(game, now):
            continue
        event = matches.get(game_id)
        if not event:
            warnings.append(f"Game {game_id}: no unambiguous odds event yet.")
            continue
        try:
            payload = get_json(base + f"/events/{event['id']}/odds", {
                "apiKey": api_key, "bookmakers": "draftkings,fanatics",
                "markets": "batter_home_runs", "oddsFormat": "american"})
        except RuntimeError as exc:
            warnings.append(f"Game {game_id}: {exc}")
            continue
        for book in payload.get("bookmakers", []):
            if book.get("key") not in BOOKS:
                continue
            for market in book.get("markets", []):
                if market.get("key") != "batter_home_runs":
                    continue
                for outcome in market.get("outcomes", []):
                    price = number(outcome.get("price"))
                    if outcome.get("name") == "Over" and outcome.get("point") == 0.5 and price is not None and abs(price) >= 100:
                        rows.append({"game_id": game_id, "player_key": key(outcome.get("description")),
                                     "book": book["key"], "price": price, "event_id": event["id"],
                                     "updated": market.get("last_update", book.get("last_update", ""))})
    warnings.append("The Odds API does not cover US bet365 MLB props; those prices require another provider or a manual quote.")
    for book in ("draftkings", "fanatics"):
        if not any(row["book"] == book for row in rows):
            warnings.append(f"No pregame HR quotes returned for {book}; market or subscription coverage may be unavailable.")
    return rows, warnings


def prepare_market_board(frame: pd.DataFrame, games: list[dict], starters: list[dict], prices: list[dict],
                         overrides: list[dict], *, live: bool, confirmed_only: bool = False,
                         as_of: datetime | None = None) -> pd.DataFrame:
    games_by_id = {str(g["game_id"]): g for g in games}
    starter_keys = {(str(s["game_id"]), str(s["player_id"])): s for s in starters}
    confirmed_teams = {(str(s["game_id"]), s["team_abbrev"]) for s in starters}
    manual = {(str(o["game_id"]), str(o["player_id"])): o for o in overrides}
    price_index: dict[tuple, list] = {}
    for price in prices:
        price_index.setdefault((str(price["game_id"]), price["player_key"]), []).append(price)
    output = []
    now = as_of or datetime.now(timezone.utc)
    for source in frame.fillna("").to_dict("records"):
        row = dict(source)
        gid = str(row.get("game_id", "")).removesuffix(".0")
        pid = str(row.get("player_id", "")).removesuffix(".0")
        row.update(game_id=gid, player_id=pid)
        game = games_by_id.get(gid, {})
        team = row.get("team_abbrev", "")
        if not team and game:
            side = "home" if row.get("home_away") == "home" else "away"
            team = game.get(f"{side}_abbrev") or game.get(f"{side}_team_abbrev", "")
        row.update(team_abbrev=team, game_number=game.get("game_number", ""), start_time=game.get("start_time", ""))
        starter = starter_keys.get((gid, pid))
        if live:
            row["lineup_status"] = "confirmed" if starter else ("out" if (gid, team) in confirmed_teams else "not_confirmed")
            if starter:
                row["batting_order"] = starter["batting_order"]
            # Never reuse a disappeared market as though it had just been quoted.
            for col in ["book_american_odds", "bookmaker_used", "edge_percent", "odds_last_update", "odds_source", "odds_event_id", "odds_timestamp_kind", "odds_source_url", *BOOKS.values()]:
                row[col] = ""
            offers = price_index.get((gid, key(row.get("player_name"))), [])
            if offers:
                for offer in offers:
                    row[BOOKS[offer["book"]]] = offer["price"]
                best = max(offers, key=lambda x: decimal_odds(x["price"]))
                row.update(book_american_odds=best["price"], bookmaker_used=BOOK_NAMES[best["book"]],
                           odds_last_update=best["updated"], odds_event_id=best["event_id"], odds_source=best.get("provider", "the_odds_api"),
                           odds_timestamp_kind=best.get("timestamp_kind", "book_updated"),
                           odds_source_url=best.get("source_url", ""))
        override = manual.get((gid, pid), {})
        if override.get("out"):
            row["lineup_status"] = "out"
        odds = number(override.get("odds"))
        if odds is not None and abs(odds) >= 100:
            row.update(book_american_odds=odds, bookmaker_used=override.get("sportsbook") or "Manual",
                       odds_source="manual", odds_last_update=override.get("updated", ""),
                       odds_timestamp_kind="manual", odds_source_url="", odds_event_id="")
            for col in BOOKS.values():
                row[col] = ""
        odds = number(row.get("book_american_odds"))
        probability = number(row.get("adjusted_hr_probability_percent"))
        if odds is not None and abs(odds) >= 100 and probability is not None:
            row["edge_percent"] = probability - 100 / decimal_odds(odds)
        reasons = []
        if live and not is_pregame(game, now):
            reasons.append("Game started, finished, postponed, or schedule unavailable")
        if row.get("lineup_status") == "out":
            reasons.append("Not starting / marked out")
        elif confirmed_only and row.get("lineup_status") != "confirmed":
            reasons.append("Waiting for confirmed lineup")
        if odds is None or abs(odds) < 100:
            reasons.append("Waiting for sportsbook odds")
        row["ready"] = not reasons
        row["pending_reason"] = "; ".join(reasons)
        output.append(row)
    result = pd.DataFrame(output)
    if not result.empty:
        result["_name"] = result["player_name"].map(key)
        # Model 4 merges by player name: allow only one ready game per hitter.
        ready = result[result["ready"]].sort_values(["start_time", "game_id"], kind="stable")
        duplicate = ready[ready.duplicated("_name")].index
        result.loc[duplicate, "ready"] = False
        result.loc[duplicate, "pending_reason"] = "Later doubleheader game; recheck after earlier game"
        result = result.drop(columns="_name")
    return result


def decimal_odds(american: float) -> float:
    return 1 + american / 100 if american > 0 else 1 + 100 / abs(american)

