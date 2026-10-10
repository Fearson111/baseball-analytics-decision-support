from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from .boards import BOARD_SPECS, BoardEntry
from .io import load_signal_folder, player_key
from .scoring import normalize_numeric_score, rank_to_score


@dataclass(frozen=True)
class CloserCandidate:
    player: str
    conviction_score: float
    decision: str
    eye_rank: int
    eye_score: float
    ranks: dict[str, int | None]
    reasons: list[str]
    checks: list[str]


def run_closer(
    eye_output_folder: Path,
    input_folder: Path,
    output_folder: Path,
    *,
    pool_limit: int = 40,
    output_limit: int = 20,
) -> list[CloserCandidate]:
    eye_rows = read_eye_board(eye_output_folder / "all_seeing_eye_board.csv")
    player_entries = load_player_entries(input_folder)
    candidates = score_closer_candidates(eye_rows[:pool_limit], player_entries)[:output_limit]
    write_closer_outputs(output_folder, candidates)
    return candidates


def score_closer_candidates(
    eye_rows: list[dict[str, str]],
    player_entries: dict[str, dict[str, BoardEntry]],
) -> list[CloserCandidate]:
    candidates: list[CloserCandidate] = []
    for row in eye_rows:
        player = row["player"]
        entries = player_entries.get(player_key(player), {})
        candidates.append(score_closer_candidate(row, entries))
    return sorted(candidates, key=lambda item: (-item.conviction_score, item.eye_rank, item.player))


def score_closer_candidate(row: dict[str, str], entries: dict[str, BoardEntry]) -> CloserCandidate:
    player = row["player"]
    eye_score = parse_float(row.get("eye_score")) or 0.0
    eye_rank = int(parse_float(row.get("eye_rank")) or 999)
    reasons: list[str] = []
    checks: list[str] = []

    gbm_strength = board_strength(entries.get("gbm_top80"), "gbm_top80")
    progression_strength = board_strength(entries.get("gbm_progression_top80"), "gbm_progression_top80")
    sequence_strength = board_strength(entries.get("sequence_top150"), "sequence_top150")
    pitch_strength = board_strength(entries.get("pitcher_batter_top80"), "pitcher_batter_top80")

    score = eye_score * 0.16
    score += gbm_strength * 0.28
    score += progression_strength * 0.09
    score += sequence_strength * 0.14
    score += pitch_strength * 0.21

    if gbm_strength >= 75:
        reasons.append("Strong GBM base power signal")
    elif gbm_strength <= 0:
        score -= 5.0
        reasons.append("No GBM base-board support; requires extra caution")

    if pitch_strength >= 70:
        reasons.append("Strong pitcher/batter or pitch-shape support")
    if sequence_strength >= 70:
        reasons.append("Strong sequence support")
    if progression_strength >= 70:
        reasons.append("Positive-regression board support")

    lineup_adjustment, lineup_reasons, lineup_checks = lineup_adjustment_for(entries)
    score += lineup_adjustment
    reasons.extend(lineup_reasons)
    checks.extend(lineup_checks)

    value_adjustment, value_reasons, value_checks = value_adjustment_for(entries)
    score += value_adjustment
    reasons.extend(value_reasons)
    checks.extend(value_checks)

    movement_text = (row.get("movement_summary") or "").lower()
    reasoning_text = (row.get("reasoning") or "").lower()
    if "cross-system acceleration" in movement_text:
        score += 4.0
        reasons.append("Cross-system movement adds bet interest")
    elif "accelerated from" in movement_text:
        score += 2.0
        reasons.append("Recent rank acceleration adds bet interest")
    if "surprise case" in reasoning_text:
        score += 2.0
        reasons.append("Disagreement/surprise signal deserves price check")

    if not checks:
        checks.append("Confirm lineup, batting order, park, and final price")

    conviction_score = round(max(0.0, min(99.0, score)), 2)
    return CloserCandidate(
        player=player,
        conviction_score=conviction_score,
        decision=decision_for(conviction_score),
        eye_rank=eye_rank,
        eye_score=eye_score,
        ranks={
            "gbm_top80": entry_rank(entries, "gbm_top80"),
            "gbm_progression_top80": entry_rank(entries, "gbm_progression_top80"),
            "sequence_top150": entry_rank(entries, "sequence_top150"),
            "pitcher_batter_top80": entry_rank(entries, "pitcher_batter_top80"),
        },
        reasons=reasons[:6],
        checks=dedupe(checks),
    )


def board_strength(entry: BoardEntry | None, board_id: str) -> float:
    if not entry:
        return 0.0
    spec = BOARD_SPECS[board_id]
    rank_strength = rank_to_score(entry.rank, spec["max_rank"])
    optional_strength = first_optional_score(entry, spec["optional_scores"])
    if optional_strength is None:
        return rank_strength
    return (rank_strength * 0.7) + (optional_strength * 0.3)


def first_optional_score(entry: BoardEntry, aliases: tuple[str, ...]) -> float | None:
    for alias in aliases:
        if alias not in entry.fields:
            continue
        parsed = parse_float(entry.fields[alias])
        if parsed is not None:
            return normalize_numeric_score(parsed)
    return None


def lineup_adjustment_for(entries: dict[str, BoardEntry]) -> tuple[float, list[str], list[str]]:
    fields = merged_fields(entries)
    adjustment = 0.0
    reasons: list[str] = []
    checks: list[str] = []

    batting_order = parse_float(fields.get("batting_order"))
    if batting_order is not None:
        if batting_order <= 4:
            adjustment += 4.0
            reasons.append("Premium lineup slot")
        elif batting_order <= 6:
            adjustment += 2.0
            reasons.append("Playable lineup slot")
        elif batting_order >= 8:
            adjustment -= 3.0
            checks.append("Batting order is low; confirm plate appearance expectation")

    lineup_status = str(fields.get("lineup_status") or "").lower()
    if "confirmed" in lineup_status and "not_confirmed" not in lineup_status:
        adjustment += 3.0
        reasons.append("Lineup is confirmed")
    elif lineup_status:
        adjustment -= 2.0
        checks.append("Lineup is not confirmed yet")
    else:
        checks.append("Confirm lineup status")

    projected_pa = parse_float(fields.get("projected_pa"))
    if projected_pa is not None and projected_pa >= 4.4:
        adjustment += 2.0
        reasons.append("Strong projected plate appearances")
    elif projected_pa is not None and projected_pa < 4.0:
        adjustment -= 2.0
        checks.append("Projected plate appearances are light")

    return adjustment, reasons, checks


def value_adjustment_for(entries: dict[str, BoardEntry]) -> tuple[float, list[str], list[str]]:
    fields = merged_fields(entries)
    adjustment = 0.0
    reasons: list[str] = []
    checks: list[str] = []

    edge = parse_float(fields.get("edge_percent"))
    if edge is not None:
        if edge >= 5:
            adjustment += 7.0
            reasons.append("Positive price edge is available")
        elif edge > 0:
            adjustment += 3.0
            reasons.append("Slight positive price edge")
        elif edge <= -5:
            adjustment -= 5.0
            checks.append("Price edge is negative")

    odds = parse_float(fields.get("american_betting_odds")) or parse_float(fields.get("book_american_odds"))
    if odds is not None:
        if 250 <= odds <= 900:
            adjustment += 2.0
            reasons.append("Price range is playable")
        elif odds < 200:
            adjustment -= 4.0
            checks.append("Price may be too short for HR market")
    else:
        checks.append("Check final HR price")

    return adjustment, reasons, checks


def decision_for(score: float) -> str:
    if score >= 78:
        return "BET_CANDIDATE"
    if score >= 68:
        return "LEAN"
    if score >= 58:
        return "PRICE_DEPENDENT"
    return "WATCH_ONLY"


def read_eye_board(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing Model 4 board: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_player_entries(input_folder: Path) -> dict[str, dict[str, BoardEntry]]:
    boards = load_signal_folder(input_folder, required=True)
    players: dict[str, dict[str, BoardEntry]] = {}
    for board_id, entries in boards.items():
        for entry in entries:
            players.setdefault(player_key(entry.player), {})[board_id] = entry
    return players


def write_closer_outputs(output_folder: Path, candidates: list[CloserCandidate]) -> None:
    output_folder.mkdir(parents=True, exist_ok=True)
    write_closer_csv(output_folder / "closer_board.csv", candidates)
    write_closer_markdown(output_folder / "closer_recommendations.md", candidates)


def write_closer_csv(path: Path, candidates: list[CloserCandidate]) -> None:
    fieldnames = [
        "closer_rank",
        "player",
        "conviction_score",
        "decision",
        "eye_rank",
        "eye_score",
        "gbm_rank",
        "gbm_progression_rank",
        "sequence_rank",
        "pitcher_batter_rank",
        "why",
        "checks",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, candidate in enumerate(candidates, start=1):
            writer.writerow(
                {
                    "closer_rank": index,
                    "player": candidate.player,
                    "conviction_score": candidate.conviction_score,
                    "decision": candidate.decision,
                    "eye_rank": candidate.eye_rank,
                    "eye_score": candidate.eye_score,
                    "gbm_rank": candidate.ranks["gbm_top80"] or "",
                    "gbm_progression_rank": candidate.ranks["gbm_progression_top80"] or "",
                    "sequence_rank": candidate.ranks["sequence_top150"] or "",
                    "pitcher_batter_rank": candidate.ranks["pitcher_batter_top80"] or "",
                    "why": " | ".join(candidate.reasons),
                    "checks": " | ".join(candidate.checks),
                }
            )


def write_closer_markdown(path: Path, candidates: list[CloserCandidate]) -> None:
    lines = ["# The Closer", ""]
    lines.append("Final bet-candidate lens from the Model 4 review pool.")
    lines.append("")
    lines.append("| Rank | Player | Conviction | Decision | Eye Rank | Eye Score |")
    lines.append("| ---: | --- | ---: | --- | ---: | ---: |")
    for index, candidate in enumerate(candidates, start=1):
        lines.append(
            f"| {index} | {candidate.player} | {candidate.conviction_score} | "
            f"{candidate.decision} | {candidate.eye_rank} | {candidate.eye_score} |"
        )
    lines.append("")

    if candidates:
        best = candidates[0]
        lines.append("## Best HR Bet Candidate")
        lines.append("")
        lines.append(f"{best.player} - {best.conviction_score} ({best.decision})")
        lines.append("")

    for index, candidate in enumerate(candidates, start=1):
        lines.append(f"## {index}. {candidate.player}")
        lines.append("")
        lines.append(f"Conviction Score: {candidate.conviction_score}")
        lines.append(f"Decision: {candidate.decision}")
        lines.append(f"Eye Rank: {candidate.eye_rank}")
        lines.append("")
        lines.append("Why:")
        for reason in candidate.reasons or ["No dominant bet signal; keep as review-only."]:
            lines.append(f"- {reason}")
        lines.append("")
        lines.append("Review Before Bet:")
        for check in candidate.checks:
            lines.append(f"- {check}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def merged_fields(entries: dict[str, BoardEntry]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for board_id in ("gbm_top80", "gbm_progression_top80", "sequence_top150", "pitcher_batter_top80"):
        entry = entries.get(board_id)
        if entry:
            fields.update({key: value for key, value in entry.fields.items() if value not in ("", None)})
    return fields


def entry_rank(entries: dict[str, BoardEntry], board_id: str) -> int | None:
    entry = entries.get(board_id)
    return entry.rank if entry else None


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
