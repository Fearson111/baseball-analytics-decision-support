from __future__ import annotations

from collections import defaultdict
from typing import Any

from .tracker import parse_american_odds, parse_float


# Sportsbooks price same-game HR parlays as a block, then multiply that block
# against legs from other games. These constants keep the estimate close to
# the observed Fanatics/DK shape without pretending we have their SGP API.
SAME_TEAM_GROUP_PAIR_FACTOR = 0.77
SAME_TEAM_ADDITIONAL_LEG_FACTOR = 0.92
MIXED_GAME_PAIR_GROUP_FACTOR = 1.14
MIXED_GAME_ADDITIONAL_LEG_FACTOR = 1.18


def decimal_odds_from_american(value: Any) -> float | None:
    odds = parse_american_odds(value)
    if odds is None or odds == 0:
        return None
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)


def implied_probability(value: Any) -> float | None:
    odds = parse_american_odds(value)
    if odds is None or odds == 0:
        return None
    if odds > 0:
        return round(100 / (odds + 100), 6)
    return round(abs(odds) / (abs(odds) + 100), 6)


def product(values: Any) -> float:
    total = 1.0
    for value in values:
        total *= float(value)
    return total


def correlated_parlay_odds(legs: list[dict[str, Any]]) -> dict[str, Any]:
    raw_decimal = round(product(decimal_odds_from_american(leg.get("book_american_odds")) or 0.0 for leg in legs), 4)
    grouped_decimal, notes = grouped_same_game_parlay_decimal(legs)
    adjusted_decimal = round(max(1.01, grouped_decimal), 4)
    factor = adjusted_decimal / raw_decimal if raw_decimal else 1.0
    return {
        "independent_parlay_decimal_odds": raw_decimal,
        "correlation_factor": round(factor, 4),
        "correlation_note": "; ".join(notes) if notes else "No same-game grouped pricing adjustment",
        "parlay_decimal_odds": adjusted_decimal,
    }


def grouped_same_game_parlay_decimal(legs: list[dict[str, Any]]) -> tuple[float, list[str]]:
    total_decimal = 1.0
    notes: list[str] = []
    for group in same_game_groups(legs):
        raw_group_decimal = product(decimal_odds_from_american(leg.get("book_american_odds")) or 0.0 for leg in group)
        if len(group) == 1:
            total_decimal *= raw_group_decimal
            continue

        factor, note = same_game_group_factor(group)
        grouped_decimal = raw_group_decimal * factor
        total_decimal *= grouped_decimal
        notes.append(
            f"{game_label(group)} SGP block {len(group)} legs: "
            f"{raw_group_decimal:.1f}x raw -> {grouped_decimal:.1f}x ({note})"
        )
    return total_decimal, notes


def same_game_group_factor(group: list[dict[str, Any]]) -> tuple[float, str]:
    teams = {str(leg.get("team_abbrev") or "").strip().upper() for leg in group if leg.get("team_abbrev")}
    leg_count = len(group)
    if len(teams) <= 1:
        factor = SAME_TEAM_GROUP_PAIR_FACTOR
        if leg_count > 2:
            factor *= SAME_TEAM_ADDITIONAL_LEG_FACTOR ** (leg_count - 2)
        return factor, "same-team correlated SGP estimate"

    factor = MIXED_GAME_PAIR_GROUP_FACTOR
    if leg_count > 2:
        factor *= MIXED_GAME_ADDITIONAL_LEG_FACTOR ** (leg_count - 2)
    return factor, "mixed-team same-game SGP estimate"


def same_game_groups(legs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    singles: list[list[dict[str, Any]]] = []
    for leg in legs:
        game = game_key(leg)
        if game:
            grouped[game].append(leg)
        else:
            singles.append([leg])

    groups = list(grouped.values())
    groups.extend(singles)
    return groups


def correlation_factor(legs: list[dict[str, Any]]) -> tuple[float, list[str]]:
    raw_decimal = product(decimal_odds_from_american(leg.get("book_american_odds")) or 0.0 for leg in legs)
    grouped_decimal, notes = grouped_same_game_parlay_decimal(legs)
    if not raw_decimal:
        return 1.0, notes
    return grouped_decimal / raw_decimal, notes


def same_team_cluster_count(legs: list[dict[str, Any]]) -> int:
    groups: dict[tuple[str, str], int] = defaultdict(int)
    for leg in legs:
        game = game_key(leg)
        team = str(leg.get("team_abbrev") or "").strip().upper()
        if game and team:
            groups[(game, team)] += 1
    return sum(1 for count in groups.values() if count >= 2)


def same_game(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_game = game_key(left)
    right_game = game_key(right)
    return bool(left_game and right_game and left_game == right_game)


def same_team(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_team = str(left.get("team_abbrev") or "").strip().upper()
    right_team = str(right.get("team_abbrev") or "").strip().upper()
    return bool(left_team and right_team and left_team == right_team)


def game_key(row: dict[str, Any]) -> str:
    explicit = str(row.get("game_key") or "").strip()
    if explicit:
        return explicit
    team = str(row.get("team_abbrev") or "").strip().upper()
    opponent = str(row.get("opponent_abbrev") or "").strip().upper()
    if not team or not opponent:
        return ""
    return "@".join(sorted([team, opponent]))


def game_label(group: list[dict[str, Any]]) -> str:
    key = game_key(group[0]) if group else ""
    return key.replace("@", "/") if key else "Unknown game"


def safe_float(value: Any) -> float | None:
    parsed = parse_float(value)
    if parsed is None or parsed != parsed:
        return None
    return parsed
