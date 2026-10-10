from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .io import (
    load_history_folders,
    load_signal_folder,
    merge_player_signals,
    player_key,
    write_board_csv,
    write_reasoning_markdown,
)
from .scoring import score_players


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create an All-Seeing Eye review-priority board from downstream model outputs."
    )
    parser.add_argument("--today", required=True, type=Path, help="Folder containing today's four CSV boards.")
    parser.add_argument(
        "--yesterday",
        type=Path,
        help="Optional folder containing the previous run's four CSV boards for movement detection.",
    )
    parser.add_argument(
        "--history",
        type=Path,
        help="Optional folder of dated board folders for persistence and stale-signal detection.",
    )
    parser.add_argument("--out", default=Path("outputs"), type=Path, help="Output folder.")
    parser.add_argument("--limit", default=120, type=int, help="Maximum number of players to output.")
    args = parser.parse_args(argv)

    today_boards = load_signal_folder(args.today, required=True)
    previous_boards = load_signal_folder(args.yesterday, required=False) if args.yesterday else {}
    history_boards = load_history_folders(args.history) if args.history else []
    players = merge_player_signals(today_boards, previous_boards, history_boards)
    scored = score_players(players)[: args.limit]

    rows = [_row(index, player, players) for index, player in enumerate(scored, start=1)]
    write_board_csv(args.out / "all_seeing_eye_board.csv", rows)
    write_reasoning_markdown(args.out / "all_seeing_eye_reasoning.md", rows)

    print(f"Wrote {len(rows)} players to {args.out / 'all_seeing_eye_board.csv'}")
    print(f"Wrote reasoning to {args.out / 'all_seeing_eye_reasoning.md'}")
    return 0


def _row(index: int, scored: Any, players: dict[str, Any] | None = None) -> dict[str, Any]:
    signal = players.get(player_key(scored.player)) if players else None
    row = {
        "eye_rank": index,
        "player": scored.player,
        "eye_score": scored.eye_score,
        "accel_score": scored.accel_score,
        "stale_signal_status": scored.stale_signal_status,
        "review_priority": scored.review_priority,
        "layers_present": scored.layers_present,
        "gbm_rank": scored.ranks["gbm_top80"] or "",
        "gbm_progression_rank": scored.ranks["gbm_progression_top80"] or "",
        "sequence_rank": scored.ranks["sequence_top150"] or "",
        "pitcher_batter_rank": scored.ranks["pitcher_batter_top80"] or "",
        "movement_summary": scored.movement_summary,
        "reasoning": " | ".join(scored.reasoning),
    }
    row.update(_market_row(signal))
    return row


def _market_row(signal: Any | None) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if signal:
        for board_id in ("gbm_top80", "gbm_progression_top80", "pitcher_batter_top80"):
            entry = signal.entries.get(board_id)
            if not entry:
                continue
            for key, value in entry.fields.items():
                if value not in (None, "") and key not in fields:
                    fields[key] = value

    return {
        "game_date": fields.get("game_date", ""),
        "player_id": fields.get("player_id", ""),
        "team_abbrev": fields.get("team_abbrev") or fields.get("player_team") or "",
        "opponent_abbrev": fields.get("opponent_abbrev") or fields.get("opponent") or "",
        "lineup_status": fields.get("lineup_status", ""),
        "batting_order": fields.get("batting_order", ""),
        "model_hr_probability_percent": fields.get("adjusted_hr_probability_percent", ""),
        "model_american_odds": fields.get("american_betting_odds", ""),
        "bookmaker_used": fields.get("bookmaker_used", ""),
        "book_american_odds": fields.get("book_american_odds", ""),
        "dk_odds": fields.get("dk_odds", ""),
        "fan_odds": fields.get("fan_odds", ""),
        "365_odds": fields.get("365_odds", ""),
        "edge_percent": fields.get("edge_percent", ""),
        "odds_source": fields.get("odds_source", ""),
        "odds_last_update": fields.get("odds_last_update", ""),
    }
