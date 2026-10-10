"""Personal wager bookkeeping, independent of model eligibility and game timing."""
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import uuid

import pandas as pd

from . import history
from .config import Config
from .pricing import break_even, bucket
from ..daily_hub.markets import key


def player_options(root, day):
    options = {}
    folders = sorted((Path(root)/"DAILY_BASEBALL/runs"/day).glob("*/market_board.csv"), reverse=True)
    if folders:
        for r in pd.read_csv(folders[0], dtype=str).fillna("").to_dict("records"):
            gid, pid = str(r.get("game_id", "")), str(r.get("player_id", ""))
            options[(gid,pid)] = dict(player=r["player_name"], player_key=key(r["player_name"]),
                                      game_id=gid, player_id=pid, team=r.get("team_abbrev", ""),
                                      opponent=r.get("opponent_abbrev", ""), start_time=r.get("start_time", ""),
                                      american_odds=r.get("book_american_odds"), sportsbook=r.get("bookmaker_used", ""),
                                      game_number=r.get("game_number", ""))
    with history.database(root) as db:
        saved = db.execute("SELECT payload,captured FROM snapshots WHERE day=? ORDER BY captured", (day,)).fetchall()
    for payload, captured in saved:
        r = json.loads(payload)
        pair = (str(r.get("game_id", "")), str(r.get("player_id", "")))
        existing = options.setdefault(pair, {field:r.get(field) for field in
                                            ["player","player_key","game_id","player_id","team","opponent",
                                             "start_time","american_odds","sportsbook"]})
        try:
            pregame = history.timestamp(captured) < history.timestamp(r["start_time"])
        except (ValueError, KeyError):
            pregame = False
        if pregame and not existing.get("prediction") and r.get("probability_method") != "Not modeled":
            existing["prediction"] = r
    return sorted(options.values(), key=lambda r: (r["player"], r.get("start_time") or ""))


def log_bet(root, day, player, units, odds, sportsbook="", *, context=None, replace=False):
    day = date.fromisoformat(str(day)).isoformat()
    player = str(player).strip()
    if not player:
        raise ValueError("Enter a player.")
    units, odds = float(units), float(odds)
    if not math.isfinite(units) or units <= 0:
        raise ValueError("Stake must be greater than zero.")
    break_even(odds)
    context = context or {}
    name_key = key(player)
    ident = day + ":" + name_key
    row = dict(context.get("prediction") or {})
    row.update(date=day, player=player, player_key=name_key,
               game_id=str(context.get("game_id") or row.get("game_id") or "unmatched:"+day+":"+name_key),
               player_id=str(context.get("player_id") or row.get("player_id") or "unmatched:"+name_key),
               team=context.get("team") or row.get("team") or "Unknown",
               opponent=context.get("opponent") or row.get("opponent") or "",
               start_time=context.get("start_time") or row.get("start_time") or "",
               american_odds=odds, sportsbook=str(sportsbook).strip(),
               price_bucket=bucket(odds, Config()), bet_origin="Personal bet log")
    defaults = dict(decision="MANUAL", recommended_units=0., estimated_hr_probability=None,
                    probability_method="Not modeled", alpha=None, beta=None, p_positive_ev=None,
                    signal_families=[], model_families=[], signal_labels=[], independent_family_count=0,
                    model_version="manual", config_version="manual")
    for field, value in defaults.items():
        row.setdefault(field, value)
    sid = "manual-" + uuid.uuid4().hex
    row["snapshot_id"] = sid
    now = datetime.now(timezone.utc).isoformat()
    with history.database(root) as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT snapshot_id,units,odds,recorded FROM wagers WHERE identity=?", (ident,)).fetchone()
        if previous and not replace:
            raise ValueError("This player already has a bet for this date. Use Update Bet to change it.")
        db.execute("CREATE TABLE IF NOT EXISTS wager_edits (identity TEXT, edited TEXT, previous TEXT)")
        if previous:
            db.execute("INSERT INTO wager_edits VALUES(?,?,?)", (ident, now, json.dumps(previous)))
        db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)",
                   (sid, day, name_key, json.dumps(history.clean(row)), now))
        db.execute("INSERT INTO wagers VALUES(?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET "
                   "snapshot_id=excluded.snapshot_id,units=excluded.units,odds=excluded.odds,recorded=excluded.recorded",
                   (ident, sid, units, odds, now))
        db.execute("INSERT INTO wager_entries VALUES(?,?,?,?) ON CONFLICT(identity) DO UPDATE SET "
                   "entry_method=excluded.entry_method,sportsbook=excluded.sportsbook",
                   (ident, None, "Personal bet log", str(sportsbook).strip()))
    return sid

