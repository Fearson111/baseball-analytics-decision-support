import json
import math
import numpy as np
import pandas as pd

from ..daily_hub.markets import key
from .pricing import break_even, bucket, decimal_odds

FAMILIES = ["market_edge", "model_rank", "eye", "matchup", "pitch_fit", "sequence_motif",
            "contact_quality", "book_price_rule", "regression"]
MODEL_MAP = {"market_edge": "GBM", "model_rank": "GBM", "regression": "Regression",
             "eye": "Eye", "matchup": "Matchup", "pitch_fit": "Matchup",
             "sequence_motif": "Sequence", "contact_quality": "Sequence"}


def families(label):
    label = label.lower()
    output = set()
    if "edge" in label or label in {"premium signal", "main watch rule", "primary watch zone"}:
        output.add("market_edge")
    if "model rank" in label or "gbm rank" in label or "model hr" in label:
        output.add("model_rank")
    if "eye" in label:
        output.add("eye")
    if "matchup" in label:
        output.add("matchup")
    if "pitch-fit" in label or "sharp fit" in label:
        output.add("pitch_fit")
    if "5-step" in label or "high-lift 5" in label or "sequence" in label:
        output.add("sequence_motif")
    if "contact quality" in label:
        output.add("contact_quality")
    if "book" in label or "price" in label or "500 to 800" in label or "longshot" in label:
        output.add("book_price_rule")
    if label in {"aggressive flag", "main watch rule", "main watch rule no edge", "premium signal", "primary watch zone"}:
        output.update(["regression", "book_price_rule"])
    return sorted(output)


def finite(value, fallback=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else fallback
    except (ValueError, TypeError):
        return fallback


def labels(value):
    return value if isinstance(value, list) else json.loads(value or "[]")


def enrich(row, config):
    signals = sorted(set(labels(row["signal_labels"])))
    fs = sorted({f for label in signals for f in families(label)})
    row.update(signal_labels=signals, signal_families=fs,
               model_families=sorted({MODEL_MAP[f] for f in fs if f in MODEL_MAP}),
               trigger_count_raw=len(signals), independent_family_count=len(fs),
               price_bucket=bucket(row["american_odds"], config),
               break_even_probability=break_even(row["american_odds"]))
    row["base_model_probability"] = finite(row.get("base_model_probability"))
    if row["base_model_probability"] is not None and not 0 < row["base_model_probability"] < 1:
        row["base_model_probability"] = None
    row["model_probability_missing"] = row["base_model_probability"] is None
    return row


def history_players(raw, before, config):
    """One outcome per player-day. Conflicting outcomes/doubleheaders are excluded."""
    if raw.empty:
        return pd.DataFrame()
    frame = raw.copy()
    frame = frame[frame.game_date.astype(str).lt(str(before))]
    frame = frame[frame.result.astype(str).str.upper().isin(["HR", "NO HR", "NO_HR"])]
    frame["_name"] = frame.player.map(key)
    output = []
    for (day, name), group in frame.groupby(["game_date", "_name"], sort=True):
        results = group.result.str.upper().eq("HR")
        if results.nunique() != 1:
            continue
        gids = {str(x).removesuffix(".0") for x in group.get("game_id", pd.Series(dtype=str)).dropna() if str(x).strip()}
        if len(gids) > 1:
            continue
        odds = pd.to_numeric(group.book_american_odds, errors="coerce").dropna()
        odds = odds[(odds.abs() >= 100) & np.isfinite(odds)]
        if odds.empty:
            continue
        # Historical sources can disagree on price. Use the shortest available price,
        # never count those alternative quotes as separate outcomes.
        price = min(odds, key=decimal_odds)
        row = group.iloc[0].to_dict()
        models = pd.to_numeric(group.get("model_hr_probability_percent", pd.Series(dtype=float)), errors="coerce")
        output.append(enrich(dict(
            date=str(day), player=row["player"], player_key=name, game_id=next(iter(gids), ""),
            player_id=str(row.get("player_id", "")), team=row.get("team_abbrev", ""),
            opponent=row.get("opponent_abbrev", ""), american_odds=float(price),
            base_model_probability=float(models.median()) / 100 if models.notna().any() else None,
            signal_labels=sorted(group.signal.dropna().unique()), result_hr=int(results.iloc[0]),
            eye_rank=finite(row.get("eye_rank")), model_rank=finite(row.get("gbm_rank")),
            matchup_rank=finite(row.get("pitcher_batter_rank")), sequence_rank=finite(row.get("sequence_rank")),
            eye_score=finite(row.get("eye_score")), quote_conflict=odds.nunique() > 1,
        ), config))
    return pd.DataFrame(output)


def candidates(straight, market, board, day, config):
    if straight.empty:
        return pd.DataFrame()
    ready = market[market.ready.astype(str).str.lower().eq("true")].copy()
    ready["_name"] = ready.player_name.map(key)
    eye = {key(r["player"]): r for r in board.to_dict("records")}
    signals = straight.copy()
    signals["_name"] = signals.player.map(key)
    rows = []
    for name, group in signals.groupby("_name", sort=True):
        choices = ready[ready["_name"].eq(name)]
        if len(choices) != 1:
            continue
        r = choices.iloc[0].to_dict()
        e = eye.get(name, {})
        rows.append(enrich(dict(
            date=day, player=r["player_name"], player_key=name,
            game_id=str(r["game_id"]).removesuffix(".0"), player_id=str(r["player_id"]).removesuffix(".0"),
            team=r.get("team_abbrev", ""), opponent=r.get("opponent_abbrev", ""),
            opposing_pitcher=r.get("opposing_pitcher", ""), start_time=r.get("start_time", ""),
            lineup_status=r.get("lineup_status", ""), american_odds=float(r["book_american_odds"]),
            sportsbook=r.get("bookmaker_used", ""), odds_observed=r.get("odds_last_update", ""),
            odds_source=r.get("odds_source", ""), odds_timestamp_kind=r.get("odds_timestamp_kind", ""),
            base_model_probability=finite(r.get("adjusted_hr_probability_percent"), 0)/100,
            signal_labels=list(group.signal.unique()), eye_rank=finite(e.get("eye_rank")),
            eye_score=finite(e.get("eye_score")), model_rank=finite(e.get("gbm_rank"), finite(r.get("rank"))),
            matchup_rank=finite(e.get("pitcher_batter_rank")), sequence_rank=finite(e.get("sequence_rank")),
        ), config))
    return pd.DataFrame(rows)

