from __future__ import annotations

import csv
import os
import re
import subprocess
import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .io import player_key
from .paths import GBM, UPSTREAM_PYTHON


DEFAULT_GBM_PROJECT = GBM
DEFAULT_RESULTS_DIR = DEFAULT_GBM_PROJECT / "data" / "history" / "daily_results"
DEFAULT_STATCAST_DIR = DEFAULT_GBM_PROJECT / "data" / "raw" / "statcast"

MARKET_COLUMNS = (
    "game_date",
    "player_id",
    "team_abbrev",
    "opponent_abbrev",
    "lineup_status",
    "batting_order",
    "model_hr_probability_percent",
    "model_american_odds",
    "bookmaker_used",
    "book_american_odds",
    "dk_odds",
    "fan_odds",
    "365_odds",
    "edge_percent",
    "odds_source",
    "odds_last_update",
)


@dataclass(frozen=True)
class TrackerOutputs:
    detail_path: Path
    summary_path: Path
    report_path: Path
    graded_rows: int
    graded_days: int


def run_rank_tracker(
    *,
    board_root: Path = Path("MODEL4_DAILY_READS"),
    input_root: Path = Path("inputs"),
    output_folder: Path = Path("MODEL4_RANK_TRACKING"),
    results_dir: Path = DEFAULT_RESULTS_DIR,
    statcast_dir: Path = DEFAULT_STATCAST_DIR,
    start_date: date | None = None,
    end_date: date | None = None,
    use_pybaseball: bool = False,
    limit: int | None = None,
) -> TrackerOutputs:
    boards = discover_daily_boards(board_root, start_date=start_date, end_date=end_date)
    detail_rows: list[dict[str, Any]] = []
    result_cache: dict[str, dict[str, Any]] = {}

    for board_date, board_path in boards:
        date_key = board_date.isoformat()
        if date_key not in result_cache:
            result_cache[date_key] = load_home_run_results(
                board_date,
                results_dir=results_dir,
                statcast_dir=statcast_dir,
                use_pybaseball=use_pybaseball,
            )

        rows = read_csv_rows(board_path)
        if limit is not None:
            rows = rows[:limit]
        gbm_market = load_input_market_for_date(board_date, input_root)
        detail_rows.extend(grade_board_rows(board_date, board_path, rows, result_cache[date_key], gbm_market))

    summary_rows = summarize_rank_slots(detail_rows)
    output_folder.mkdir(parents=True, exist_ok=True)
    detail_path = output_folder / "model4_rank_results.csv"
    summary_path = output_folder / "model4_rank_summary.csv"
    report_path = output_folder / "model4_rank_report.md"
    write_csv(detail_path, detail_fieldnames(), detail_rows)
    write_csv(summary_path, summary_fieldnames(), summary_rows)
    write_report(report_path, detail_rows, summary_rows)

    graded_days = len({row["game_date"] for row in detail_rows if row.get("result_available") == "1"})
    graded_rows = sum(1 for row in detail_rows if row.get("result_available") == "1")
    return TrackerOutputs(detail_path, summary_path, report_path, graded_rows, graded_days)


def run_gbm_odds_pull(game_date: date, *, gbm_project: Path = DEFAULT_GBM_PROJECT) -> None:
    script = gbm_project / "scripts" / "pull_top10_hr_prop_odds.py"
    if not script.exists():
        raise FileNotFoundError(f"Missing GBM odds pull script: {script}")

    command = [str(UPSTREAM_PYTHON), str(script), "--date", game_date.isoformat(), "--all-schedule"]
    if not (os.environ.get("ODDS_API_KEY") or os.environ.get("THE_ODDS_API_KEY")):
        command.append("--prompt-key")
    subprocess.run(command, cwd=gbm_project, check=True)


def refresh_completed_results(
    board_root: Path = Path("MODEL4_DAILY_READS"),
    *,
    gbm_project: Path = DEFAULT_GBM_PROJECT,
    start_date: date | None = None,
    end_date: date | None = None,
    force: bool = False,
) -> list[date]:
    script = gbm_project / "scripts" / "pull_daily_results.py"
    if not script.exists():
        raise FileNotFoundError(f"Missing GBM results pull script: {script}")

    last_completed_date = min(end_date or yesterday(), yesterday())
    board_dates = [
        board_date
        for board_date, _ in discover_daily_boards(board_root, start_date=start_date, end_date=last_completed_date)
    ]
    refreshed: list[date] = []
    for board_date in board_dates:
        output_path = gbm_project / "data" / "history" / "daily_results" / f"daily_results_{board_date.isoformat()}.csv"
        if output_path.exists() and not force:
            continue
        subprocess.run(
            ["python3", str(script), "--date", board_date.isoformat()],
            cwd=gbm_project,
            check=True,
        )
        refreshed.append(board_date)
    return refreshed


def discover_daily_boards(
    board_root: Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[tuple[date, Path]]:
    boards: list[tuple[date, Path]] = []
    if not board_root.exists():
        return boards

    for path in board_root.glob("*/MODEL4_*_BOARD.csv"):
        board_date = parse_date_from_daily_board(path)
        if not board_date:
            continue
        if start_date and board_date < start_date:
            continue
        if end_date and board_date > end_date:
            continue
        boards.append((board_date, path))

    return sorted(boards, key=lambda item: item[0])


def parse_date_from_daily_board(path: Path) -> date | None:
    for text in (path.parent.name, path.name):
        match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
        if match:
            return parse_date(match.group(1))
    return None


def load_input_market_for_date(game_date: date, input_root: Path) -> dict[str, dict[str, Any]]:
    folder = latest_input_folder_for_date(game_date, input_root)
    if not folder:
        return {}

    market: dict[str, dict[str, Any]] = {}
    for filename in ("gbm_top80.csv", "gbm_progression_top80.csv", "pitcher_batter_top80.csv"):
        path = folder / filename
        if not path.exists():
            continue
        for row in read_csv_rows(path):
            player = row.get("player_name") or row.get("player") or row.get("batter") or row.get("name")
            if not player:
                continue
            key = player_key(str(player))
            market.setdefault(key, {})
            normalized = {normalize_header(name): value for name, value in row.items()}
            for source, target in market_aliases().items():
                value = normalized.get(source)
                if value not in (None, "") and not market[key].get(target):
                    market[key][target] = value
    return market


def latest_input_folder_for_date(game_date: date, input_root: Path) -> Path | None:
    date_key = game_date.strftime("%Y%m%d")
    candidates = [path for path in input_root.glob(f"manual_{date_key}_*") if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def market_aliases() -> dict[str, str]:
    return {
        "game_date": "game_date",
        "player_id": "player_id",
        "team_abbrev": "team_abbrev",
        "player_team": "team_abbrev",
        "opponent_abbrev": "opponent_abbrev",
        "opponent": "opponent_abbrev",
        "lineup_status": "lineup_status",
        "batting_order": "batting_order",
        "adjusted_hr_probability_percent": "model_hr_probability_percent",
        "hr_probability": "model_hr_probability_percent",
        "american_betting_odds": "model_american_odds",
        "bookmaker_used": "bookmaker_used",
        "sportsbook_used": "bookmaker_used",
        "sportsbook": "bookmaker_used",
        "best_book": "bookmaker_used",
        "book_american_odds": "book_american_odds",
        "best_book_odds": "book_american_odds",
        "dk_odds": "dk_odds",
        "draftkings_odds": "dk_odds",
        "fan_odds": "fan_odds",
        "fanatics_odds": "fan_odds",
        "365_odds": "365_odds",
        "bet365_odds": "365_odds",
        "edge_percent": "edge_percent",
        "odds_source": "odds_source",
        "odds_last_update": "odds_last_update",
    }


def grade_board_rows(
    game_date: date,
    board_path: Path,
    rows: list[dict[str, Any]],
    results: dict[str, Any],
    gbm_market: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    homers = results.get("homers", {})
    played = results.get("played")
    voided = results.get("voided", {})
    result_source = results.get("source", "")
    result_available = bool(results.get("available"))
    graded: list[dict[str, Any]] = []

    for row in rows:
        player = str(row.get("player") or "").strip()
        key = player_key(player)
        market = {column: row.get(column, "") for column in MARKET_COLUMNS}
        for column, value in gbm_market.get(key, {}).items():
            if not market.get(column):
                market[column] = value
        market.pop("game_date", None)

        void_reason = ""
        if result_available and isinstance(voided, dict):
            void_reason = str(voided.get(key) or "")
        if result_available and isinstance(played, set) and key not in played:
            void_reason = "Player not listed with a PA in completed daily results"
        is_void = bool(void_reason)
        if is_void:
            actual_hr = ""
            did_hr = ""
            result = "Void"
            profit = 0.0
        else:
            actual_hr = int(homers.get(key, 0)) if result_available else ""
            did_hr = int(actual_hr > 0) if result_available else ""
            result = "HR" if did_hr else ("No HR" if result_available else "")
            book_odds = parse_american_odds(market.get("book_american_odds"))
            profit = profit_for_1u(book_odds, bool(did_hr)) if result_available and book_odds is not None else ""

        graded.append(
            {
                "game_date": game_date.isoformat(),
                "eye_rank": row.get("eye_rank", ""),
                "player": player,
                "eye_score": row.get("eye_score", ""),
                "accel_score": row.get("accel_score", ""),
                "stale_signal_status": row.get("stale_signal_status", ""),
                **market,
                "result_available": "1" if result_available else "0",
                "result": result,
                "is_void": "1" if is_void else "0",
                "void_reason": void_reason,
                "actual_hr": actual_hr,
                "did_hr": did_hr,
                "profit_1u": round(profit, 4) if isinstance(profit, float) else "",
                "result_source": result_source,
                "board_path": str(board_path),
            }
        )
    return graded


def load_home_run_results(
    game_date: date,
    *,
    results_dir: Path,
    statcast_dir: Path,
    use_pybaseball: bool,
) -> dict[str, Any]:
    daily_results = results_dir / f"daily_results_{game_date.isoformat()}.csv"
    if daily_results.exists():
        homers: dict[str, int] = {}
        played: set[str] = set()
        voided: dict[str, str] = {}
        for row in read_csv_rows(daily_results):
            player = row.get("player_name") or row.get("player")
            if not player:
                continue
            key = player_key(str(player))
            pa = parse_int(row.get("actual_pa"))
            ab = parse_int(row.get("actual_ab"))
            if pa is None and ab is None:
                played.add(key)
            elif (pa or 0) > 0 or (ab or 0) > 0:
                played.add(key)
            reason = result_void_reason(row)
            if reason:
                voided[key] = reason
            actual_hr = parse_int(row.get("actual_hr")) or parse_int(row.get("actual_hr_binary")) or 0
            if actual_hr > 0:
                homers[key] = homers.get(key, 0) + actual_hr
        return {"available": True, "homers": homers, "played": played, "voided": voided, "source": str(daily_results)}

    statcast_homers = load_statcast_home_runs(game_date, statcast_dir)
    if statcast_homers is not None:
        return {"available": True, "homers": statcast_homers, "played": None, "voided": {}, "source": "local_statcast"}

    if use_pybaseball:
        pybaseball_homers = fetch_pybaseball_home_runs(game_date)
        if pybaseball_homers is not None:
            return {"available": True, "homers": pybaseball_homers, "played": None, "voided": {}, "source": "pybaseball"}

    return {"available": False, "homers": {}, "played": None, "voided": {}, "source": "missing_results"}


def result_void_reason(row: dict[str, Any]) -> str:
    position = str(row.get("lineup_position") or "").strip().upper()
    ab = parse_int(row.get("actual_ab")) or 0
    if position == "PH" and ab == 1:
        return "Pinch-hit one AB without starting"
    return ""

def load_statcast_home_runs(game_date: date, statcast_dir: Path) -> dict[str, int] | None:
    if not statcast_dir.exists():
        return None

    homers: dict[str, int] = {}
    found_covering_file = False
    for path in statcast_dir.glob("statcast_*.csv"):
        date_range = parse_statcast_date_range(path.name)
        if not date_range:
            continue
        start, end = date_range
        if not (start <= game_date <= end):
            continue
        found_covering_file = True
        for row in read_csv_rows(path):
            if str(row.get("game_date") or "") != game_date.isoformat():
                continue
            if str(row.get("events") or "").lower() != "home_run":
                continue
            player = parse_homer_name(row.get("des"))
            if player:
                key = player_key(player)
                homers[key] = homers.get(key, 0) + 1
    return homers if found_covering_file else None


def fetch_pybaseball_home_runs(game_date: date) -> dict[str, int] | None:
    os.environ.setdefault("PYBASEBALL_CACHE", str(Path(".cache") / "pybaseball"))
    os.environ.setdefault("MPLCONFIGDIR", str(Path(".cache") / "matplotlib"))
    try:
        from pybaseball import statcast  # type: ignore
    except ImportError:
        return None

    try:
        frame = statcast(game_date.isoformat(), game_date.isoformat())
    except Exception:
        return None

    homers: dict[str, int] = {}
    if frame is None or frame.empty or "events" not in frame.columns:
        return homers

    for _, row in frame[frame["events"].eq("home_run")].iterrows():
        player = parse_homer_name(row.get("des"))
        if player:
            key = player_key(player)
            homers[key] = homers.get(key, 0) + 1
    return homers


def is_void_row(row: dict[str, Any]) -> bool:
    return str(row.get("is_void") or "").strip() == "1" or str(row.get("result") or "").strip().lower() == "void"

def summarize_rank_slots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        rank = parse_int(row.get("eye_rank"))
        if rank is None or row.get("result_available") != "1" or is_void_row(row):
            continue
        grouped.setdefault(rank, []).append(row)

    summary: list[dict[str, Any]] = []
    for rank in sorted(grouped):
        rank_rows = grouped[rank]
        wins = sum(parse_int(row.get("did_hr")) or 0 for row in rank_rows)
        days = len(rank_rows)
        odds_rows = [row for row in rank_rows if parse_american_odds(row.get("book_american_odds")) is not None]
        profits = [parse_float(row.get("profit_1u")) or 0.0 for row in odds_rows]
        odds_values = [parse_american_odds(row.get("book_american_odds")) for row in odds_rows]
        odds_values = [value for value in odds_values if value is not None]
        hit_rate = wins / days if days else 0.0
        profit = sum(profits)
        summary.append(
            {
                "eye_rank": rank,
                "tracked_days": days,
                "home_runs": wins,
                "hit_rate_percent": round(hit_rate * 100, 2),
                "fair_american_odds": probability_to_american(hit_rate),
                "bets_with_book_odds": len(odds_rows),
                "avg_book_american_odds": round(sum(odds_values) / len(odds_values), 1) if odds_values else "",
                "profit_1u_flat": round(profit, 4),
                "roi_percent": round((profit / len(odds_rows)) * 100, 2) if odds_rows else "",
            }
        )
    return summary


def write_report(path: Path, detail_rows: list[dict[str, Any]], summary_rows: list[dict[str, Any]]) -> None:
    graded_rows = [row for row in detail_rows if row.get("result_available") == "1"]
    graded_days = sorted({row["game_date"] for row in graded_rows})
    lines = ["# Model 4 Rank Tracker", ""]
    lines.append(f"Graded days: {len(graded_days)}")
    lines.append(f"Graded player rows: {len(graded_rows)}")
    lines.append("")
    lines.append("| Eye Rank | Days | HR | HR% | Fair Odds | Bets w/Odds | Profit 1u | ROI |")
    lines.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in summary_rows[:30]:
        lines.append(
            f"| {row['eye_rank']} | {row['tracked_days']} | {row['home_runs']} | "
            f"{row['hit_rate_percent']} | {row['fair_american_odds']} | "
            f"{row['bets_with_book_odds']} | {row['profit_1u_flat']} | {row['roi_percent']} |"
        )
    lines.append("")

    top_one = next((row for row in summary_rows if int(row["eye_rank"]) == 1), None)
    if top_one:
        lines.append(
            "#1 snapshot: "
            f"{top_one['home_runs']}/{top_one['tracked_days']} HR, "
            f"{top_one['hit_rate_percent']}%, fair odds {top_one['fair_american_odds']}, "
            f"profit {top_one['profit_1u_flat']}u."
        )
        lines.append("")

    profitable = sorted(
        [row for row in summary_rows if row.get("bets_with_book_odds")],
        key=lambda row: float(row.get("profit_1u_flat") or 0),
        reverse=True,
    )
    if profitable:
        lines.append("## Best Rank Slots By Flat Profit")
        lines.append("")
        lines.append("| Eye Rank | Bets | HR% | Profit 1u | ROI |")
        lines.append("| ---: | ---: | ---: | ---: | ---: |")
        for row in profitable[:10]:
            lines.append(
                f"| {row['eye_rank']} | {row['bets_with_book_odds']} | "
                f"{row['hit_rate_percent']} | {row['profit_1u_flat']} | {row['roi_percent']} |"
            )
        lines.append("")

    rank_one_hits = [
        row for row in detail_rows
        if str(row.get("eye_rank")) == "1" and str(row.get("did_hr")) == "1"
    ]
    if rank_one_hits:
        lines.append("## #1 Hit Dates")
        lines.append("")
        for row in rank_one_hits:
            odds = f" at {row['book_american_odds']}" if row.get("book_american_odds") else ""
            lines.append(f"- {row['game_date']}: {row['player']}{odds}")
        lines.append("")

    missing_odds = sum(1 for row in graded_rows if not row.get("book_american_odds"))
    if missing_odds:
        lines.append(f"Rows without book odds: {missing_odds}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def detail_fieldnames() -> list[str]:
    return [
        "game_date",
        "eye_rank",
        "player",
        "eye_score",
        "accel_score",
        "stale_signal_status",
        *[column for column in MARKET_COLUMNS if column != "game_date"],
        "result_available",
        "result",
        "is_void",
        "void_reason",
        "actual_hr",
        "did_hr",
        "profit_1u",
        "result_source",
        "board_path",
    ]


def summary_fieldnames() -> list[str]:
    return [
        "eye_rank",
        "tracked_days",
        "home_runs",
        "hit_rate_percent",
        "fair_american_odds",
        "bets_with_book_odds",
        "avg_book_american_odds",
        "profit_1u_flat",
        "roi_percent",
    ]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_optional_date(value: str) -> date | None:
    text = value.strip()
    return parse_date(text) if text else None


def parse_statcast_date_range(filename: str) -> tuple[date, date] | None:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})_to_(20\d{2}-\d{2}-\d{2})", filename)
    if not match:
        return None
    return parse_date(match.group(1)), parse_date(match.group(2))


def parse_homer_name(description: Any) -> str:
    text = str(description or "")
    match = re.search(r"^(?:Umpire reviewed \([^)]*\), call on the field was overturned: )?(.+?) homers? ", text)
    return match.group(1).strip() if match else ""


def parse_american_odds(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace("+", "")
    if not text:
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("+", ""))
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    parsed = parse_float(value)
    return int(parsed) if parsed is not None else None


def profit_for_1u(odds: int, did_win: bool) -> float:
    if not did_win:
        return -1.0
    if odds > 0:
        return odds / 100
    return 100 / abs(odds)


def probability_to_american(probability: float) -> str:
    if probability <= 0:
        return ""
    if probability >= 1:
        return "-10000"
    if probability >= 0.5:
        return str(int(round(-100 * probability / (1 - probability))))
    return f"+{int(round(100 * (1 - probability) / probability))}"


def normalize_header(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", " ").split())


def yesterday() -> date:
    return date.today() - timedelta(days=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade Model 4 rank slots against HR results and odds.")
    parser.add_argument("--boards", default=Path("MODEL4_DAILY_READS"), type=Path)
    parser.add_argument("--inputs", default=Path("inputs"), type=Path)
    parser.add_argument("--out", default=Path("MODEL4_RANK_TRACKING"), type=Path)
    parser.add_argument("--results", default=DEFAULT_RESULTS_DIR, type=Path)
    parser.add_argument("--statcast", default=DEFAULT_STATCAST_DIR, type=Path)
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--use-pybaseball", action="store_true")
    parser.add_argument("--refresh-gbm-odds-date", default="")
    parser.add_argument("--refresh-results", action="store_true")
    parser.add_argument("--force-refresh-results", action="store_true")
    args = parser.parse_args(argv)

    if args.refresh_gbm_odds_date:
        run_gbm_odds_pull(parse_date(args.refresh_gbm_odds_date))

    start_date = parse_optional_date(args.start_date)
    end_date = parse_optional_date(args.end_date)
    if args.refresh_results:
        refreshed = refresh_completed_results(
            args.boards,
            start_date=start_date,
            end_date=end_date,
            force=args.force_refresh_results,
        )
        if refreshed:
            print("Refreshed completed results:", ", ".join(day.isoformat() for day in refreshed))
        else:
            print("Completed results already up to date for available Model 4 board dates.")

    outputs = run_rank_tracker(
        board_root=args.boards,
        input_root=args.inputs,
        output_folder=args.out,
        results_dir=args.results,
        statcast_dir=args.statcast,
        start_date=start_date,
        end_date=end_date,
        use_pybaseball=args.use_pybaseball,
        limit=args.limit,
    )
    print(f"Wrote rank results: {outputs.detail_path}")
    print(f"Wrote rank summary: {outputs.summary_path}")
    print(f"Wrote rank report: {outputs.report_path}")
    print(f"Graded {outputs.graded_rows} rows across {outputs.graded_days} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
