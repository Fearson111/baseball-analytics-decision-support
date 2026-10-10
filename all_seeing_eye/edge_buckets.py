from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .io import player_key
from .profit_lenses import read_csv_rows
from .tracker import DEFAULT_GBM_PROJECT, DEFAULT_RESULTS_DIR, parse_american_odds, parse_float, profit_for_1u

DEFAULT_PROJECTIONS_DIR = DEFAULT_GBM_PROJECT / "data" / "projections"
EDGE_BUCKET_START_DATE = "2026-05-26"


@dataclass(frozen=True)
class EdgeBucketSignal:
    signal_id: str
    title: str
    section: str
    definition: str
    backtest_note: str
    predicate: Callable[[dict[str, Any]], bool]
    sort_key: Callable[[dict[str, Any]], tuple[Any, ...]]


EDGE_BUCKET_COLUMNS = [
    "signal",
    "section",
    "signal_note",
    "game_date",
    "model_top25_rank",
    "original_model_rank",
    "player",
    "team_abbrev",
    "opponent_abbrev",
    "lineup_status",
    "batting_order",
    "model_american_odds",
    "bookmaker_used",
    "book_american_odds",
    "dk_odds",
    "fan_odds",
    "365_odds",
    "edge_percent",
    "model_hr_probability_percent",
    "regression_rank",
    "reg_score",
]

EDGE_BUCKET_HISTORY_COLUMNS = [
    *EDGE_BUCKET_COLUMNS,
    "result",
    "actual_hr",
    "profit_1u",
    "running_profit_1u",
]

EDGE_BUCKET_SUMMARY_COLUMNS = [
    "bucket",
    "n",
    "hr",
    "hr_percent",
    "profit_1u",
    "roi_percent",
    "read",
]


def edge_bucket_signals() -> list[EdgeBucketSignal]:
    return [
        EdgeBucketSignal(
            signal_id="primary_mid_price_edge",
            title="Primary Mid-Price Edge Rule",
            section="Primary",
            definition="Top 25 model board, book odds +401 to +500, edge 0% to 2.5%",
            backtest_note="n 119, HR 28, HR% 23.53%, ROI +29.53%. Cleanest practical rule to monitor.",
            predicate=lambda row: in_book_range(row, 401, 500) and in_edge_range(row, 0, 2.5),
            sort_key=default_signal_sort_key,
        ),
        EdgeBucketSignal(
            signal_id="book_301_400_edge_2_5_5",
            title="Book 301-400 / Edge 2.5-5%",
            section="Best Combo",
            definition="Top 25 model board, book odds +301 to +400, edge 2.5% to 5%",
            backtest_note="n 63, HR% 28.57%, ROI +31.63%.",
            predicate=lambda row: in_book_range(row, 301, 400) and in_edge_range(row, 2.5, 5),
            sort_key=default_signal_sort_key,
        ),
        EdgeBucketSignal(
            signal_id="book_501_650_edge_2_5_5",
            title="Book 501-650 / Edge 2.5-5%",
            section="Best Combo",
            definition="Top 25 model board, book odds +501 to +650, edge 2.5% to 5%",
            backtest_note="n 47, HR% 19.15%, ROI +27.30%.",
            predicate=lambda row: in_book_range(row, 501, 650) and in_edge_range(row, 2.5, 5),
            sort_key=default_signal_sort_key,
        ),
        EdgeBucketSignal(
            signal_id="rank_1_5_edge_2_5_5",
            title="Model Rank 1-5 / Edge 2.5-5%",
            section="Best Combo",
            definition="Model top-25 rank 1 to 5, edge 2.5% to 5%",
            backtest_note="n 64, HR% 26.56%, ROI +18.64%.",
            predicate=lambda row: in_rank_range(row, 1, 5) and in_edge_range(row, 2.5, 5),
            sort_key=default_signal_sort_key,
        ),
        EdgeBucketSignal(
            signal_id="rank_11_25_edge_0_2_5",
            title="Model Rank 11-25 / Edge 0-2.5%",
            section="Best Combo",
            definition="Model top-25 rank 11 to 25, edge 0% to 2.5%",
            backtest_note="n 160, HR% 20.00%, ROI +11.34%.",
            predicate=lambda row: in_rank_range(row, 11, 25) and in_edge_range(row, 0, 2.5),
            sort_key=default_signal_sort_key,
        ),
    ]


def build_edge_bucket_active_rows(game_date: str, projections_dir: Path = DEFAULT_PROJECTIONS_DIR) -> list[dict[str, Any]]:
    rows = top25_projection_rows(game_date, projections_dir)
    return signal_rows(rows)


def build_edge_bucket_base_history_rows(
    projections_dir: Path = DEFAULT_PROJECTIONS_DIR,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    *,
    start_date: str = EDGE_BUCKET_START_DATE,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for game_date in projection_dates(projections_dir):
        if game_date < start_date:
            continue
        if end_date and game_date > end_date:
            continue
        result_path = results_dir / f"daily_results_{game_date}.csv"
        if not result_path.exists():
            continue
        result_index = load_result_index(result_path)
        for row in top25_projection_rows(game_date, projections_dir):
            result = result_for_projection(row, result_index)
            odds = parse_american_odds(row.get("book_american_odds"))
            edge = parse_float(row.get("edge_percent"))
            if odds is None or edge is None:
                continue
            void_reason = result_void_reason(result)
            is_void = bool(void_reason)
            actual_hr = 0 if is_void else int(safe_float(result.get("actual_hr_binary") or result.get("actual_hr"), 0) or 0)
            profit = 0.0 if is_void else profit_for_1u(odds, actual_hr > 0)
            output = {column: row.get(column, "") for column in EDGE_BUCKET_COLUMNS if column not in {"signal", "section", "signal_note"}}
            output.update(
                {
                    "result": "Void" if is_void else ("HR" if actual_hr > 0 else "No HR"),
                    "actual_hr": "" if is_void else actual_hr,
                    "profit_1u": round(profit, 2),
                    "is_void": "1" if is_void else "0",
                    "void_reason": void_reason if is_void else "",
                }
            )
            history.append(output)
    return history


def build_edge_bucket_history_rows(
    projections_dir: Path = DEFAULT_PROJECTIONS_DIR,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    *,
    start_date: str = EDGE_BUCKET_START_DATE,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    base_rows = build_edge_bucket_base_history_rows(
        projections_dir,
        results_dir,
        start_date=start_date,
        end_date=end_date,
    )
    history: list[dict[str, Any]] = []
    running: dict[str, float] = {}
    for signal in edge_bucket_signals():
        candidates = sorted([row for row in base_rows if signal.predicate(row)], key=lambda row: (str(row.get("game_date") or ""), *signal.sort_key(row)))
        for candidate in candidates:
            profit = safe_float(candidate.get("profit_1u"), 0)
            running[signal.title] = running.get(signal.title, 0.0) + profit
            output = edge_bucket_output_row(signal, candidate)
            output.update(
                {
                    "result": candidate.get("result", ""),
                    "actual_hr": candidate.get("actual_hr", ""),
                    "profit_1u": round(profit, 2),
                    "running_profit_1u": round(running[signal.title], 2),
                }
            )
            history.append(output)
    return history


def build_edge_bucket_summary_rows(history_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_signal: dict[str, list[dict[str, Any]]] = {}
    for row in history_rows:
        by_signal.setdefault(str(row.get("signal") or ""), []).append(row)
    for signal in edge_bucket_signals():
        signal_rows_for_title = by_signal.get(signal.title, [])
        rows.append(summary_row(signal.title, signal_rows_for_title, ""))
    return rows


def build_edge_bucket_edge_summary_rows(base_history_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = [
        (">10", lambda row: safe_float(row.get("edge_percent"), -999) > 10, "too small to trust"),
        ("2.5 to 5", lambda row: in_edge_range(row, 2.5, 5), "barely positive with a better sample"),
        ("5 to 10", lambda row: in_edge_range(row, 5, 10), "near breakeven in the historical run"),
        ("0 to 2.5", lambda row: in_edge_range(row, 0, 2.5), "useful only with price/rank filters"),
        ("-5 to 0", lambda row: in_edge_range(row, -5, 0), "negative overall in the broad sample"),
        ("-10 to -5", lambda row: in_edge_range(row, -10, -5), "only interesting in top-rank pockets"),
        ("<= -10", lambda row: safe_float(row.get("edge_percent"), 999) <= -10, "weak broad bucket"),
    ]
    return [summary_row(label, [row for row in base_history_rows if predicate(row)], read) for label, predicate, read in buckets]


def build_edge_bucket_daily_stability_rows(history_rows: list[dict[str, Any]], signal_title: str = "Primary Mid-Price Edge Rule") -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in history_rows:
        if row.get("signal") == signal_title:
            by_date.setdefault(str(row.get("game_date") or ""), []).append(row)
    stability: list[dict[str, Any]] = []
    running = 0.0
    for game_date in sorted(by_date):
        rows = by_date[game_date]
        profit = sum(safe_float(row.get("profit_1u"), 0) for row in rows)
        running += profit
        bets = len(rows)
        hrs = sum(1 for row in rows if row.get("result") == "HR")
        stability.append(
            {
                "game_date": game_date,
                "signal": signal_title,
                "bets": bets,
                "hr": hrs,
                "profit_1u": round(profit, 2),
                "running_profit_1u": round(running, 2),
                "roi_percent": round((profit / bets) * 100, 2) if bets else 0,
            }
        )
    return stability


def top25_projection_rows(game_date: str, projections_dir: Path) -> list[dict[str, Any]]:
    path = projections_dir / f"daily_hr_projections_{game_date}.csv"
    if not path.exists():
        return []
    rows = []
    regression_context = load_regression_context(projections_dir / f"daily_positive_regression_targets_{game_date}.csv")
    for source in read_csv_rows(path):
        model_odds = parse_american_odds(source.get("american_betting_odds"))
        if model_odds is None:
            continue
        player = source.get("player_name") or source.get("player") or source.get("batter") or source.get("name")
        if not player:
            continue
        row = dict(source)
        row["player"] = player
        row["model_american_odds"] = model_odds
        book_odds = parse_american_odds(source.get("book_american_odds"))
        edge = parse_float(source.get("edge_percent"))
        row["book_american_odds"] = book_odds if book_odds is not None else ""
        row["edge_percent"] = edge if edge is not None else ""
        row["original_model_rank"] = source.get("rank", "")
        row["model_hr_probability_percent"] = source.get("adjusted_hr_probability_percent", "")
        context = regression_context.get(regression_key(row)) or regression_context.get(player_key(str(player)), {})
        row["regression_rank"] = context.get("regression_rank", "")
        row["reg_score"] = context.get("positive_regression_score", "")
        rows.append(row)
    rows = sorted(rows, key=lambda row: (safe_float(row.get("model_american_odds"), 999999), safe_float(row.get("original_model_rank"), 999999)))[:25]
    for index, row in enumerate(rows, start=1):
        row["model_top25_rank"] = index
    return rows


def signal_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for signal in edge_bucket_signals():
        for row in sorted([row for row in rows if signal.predicate(row)], key=signal.sort_key):
            output.append(edge_bucket_output_row(signal, row))
    return output


def edge_bucket_output_row(signal: EdgeBucketSignal, row: dict[str, Any]) -> dict[str, Any]:
    output = {column: row.get(column, "") for column in EDGE_BUCKET_COLUMNS}
    output["signal"] = signal.title
    output["section"] = signal.section
    output["signal_note"] = signal.backtest_note
    return output


def projection_dates(projections_dir: Path) -> list[str]:
    if not projections_dir.exists():
        return []
    dates = []
    for path in projections_dir.glob("daily_hr_projections_*.csv"):
        if "_confirmed" in path.name:
            continue
        date_key = date_key_from_text(path.name)
        if date_key:
            dates.append(date_key)
    return sorted(set(dates))


def load_result_index(result_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in read_csv_rows(result_path):
        game_id = str(row.get("game_id") or "").strip()
        player_id = str(row.get("player_id") or "").strip()
        if game_id and player_id:
            index[(game_id, player_id)] = row
        player = row.get("player_name") or ""
        if player:
            index[("player", player_key(str(player)))] = row
    return index


def result_for_projection(row: dict[str, Any], result_index: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any] | None:
    game_id = str(row.get("game_id") or "").strip()
    player_id = str(row.get("player_id") or "").strip()
    if game_id and player_id and (game_id, player_id) in result_index:
        return result_index[(game_id, player_id)]
    return result_index.get(("player", player_key(str(row.get("player") or ""))))


def load_regression_context(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    context: dict[str, dict[str, Any]] = {}
    for row in read_csv_rows(path):
        player = row.get("player_name") or row.get("player") or ""
        value = {
            "regression_rank": row.get("regression_rank", ""),
            "positive_regression_score": row.get("positive_regression_score", ""),
        }
        key = regression_key(row)
        if key:
            context[key] = value
        if player:
            context[player_key(str(player))] = value
    return context


def regression_key(row: dict[str, Any]) -> str:
    player_id = str(row.get("player_id") or "").strip()
    return f"id:{player_id}" if player_id else ""


def dedup_player_days(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row.get("game_date") or ""), str(row.get("player") or ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def result_void_reason(result: dict[str, Any] | None) -> str:
    if result is None:
        return "Player not listed with a PA in completed daily results"
    position = str(result.get("lineup_position") or "").strip().upper()
    ab = parse_float(result.get("actual_ab")) or 0
    if position == "PH" and ab == 1:
        return "Pinch-hit one AB without starting"
    pa = parse_float(result.get("actual_pa"))
    if pa is None and parse_float(result.get("actual_ab")) is None:
        return ""
    if (pa or 0) <= 0 and (parse_float(result.get("actual_ab")) or 0) <= 0:
        return "Player not listed with a PA in completed daily results"
    return ""


def result_is_void(result: dict[str, Any] | None) -> bool:
    return bool(result_void_reason(result))


def is_void_row(row: dict[str, Any]) -> bool:
    return str(row.get("is_void") or "").strip() == "1" or str(row.get("result") or "").strip().lower() == "void"

def summary_row(label: str, rows: list[dict[str, Any]], read: str) -> dict[str, Any]:
    graded_rows = [row for row in rows if not is_void_row(row)]
    bets = len(graded_rows)
    hrs = sum(1 for row in graded_rows if row.get("result") == "HR" or int(safe_float(row.get("actual_hr"), 0) or 0) > 0)
    profit = sum(safe_float(row.get("profit_1u"), 0) for row in graded_rows)
    return {
        "bucket": label,
        "n": bets,
        "hr": hrs,
        "hr_percent": round((hrs / bets) * 100, 2) if bets else 0,
        "profit_1u": round(profit, 2),
        "roi_percent": round((profit / bets) * 100, 2) if bets else 0,
        "read": read or edge_bucket_stat_sentence(bets, hrs, profit),
    }


def edge_bucket_stat_sentence(bets: int, hrs: int, profit: float) -> str:
    roi = (profit / bets * 100) if bets else 0.0
    return f"{bets} bets, {hrs} HR, {profit:+.2f}u, {roi:+.2f}% ROI"


def default_signal_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        safe_float(row.get("model_top25_rank"), 999),
        -safe_float(row.get("edge_percent"), -999),
        safe_float(row.get("book_american_odds"), 999999),
    )


def in_book_range(row: dict[str, Any], low: float, high: float) -> bool:
    value = safe_float(row.get("book_american_odds"), 999999)
    return low <= value <= high


def in_edge_range(row: dict[str, Any], low: float, high: float) -> bool:
    value = safe_float(row.get("edge_percent"), -999999)
    return low <= value <= high


def in_rank_range(row: dict[str, Any], low: int, high: int) -> bool:
    value = safe_float(row.get("model_top25_rank"), 999999)
    return low <= value <= high


def safe_float(value: Any, default: float = 0.0) -> float:
    parsed = parse_float(value)
    return parsed if parsed is not None else default


def date_key_from_text(text: str) -> str | None:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    return match.group(1) if match else None
