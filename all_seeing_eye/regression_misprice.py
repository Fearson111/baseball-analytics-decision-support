from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .io import player_key
from .profit_lenses import enrich_rows_from_input_folder, num, read_csv_rows, write_csv
from .tracker import DEFAULT_GBM_PROJECT, DEFAULT_RESULTS_DIR, DEFAULT_STATCAST_DIR, latest_input_folder_for_date, load_home_run_results, parse_american_odds, parse_float


@dataclass(frozen=True)
class RegressionMispriceZone:
    zone_id: str
    title: str
    filename: str
    definition: str
    backtest_note: str
    predicate: Callable[[dict[str, Any]], bool]
    sort_key: Callable[[dict[str, Any]], tuple[Any, ...]]
    history_start_date: str = ""


REGRESSION_MISPRICE_COLUMNS = [
    "zone",
    "zone_note",
    "bet",
    "stake_units",
    "notes",
    "player",
    "team_abbrev",
    "opponent_abbrev",
    "lineup_status",
    "batting_order",
    "bookmaker_used",
    "book_american_odds",
    "dk_odds",
    "fan_odds",
    "365_odds",
    "edge_percent",
    "reg_score",
    "regression_rank",
    "model_hr_probability_percent",
    "eye_rank",
    "eye_score",
    "accel_score",
    "stale_signal_status",
    "gbm_rank",
    "gbm_progression_rank",
    "sequence_rank",
    "pitcher_batter_rank",
    "movement_summary",
    "reasoning",
]


REGRESSION_MISPRICE_HISTORY_COLUMNS = [
    "game_date",
    *REGRESSION_MISPRICE_COLUMNS,
    "result",
    "actual_hr",
    "profit_1u",
    "running_profit_1u",
]


DEFAULT_REGRESSION_TARGETS_DIR = DEFAULT_GBM_PROJECT / "data" / "projections"


def build_regression_misprice_from_run(board_path: Path, input_folder: Path, output_folder: Path) -> dict[str, Path]:
    rows = enrich_regression_rows(enrich_rows_from_input_folder(read_csv_rows(board_path), input_folder), input_folder)
    return write_regression_misprice(rows, output_folder)


def enrich_regression_rows(rows: list[dict[str, Any]], input_folder: Path) -> list[dict[str, Any]]:
    signals = load_regression_signals(input_folder)
    enriched: list[dict[str, Any]] = []
    for row in rows:
        merged = dict(row)
        player = str(row.get("player") or "").strip()
        signal = signals.get(player_key(player), {})
        for column, value in signal.items():
            if value not in (None, ""):
                merged[column] = value
        enriched.append(merged)
    return enriched


def load_regression_signals(input_folder: Path) -> dict[str, dict[str, Any]]:
    path = input_folder / "gbm_progression_top80.csv"
    if not path.exists():
        return {}

    signals: dict[str, dict[str, Any]] = {}
    for row in read_csv_rows(path):
        player = row.get("player_name") or row.get("player") or row.get("batter") or row.get("name")
        if not player:
            continue
        signals[player_key(str(player))] = {
            "reg_score": row.get("positive_regression_score", "") or row.get("reg_score", ""),
            "regression_rank": row.get("regression_rank", "") or row.get("rank", ""),
            "bookmaker_used": row.get("bookmaker_used", ""),
            "book_american_odds": row.get("book_american_odds", ""),
            "dk_odds": row.get("dk_odds", ""),
            "fan_odds": row.get("fan_odds", ""),
            "365_odds": row.get("365_odds", ""),
            "edge_percent": row.get("edge_percent", ""),
            "model_hr_probability_percent": row.get("adjusted_hr_probability_percent", ""),
            "team_abbrev": row.get("team_abbrev", "") or row.get("player_team", ""),
            "opponent_abbrev": row.get("opponent_abbrev", "") or row.get("opponent", ""),
            "lineup_status": row.get("lineup_status", ""),
            "batting_order": row.get("batting_order", ""),
        }
    return signals


def write_regression_misprice(rows: list[dict[str, Any]], output_folder: Path) -> dict[str, Path]:
    output_folder.mkdir(parents=True, exist_ok=True)
    for stale_file in output_folder.glob("regression_misprice_*.csv"):
        stale_file.unlink()
    written: dict[str, Path] = {}
    combined_rows: list[dict[str, Any]] = []

    for zone in regression_misprice_zones():
        candidates = sorted([row for row in rows if zone.predicate(row)], key=zone.sort_key)
        zone_rows = [regression_misprice_row(zone, row) for row in candidates]
        path = output_folder / zone.filename
        write_csv(path, REGRESSION_MISPRICE_COLUMNS, zone_rows)
        written[zone.zone_id] = path
        combined_rows.extend(zone_rows)

    combined_path = output_folder / "regression_misprice_combined.csv"
    write_csv(combined_path, REGRESSION_MISPRICE_COLUMNS, combined_rows)
    written["combined"] = combined_path
    return written


def regression_misprice_zones() -> list[RegressionMispriceZone]:
    return [
        RegressionMispriceZone(
            zone_id="primary_watch",
            title="Primary Watch Zone",
            filename="regression_misprice_primary_watch.csv",
            definition="reg_score >= 40, book odds <= +350, edge% <= 0",
            backtest_note="Related tested pocket reg_score >= 40, edge% <= -5, book odds <= +350: n 16, HR 50.00%, ROI +69.38%.",
            predicate=is_primary_watch_zone,
            sort_key=lambda row: (-num(row, "reg_score", -999), book_odds(row), num(row, "eye_rank", 999)),
        ),
        RegressionMispriceZone(
            zone_id="aggressive_flag",
            title="Aggressive Flag",
            filename="regression_misprice_aggressive_flag.csv",
            definition="reg_score >= 42, any book odds <= +500",
            backtest_note="Related tighter negative-edge bucket reg_score >= 42, edge% <= -5: n 11, HR 54.55%, ROI +75.45%. Treat as a flag, not a finished betting rule.",
            predicate=is_aggressive_flag_zone,
            sort_key=lambda row: (-num(row, "reg_score", -999), book_odds(row), num(row, "eye_rank", 999)),
        ),
        RegressionMispriceZone(
            zone_id="main_watch_rule",
            title="Main Watch Rule",
            filename="regression_misprice_main_watch_rule.csv",
            definition="reg_score >= 38, regression rank <= 10, book odds <= +500, any edge",
            backtest_note="n 75, HR 22, HR% 29.33%, ROI +20.80%, max bet losing streak 9, max day losing streak 4, avg picks/day 2.27.",
            predicate=is_main_watch_rule_zone,
            sort_key=rank_top10_sort_key,
            history_start_date="2026-06-27",
        ),
        RegressionMispriceZone(
            zone_id="main_watch_rule_no_edge",
            title="Main Watch Rule No Edge",
            filename="regression_misprice_main_watch_rule_no_edge.csv",
            definition="reg_score >= 38, regression rank <= 10, book odds <= +500, edge% <= 0",
            backtest_note="n 62, HR 20, HR% 32.26%, ROI +30.00%, avg book odds +330, max bet losing streak 8, max day losing streak 4, days with at least 1 HR 45.16%, avg picks/day 2.00.",
            predicate=is_main_watch_rule_no_edge_zone,
            sort_key=rank_top10_sort_key,
            history_start_date="2026-06-27",
        ),
        RegressionMispriceZone(
            zone_id="premium_signal",
            title="Premium Signal",
            filename="regression_misprice_premium_signal.csv",
            definition="reg_score >= 40, regression rank <= 10, book odds <= +500, edge% <= 0",
            backtest_note="n 34, HR 15, HR% 44.12%, ROI +70.29%, avg book odds +311, max bet losing streak 4, max day losing streak 3, avg picks/day 1.55. Red-hot regression signal, not a full-season law yet.",
            predicate=is_premium_signal_zone,
            sort_key=rank_top10_sort_key,
            history_start_date="2026-06-27",
        ),
    ]


def regression_misprice_row(zone: RegressionMispriceZone, row: dict[str, Any]) -> dict[str, Any]:
    output = {column: row.get(column, "") for column in REGRESSION_MISPRICE_COLUMNS}
    output["zone"] = zone.title
    output["zone_note"] = zone.backtest_note
    output.setdefault("bet", "")
    output.setdefault("stake_units", "1")
    output.setdefault("notes", "")
    output["stake_units"] = output.get("stake_units") or "1"
    return output


def is_primary_watch_zone(row: dict[str, Any]) -> bool:
    return num(row, "reg_score", -999) >= 40 and book_odds(row) <= 350 and num(row, "edge_percent", 999) <= 0



def is_aggressive_flag_zone(row: dict[str, Any]) -> bool:
    return num(row, "reg_score", -999) >= 42 and book_odds(row) <= 500


def is_main_watch_rule_zone(row: dict[str, Any]) -> bool:
    return (
        num(row, "reg_score", -999) >= 38
        and num(row, "regression_rank", 999) <= 10
        and book_odds(row) <= 500
    )


def is_main_watch_rule_no_edge_zone(row: dict[str, Any]) -> bool:
    return is_main_watch_rule_zone(row) and num(row, "edge_percent", 999) <= 0


def is_premium_signal_zone(row: dict[str, Any]) -> bool:
    return (
        num(row, "reg_score", -999) >= 40
        and num(row, "regression_rank", 999) <= 10
        and book_odds(row) <= 500
        and num(row, "edge_percent", 999) <= 0
    )


def rank_top10_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (-num(row, "reg_score", -999), num(row, "regression_rank", 999), book_odds(row), num(row, "eye_rank", 999))


def book_odds(row: dict[str, Any]) -> float:
    parsed = parse_american_odds(row.get("book_american_odds"))
    if parsed is None:
        parsed_float = parse_float(row.get("book_american_odds"))
        return parsed_float if parsed_float is not None else 999999.0
    return float(parsed)


def build_regression_misprice_history_rows(rows: list[dict[str, Any]], input_root: Path = Path("inputs")) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        date_key = str(row.get("game_date") or "")
        if date_key:
            by_date.setdefault(date_key, []).append(row)

    history: list[dict[str, Any]] = []
    running: dict[str, float] = {}
    for date_key in sorted(by_date):
        input_folder = input_folder_for_date_key(date_key, input_root)
        day_rows = enrich_regression_rows(by_date[date_key], input_folder) if input_folder else by_date[date_key]
        for zone in regression_misprice_zones():
            if zone.history_start_date and date_key < zone.history_start_date:
                continue
            for candidate in sorted([row for row in day_rows if zone.predicate(row)], key=zone.sort_key):
                is_void = is_void_candidate(candidate)
                actual_hr = 0 if is_void else int(parse_float(candidate.get("actual_hr")) or parse_float(candidate.get("did_hr")) or 0)
                odds = parse_american_odds(candidate.get("book_american_odds"))
                profit = 0.0 if is_void else (profit_for_1u(odds, actual_hr > 0) if odds is not None else 0.0)
                running[zone.title] = running.get(zone.title, 0.0) + profit
                output = regression_misprice_row(zone, candidate)
                output.update(
                    {
                        "game_date": date_key,
                        "result": "Void" if is_void else ("HR" if actual_hr > 0 else "No HR"),
                        "actual_hr": "" if is_void else actual_hr,
                        "profit_1u": round(profit, 2),
                        "running_profit_1u": round(running[zone.title], 2),
                        "is_void": "1" if is_void else "0",
                        "void_reason": candidate.get("void_reason", "") if is_void else "",
                    }
                )
                history.append(output)
    return history



def build_regression_misprice_history_from_archives(
    regression_targets_dir: Path = DEFAULT_REGRESSION_TARGETS_DIR,
    results_dir: Path = DEFAULT_RESULTS_DIR,
) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    running: dict[str, float] = {}
    for date_key, target_path in dated_regression_target_files(regression_targets_dir).items():
        result_path = results_dir / f"daily_results_{date_key}.csv"
        if not result_path.exists():
            continue
        rows = regression_rows_from_archive_files(target_path, result_path, date_key)
        for zone in regression_misprice_zones():
            if zone.history_start_date and date_key < zone.history_start_date:
                continue
            candidates = sorted([row for row in rows if zone.predicate(row)], key=zone.sort_key)
            for candidate in candidates:
                is_void = is_void_candidate(candidate)
                actual_hr = 0 if is_void else int(parse_float(candidate.get("actual_hr")) or 0)
                odds = parse_american_odds(candidate.get("book_american_odds"))
                if odds is None:
                    continue
                profit = 0.0 if is_void else profit_for_1u(odds, actual_hr > 0)
                running[zone.title] = running.get(zone.title, 0.0) + profit
                output = regression_misprice_row(zone, candidate)
                output.update(
                    {
                        "game_date": date_key,
                        "result": "Void" if is_void else ("HR" if actual_hr > 0 else "No HR"),
                        "actual_hr": "" if is_void else actual_hr,
                        "profit_1u": round(profit, 2),
                        "running_profit_1u": round(running[zone.title], 2),
                        "is_void": "1" if is_void else "0",
                        "void_reason": candidate.get("void_reason", "") if is_void else "",
                    }
                )
                history.append(output)
    return history


def dated_regression_target_files(regression_targets_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not regression_targets_dir.exists():
        return files
    for path in sorted(regression_targets_dir.glob("daily_positive_regression_targets_*.csv")):
        date_key = date_key_from_text(path.name)
        if date_key:
            files[date_key] = path
    return files


def date_key_from_text(text: str) -> str | None:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    return match.group(1) if match else None


def regression_rows_from_archive_files(target_path: Path, result_path: Path, date_key: str) -> list[dict[str, Any]]:
    results_by_id: dict[str, dict[str, Any]] = {}
    results_by_name: dict[str, dict[str, Any]] = {}
    for result in read_csv_rows(result_path):
        player_id = str(result.get("player_id") or "").strip()
        player = result.get("player_name") or result.get("player") or ""
        if player_id:
            results_by_id[player_id] = result
        if player:
            results_by_name[player_key(str(player))] = result

    rows: list[dict[str, Any]] = []
    for source in read_csv_rows(target_path):
        player = source.get("player_name") or source.get("player") or source.get("batter") or source.get("name")
        if not player:
            continue
        player_id = str(source.get("player_id") or "").strip()
        result = (results_by_id.get(player_id) if player_id else None) or results_by_name.get(player_key(str(player)))
        if parse_american_odds(source.get("book_american_odds")) is None:
            continue
        void_reason = result_void_reason(result)
        is_void = bool(void_reason)
        row = dict(source)
        row["game_date"] = date_key
        row["player"] = player
        row["reg_score"] = row.get("positive_regression_score", "") or row.get("reg_score", "")
        row["regression_rank"] = row.get("regression_rank", "") or row.get("rank", "")
        row["model_hr_probability_percent"] = row.get("adjusted_hr_probability_percent", "")
        row["team_abbrev"] = (result or {}).get("team_abbrev", "") or row.get("team_abbrev", "") or row.get("player_team", "")
        row["opponent_abbrev"] = row.get("opponent_abbrev", "") or row.get("opponent", "")
        row["lineup_status"] = row.get("lineup_status", "")
        row["batting_order"] = (result or {}).get("batting_order", "") or row.get("batting_order", "")
        row["actual_hr"] = "" if is_void else int(parse_float(result.get("actual_hr_binary")) or parse_float(result.get("actual_hr")) or 0)
        row["result"] = "Void" if is_void else ""
        row["is_void"] = "1" if is_void else "0"
        row["void_reason"] = void_reason if is_void else ""
        rows.append(row)
    return rows


def build_regression_misprice_history_from_inputs(
    input_root: Path = Path("inputs"),
    *,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    statcast_dir: Path = DEFAULT_STATCAST_DIR,
) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    running: dict[str, float] = {}
    for date_key, input_folder in dated_input_folders(input_root).items():
        results = load_results_for_date_key(date_key, results_dir=results_dir, statcast_dir=statcast_dir)
        if not results.get("available"):
            continue
        rows = regression_rows_from_input_folder(input_folder, date_key, results.get("homers", {}))
        for zone in regression_misprice_zones():
            if zone.history_start_date and date_key < zone.history_start_date:
                continue
            candidates = sorted([row for row in rows if zone.predicate(row)], key=zone.sort_key)
            for candidate in candidates:
                actual_hr = int(parse_float(candidate.get("actual_hr")) or 0)
                odds = parse_american_odds(candidate.get("book_american_odds"))
                profit = profit_for_1u(odds, actual_hr > 0) if odds is not None else 0.0
                running[zone.title] = running.get(zone.title, 0.0) + profit
                output = regression_misprice_row(zone, candidate)
                output.update(
                    {
                        "game_date": date_key,
                        "result": "HR" if actual_hr > 0 else "No HR",
                        "actual_hr": actual_hr,
                        "profit_1u": round(profit, 2),
                        "running_profit_1u": round(running[zone.title], 2),
                    }
                )
                history.append(output)
    return history


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


def is_void_candidate(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("is_void") or "").strip() == "1" or str(candidate.get("result") or "").strip().lower() == "void"

def dated_input_folders(input_root: Path) -> dict[str, Path]:
    folders: dict[str, Path] = {}
    for folder in sorted(input_root.glob("manual_*")):
        date_key = date_key_from_input_folder(folder)
        if date_key and (folder / "gbm_progression_top80.csv").exists():
            folders[date_key] = folder
    return folders


def date_key_from_input_folder(folder: Path) -> str | None:
    parts = folder.name.split("_")
    if len(parts) < 2 or len(parts[1]) != 8:
        return None
    value = parts[1]
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def load_results_for_date_key(date_key: str, *, results_dir: Path, statcast_dir: Path) -> dict[str, Any]:
    try:
        year, month, day = [int(part) for part in date_key.split("-")]
    except ValueError:
        return {"available": False}
    return load_home_run_results(date(year, month, day), results_dir=results_dir, statcast_dir=statcast_dir, use_pybaseball=False)


def regression_rows_from_input_folder(input_folder: Path, date_key: str, homers: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    path = input_folder / "gbm_progression_top80.csv"
    if not path.exists():
        return rows
    for source in read_csv_rows(path):
        player = source.get("player_name") or source.get("player") or source.get("batter") or source.get("name")
        if not player:
            continue
        row = dict(source)
        row["game_date"] = date_key
        row["player"] = player
        row["reg_score"] = row.get("positive_regression_score", "") or row.get("reg_score", "")
        row["regression_rank"] = row.get("regression_rank", "") or row.get("rank", "")
        row["model_hr_probability_percent"] = row.get("adjusted_hr_probability_percent", "")
        row["team_abbrev"] = row.get("team_abbrev", "") or row.get("player_team", "")
        row["opponent_abbrev"] = row.get("opponent_abbrev", "") or row.get("opponent", "")
        row["actual_hr"] = int(homers.get(player_key(str(player)), 0))
        rows.append(row)
    return rows


def input_folder_for_date_key(date_key: str, input_root: Path) -> Path | None:
    try:
        from datetime import date
        year, month, day = [int(part) for part in date_key.split("-")]
        return latest_input_folder_for_date(date(year, month, day), input_root)
    except Exception:
        return None


def profit_for_1u(american_odds: int | None, won: bool) -> float:
    if american_odds is None:
        return 0.0
    if not won:
        return -1.0
    if american_odds > 0:
        return american_odds / 100.0
    return 100.0 / abs(american_odds)
