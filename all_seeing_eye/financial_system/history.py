"""Independent financial snapshots, prospective cohort, and explicitly recorded stakes."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import pandas as pd

from .pricing import ev, break_even


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@contextmanager
def database(root):
    path = Path(root) / "DAILY_BASEBALL" / "financial" / "history.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute("CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, day TEXT, player_key TEXT, payload TEXT, captured TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS cohort (identity TEXT PRIMARY KEY, snapshot_id TEXT, result TEXT DEFAULT 'Pending')")
    db.execute("CREATE TABLE IF NOT EXISTS wagers (identity TEXT PRIMARY KEY, snapshot_id TEXT, units REAL, odds REAL, recorded TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS wager_entries (identity TEXT PRIMARY KEY, placed_at TEXT, entry_method TEXT, sportsbook TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS result_cache (game_id TEXT, player_id TEXT, day TEXT, payload TEXT, fetched TEXT, PRIMARY KEY(game_id,player_id))")
    db.execute("CREATE TABLE IF NOT EXISTS outcomes (game_id TEXT, player_id TEXT, result TEXT, settled TEXT, PRIMARY KEY(game_id,player_id))")
    try:
        with db:
            yield db
    finally:
        db.close()


def identity(row):
    return row["date"] + ":" + row["player_key"]


def capture(root, rows, snapshot):
    now = datetime.now(timezone.utc)
    result = []
    with database(root) as db:
        for source in rows:
            row = clean(source)
            sid = hashlib.sha256((str(snapshot)+json.dumps(row,sort_keys=True,allow_nan=False)).encode()).hexdigest()
            row["snapshot_id"] = sid
            payload = json.dumps(row, allow_nan=False)
            db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?)", (sid, row["date"], row["player_key"], payload, now.isoformat()))
            try:
                pregame = datetime.fromisoformat(row["start_time"].replace("Z", "+00:00")) > now
            except (ValueError, KeyError):
                pregame = False
            if pregame:
                db.execute("INSERT OR IGNORE INTO cohort(identity,snapshot_id) VALUES(?,?)", (identity(row), sid))
            result.append(row)
    return result


def read(root, actual=False):
    with database(root) as db:
        sql = ("SELECT s.payload,w.units,w.odds,w.recorded FROM wagers w JOIN snapshots s ON s.id=w.snapshot_id" if actual else
               "SELECT s.payload,0,NULL,s.captured FROM cohort c JOIN snapshots s ON s.id=c.snapshot_id")
        fetched = db.execute(sql).fetchall()
        outcomes = {(str(g), str(p)): r for g,p,r in db.execute("SELECT game_id,player_id,result FROM outcomes")}
        provisional = {(str(g),str(p)) for g,p,payload in db.execute("SELECT game_id,player_id,payload FROM result_cache")
                       if json.loads(payload).get("is_final") is False}
        entries = {key: (placed, method, book) for key,placed,method,book in
                   db.execute("SELECT identity,placed_at,entry_method,sportsbook FROM wager_entries")}
    rows = []
    for payload, units, odds, recorded in fetched:
        row = json.loads(payload)
        row.update(actual_units_bet=units, actual_american_odds=odds, recorded=recorded,
                   result=outcomes.get((row["game_id"], row["player_id"]), "Pending"),
                   result_provisional=(row["game_id"],row["player_id"]) in provisional)
        if actual:
            placed, method, book = entries.get(identity(row), (recorded, "Recorded pregame", row.get("sportsbook", "")))
            row.update(placed_at=placed, entry_method=method, actual_sportsbook=book)
        row["result_hr"] = 1 if row["result"] == "HR" else 0 if row["result"] == "No HR" else None
        row["profit_units"] = units*ev(row["result_hr"], odds) if actual and row["result_hr"] is not None else 0 if row["result"] == "Void" else None
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["date", "placed_at" if actual else "recorded", "player_key"]) if rows else pd.DataFrame()


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Enter a valid placement time.") from exc
    if parsed.tzinfo is None:
        raise ValueError("Placement time must include a timezone.")
    return parsed


def bet_snapshots(root, day=None):
    """Only genuine captured pregame BET snapshots can support a later ledger entry."""
    with database(root) as db:
        sql = "SELECT payload,captured FROM snapshots"
        fetched = db.execute(sql + (" WHERE day=?" if day else ""), (day,) if day else ()).fetchall()
    rows = []
    for payload, captured in fetched:
        row = json.loads(payload)
        try:
            eligible = row.get("decision") == "BET" and timestamp(captured) < timestamp(row["start_time"])
        except (ValueError, KeyError):
            eligible = False
        if eligible:
            rows.append(dict(row, captured_at=captured))
    return sorted(rows, key=lambda r: r["captured_at"])


def record_earlier(root, day, player_key, placed_at, units, odds, sportsbook=None):
    placed = timestamp(placed_at)
    eligible = [r for r in bet_snapshots(root, day)
                if r["player_key"] == player_key and timestamp(r["captured_at"]) <= placed < timestamp(r["start_time"])]
    if not eligible:
        raise ValueError("No saved pregame BET decision exists for this player at or before that placement time.")
    row = eligible[-1]
    record(root, row["snapshot_id"], units, odds, placed_at=placed.isoformat(),
           late_entry=True, sportsbook=sportsbook)
    return row["snapshot_id"]


def record(root, snapshot_id, units, odds, *, placed_at=None, late_entry=False, sportsbook=None):
    units, odds = float(units), float(odds)
    if not math.isfinite(units) or units <= 0:
        raise ValueError("Actual stake must be positive.")
    break_even(odds)
    now = datetime.now(timezone.utc)
    if late_entry and placed_at is None:
        raise ValueError("Enter when you actually placed the earlier wager.")
    if placed_at is not None and not late_entry:
        raise ValueError("Use the earlier-bet workflow to supply a past placement time.")
    placed = timestamp(placed_at) if late_entry else now
    if placed > now:
        raise ValueError("Placement time cannot be in the future.")
    with database(root) as db:
        found = db.execute("SELECT payload,captured FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if not found:
            raise ValueError("Unknown decision snapshot.")
        row = json.loads(found[0])
        start, captured = timestamp(row["start_time"]), timestamp(found[1])
        if captured >= start:
            raise ValueError("A post-start snapshot cannot support a pregame wager.")
        if placed < captured:
            raise ValueError("This decision was captured after the time you placed the wager.")
        if placed >= start:
            raise ValueError("This game has started; log an earlier bet with its actual pregame placement time.")
        if row["decision"] != "BET":
            raise ValueError("Only BET decisions can be recorded in the financial wager ledger.")
        if db.execute("SELECT 1 FROM wagers WHERE identity=?", (identity(row),)).fetchone():
            raise ValueError("This player already has a recorded financial wager today.")
        db.execute("INSERT INTO wagers VALUES(?,?,?,?,?)", (identity(row), snapshot_id, units, odds, now.isoformat()))
        db.execute("INSERT INTO wager_entries VALUES(?,?,?,?)",
                   (identity(row), placed.astimezone(timezone.utc).isoformat(), "Logged later" if late_entry else "Recorded pregame",
                    str(sportsbook or row.get("sportsbook") or "")))


def remove_record(root, player_identity):
    with database(root) as db:
        found = db.execute("SELECT s.payload FROM wagers w JOIN snapshots s ON s.id=w.snapshot_id WHERE w.identity=?", (player_identity,)).fetchone()
        if not found:
            raise ValueError("No recorded wager found.")
        row = json.loads(found[0])
        if datetime.fromisoformat(row["start_time"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise ValueError("This game has started; the wager record is locked.")
        db.execute("DELETE FROM wagers WHERE identity=?", (player_identity,))
        db.execute("DELETE FROM wager_entries WHERE identity=?", (player_identity,))


def bankroll(root, config):
    actual = read(root, actual=True)
    return config.starting_bankroll + (actual.profit_units.fillna(0).sum() if not actual.empty else 0)


@contextmanager
def results_lock(root):
    import fcntl
    import time
    path = Path(root) / "DAILY_BASEBALL/financial/results.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock:
        deadline = time.monotonic()+60
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Another portfolio results update is running. Please retry shortly.")
                time.sleep(.1)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def tracked_positions(root, before=None, day=None):
    with database(root) as db:
        fetched = db.execute(
            "SELECT s.payload FROM snapshots s JOIN "
            "(SELECT snapshot_id FROM cohort UNION SELECT snapshot_id FROM wagers) t "
            "ON s.id=t.snapshot_id").fetchall()
    unique = {}
    for payload, in fetched:
        row = json.loads(payload)
        if before and row["date"] > before or day and row["date"] != day:
            continue
        unique[(row["date"], row["game_id"], row["player_id"])] = row
    return list(unique.values())


def outcome_from_result(actual):
    from ..edge_buckets import result_void_reason
    from .data import finite
    if actual is None:
        return None
    hr = finite(actual.get("actual_hr"))
    pa, ab = finite(actual.get("actual_pa")), finite(actual.get("actual_ab"))
    if hr is None or hr < 0 or pa is None and ab is None:
        return None
    return "Void" if result_void_reason(actual) else "HR" if hr > 0 else "No HR"


def write_outcome(db, gid, pid, actual):
    result = outcome_from_result(actual)
    if result is None:
        return "unresolved"
    previous = db.execute("SELECT result FROM outcomes WHERE game_id=? AND player_id=?", (gid,pid)).fetchone()
    if previous and previous[0] == result:
        return "unchanged"
    db.execute("INSERT INTO outcomes VALUES(?,?,?,?) ON CONFLICT(game_id,player_id) "
               "DO UPDATE SET result=excluded.result,settled=excluded.settled",
               (gid,pid,result,datetime.now(timezone.utc).isoformat()))
    return "corrected" if previous else "newly_graded"


def settle(root, results_dir, before, schedule_loader=None):
    from ..daily_hub.markets import get_json
    loader = schedule_loader or (lambda day: get_json("https://statsapi.mlb.com/api/v1/schedule", {"sportId":1,"date":day}))
    with results_lock(root):
        payloads = tracked_positions(root, before=before)
        updates = 0
        for day in sorted({r["date"] for r in payloads}):
            path = Path(results_dir) / f"daily_results_{day}.csv"
            records = {}
            if path.exists():
                frame = pd.read_csv(path, dtype=str).fillna("")
                records = {(r["game_id"],r["player_id"]): r for r in frame.to_dict("records")}
            with database(root) as db:
                cached = {(g,p): json.loads(value) for g,p,value in db.execute(
                    "SELECT game_id,player_id,payload FROM result_cache WHERE day=?", (day,))}
            if not records and not cached:
                continue
            schedule = loader(day)
            final = {str(g["gamePk"]) for d in schedule.get("dates", []) for g in d.get("games", [])
                     if g.get("status", {}).get("abstractGameState") == "Final"}
            identities = {(r["game_id"],r["player_id"]) for r in payloads if r["date"] == day}
            with database(root) as db:
                for gid,pid in identities:
                    # Official fetched final boxes take precedence over possibly older generic CSVs.
                    if (gid,pid) in cached and cached[(gid,pid)].get("is_final", True):
                        actual = cached[(gid,pid)]
                    elif gid in final:
                        actual = records.get((gid,pid))
                    else:
                        continue
                    if write_outcome(db,gid,pid,actual) in {"newly_graded","corrected"}:
                        updates += 1
                    if actual is not None and (gid,pid) in cached and cached[(gid,pid)].get("is_final") is False:
                        db.execute("DELETE FROM result_cache WHERE game_id=? AND player_id=?", (gid,pid))
        return updates


