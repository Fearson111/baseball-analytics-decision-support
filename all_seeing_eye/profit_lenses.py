from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .io import player_key
from .tracker import market_aliases, normalize_header, parse_float


@dataclass(frozen=True)
class LensSpec:
    lens_id: str
    title: str
    filename: str
    description: str
    backtest_note: str
    predicate: Callable[[dict[str, Any]], bool]
    sort_key: Callable[[dict[str, Any]], tuple[Any, ...]]
    limit: int | None = None


LENS_COLUMNS = [
    "lens",
    "lens_note",
    "bet",
    "stake_units",
    "notes",
    "eye_rank",
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
    "model_hr_probability_percent",
    "edge_percent",
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


def build_profit_lenses(board_path: Path, output_folder: Path) -> dict[str, Path]:
    rows = read_csv_rows(board_path)
    return write_profit_lenses(rows, output_folder)


def build_profit_lenses_from_run(board_path: Path, input_folder: Path, output_folder: Path) -> dict[str, Path]:
    rows = enrich_rows_from_input_folder(read_csv_rows(board_path), input_folder)
    return write_profit_lenses(rows, output_folder)


def write_profit_lenses(rows: list[dict[str, Any]], output_folder: Path) -> dict[str, Path]:
    output_folder.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    for spec in lens_specs():
        candidates = [row for row in rows if spec.predicate(row)]
        candidates = sorted(candidates, key=spec.sort_key)
        if spec.limit is not None:
            candidates = candidates[: spec.limit]
        lens_rows = [lens_row(spec, row) for row in candidates]
        path = output_folder / spec.filename
        write_csv(path, LENS_COLUMNS, lens_rows)
        written[spec.lens_id] = path

    combined_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for spec in lens_specs():
        for row in read_csv_rows(output_folder / spec.filename):
            key = (str(row.get("player", "")), str(row.get("book_american_odds", "")))
            if key in seen:
                continue
            seen.add(key)
            combined_rows.append(row)
    combined_path = output_folder / "profit_lenses_combined.csv"
    write_csv(combined_path, LENS_COLUMNS, combined_rows)
    written["combined"] = combined_path
    return written


def enrich_rows_from_input_folder(rows: list[dict[str, Any]], input_folder: Path) -> list[dict[str, Any]]:
    market = load_market_from_input_folder(input_folder)
    if not market:
        return rows

    enriched: list[dict[str, Any]] = []
    for row in rows:
        merged = dict(row)
        player = str(row.get("player") or "").strip()
        for column, value in market.get(player_key(player), {}).items():
            if value not in (None, "") and not merged.get(column):
                merged[column] = value
        enriched.append(merged)
    return enriched


def load_market_from_input_folder(input_folder: Path) -> dict[str, dict[str, Any]]:
    market: dict[str, dict[str, Any]] = {}
    for filename in ("gbm_top80.csv", "gbm_progression_top80.csv", "pitcher_batter_top80.csv"):
        path = input_folder / filename
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


def lens_specs() -> list[LensSpec]:
    return [
        LensSpec(
            lens_id="daily_capped_eye_top1",
            title="Daily Capped Eye Top 1",
            filename="profit_lens_daily_capped_eye_top1.csv",
            description="Broad pitch-fit longshot filter, then take the best Eye rank.",
            backtest_note="51 bets, 11 HR, +21.15u, +41.47% ROI.",
            predicate=is_h4_broad,
            sort_key=lambda row: (num(row, "eye_rank", 999), num(row, "pitcher_batter_rank", 999)),
            limit=1,
        ),
        LensSpec(
            lens_id="daily_capped_edge_top2",
            title="Daily Capped Edge Top 2",
            filename="profit_lens_daily_capped_edge_top2.csv",
            description="Broad pitch-fit longshot filter, then take the two best edge readings.",
            backtest_note="95 bets, 19 HR, +38.67u, +40.71% ROI.",
            predicate=is_h4_broad,
            sort_key=lambda row: (-num(row, "edge_percent", -999), num(row, "pitcher_batter_rank", 999)),
            limit=2,
        ),
        LensSpec(
            lens_id="daily_capped_modelhr_top2",
            title="Daily Capped Model HR Top 2",
            filename="profit_lens_daily_capped_modelhr_top2.csv",
            description="Broad pitch-fit longshot filter, then take the two best model HR percentages.",
            backtest_note="95 bets, 20 HR, +38.27u, +40.28% ROI.",
            predicate=is_h4_broad,
            sort_key=lambda row: (
                -num(row, "model_hr_probability_percent", -999),
                num(row, "pitcher_batter_rank", 999),
            ),
            limit=2,
        ),
        LensSpec(
            lens_id="sharper_pitchfit",
            title="Sharper Pitch-Fit Longshot",
            filename="profit_lens_sharper_pitchfit.csv",
            description="Sharper filter: odds +500 to +800, GBM rank 20 to 100, Pitcher/Batter rank <= 10.",
            backtest_note="46 bets, 11 HR, +25.52u, +55.48% ROI.",
            predicate=is_sharper_pitchfit,
            sort_key=lambda row: (num(row, "eye_rank", 999), num(row, "pitcher_batter_rank", 999)),
            limit=None,
        ),
        LensSpec(
            lens_id="sharper_pitchfit_eye_top1",
            title="Sharper Pitch-Fit Eye Top 1",
            filename="profit_lens_sharper_pitchfit_eye_top1.csv",
            description="Sharper pitch-fit filter, then take the best Eye rank.",
            backtest_note="34 bets, 9 HR, +25.15u, +73.97% ROI.",
            predicate=is_sharper_pitchfit,
            sort_key=lambda row: (num(row, "eye_rank", 999), num(row, "pitcher_batter_rank", 999)),
            limit=1,
        ),
    ]


def is_h4_broad(row: dict[str, Any]) -> bool:
    return (
        between(num(row, "book_american_odds"), 500, 900)
        and between(num(row, "gbm_rank"), 40, 130)
        and num(row, "pitcher_batter_rank", 999) <= 30
    )


def is_sharper_pitchfit(row: dict[str, Any]) -> bool:
    return (
        between(num(row, "book_american_odds"), 500, 800)
        and between(num(row, "gbm_rank"), 20, 100)
        and num(row, "pitcher_batter_rank", 999) <= 10
    )


def lens_row(spec: LensSpec, row: dict[str, Any]) -> dict[str, Any]:
    output = {column: row.get(column, "") for column in LENS_COLUMNS}
    output["lens"] = spec.title
    output["lens_note"] = spec.backtest_note
    output.setdefault("bet", "")
    output.setdefault("stake_units", "1")
    output.setdefault("notes", "")
    output["stake_units"] = output.get("stake_units") or "1"
    return output


def num(row: dict[str, Any], column: str, default: float = 0) -> float:
    parsed = parse_float(row.get(column))
    if parsed is None or parsed != parsed:
        return default
    return parsed


def between(value: float, low: float, high: float) -> bool:
    return low <= value <= high


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
