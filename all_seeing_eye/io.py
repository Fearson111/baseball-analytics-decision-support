from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .boards import BOARD_SPECS, BoardEntry, PlayerSignal


PLAYER_ALIASES = ("player", "batter", "name", "player_name", "hitter")
RANK_ALIASES = (
    "rank",
    "gbm_rank",
    "sequence_rank",
    "pitch_rank",
    "board_rank",
    "projection_rank",
    "regression_rank",
)


def load_signal_folder(folder: Path, *, required: bool) -> dict[str, list[BoardEntry]]:
    boards: dict[str, list[BoardEntry]] = {}
    for board_id, spec in BOARD_SPECS.items():
        path = folder / spec["filename"]
        if not path.exists():
            if required:
                raise FileNotFoundError(f"Missing required input file: {path}")
            continue
        boards[board_id] = read_board_csv(path, board_id)
    return boards


def load_history_folders(folder: Path) -> list[dict[str, list[BoardEntry]]]:
    if not folder.exists():
        raise FileNotFoundError(f"Missing history folder: {folder}")

    history: list[dict[str, list[BoardEntry]]] = []
    for child in sorted(folder.iterdir()):
        if not child.is_dir():
            continue
        boards = load_signal_folder(child, required=False)
        if boards:
            history.append(boards)
    return history


def read_board_csv(path: Path, board_id: str) -> list[BoardEntry]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []

        normalized = {_normalize_header(name): name for name in reader.fieldnames}
        player_key = _first_present(normalized, PLAYER_ALIASES)
        rank_key = _first_present(normalized, RANK_ALIASES)

        if not player_key or not rank_key:
            raise ValueError(f"{path} must contain player and rank columns")

        entries: list[BoardEntry] = []
        for row_number, row in enumerate(reader, start=2):
            player = (row.get(player_key) or "").strip()
            if not player:
                continue
            rank = _parse_int(row.get(rank_key))
            if rank is None:
                raise ValueError(f"{path}:{row_number} has an invalid rank for {player!r}")
            fields = {_normalize_header(key): value for key, value in row.items() if key}
            entries.append(BoardEntry(board_id=board_id, player=player, rank=rank, fields=fields))
        return entries


def merge_player_signals(
    today_boards: dict[str, list[BoardEntry]],
    previous_boards: dict[str, list[BoardEntry]] | None = None,
    history_boards: list[dict[str, list[BoardEntry]]] | None = None,
) -> dict[str, PlayerSignal]:
    players: dict[str, PlayerSignal] = {}
    previous_boards = previous_boards or {}
    history_boards = history_boards or []
    if not previous_boards and history_boards:
        previous_boards = history_boards[-1]
    has_previous_context = bool(previous_boards)
    has_history_context = bool(history_boards)

    for board_id, entries in today_boards.items():
        for entry in entries:
            key = player_key(entry.player)
            signal = players.setdefault(key, PlayerSignal(player=entry.player))
            signal.has_previous_context = has_previous_context
            signal.has_history_context = has_history_context
            signal.entries[board_id] = entry

    for board_id, entries in previous_boards.items():
        for entry in entries:
            key = player_key(entry.player)
            signal = players.setdefault(key, PlayerSignal(player=entry.player))
            signal.has_previous_context = has_previous_context
            signal.has_history_context = has_history_context
            signal.previous_entries[board_id] = entry

    for day_boards in history_boards:
        for board_id, entries in day_boards.items():
            for entry in entries:
                key = player_key(entry.player)
                signal = players.setdefault(key, PlayerSignal(player=entry.player))
                signal.has_previous_context = has_previous_context
                signal.has_history_context = has_history_context
                signal.historical_entries.setdefault(board_id, []).append(entry)

    return players


def write_board_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "eye_rank",
        "player",
        "eye_score",
        "accel_score",
        "stale_signal_status",
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
        "review_priority",
        "layers_present",
        "gbm_rank",
        "gbm_progression_rank",
        "sequence_rank",
        "pitcher_batter_rank",
        "movement_summary",
        "reasoning",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_reasoning_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# All-Seeing Eye Board", ""]
    lines.append("| Rank | Player | Eye Score | Accel Score | Stale Signal | Priority | Layers |")
    lines.append("| ---: | --- | ---: | ---: | --- | --- | --- |")
    for row in rows:
        lines.append(
            f"| {row['eye_rank']} | {row['player']} | {row['eye_score']} | "
            f"{row['accel_score']} | "
            f"{row.get('stale_signal_status', 'fresh')} | "
            f"{row['review_priority']} | {row['layers_present']} |"
        )
    lines.append("")

    for row in rows:
        lines.append(f"## {row['eye_rank']}. {row['player']}")
        lines.append("")
        lines.append(f"Eye Score: {row['eye_score']}")
        lines.append(f"Acceleration Score: {row['accel_score']}")
        lines.append(f"Stale Signal: {row.get('stale_signal_status', 'fresh')}")
        lines.append(f"Review Priority: {row['review_priority']}")
        lines.append("")
        lines.append("Reasoning:")
        for reason in row["reasoning"].split(" | "):
            lines.append(f"- {reason}")
        if row["movement_summary"]:
            lines.append(f"- Movement: {row['movement_summary']}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def player_key(player: str) -> str:
    return " ".join(player.lower().replace(".", "").split())


def _normalize_header(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", " ").split())


def _first_present(normalized: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None
