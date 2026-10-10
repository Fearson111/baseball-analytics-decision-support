"""Recover full-day model coverage from immutable, timestamped run inputs."""
import json
from pathlib import Path

import pandas as pd

from .markets import key, utc


MODELS = {"gbm": ("adjusted_hr_probability_percent", "rank"),
          "regression": ("positive_regression_score", "regression_rank"),
          "sequence": ("hr_probability", "projection_rank"), "matchup": ("score", "rank")}


def clean(value):
    return "" if pd.isna(value) else str(value).removesuffix(".0")


def identify(frame, gbm, games):
    """Use only unambiguous same-snapshot identities, including doubleheaders."""
    by_name = {}
    for row in gbm.fillna("").to_dict("records"):
        by_name.setdefault(key(row["player_name"]), []).append(row)
    schedule = {clean(g["game_id"]): g for g in games}
    rows = []
    for source in frame.fillna("").to_dict("records"):
        row = dict(source)
        candidates = by_name.get(key(row["player_name"]), [])
        if clean(row.get("game_id")):
            candidates = [r for r in candidates if clean(r.get("game_id")) == clean(row["game_id"])]
        opposing = key(row.get("opposing_pitcher", ""))
        if len(candidates) > 1 and opposing:
            candidates = [r for r in candidates if key(r.get("opposing_pitcher", "")) == opposing]
        if len(candidates) == 1:
            for col in ("game_id", "player_id", "team_abbrev"):
                if not clean(row.get(col)):
                    row[col] = candidates[0].get(col, "")
        game = schedule.get(clean(row.get("game_id")), {})
        row["prediction_game_start"] = game.get("start_time", row.get("prediction_game_start", ""))
        rows.append(row)
    return pd.DataFrame(rows)


def identity(row):
    return (key(row["player_name"]), clean(row.get("game_id")),
            "" if clean(row.get("game_id")) else key(row.get("opponent_abbrev", row.get("opponent", ""))),
            "" if clean(row.get("game_id")) else key(row.get("opposing_pitcher", "")))


def retain_day(runs: Path, current: Path, frames: dict, games: list, observed_at: str, cutoff=None):
    observations = []
    for status in runs.glob("*/status.json"):
        if status.parent == current:
            continue
        state = json.loads(status.read_text())
        if state.get("status") != "complete" or state.get("mode") not in {"full", "refresh", "correction"}:
            continue
        if cutoff and utc(state.get("finished", state.get("started"))) > utc(cutoff):
            continue
        incoming = status.parent / "incoming"
        if not all((incoming / f"{model}.csv").exists() for model in MODELS):
            continue
        old = {model: pd.read_csv(incoming / f"{model}.csv", dtype=str).fillna("") for model in MODELS}
        game_path = status.parent / "games.json"
        old_games = json.loads(game_path.read_text()) if game_path.exists() else []
        stamp = state.get("model_inputs_as_of") or state.get("finished") or state["started"]
        observations.append((stamp, status.parent.name, old, old_games))
    observations.append((observed_at, current.name, frames, games))
    observations.sort(key=lambda item: (item[0], item[1]))
    universe = pd.concat([source["gbm"] for _, _, source, _ in observations], ignore_index=True)
    universe = universe.drop_duplicates(["player_name", "game_id"], keep="last")
    schedule_by_id = {clean(game["game_id"]): game for _, _, _, schedule in observations for game in schedule}
    result = {}
    for model, (score, rank) in MODELS.items():
        records = {}
        for stamp, run_id, source, schedule in observations:
            for row in identify(source[model], universe, list(schedule_by_id.values())).fillna("").to_dict("records"):
                ident = identity(row)
                own_stamp = row.get("prediction_observed_at") or stamp
                start, observed = utc(row.get("prediction_game_start")), utc(own_stamp)
                pregame = bool(start and observed and observed < start)
                old = records.get(ident)
                if old and (not pregame or (utc(old["prediction_observed_at"]) and observed
                                            and observed < utc(old["prediction_observed_at"]))):
                    continue
                row.update(prediction_observed_at=own_stamp, prediction_source_run=run_id,
                           prediction_pregame_verified=pregame,
                           rank_at_observation=row.get("rank_at_observation", row.get(rank, "")))
                records[ident] = row
        frame = pd.DataFrame(records.values())
        if score in frame:
            frame = frame.sort_values(score, ascending=False, key=lambda s: pd.to_numeric(s, errors="coerce"), kind="stable")
            frame[rank] = range(1, len(frame) + 1)
        result[model] = frame.reset_index(drop=True)
    return result
