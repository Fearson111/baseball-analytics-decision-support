from __future__ import annotations

from datetime import date, datetime, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3

import pandas as pd

from .markets import key, number, decimal_odds, get_json


@contextmanager
def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute("CREATE TABLE IF NOT EXISTS tickets (ticket_id TEXT PRIMARY KEY, day TEXT, kind TEXT, signal TEXT, snapshot TEXT, payload TEXT, result TEXT DEFAULT 'Pending', profit REAL)")
    try:
        with db:
            yield db
    finally:
        db.close()


def capture(path: Path, day: str, snapshot: str, straight: pd.DataFrame, parlays: pd.DataFrame, market: pd.DataFrame):
    available = {key(r["player_name"]): r for r in market[market["ready"]].to_dict("records")}
    labels = {}
    for source in (Path(snapshot) / "PROFIT_PARLAYS").glob("profit_parlays*combined.csv"):
        for record in pd.read_csv(source, dtype=str).fillna("").to_dict("records"):
            names = tuple(sorted(key(record.get(f"leg{i}_player", "")) for i in range(1, 5) if record.get(f"leg{i}_player")))
            if names:
                labels.setdefault(names, set()).add(record.get("parlay", ""))
    rows = []
    for row in straight.to_dict("records"):
        player = available[key(row["player"])]
        rows.append(("straight", row["signal"], [{"player": row["player"], "game_id": player["game_id"],
                     "player_id": player["player_id"], "odds": row["odds"], "sportsbook": row["sportsbook"]}], decimal_odds(float(row["odds"]))))
    for row in parlays.to_dict("records"):
        legs = []
        for i in range(1, 5):
            name = str(row.get(f"leg{i}", ""))
            if not name:
                continue
            player = available.get(key(name))
            if player is None:
                break
            legs.append({"player": name, "game_id": player["game_id"], "player_id": player["player_id"],
                         "odds": row[f"odds{i}"], "sportsbook": player["bookmaker_used"]})
        else:
            if len(legs) >= 2:
                names = tuple(sorted(key(leg["player"]) for leg in legs))
                signal = " | ".join(sorted(labels.get(names, set()))) or row["parlay_test_group"]
                rows.append(("parlay", signal, legs, decimal_odds(float(row["parlay_odds"])) ))
    with connect(path) as db:
        for kind, signal, legs, total in rows:
            identity = [day, kind, signal if kind == "straight" else "", sorted((str(l["game_id"]), str(l["player_id"])) for l in legs)]
            ticket_id = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
            payload = json.dumps({"legs": legs, "decimal_odds": total, "captured": datetime.now(timezone.utc).isoformat()})
            db.execute("INSERT OR IGNORE INTO tickets(ticket_id,day,kind,signal,snapshot,payload) VALUES(?,?,?,?,?,?)",
                       (ticket_id, day, kind, signal, snapshot, payload))


def grade(path: Path, results_dir: Path, before: str) -> int:
    from ..edge_buckets import result_void_reason
    if not path.exists():
        return 0
    updates = 0
    with connect(path) as db:
        pending = db.execute("SELECT ticket_id,day,payload FROM tickets WHERE result='Pending' AND day < ?", (before,)).fetchall()
        results, finals = {}, {}
        for _, day, _ in pending:
            if day in results:
                continue
            result_file = results_dir / f"daily_results_{day}.csv"
            if not result_file.exists():
                continue
            frame = pd.read_csv(result_file, dtype=str).fillna("")
            results[day] = {(r["game_id"], r["player_id"]): r for r in frame.to_dict("records")}
            schedule = get_json("https://statsapi.mlb.com/api/v1/schedule", {"sportId": 1, "date": day})
            finals[day] = {str(g["gamePk"]) for d in schedule.get("dates", []) for g in d.get("games", [])
                           if g.get("status", {}).get("abstractGameState") == "Final"}
        for ticket_id, day, raw in pending:
            data = json.loads(raw)
            if day not in results or not all(str(l["game_id"]) in finals[day] for l in data["legs"]):
                continue
            leg_results = [results[day].get((str(l["game_id"]), str(l["player_id"]))) for l in data["legs"]]
            if any(result_void_reason(r) for r in leg_results):
                result, profit = "Void", 0.0
            elif all((number(r.get("actual_hr")) or 0) > 0 for r in leg_results):
                result, profit = "HR", data["decimal_odds"] - 1
            else:
                result, profit = "No HR", -1.0
            for leg, actual in zip(data["legs"], leg_results):
                leg["result"] = "Void" if result_void_reason(actual) else "HR" if (number(actual.get("actual_hr")) or 0) > 0 else "No HR"
            db.execute("UPDATE tickets SET result=?,profit=?,payload=? WHERE ticket_id=?", (result, profit, json.dumps(data), ticket_id))
            updates += 1
    return updates


def history(path: Path, kind: str = "straight") -> pd.DataFrame:
    columns = ["game_date", "signal", "player", "result", "book_american_odds", "sportsbook", "profit_1u"]
    if not path.exists():
        return pd.DataFrame(columns=columns)
    records = []
    with connect(path) as db:
        for day, signal, raw, result, profit in db.execute(
            "SELECT day,signal,payload,result,profit FROM tickets WHERE kind=? ORDER BY day,ticket_id", (kind,)):
            if kind == "parlay" and result == "Void":
                continue
            payload = json.loads(raw)
            legs = payload["legs"]
            row = {"game_date": day, "signal": signal, "player": legs[0]["player"], "result": result,
                   "book_american_odds": legs[0]["odds"], "sportsbook": legs[0].get("sportsbook", ""), "profit_1u": profit,
                   "parlay_decimal_odds": payload["decimal_odds"]}
            for i, leg in enumerate(legs, 1):
                row[f"leg{i}"] = leg["player"]
                row[f"leg{i}_result"] = leg.get("result", "Pending")
            records.append(row)
    return pd.DataFrame(records) if records else pd.DataFrame(columns=columns)


def first_day(path: Path) -> str | None:
    if not path.exists():
        return None
    with connect(path) as db:
        return db.execute("SELECT MIN(day) FROM tickets").fetchone()[0]
