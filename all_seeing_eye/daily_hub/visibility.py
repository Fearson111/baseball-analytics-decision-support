"""Read-only posting filters, isolated from model selection and history grading."""
from contextlib import contextmanager
from contextvars import ContextVar

import pandas as pd

from .markets import key

_current = ContextVar("posting_visibility", default=None)


def clean(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().removesuffix(".0")


class PostingVisibility:
    def __init__(self, market: pd.DataFrame):
        self.by_name = {}
        for row in market.fillna("").to_dict("records"):
            name = key(row.get("player_name", row.get("player", "")))
            if name:
                self.by_name.setdefault(name, []).append(row)

    def confirmed(self, name, game_id="", player_id="", pitcher="") -> bool:
        rows = self.by_name.get(key(clean(name)), [])
        gid, pid, opposing = clean(game_id), clean(player_id), key(clean(pitcher))
        if gid:
            rows = [r for r in rows if clean(r.get("game_id")) == gid]
        if pid:
            rows = [r for r in rows if clean(r.get("player_id")) == pid]
        if opposing and len(rows) > 1:
            rows = [r for r in rows if key(clean(r.get("opposing_pitcher"))) == opposing]
        if not gid and len({clean(r.get("game_id")) for r in rows}) > 1:
            # Name-keyed Eye outputs use the one game selected by the pipeline.
            selected = [r for r in rows if clean(r.get("ready")).lower() == "true"]
            rows = selected if len(selected) == 1 else []
        return bool(rows) and all(clean(r.get("lineup_status")).lower() == "confirmed" for r in rows)

    def filter(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()
        legs = [c for i in range(1, 5) for c in (f"leg{i}_player", f"leg{i}") if c in frame.columns]
        player_column = next((c for c in ("player", "player_name") if c in frame.columns), None)
        if not legs and not player_column:
            return frame.copy()
        def visible(row):
            if legs:
                names = [(c, row.get(c)) for c in legs if clean(row.get(c))]
                return bool(names) and all(self.confirmed(
                    name, row.get(c.split("_")[0] + "_game_id", ""),
                    row.get(c.split("_")[0] + "_player_id", ""))
                    for c, name in names)
            return self.confirmed(row.get(player_column), row.get("game_id", ""),
                                  row.get("player_id", ""), row.get("opposing_pitcher", ""))
        return frame.loc[frame.apply(visible, axis=1)].copy()


def with_lineups(market: pd.DataFrame, games: list[dict], starters: list[dict], overrides=()) -> pd.DataFrame:
    """Overlay current lineup facts in memory without changing quotes or the snapshot."""
    result = market.copy()
    starter_keys = {(clean(s["game_id"]), clean(s["player_id"])) for s in starters}
    known_games = {clean(g["game_id"]) for g in games}
    announced_teams = {(clean(s["game_id"]), s["team_abbrev"]) for s in starters}
    outs = {(clean(r["game_id"]), clean(r["player_id"])) for r in overrides if r.get("out")}
    statuses = []
    for row in result.fillna("").to_dict("records"):
        identity = (clean(row.get("game_id")), clean(row.get("player_id")))
        if identity in outs:
            status = "out"
        elif identity[0] not in known_games:
            status = "not_confirmed"
        elif identity in starter_keys:
            status = "confirmed"
        elif (identity[0], row.get("team_abbrev")) in announced_teams:
            status = "out"
        else:
            status = "not_confirmed"
        statuses.append(status)
    result["lineup_status"] = statuses
    return result


@contextmanager
def posting_scope(visibility):
    token = _current.set(visibility)
    try:
        yield
    finally:
        _current.reset(token)


def posting_filter_active() -> bool:
    return _current.get() is not None


def filter_posting_rows(frame: pd.DataFrame) -> pd.DataFrame:
    visibility = _current.get()
    return visibility.filter(frame) if visibility is not None else frame
