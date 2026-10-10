from __future__ import annotations

import csv
import shlex
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from .boards import BOARD_SPECS
from .cli import main as run_cli
from .io import write_reasoning_markdown
from .closer import run_closer
from .profit_lenses import build_profit_lenses_from_run, read_csv_rows
from .profit_parlays import build_profit_parlays_from_run
from .prospective_parlays import build_prospective_parlays_from_run
from .regression_misprice import build_regression_misprice_from_run
from .sequence_edge import build_daily_sequence_edge, save_sequence_edge_daily_copy
from .tracker import (
    DEFAULT_RESULTS_DIR,
    DEFAULT_STATCAST_DIR,
    parse_american_odds,
    parse_optional_date,
    refresh_completed_results,
    run_gbm_odds_pull,
    run_rank_tracker,
)


BOARD_PROMPTS = (
    ("gbm_top80", "Top 80 HR projections", "gbm_top80.csv"),
    ("gbm_progression_top80", "Top 80 progression list", "gbm_progression_top80.csv"),
    ("sequence_top150", "Sequence list", "sequence_top150.csv"),
    ("pitcher_batter_top80", "Last model CSV", "pitcher_batter_top80.csv"),
)


def main() -> int:
    print("\nAll-Seeing Eye Model 4")
    print("======================")
    while True:
        print("\nMenu")
        print("1. Build an input set from files or pasted lists, then run")
        print("2. Run an existing input folder")
        print("3. Run The Closer from a Model 4 output")
        print("4. Update rank results tracker")
        print("5. Open profit lens Streamlit page")
        print("6. Show the expected CSV filenames")
        print("7. Quit")
        choice = input("\nChoose 1-7: ").strip()

        if choice == "1":
            build_and_run()
        elif choice == "2":
            run_existing_folder()
        elif choice == "3":
            run_closer_from_menu()
        elif choice == "4":
            run_tracker_from_menu()
        elif choice == "5":
            run_profit_lens_app_from_menu()
        elif choice == "6":
            show_expected_files()
        elif choice == "7":
            print("Done.")
            return 0
        else:
            print("Please choose 1, 2, 3, 4, 5, 6, or 7.")


def build_and_run() -> int:
    auto_update_previous_results()

    default_name = f"manual_{datetime.now().strftime('%Y%m%d_%H%M')}"
    input_name = prompt_default("Input set name", default_name)
    input_folder = Path("inputs") / input_name
    input_folder.mkdir(parents=True, exist_ok=True)

    print("\nYou will enter exactly four inputs, one at a time:")
    for index, (_, label, filename) in enumerate(BOARD_PROMPTS, start=1):
        print(f"{index}. {label} -> {filename}")
    print("\nFor each input, choose a CSV file or paste a ranked list.")
    print("Pasted lines can look like: 1, Kyle Schwarber  |  Kyle Schwarber,1  |  1 Kyle Schwarber")
    print("Finish a pasted list with a blank line.\n")

    total_inputs = len(BOARD_PROMPTS)
    for index, (board_id, label, _) in enumerate(BOARD_PROMPTS, start=1):
        write_board_input(input_folder, board_id, label, index, total_inputs)

    yesterday = ask_optional_path("\nOptional yesterday folder for day-over-day movement")
    history = ask_optional_path("Optional history folder for stale-signal detection")
    output_folder = Path(prompt_default("Output folder", f"outputs/{input_name}"))
    limit = prompt_default("Output limit", "120")

    return run_model(input_folder, output_folder, yesterday, history, limit)


def auto_update_previous_results(
    *,
    board_root: Path = Path("MODEL4_DAILY_READS"),
    input_root: Path = Path("inputs"),
    output_folder: Path = Path("MODEL4_RANK_TRACKING"),
    results_dir: Path = DEFAULT_RESULTS_DIR,
    statcast_dir: Path = DEFAULT_STATCAST_DIR,
    target_date: date | None = None,
) -> bool:
    previous_date = target_date or (date.today() - timedelta(days=1))
    board_path = daily_board_path(board_root, previous_date)

    if not board_path.exists():
        print(f"\nNo Model 4 board found for {previous_date.isoformat()}; skipping yesterday results update.")
        return False

    print(f"\nChecking yesterday's Model 4 results: {previous_date.isoformat()}")
    try:
        refreshed = refresh_completed_results(board_root, start_date=previous_date, end_date=previous_date)
        if refreshed:
            print("Refreshed completed results: " + ", ".join(day.isoformat() for day in refreshed))
        else:
            print("Completed results already exist for yesterday.")

        outputs = run_rank_tracker(
            board_root=board_root,
            input_root=input_root,
            output_folder=output_folder,
            results_dir=results_dir,
            statcast_dir=statcast_dir,
            use_pybaseball=False,
        )
        print(f"Updated Streamlit history tracker: {outputs.graded_rows} rows across {outputs.graded_days} days.")
        return True
    except Exception as exc:
        print(f"Yesterday results preflight could not complete: {exc}")
        print("Continuing to today's Model 4 run.")
        return False


def daily_board_path(board_root: Path, board_date: date) -> Path:
    day = board_date.isoformat()
    return board_root / day / f"MODEL4_{day}_BOARD.csv"


def run_existing_folder() -> int:
    input_folder = Path(prompt_default("Input folder", "inputs/today"))
    yesterday = ask_optional_path("Optional yesterday folder for day-over-day movement")
    history = ask_optional_path("Optional history folder for stale-signal detection")
    output_folder = Path(prompt_default("Output folder", "outputs"))
    limit = prompt_default("Output limit", "120")
    return run_model(input_folder, output_folder, yesterday, history, limit)


def run_closer_from_menu() -> int:
    default_output = latest_eye_output_folder() or Path("outputs")
    output_folder = Path(prompt_default("Model 4 output folder", str(default_output)))
    default_input = infer_input_folder(output_folder) or Path("inputs/today")
    input_folder = Path(prompt_default("Input folder used for that Model 4 run", str(default_input)))
    closer_output = Path(prompt_default("Closer output folder", str(output_folder / "closer")))
    pool_limit = prompt_default("How many Eye players should The Closer review", "40")
    output_limit = prompt_default("How many Closer candidates should it output", "20")

    candidates = run_closer(
        output_folder,
        input_folder,
        closer_output,
        pool_limit=int(pool_limit),
        output_limit=int(output_limit),
    )
    save_closer_daily_copy(closer_output)
    show_closer_rows(candidates)
    return 0


def run_tracker_from_menu() -> int:
    refresh = input("Run GBM odds API pull first? [y/N]: ").strip().lower()
    if refresh == "y":
        odds_date = prompt_default("GBM odds date", datetime.now().strftime("%Y-%m-%d"))
        run_gbm_odds_pull(parse_optional_date(odds_date) or datetime.now().date())

    board_root = Path(prompt_default("Model 4 daily board folder", "MODEL4_DAILY_READS"))
    input_root = Path(prompt_default("Model 4 input folder root", "inputs"))
    results_dir = Path(
        prompt_default(
            "Daily results folder",
            str(DEFAULT_RESULTS_DIR),
        )
    )
    statcast_dir = Path(
        prompt_default(
            "Statcast fallback folder",
            str(DEFAULT_STATCAST_DIR),
        )
    )
    start_date = parse_optional_date(prompt_default("Start date", ""))
    end_date = parse_optional_date(prompt_default("End date", ""))
    refresh_results = input("Refresh completed HR results before grading? [Y/n]: ").strip().lower()
    if refresh_results != "n":
        refreshed = refresh_completed_results(board_root, start_date=start_date, end_date=end_date)
        if refreshed:
            print("Refreshed completed results:", ", ".join(day.isoformat() for day in refreshed))
        else:
            print("Completed results already up to date for available Model 4 board dates.")

    use_pybaseball = input("Use pybaseball if local results are missing? [y/N]: ").strip().lower() == "y"
    output_folder = Path(prompt_default("Tracking output folder", "MODEL4_RANK_TRACKING"))

    outputs = run_rank_tracker(
        board_root=board_root,
        input_root=input_root,
        output_folder=output_folder,
        results_dir=results_dir,
        statcast_dir=statcast_dir,
        start_date=start_date,
        end_date=end_date,
        use_pybaseball=use_pybaseball,
    )
    print(f"Wrote rank results to {outputs.detail_path}")
    print(f"Wrote rank summary to {outputs.summary_path}")
    print(f"Wrote readable report to {outputs.report_path}")
    print(f"Graded {outputs.graded_rows} player rows across {outputs.graded_days} days")
    return 0


def run_profit_lens_app_from_menu() -> int:
    script = Path("scripts") / "profit_lens_app.py"
    print("\nStarting Streamlit profit lens page.")
    print("Local URL: http://localhost:8501")
    print("Press Ctrl+C in this terminal when you are done with the page.")
    return subprocess.run([sys.executable, "-m", "streamlit", "run", str(script)], check=False).returncode


def run_model(
    input_folder: Path,
    output_folder: Path,
    yesterday: Path | None,
    history: Path | None,
    limit: str,
) -> int:
    argv = ["--today", str(input_folder), "--out", str(output_folder), "--limit", limit]
    if yesterday:
        argv.extend(["--yesterday", str(yesterday)])
    if history:
        argv.extend(["--history", str(history)])

    result = run_cli(argv)
    if result == 0:
        board_path = output_folder / "all_seeing_eye_board.csv"
        reasoning_path = output_folder / "all_seeing_eye_reasoning.md"
        resolve_missing_book_odds(board_path, reasoning_path)
        lens_folder = build_daily_profit_lenses(output_folder, input_folder)
        parlay_folder = build_daily_profit_parlays(output_folder, input_folder)
        prospective_folder = build_daily_prospective_parlays(output_folder, input_folder)
        regression_folder = build_daily_regression_misprice(output_folder, input_folder)
        save_daily_read_copy(output_folder)
        sequence_edge_folder = build_daily_sequence_edge(output_folder)
        if lens_folder:
            save_profit_lens_daily_copy(lens_folder)
        if parlay_folder:
            save_profit_parlay_daily_copy(parlay_folder)
        if prospective_folder:
            save_prospective_parlay_daily_copy(prospective_folder)
        if regression_folder:
            save_regression_misprice_daily_copy(regression_folder)
        if sequence_edge_folder:
            saved_sequence_edge = save_sequence_edge_daily_copy(sequence_edge_folder)
            print(f"Saved daily sequence edge files to {saved_sequence_edge}")
        show_top_rows(output_folder / "all_seeing_eye_board.csv")
        if lens_folder:
            show_profit_lens_rows(lens_folder / "profit_lenses_combined.csv")
        if parlay_folder:
            show_profit_parlay_rows(parlay_folder / "profit_parlays_combined.csv")
            show_profit_parlay_rows(parlay_folder / "profit_parlays_3leg_combined.csv", title="Profit 3-leg parlay candidates")
            show_profit_parlay_rows(parlay_folder / "profit_parlays_4leg_combined.csv", title="Profit 4-leg parlay candidates")
            show_profit_parlay_rows(parlay_folder / "profit_parlays_movement_combined.csv", title="Profit movement parlay candidates")
        if prospective_folder:
            show_prospective_parlay_rows(prospective_folder / "prospective_parlays_combined.csv")
        if regression_folder:
            show_regression_misprice_rows(regression_folder / "regression_misprice_combined.csv")
    return result


def write_board_input(
    input_folder: Path,
    board_id: str,
    label: str,
    index: int,
    total_inputs: int,
) -> None:
    filename = BOARD_SPECS[board_id]["filename"]
    destination = input_folder / filename

    while True:
        print(f"\nInput {index} of {total_inputs}: {label}")
        print(f"This will be saved as: {filename}")
        print("  F = use a CSV file")
        print("  P = paste a simple ranked list")
        mode = input("Choose F or P: ").strip().lower()

        if mode == "f":
            source_text = input("CSV path: ")
            source = parse_path(source_text)
            if not source.exists():
                print(f"Could not find: {source}")
                print(f"Still on Input {index} of {total_inputs}: {label}. Please try that same CSV again.")
                continue
            shutil.copyfile(source, destination)
            print(f"Completed Input {index} of {total_inputs}: saved {destination}")
            return

        if mode == "p":
            rows = collect_pasted_rows()
            if not rows:
                print(f"No rows pasted. Still on Input {index} of {total_inputs}: {label}.")
                continue
            write_simple_board(destination, rows)
            print(f"Completed Input {index} of {total_inputs}: saved {len(rows)} rows to {destination}")
            return

        print("Please choose F or P.")


def collect_pasted_rows() -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    while True:
        line = input()
        if not line.strip():
            return rows
        parsed = parse_ranked_line(line)
        if parsed:
            rows.append(parsed)
        else:
            print(f"Skipped line I could not parse: {line}")


def resolve_missing_book_odds(board_path: Path, reasoning_path: Path | None = None, prompt_func=input) -> tuple[int, int]:
    if not board_path.exists():
        return 0, 0

    with board_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if not rows:
        return 0, 0

    missing_rows = [row for row in rows if is_missing_book_odds(row)]
    if not missing_rows:
        print("All Model 4 board rows have book odds.")
        return 0, 0

    print("\nMissing book odds check")
    print("-----------------------")
    print(f"Found {len(missing_rows)} Model 4 board rows without book odds.")
    print("For each player, enter odds like +450 or 450, or type out to remove/ignore them today.")

    removed_players: set[str] = set()
    filled_count = 0
    for row in missing_rows:
        player = row.get("player", "")
        rank = row.get("eye_rank", "")
        team = row.get("team_abbrev", "")
        opponent = row.get("opponent_abbrev", "")
        context = f"rank {rank}" if rank else "unranked"
        if team or opponent:
            context += f", {team or '?'} vs {opponent or '?'}"

        while True:
            value = prompt_func(f"Book odds for {player} ({context}) or out: ").strip()
            lowered = value.lower()
            if lowered in {"out", "out today", "o", "remove", "ignore", "x", "scratch", "scratched"}:
                removed_players.add(player)
                print(f"Removed {player} from today's Model 4 board.")
                break
            odds = normalize_american_odds(value)
            if odds is not None:
                row["book_american_odds"] = odds
                row["odds_source"] = row.get("odds_source") or "manual_menu"
                row["bookmaker_used"] = row.get("bookmaker_used") or "Manual"
                row["odds_last_update"] = datetime.now().isoformat(timespec="seconds")
                filled_count += 1
                print(f"Added {odds} for {player}.")
                break
            print("Please enter odds like +450, 450, -120, or type out.")

    if removed_players:
        rows = [row for row in rows if row.get("player", "") not in removed_players]
        renumber_eye_ranks(rows)

    write_board_rows(board_path, fieldnames, rows)
    if reasoning_path:
        write_reasoning_markdown(reasoning_path, rows)

    if filled_count or removed_players:
        print(f"Cleaned missing odds: added {filled_count}, removed {len(removed_players)}.")
    else:
        print("No missing-odds changes were made.")
    return filled_count, len(removed_players)


def is_missing_book_odds(row: dict[str, str]) -> bool:
    return parse_american_odds(row.get("book_american_odds")) is None


def normalize_american_odds(value: str) -> str | None:
    odds = parse_american_odds(value)
    if odds is None or odds == 0:
        return None
    return f"+{odds}" if odds > 0 else str(odds)


def renumber_eye_ranks(rows: list[dict[str, str]]) -> None:
    rows.sort(key=lambda row: parse_rank(str(row.get("eye_rank", ""))) or 9999)
    for index, row in enumerate(rows, start=1):
        row["eye_rank"] = str(index)


def write_board_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    if not fieldnames:
        fieldnames = sorted({key for row in rows for key in row})
    for field in ("book_american_odds", "odds_source", "bookmaker_used", "odds_last_update"):
        if field not in fieldnames:
            fieldnames.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_ranked_line(line: str) -> tuple[str, int] | None:
    text = line.strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered.startswith("rank,") or lowered.startswith("player,"):
        return None

    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) >= 2:
            first_rank = parse_rank(parts[0])
            last_rank = parse_rank(parts[-1])
            if first_rank is not None:
                return " ".join(parts[1:]).strip(), first_rank
            if last_rank is not None:
                return " ".join(parts[:-1]).strip(), last_rank

    parts = text.replace(".", " ", 1).replace(")", " ", 1).split()
    if len(parts) >= 2:
        rank = parse_rank(parts[0])
        if rank is not None:
            return " ".join(parts[1:]).strip(), rank

    return None


def parse_rank(value: str) -> int | None:
    try:
        rank = int(float(value.strip()))
    except ValueError:
        return None
    if rank <= 0:
        return None
    return rank


def parse_path(value: str) -> Path:
    text = value.strip()
    if not text:
        return Path("__missing_path__")

    try:
        parts = shlex.split(text)
    except ValueError:
        parts = []

    if len(parts) == 1:
        text = parts[0]
    else:
        text = text.strip("'\"")

    return Path(text).expanduser()


def write_simple_board(path: Path, rows: list[tuple[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["player", "rank"])
        writer.writeheader()
        for player, rank in rows:
            writer.writerow({"player": player, "rank": rank})


def ask_optional_path(prompt: str) -> Path | None:
    value = input(f"{prompt} (blank for none): ")
    if not value.strip():
        return None
    return parse_path(value)


def prompt_default(prompt: str, default: str) -> str:
    value = input(f"{prompt} [{default}]: ").strip()
    return value or default


def show_expected_files() -> None:
    print("\nThe menu asks for exactly these four inputs:")
    for index, (_, label, filename) in enumerate(BOARD_PROMPTS, start=1):
        print(f"{index}. {label} -> {filename}")


def show_top_rows(path: Path, limit: int = 15) -> None:
    if not path.exists():
        return

    print("\nTop Model 4 rows")
    print("----------------")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            if index > limit:
                break
            print(
                f"{row['eye_rank']}. {row['player']} | "
                f"Eye {row['eye_score']} | Accel {row.get('accel_score', '')} | {row['review_priority']}"
            )


def save_daily_read_copy(output_folder: Path) -> None:
    run_date = datetime.now().strftime("%Y-%m-%d")
    daily_folder = Path("MODEL4_DAILY_READS") / run_date
    daily_folder.mkdir(parents=True, exist_ok=True)

    reasoning = output_folder / "all_seeing_eye_reasoning.md"
    board = output_folder / "all_seeing_eye_board.csv"

    if reasoning.exists():
        target = daily_folder / f"MODEL4_{run_date}_BIG_LIST.md"
        shutil.copyfile(reasoning, target)
        print(f"Saved readable daily list to {target}")

    if board.exists():
        target = daily_folder / f"MODEL4_{run_date}_BOARD.csv"
        shutil.copyfile(board, target)


def build_daily_profit_lenses(output_folder: Path, input_folder: Path) -> Path | None:
    board = output_folder / "all_seeing_eye_board.csv"
    if not board.exists():
        return None

    lens_folder = output_folder / "profit_lenses"
    paths = build_profit_lenses_from_run(board, input_folder, lens_folder)
    print(f"Saved profit lens CSVs to {lens_folder}")
    for path in paths.values():
        print(f"  {path}")
    return lens_folder


def save_profit_lens_daily_copy(lens_folder: Path) -> None:
    run_date = datetime.now().strftime("%Y-%m-%d")
    daily_folder = Path("MODEL4_DAILY_READS") / run_date / "PROFIT_LENSES"
    daily_folder.mkdir(parents=True, exist_ok=True)

    for source in lens_folder.glob("*.csv"):
        target = daily_folder / source.name
        shutil.copyfile(source, target)
    print(f"Saved daily profit lenses to {daily_folder}")


def build_daily_profit_parlays(output_folder: Path, input_folder: Path) -> Path | None:
    board = output_folder / "all_seeing_eye_board.csv"
    if not board.exists():
        return None

    parlay_folder = output_folder / "profit_parlays"
    paths = build_profit_parlays_from_run(board, input_folder, parlay_folder)
    print(f"Saved profit parlay CSVs to {parlay_folder}")
    for path in paths.values():
        print(f"  {path}")
    return parlay_folder


def build_daily_regression_misprice(output_folder: Path, input_folder: Path) -> Path | None:
    board = output_folder / "all_seeing_eye_board.csv"
    if not board.exists():
        return None

    regression_folder = output_folder / "regression_misprice"
    paths = build_regression_misprice_from_run(board, input_folder, regression_folder)
    print(f"Saved regression misprice CSVs to {regression_folder}")
    for path in paths.values():
        print(f"  {path}")
    return regression_folder


def save_regression_misprice_daily_copy(regression_folder: Path) -> None:
    run_date = datetime.now().strftime("%Y-%m-%d")
    daily_folder = Path("MODEL4_DAILY_READS") / run_date / "REGRESSION_MISPRICE"
    daily_folder.mkdir(parents=True, exist_ok=True)

    for source in regression_folder.glob("*.csv"):
        target = daily_folder / source.name
        shutil.copyfile(source, target)
    print(f"Saved daily regression misprice files to {daily_folder}")


def build_daily_prospective_parlays(output_folder: Path, input_folder: Path) -> Path | None:
    board = output_folder / "all_seeing_eye_board.csv"
    if not board.exists():
        return None

    prospective_folder = output_folder / "prospective_parlays"
    paths = build_prospective_parlays_from_run(board, input_folder, prospective_folder)
    print(f"Saved prospective parlay CSVs to {prospective_folder}")
    for path in paths.values():
        print(f"  {path}")
    return prospective_folder


def save_prospective_parlay_daily_copy(prospective_folder: Path) -> None:
    run_date = datetime.now().strftime("%Y-%m-%d")
    daily_folder = Path("MODEL4_DAILY_READS") / run_date / "PROSPECTIVE_PARLAYS"
    daily_folder.mkdir(parents=True, exist_ok=True)

    for source in prospective_folder.glob("*.csv"):
        target = daily_folder / source.name
        shutil.copyfile(source, target)
    print(f"Saved daily prospective parlays to {daily_folder}")


def save_profit_parlay_daily_copy(parlay_folder: Path) -> None:
    run_date = datetime.now().strftime("%Y-%m-%d")
    daily_folder = Path("MODEL4_DAILY_READS") / run_date / "PROFIT_PARLAYS"
    daily_folder.mkdir(parents=True, exist_ok=True)

    for source in parlay_folder.glob("*.csv"):
        target = daily_folder / source.name
        shutil.copyfile(source, target)
    print(f"Saved daily profit parlays to {daily_folder}")


def save_closer_daily_copy(output_folder: Path) -> None:
    run_date = datetime.now().strftime("%Y-%m-%d")
    daily_folder = Path("MODEL4_DAILY_READS") / run_date
    daily_folder.mkdir(parents=True, exist_ok=True)

    recommendations = output_folder / "closer_recommendations.md"
    board = output_folder / "closer_board.csv"

    if recommendations.exists():
        target = daily_folder / f"CLOSER_{run_date}_BET_LENS.md"
        shutil.copyfile(recommendations, target)
        print(f"Saved Closer read to {target}")

    if board.exists():
        target = daily_folder / f"CLOSER_{run_date}_BOARD.csv"
        shutil.copyfile(board, target)


def latest_eye_output_folder() -> Path | None:
    candidates = [
        path.parent
        for path in Path("outputs").glob("**/all_seeing_eye_board.csv")
        if path.is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path / "all_seeing_eye_board.csv").stat().st_mtime)


def infer_input_folder(output_folder: Path) -> Path | None:
    name = output_folder.name
    candidate = Path("inputs") / name
    if (candidate / "gbm_top80.csv").exists():
        return candidate
    return None


def show_regression_misprice_rows(path: Path, limit: int = 10) -> None:
    if not path.exists():
        return
    rows = read_csv_rows(path)[:limit]
    if not rows:
        print("\nRegression Misprice: no active watch-zone players today.")
        return
    print("\nRegression Misprice watch-zone players")
    print("--------------------------------------")
    for row in rows:
        print(
            f"{row.get('zone', '')}: {row.get('player', '')} | "
            f"Reg {row.get('reg_score', '')} | Odds {row.get('book_american_odds', '')} | "
            f"Edge {row.get('edge_percent', '')}%"
        )

def show_profit_lens_rows(path: Path, limit: int = 10) -> None:
    if not path.exists():
        return

    print("\nProfit lens candidates")
    print("----------------------")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        shown = 0
        for row in reader:
            shown += 1
            if shown > limit:
                break
            print(
                f"{shown}. {row.get('player', '')} | {row.get('lens', '')} | "
                f"odds {row.get('book_american_odds', '')} | "
                f"Eye {row.get('eye_rank', '')} | "
                f"GBM {row.get('gbm_rank', '')} | Pitch {row.get('pitcher_batter_rank', '')}"
            )
        if shown == 0:
            print("No candidates hit the profit lens filters today.")


def show_profit_parlay_rows(path: Path, limit: int = 10, title: str = "Profit parlay candidates") -> None:
    if not path.exists():
        return

    print(f"\n{title}")
    print("-" * len(title))
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        shown = 0
        for row in reader:
            shown += 1
            if shown > limit:
                break
            legs = []
            for leg_index in range(1, 5):
                player = row.get(f"leg{leg_index}_player", "")
                if player:
                    odds = row.get(f"leg{leg_index}_book_american_odds", "")
                    legs.append(f"{player} ({odds})")
            print(f"{shown}. {row.get('parlay', '')}: " + " + ".join(legs))
        if shown == 0:
            print("No parlay rules are active today.")


def show_prospective_parlay_rows(path: Path, limit: int = 10) -> None:
    title = "Prospective V1 parlay candidates"
    if not path.exists():
        return

    print(f"\n{title}")
    print("-" * len(title))
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        shown = 0
        for row in reader:
            shown += 1
            if shown > limit:
                break
            legs = []
            for leg_index in range(1, 3):
                player = row.get(f"leg{leg_index}_player", "")
                if player:
                    odds = row.get(f"leg{leg_index}_book_american_odds", "")
                    legs.append(f"{player} ({odds})")
            expected = row.get("expected_wins", "")
            odds = row.get("parlay_decimal_odds", "")
            print(f"{shown}. {row.get('criteria_id', '')}: " + " + ".join(legs) + f" | odds {odds} | expected {expected}")
        if shown == 0:
            print("No Prospective V1 tickets qualified today.")


def show_closer_rows(candidates: list[object], limit: int = 10) -> None:
    print("\nTop Closer candidates")
    print("---------------------")
    for index, candidate in enumerate(candidates[:limit], start=1):
        print(
            f"{index}. {candidate.player} | "
            f"{candidate.conviction_score} | {candidate.decision}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
