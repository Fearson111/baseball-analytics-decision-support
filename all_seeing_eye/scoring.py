from __future__ import annotations

from dataclasses import dataclass
from math import exp
from statistics import mean
from typing import Any

from .boards import BOARD_SPECS, PlayerSignal


@dataclass(frozen=True)
class ScoredPlayer:
    player: str
    eye_score: float
    accel_score: float
    stale_signal_status: str
    review_priority: str
    layers_present: str
    ranks: dict[str, int | None]
    movement_summary: str
    reasoning: list[str]


def score_players(players: dict[str, PlayerSignal]) -> list[ScoredPlayer]:
    scored = [score_player(signal) for signal in players.values() if signal.entries]
    return sorted(scored, key=lambda item: (-item.eye_score, item.player))


def score_player(signal: PlayerSignal) -> ScoredPlayer:
    rank_component = 0.0
    layer_scores: dict[str, list[float]] = {"gbm": [], "sequence": [], "pitch": []}
    reasoning: list[str] = []

    for board_id, spec in BOARD_SPECS.items():
        entry = signal.entries.get(board_id)
        if not entry:
            continue

        rank_strength = rank_to_score(entry.rank, spec["max_rank"])
        optional_strength = optional_score(entry.fields, spec["optional_scores"])
        board_strength = rank_strength
        if optional_strength is not None:
            board_strength = (rank_strength * 0.75) + (optional_strength * 0.25)

        rank_component += board_strength * spec["weight"] * 0.55
        layer_scores[spec["layer"]].append(board_strength)
        reasoning.append(f"Appears on {spec['label']} at rank {entry.rank}")

    present_layers = {layer for layer, values in layer_scores.items() if values}
    layer_count = len(present_layers)
    previous_layers = layers_from_entries(signal.previous_entries)
    convergence_bonus = {1: 0.0, 2: 3.0, 3: 6.0}.get(layer_count, 0.0)

    if layer_count == 3:
        reasoning.append("Appears across GBM, Sequence, and Pitch layers")
    elif layer_count == 2:
        reasoning.append(f"Supported by two independent layers: {', '.join(sorted(present_layers))}")

    layer_averages = {layer: mean(values) for layer, values in layer_scores.items() if values}
    agreement_bonus, disagreement_bonus = agreement_adjustments(layer_averages)
    if agreement_bonus:
        reasoning.append("Layer scores are aligned, but simple agreement is treated as supporting context")
    if disagreement_bonus:
        reasoning.append("Surprise case: layer scores diverge enough to deserve review")

    movement_bonus, movement_reasons = movement_adjustment(signal)
    reasoning.extend(movement_reasons)
    accel_score, _ = acceleration_score(signal)

    emerging_bonus, emerging_reasons = emerging_convergence_adjustment(present_layers, previous_layers, signal)
    reasoning.extend(emerging_reasons)

    persistence_penalty, persistence_reinforcement, stale_status, persistence_reasons = persistence_adjustment(
        signal,
        layer_scores,
    )
    reasoning.extend(persistence_reasons)

    raw_score = (
        rank_component
        + convergence_bonus
        + agreement_bonus
        + disagreement_bonus
        + movement_bonus
        + emerging_bonus
        + persistence_reinforcement
        - persistence_penalty
    )
    eye_score = round(scale_eye_score(raw_score), 2)

    if eye_score >= 72 or movement_bonus >= 18 or emerging_bonus >= 12 or disagreement_bonus >= 12:
        priority = "High"
    elif eye_score >= 46 or movement_bonus >= 8 or emerging_bonus >= 6 or layer_count >= 2:
        priority = "Medium"
    else:
        priority = "Watch"

    ranks = {
        "gbm_top80": _rank(signal, "gbm_top80"),
        "gbm_progression_top80": _rank(signal, "gbm_progression_top80"),
        "sequence_top150": _rank(signal, "sequence_top150"),
        "pitcher_batter_top80": _rank(signal, "pitcher_batter_top80"),
    }

    return ScoredPlayer(
        player=signal.player,
        eye_score=eye_score,
        accel_score=accel_score,
        stale_signal_status=stale_status,
        review_priority=priority,
        layers_present=", ".join(sorted(present_layers)),
        ranks=ranks,
        movement_summary="; ".join(movement_reasons),
        reasoning=reasoning,
    )


def rank_to_score(rank: int, max_rank: int) -> float:
    if rank <= 1:
        return 100.0
    if rank >= max_rank:
        return 1.0
    return 100.0 * (1.0 - ((rank - 1) / max_rank))


def scale_eye_score(raw_score: float) -> float:
    raw_score = max(0.0, raw_score)
    soft_cap_start = 92.0
    if raw_score <= soft_cap_start:
        return raw_score

    cap_span = 7.85
    compression_width = 22.0
    compressed = cap_span * (1.0 - exp(-((raw_score - soft_cap_start) / compression_width)))
    return min(99.85, soft_cap_start + compressed)


def optional_score(fields: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    for alias in aliases:
        if alias not in fields:
            continue
        parsed = _parse_float(fields[alias])
        if parsed is None:
            continue
        return normalize_numeric_score(parsed)
    return None


def normalize_numeric_score(value: float) -> float:
    if 0.0 <= value <= 1.0:
        return value * 100.0
    if 1.0 < value <= 100.0:
        return value
    return max(0.0, min(100.0, value))


def agreement_adjustments(layer_averages: dict[str, float]) -> tuple[float, float]:
    values = list(layer_averages.values())
    if len(values) < 2:
        return 0.0, 0.0

    spread = max(values) - min(values)
    if len(values) == 3 and spread <= 18:
        return 3.0, 0.0
    if spread <= 12:
        return 2.0, 0.0
    if max(values) >= 75 and min(values) <= 45:
        return 0.0, 12.0
    if max(values) >= 65 and min(values) <= 25:
        return 0.0, 9.0
    return 0.0, 0.0


def movement_adjustment(signal: PlayerSignal) -> tuple[float, list[str]]:
    bonus = 0.0
    reasons: list[str] = []
    improved_boards = 0

    for board_id, spec in BOARD_SPECS.items():
        today = signal.entries.get(board_id)
        if not today:
            continue

        previous = signal.previous_entries.get(board_id)
        if not previous:
            if signal.has_previous_context:
                entrant_bonus = 6.0
                if today.rank <= 20:
                    entrant_bonus += 12.0
                elif today.rank <= 30:
                    entrant_bonus += 8.0
                bonus += entrant_bonus
                reasons.append(f"New entrant on {spec['label']} at rank {today.rank}")
            continue

        improvement = previous.rank - today.rank
        if improvement <= 0:
            continue

        improved_boards += 1
        board_bonus = min(24.0, improvement / 2.5)
        if previous.rank > spec["max_rank"] and today.rank <= spec["max_rank"]:
            board_bonus += 6.0
        if previous.rank > 80 and today.rank <= 30:
            board_bonus += 12.0
        elif previous.rank > 50 and today.rank <= 20:
            board_bonus += 10.0

        bonus += board_bonus
        reasons.append(f"{spec['label']} accelerated from rank {previous.rank} to {today.rank}")

    if improved_boards >= 2:
        cross_bonus = 8.0 + (4.0 * (improved_boards - 2))
        bonus += cross_bonus
        reasons.append(f"Cross-system acceleration detected on {improved_boards} boards")

    return min(55.0, bonus), reasons


def acceleration_score(signal: PlayerSignal) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    improved_boards = 0
    fresh_boards = 0
    history_accel_boards = 0

    for board_id, spec in BOARD_SPECS.items():
        today = signal.entries.get(board_id)
        if not today:
            continue

        max_rank = spec["max_rank"]
        previous = signal.previous_entries.get(board_id)
        if previous:
            velocity = previous.rank - today.rank
            if velocity > 0:
                improved_boards += 1
                board_score = min(22.0, (velocity / max_rank) * 38.0)
                board_score += landing_zone_bonus(today.rank)
                if previous.rank > max_rank and today.rank <= max_rank:
                    board_score += 5.0
                if previous.rank > 80 and today.rank <= 30:
                    board_score += 7.0
                elif previous.rank > 50 and today.rank <= 20:
                    board_score += 6.0
                score += min(34.0, board_score)
                reasons.append(f"{spec['label']} positive velocity: {previous.rank} to {today.rank}")
            elif velocity < 0:
                score -= min(8.0, (abs(velocity) / max_rank) * 16.0)
        elif signal.has_previous_context:
            fresh_boards += 1
            entry_force = 4.0 + (rank_to_score(today.rank, max_rank) * 0.10)
            entry_force += landing_zone_bonus(today.rank) * 0.8
            score += min(20.0, entry_force)
            reasons.append(f"{spec['label']} fresh entry force at rank {today.rank}")

        history_score = historical_acceleration_component(signal, board_id, today.rank, max_rank)
        if history_score > 0:
            history_accel_boards += 1
            score += history_score

    if improved_boards >= 2:
        score += 10.0 + (4.0 * (improved_boards - 2))
        reasons.append(f"Multi-board acceleration confirmed on {improved_boards} boards")

    if fresh_boards >= 2:
        score += 5.0 + (2.0 * (fresh_boards - 2))
        reasons.append(f"Fresh multi-board entry pressure on {fresh_boards} boards")

    if improved_boards + fresh_boards >= 3:
        score += 6.0
        reasons.append("Broad acceleration pressure across at least three boards")

    if history_accel_boards >= 2:
        score += 8.0
        reasons.append(f"History-folder acceleration confirmed on {history_accel_boards} boards")

    return round(scale_acceleration_score(score), 2), reasons


def scale_acceleration_score(raw_score: float) -> float:
    raw_score = max(0.0, raw_score)
    soft_cap_start = 88.0
    if raw_score <= soft_cap_start:
        return raw_score

    cap_span = 11.4
    compression_width = 42.0
    compressed = cap_span * (1.0 - exp(-((raw_score - soft_cap_start) / compression_width)))
    return min(99.4, soft_cap_start + compressed)


def historical_acceleration_component(
    signal: PlayerSignal,
    board_id: str,
    today_rank: int,
    max_rank: int,
) -> float:
    if not signal.has_history_context:
        return 0.0

    historical = signal.historical_entries.get(board_id, [])
    if not historical:
        return 0.0

    ranks = [entry.rank for entry in historical[-5:]]
    if not ranks:
        return 0.0

    all_ranks = ranks + [today_rank]
    velocities = [
        previous_rank - current_rank
        for previous_rank, current_rank in zip(all_ranks, all_ranks[1:])
    ]
    recent_velocity = velocities[-1]
    if recent_velocity <= 0:
        return 0.0

    older_velocity = mean(velocities[:-1]) if len(velocities) > 1 else 0.0
    second_derivative = recent_velocity - older_velocity
    positive_steps = sum(1 for velocity in velocities[-3:] if velocity > 0)

    component = min(10.0, (recent_velocity / max_rank) * 24.0)
    if second_derivative > 0:
        component += min(8.0, (second_derivative / max_rank) * 24.0)
    if positive_steps >= 2:
        component += 4.0
    if len(historical) >= 3 and min(ranks[-3:]) > today_rank:
        component += 4.0

    return min(22.0, component)


def landing_zone_bonus(rank: int) -> float:
    if rank <= 10:
        return 8.0
    if rank <= 20:
        return 5.0
    if rank <= 30:
        return 3.0
    return 0.0


def emerging_convergence_adjustment(
    present_layers: set[str],
    previous_layers: set[str],
    signal: PlayerSignal,
) -> tuple[float, list[str]]:
    if not signal.has_previous_context:
        return 0.0, []

    reasons: list[str] = []
    bonus = 0.0
    new_layers = present_layers - previous_layers

    if len(present_layers) >= 2 and len(previous_layers) < len(present_layers):
        bonus += 8.0
        reasons.append("Newly forming cross-layer support detected")

    if len(present_layers) == 3 and len(previous_layers) < 3:
        bonus += 8.0
        reasons.append("New convergence event: now appears across all three model layers")

    if new_layers:
        bonus += min(8.0, 4.0 * len(new_layers))
        reasons.append(f"Fresh layer appearance: {', '.join(sorted(new_layers))}")

    return min(20.0, bonus), reasons


def persistence_adjustment(
    signal: PlayerSignal,
    layer_scores: dict[str, list[float]],
) -> tuple[float, float, str, list[str]]:
    reasons: list[str] = []
    if not signal.has_previous_context:
        return 0.0, 0.0, "fresh", reasons

    today_boards = set(signal.entries)
    previous_boards = set(signal.previous_entries)
    same_board_set = today_boards and today_boards == previous_boards
    repeated_non_base_boards = repeated_non_base_signal_boards(signal)
    movement_reasons = [
        signal.previous_entries[board_id].rank - entry.rank
        for board_id, entry in signal.entries.items()
        if board_id in signal.previous_entries
    ]
    largest_improvement = max(movement_reasons, default=0)

    history_days = max((len(entries) for entries in signal.historical_entries.values()), default=0)
    high_signal = any(mean(values) >= 70 for values in layer_scores.values() if values)

    penalty = 0.0
    if same_board_set and repeated_non_base_boards and largest_improvement < 5 and high_signal:
        penalty += 6.0
        reasons.append(
            "Persistence penalty: non-GBM support was already visible yesterday with limited movement"
        )

    if (
        signal.has_history_context
        and history_days >= 3
        and same_board_set
        and repeated_non_base_boards
        and largest_improvement < 10
    ):
        penalty += min(14.0, 3.0 + (history_days * 1.5))
        reasons.append(f"Stale-signal penalty: appeared repeatedly across {history_days} history snapshots")

    if not penalty:
        return 0.0, 0.0, "fresh", reasons

    elite_status = stale_elite_status(signal)
    if elite_status == "persistent_elite_reinforced":
        elite_reason = elite_support_reason(signal)
        return 0.0, 4.0, elite_status, [
            f"Stale elite reinforcement: repeated signal is still elite across {elite_reason}; stale penalty removed and small reinforcement added"
        ]
    if elite_status == "persistent_elite_protected":
        elite_reason = elite_support_reason(signal)
        return min(3.0, penalty * 0.25), 0.0, elite_status, [
            f"Stale elite protection: repeated signal remains confirmed by {elite_reason}; stale penalty reduced"
        ]

    return penalty, 0.0, "normal_stale_penalty", reasons


def stale_elite_status(signal: PlayerSignal) -> str:
    top20_count = elite_rank_count(signal, 20)
    top30_specialist = has_specialist_confirmation(signal, 30)
    collapsed = has_material_rank_collapse(signal)

    if top20_count >= 3 and not collapsed:
        return "persistent_elite_reinforced"
    if top20_count >= 2 or (top20_count >= 1 and top30_specialist):
        return "persistent_elite_protected"
    return "normal_stale_penalty"


def elite_rank_count(signal: PlayerSignal, rank_cutoff: int) -> int:
    return sum(1 for entry in signal.entries.values() if entry.rank <= rank_cutoff)


def has_specialist_confirmation(signal: PlayerSignal, rank_cutoff: int) -> bool:
    return any(
        signal.entries.get(board_id) and signal.entries[board_id].rank <= rank_cutoff
        for board_id in ("sequence_top150", "pitcher_batter_top80")
    )


def has_material_rank_collapse(signal: PlayerSignal) -> bool:
    for board_id, entry in signal.entries.items():
        previous = signal.previous_entries.get(board_id)
        if previous and entry.rank - previous.rank >= 35:
            return True
    return False


def elite_support_reason(signal: PlayerSignal) -> str:
    labels = []
    for board_id, entry in signal.entries.items():
        if entry.rank <= 30:
            labels.append(f"{BOARD_SPECS[board_id]['label']} rank {entry.rank}")
    return ", ".join(labels) if labels else "high repeated model support"


def repeated_non_base_signal_boards(signal: PlayerSignal) -> set[str]:
    base_gbm_board = "gbm_top80"
    repeated = (set(signal.entries) & set(signal.previous_entries)) - {base_gbm_board}

    if signal.has_history_context:
        repeated |= {
            board_id
            for board_id, entries in signal.historical_entries.items()
            if board_id != base_gbm_board and board_id in signal.entries and entries
        }

    return repeated


def layers_from_entries(entries: dict[str, Any]) -> set[str]:
    layers: set[str] = set()
    for board_id in entries:
        spec = BOARD_SPECS.get(board_id)
        if spec:
            layers.add(spec["layer"])
    return layers


def _rank(signal: PlayerSignal, board_id: str) -> int | None:
    entry = signal.entries.get(board_id)
    return entry.rank if entry else None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if "%" in str(value):
        return parsed
    return parsed
