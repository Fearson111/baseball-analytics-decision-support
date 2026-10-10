"""Portfolio-only MLB result fetch; shares canonical grading with saved-file settlement."""
from datetime import date, datetime, timezone
import json
import hashlib
from pathlib import Path

from . import history


def count(value):
    try:
        number = float(value)
        return int(number) if number >= 0 and number.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def box_results(box, gid, day, *, final=True):
    output = {}
    for side in ("home", "away"):
        team = box.get("teams", {}).get(side, {})
        totals = team.get("teamStats", {}).get("batting", {})
        total_pa, total_hr = count(totals.get("plateAppearances")), count(totals.get("homeRuns"))
        players = team.get("players", {})
        if total_pa is None or (final and not total_pa) or total_hr is None or not players:
            raise ValueError("Incomplete final box score; team batting totals are unavailable.")
        pa_sum = hr_sum = 0
        for player in players.values():
            stats = player.get("stats", {}).get("batting", {})
            status = player.get("gameStatus", {})
            if stats:
                pa, ab, hr = (count(stats.get(field)) for field in ("plateAppearances", "atBats", "homeRuns"))
                if None in (pa, ab, hr) or ab > pa or hr > ab:
                    raise ValueError("Incomplete or inconsistent player batting statistics.")
                pa_sum += pa
                hr_sum += hr
            elif status.get("isOnBench") is True or status.get("isSubstitute") is True:
                pa = ab = hr = 0
            else:
                continue
            pid = player.get("person", {}).get("id")
            if pid is None:
                raise ValueError("Missing MLB player identity.")
            order = str(player.get("battingOrder", ""))
            starter = (100 <= int(order) <= 900 and int(order) % 100 == 0) if order.isdigit() else status.get("isSubstitute") is False
            positions = {p.get("abbreviation") for p in player.get("allPositions", [])}
            primary = player.get("position", {}).get("abbreviation", "")
            positions.add(primary)
            position = "PH" if not starter and "PH" in positions else primary
            if starter and position == "PH":
                position = "STARTER"
            output[str(pid)] = dict(game_date=day, game_id=str(gid), player_id=str(pid),
                                    player_name=player.get("person", {}).get("fullName", ""),
                                    actual_pa=pa, actual_ab=ab, actual_hr=hr,
                                    lineup_position=position, is_starter=starter,
                                    source="MLB final box score" if final else "MLB live box score",
                                    is_final=final)
        if pa_sum != total_pa or hr_sum != total_hr:
            raise ValueError("Incomplete final box score; player statistics do not match team totals.")
    return output


def scan_day(root, day, fetch=None, *, include_live=False, recorded_only=False, min_interval_seconds=0):
    from ..daily_hub.markets import get_json
    day = date.fromisoformat(day).isoformat()
    fetch = fetch or get_json
    report = dict(day=day, tracked_players=0, games_checked=0, final_games=0,
                  newly_graded=0, corrected=0, unchanged=0, pending_players=0, live_games=0,
                  finalized=0, errors=[], checked_at=datetime.now(timezone.utc).isoformat())
    report["poll_started_at"] = report["checked_at"]
    with history.results_lock(root):
        poll_path = Path(root) / "DAILY_BASEBALL/financial" / f"live_poll_{day}_{int(recorded_only)}.json"
        if min_interval_seconds and poll_path.exists():
            cached = json.loads(poll_path.read_text())
            age = (datetime.now(timezone.utc)-datetime.fromisoformat(cached.get("poll_started_at", cached["checked_at"]))).total_seconds()
            if age < max(0, min_interval_seconds - .5):
                return {**cached, "newly_graded":0, "corrected":0, "finalized":0}
        if recorded_only:
            wagers = history.read(root, actual=True)
            positions = wagers[wagers.date.eq(day)].to_dict("records") if not wagers.empty else []
        else:
            positions = history.tracked_positions(root, day=day)
        report["tracked_players"] = len(positions)
        unmatched = [r for r in positions if not str(r["game_id"]).isdigit() or not str(r["player_id"]).isdigit()]
        report["pending_players"] = len(unmatched)
        if unmatched:
            report["errors"].append("Player/game identity needs matching for: " + ", ".join(r["player"] for r in unmatched))
        games = sorted({r["game_id"] for r in positions if str(r["game_id"]).isdigit() and str(r["player_id"]).isdigit()})
        if not games:
            return report
        try:
            # Game IDs retain correct identity for doubleheaders and resumed games.
            schedule = fetch("https://statsapi.mlb.com/api/v1/schedule",
                             {"sportId":1, "gamePks": ",".join(games)})
            statuses = {str(g["gamePk"]):g.get("status",{}).get("abstractGameState")
                        for d in schedule.get("dates",[]) for g in d.get("games",[])}
        except Exception as exc:
            report["errors"].append(f"Schedule check failed: {exc}")
            statuses = {}
        for gid in games:
            report["games_checked"] += 1
            final = statuses.get(gid) == "Final"
            if not final and not (include_live and statuses.get(gid) == "Live"):
                continue
            try:
                box = fetch(f"https://statsapi.mlb.com/api/v1/game/{gid}/boxscore", None)
                normalized = box_results(box, gid, day, final=final)
                fetched = datetime.now(timezone.utc).isoformat()
                report["final_games" if final else "live_games"] += 1
                changes = dict(newly_graded=0, corrected=0, unchanged=0, finalized=0)
                with history.database(root) as db:
                    for row in positions:
                        if row["game_id"] != gid:
                            continue
                        pid = row["player_id"]
                        actual = normalized.get(pid)
                        if actual is None:
                            report["errors"].append(f"{row['player']}: no complete player result in the final box score.")
                            continue
                        previous = db.execute("SELECT payload FROM result_cache WHERE game_id=? AND player_id=?", (gid,pid)).fetchone()
                        previous = json.loads(previous[0]) if previous else {}
                        provisional = previous.get("is_final") is False
                        if not final:
                            # Never downgrade a final result based on a live/stale schedule response.
                            existing_outcome = db.execute("SELECT 1 FROM outcomes WHERE game_id=? AND player_id=?", (gid,pid)).fetchone()
                            if (previous or existing_outcome) and not provisional:
                                continue
                            if history.outcome_from_result(actual) != "HR":
                                if provisional:
                                    db.execute("DELETE FROM outcomes WHERE game_id=? AND player_id=?", (gid,pid))
                                    db.execute("DELETE FROM result_cache WHERE game_id=? AND player_id=?", (gid,pid))
                                    changes["corrected"] += 1
                                continue
                        elif provisional:
                            changes["finalized"] += 1
                        db.execute("INSERT INTO result_cache VALUES(?,?,?,?,?) ON CONFLICT(game_id,player_id) "
                                   "DO UPDATE SET day=excluded.day,payload=excluded.payload,fetched=excluded.fetched",
                                   (gid,pid,day,json.dumps(actual),fetched))
                        outcome = history.write_outcome(db,gid,pid,actual)
                        if outcome in changes:
                            changes[outcome] += 1
                for outcome, total in changes.items():
                    report[outcome] += total
            except Exception as exc:
                report["errors"].append(f"Game {gid}: {exc}")
        with history.database(root) as db:
            outcomes = db.execute("SELECT game_id,player_id,result FROM outcomes ORDER BY game_id,player_id").fetchall()
            settled = {(g,p) for g,p,_ in outcomes}
            provisional = sorted((g,p) for g,p,payload in db.execute("SELECT game_id,player_id,payload FROM result_cache")
                                 if json.loads(payload).get("is_final") is False)
        report["result_revision"] = hashlib.sha256(json.dumps([outcomes, provisional]).encode()).hexdigest()
        report["pending_players"] = sum((r["game_id"],r["player_id"]) not in settled for r in positions)
        if min_interval_seconds:
            from ..daily_hub.runner import atomic_json
            report["checked_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(poll_path, report)
    return report


def refresh_due(root, through, fetch=None):
    """Morning reconciliation: yesterday plus older unresolved financial positions."""
    rows = history.tracked_positions(root, before=through)
    with history.database(root) as db:
        done = {(g,p) for g,p in db.execute("SELECT game_id,player_id FROM outcomes")}
        provisional = {(g,p) for g,p,payload in db.execute("SELECT game_id,player_id,payload FROM result_cache")
                       if json.loads(payload).get("is_final") is False}
        done -= provisional
    days = sorted({r["date"] for r in rows if r["date"] == through or (r["game_id"],r["player_id"]) not in done})
    return [scan_day(root, day, fetch=fetch) for day in days]
