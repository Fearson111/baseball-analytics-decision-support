from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Callable

from .boards import BOARD_SPECS
from .io import player_key
from .parlay_odds import correlated_parlay_odds
from .profit_lenses import enrich_rows_from_input_folder, num, read_csv_rows, write_csv
from .tracker import parse_american_odds, parse_float


CRITERIA_VERSION = "1"
PROSPECTIVE_MAX_LEGS = 2

STRENGTH_COLUMNS = {
    "G": "gbm_rank",
    "R": "gbm_progression_rank",
    "S": "sequence_rank",
    "M": "pitcher_batter_rank",
}

STRENGTH_MAX_RANKS = {
    "G": BOARD_SPECS["gbm_top80"]["max_rank"],
    "R": BOARD_SPECS["gbm_progression_top80"]["max_rank"],
    "S": BOARD_SPECS["sequence_top150"]["max_rank"],
    "M": BOARD_SPECS["pitcher_batter_top80"]["max_rank"],
}

LEG_FIELDS = [
    "player",
    "game_key",
    "bookmaker_used",
    "book_american_odds",
    "dk_odds",
    "fan_odds",
    "365_odds",
    "implied_probability",
    "G",
    "R",
    "S",
    "M",
    "consensus",
    "disagreement",
    "state_matchup_strength",
    "quality_regression_strength",
    "best_model",
    "best_model_strength",
    "second_best_model",
    "second_best_model_strength",
    "eye_rank",
    "eye_score",
    "accel_score",
    "stale_signal_status",
    "gbm_rank",
    "gbm_progression_rank",
    "sequence_rank",
    "pitcher_batter_rank",
    "model_hr_probability_percent",
    "edge_percent",
    "team_abbrev",
    "opponent_abbrev",
    "lineup_status",
    "batting_order",
    "qualification_reason",
]

PROSPECTIVE_TICKET_COLUMNS = [
    "ticket_id",
    "slate_date",
    "criteria_id",
    "criteria_version",
    "criteria_title",
    "generated_timestamp",
    "status",
    "hypothesis",
    "description",
    "candidate_filter_definition",
    "candidate_ranking_definition",
    "pairing_definition",
    "same_game_allowed",
    "max_tickets_per_day",
    "record_locked_before_games",
    "source_board_path",
    "source_input_folder",
    "qualifying_count",
    "leg1_role",
    *[f"leg1_{field}" for field in LEG_FIELDS],
    "leg2_role",
    *[f"leg2_{field}" for field in LEG_FIELDS],
    "naive_market_joint_probability",
    "expected_wins",
    "independent_parlay_decimal_odds",
    "correlation_factor",
    "correlation_note",
    "parlay_decimal_odds",
    "stake_units",
]

PROSPECTIVE_HISTORY_COLUMNS = [
    *PROSPECTIVE_TICKET_COLUMNS,
    "leg1_result",
    "leg1_actual_hr",
    "leg2_result",
    "leg2_actual_hr",
    "ticket_hit",
    "profit_units",
    "running_profit_units",
    "actual_minus_expected_wins",
    "actual_to_expected_ratio",
]

PROSPECTIVE_CRITERIA_COLUMNS = [
    "criteria_id",
    "criteria_version",
    "title",
    "created_at",
    "effective_start_date",
    "status",
    "description",
    "hypothesis",
    "candidate_filter_definition",
    "candidate_ranking_definition",
    "pairing_definition",
    "same_game_allowed",
    "max_tickets_per_day",
]


@dataclass(frozen=True)
class ProspectiveCriteria:
    criteria_id: str
    title: str
    filename: str
    description: str
    hypothesis: str
    candidate_filter_definition: str
    candidate_ranking_definition: str
    pairing_definition: str
    leg1_role: str
    leg1_predicate: Callable[[dict[str, Any], dict[str, Any]], bool]
    leg1_sort_key: Callable[[dict[str, Any]], tuple[Any, ...]]
    leg2_role: str
    leg2_predicate: Callable[[dict[str, Any], dict[str, Any]], bool]
    leg2_sort_key: Callable[[dict[str, Any]], tuple[Any, ...]]
    same_game_allowed: bool = False
    max_tickets_per_day: int = 1
    active: bool = True


def build_prospective_parlays_from_run(board_path: Path, input_folder: Path, output_folder: Path) -> dict[str, Path]:
    rows = enrich_rows_from_input_folder(read_csv_rows(board_path), input_folder)
    return write_prospective_parlays(rows, output_folder, board_path=board_path, input_folder=input_folder)


def write_prospective_parlays(
    rows: list[dict[str, Any]],
    output_folder: Path,
    *,
    board_path: Path | None = None,
    input_folder: Path | None = None,
    slate_date: str | None = None,
    generated_timestamp: str | None = None,
) -> dict[str, Path]:
    output_folder.mkdir(parents=True, exist_ok=True)
    generated_timestamp = generated_timestamp or datetime.now().isoformat(timespec="seconds")
    slate_date = slate_date or infer_slate_date(rows, generated_timestamp)
    enriched = add_meta_features(rows)
    context = criteria_context(enriched)

    written: dict[str, Path] = {}
    combined: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    for spec in prospective_criteria_specs():
        ticket = select_prospective_ticket(
            enriched,
            spec,
            context,
            slate_date=slate_date,
            generated_timestamp=generated_timestamp,
            board_path=board_path,
            input_folder=input_folder,
        )
        ticket_rows = [ticket] if ticket else []
        path = output_folder / spec.filename
        write_csv(path, PROSPECTIVE_TICKET_COLUMNS, ticket_rows)
        written[spec.criteria_id] = path
        combined.extend(ticket_rows)
        candidate_rows.extend(criteria_candidate_rows(enriched, spec, context, slate_date))

    combined_path = output_folder / "prospective_parlays_combined.csv"
    write_csv(combined_path, PROSPECTIVE_TICKET_COLUMNS, combined)
    written["combined"] = combined_path

    criteria_path = output_folder / "prospective_criteria_v1.csv"
    write_csv(criteria_path, PROSPECTIVE_CRITERIA_COLUMNS, [criteria_row(spec) for spec in prospective_criteria_specs()])
    written["criteria"] = criteria_path

    candidates_path = output_folder / "prospective_qualifying_players.csv"
    write_csv(candidates_path, prospective_candidate_columns(), candidate_rows)
    written["candidates"] = candidates_path
    return written


def build_prospective_history_rows(project_root: Path) -> list[dict[str, Any]]:
    tickets = read_saved_prospective_tickets(project_root / "MODEL4_DAILY_READS")
    if not tickets:
        return []

    results = load_result_lookup(project_root / "MODEL4_RANK_TRACKING" / "model4_rank_results.csv")
    history: list[dict[str, Any]] = []
    running: dict[str, float] = {}
    actuals: dict[str, int] = {}
    expecteds: dict[str, float] = {}
    for ticket in sorted(tickets, key=lambda row: (str(row.get("slate_date", "")), str(row.get("criteria_id", "")))):
        criteria_id = str(ticket.get("criteria_id") or "")
        slate_date = str(ticket.get("slate_date") or "")
        row = dict(ticket)
        leg_results: list[bool] = []
        results_available = True
        for leg_index in range(1, PROSPECTIVE_MAX_LEGS + 1):
            prefix = f"leg{leg_index}"
            player = str(row.get(f"{prefix}_player") or "")
            actual_hr = results.get((slate_date, player_key(player)))
            if actual_hr is None:
                results_available = False
                row[f"{prefix}_actual_hr"] = ""
                row[f"{prefix}_result"] = "Pending"
                continue
            row[f"{prefix}_actual_hr"] = actual_hr
            hit = actual_hr > 0
            leg_results.append(hit)
            row[f"{prefix}_result"] = "HR" if hit else "No HR"

        expected = safe_float(row.get("expected_wins")) or 0.0
        expecteds[criteria_id] = expecteds.get(criteria_id, 0.0) + expected
        if results_available and len(leg_results) == PROSPECTIVE_MAX_LEGS:
            hit = all(leg_results)
            profit = (safe_float(row.get("parlay_decimal_odds")) or 0.0) - 1.0 if hit else -1.0
            row["ticket_hit"] = "1" if hit else "0"
            row["profit_units"] = round(profit, 2)
            running[criteria_id] = running.get(criteria_id, 0.0) + profit
            actuals[criteria_id] = actuals.get(criteria_id, 0) + int(hit)
        else:
            row["ticket_hit"] = ""
            row["profit_units"] = ""
            running.setdefault(criteria_id, 0.0)
            actuals.setdefault(criteria_id, 0)

        row["running_profit_units"] = round(running.get(criteria_id, 0.0), 2)
        row["actual_minus_expected_wins"] = round(actuals.get(criteria_id, 0) - expecteds.get(criteria_id, 0.0), 4)
        row["actual_to_expected_ratio"] = round(actuals.get(criteria_id, 0) / expecteds[criteria_id], 4) if expecteds.get(criteria_id) else ""
        history.append(row)
    return history


def read_saved_prospective_tickets(daily_root: Path) -> list[dict[str, Any]]:
    tickets: list[dict[str, Any]] = []
    if not daily_root.exists():
        return tickets
    for path in sorted(daily_root.glob("*/PROSPECTIVE_PARLAYS/prospective_parlays_combined.csv")):
        tickets.extend(read_csv_rows(path))
    return tickets


def load_result_lookup(path: Path) -> dict[tuple[str, str], int]:
    lookup: dict[tuple[str, str], int] = {}
    if not path.exists():
        return lookup
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("result_available") or "") != "1":
                continue
            player = str(row.get("player") or "")
            date_key = str(row.get("game_date") or "")[:10]
            actual = safe_float(row.get("actual_hr"))
            if player and date_key and actual is not None:
                lookup[(date_key, player_key(player))] = int(actual)
    return lookup


def add_meta_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        output = dict(row)
        strengths = {key: normalized_strength(row.get(column), STRENGTH_MAX_RANKS[key]) for key, column in STRENGTH_COLUMNS.items()}
        present = {key: value is not None for key, value in strengths.items()}
        values = [value for value in strengths.values() if value is not None]
        for key, value in strengths.items():
            output[key] = round(value, 4) if value is not None else ""
            output[f"{key}_present"] = "1" if present[key] else "0"
        output["model_count_present"] = len(values)
        output["consensus"] = round(sum(values) / len(values), 4) if values else ""
        output["disagreement"] = round(population_std(values), 4) if len(values) > 1 else 0.0 if values else ""
        output["models_top_05pct"] = count_at_least(strengths, 0.95)
        output["models_top_10pct"] = count_at_least(strengths, 0.90)
        output["models_top_20pct"] = count_at_least(strengths, 0.80)
        output["models_top_25pct"] = count_at_least(strengths, 0.75)
        output["state_matchup_strength"] = mean_present([strengths["S"], strengths["M"]])
        output["quality_regression_strength"] = mean_present([strengths["G"], strengths["R"]])
        output["quality_matchup_strength"] = mean_present([strengths["G"], strengths["M"]])
        output["regression_state_strength"] = mean_present([strengths["R"], strengths["S"]])
        best = sorted(((key, value) for key, value in strengths.items() if value is not None), key=lambda item: item[1], reverse=True)
        output["best_model"] = best[0][0] if best else ""
        output["best_model_strength"] = round(best[0][1], 4) if best else ""
        output["second_best_model"] = best[1][0] if len(best) > 1 else ""
        output["second_best_model_strength"] = round(best[1][1], 4) if len(best) > 1 else ""
        output["game_key"] = game_key(output)
        output["implied_probability"] = implied_probability(output.get("book_american_odds")) or ""
        enriched.append(output)
    return enriched


def normalized_strength(rank_value: Any, max_rank: int) -> float | None:
    rank = safe_float(rank_value)
    if rank is None or rank <= 0 or max_rank <= 1:
        return None
    rank = min(rank, float(max_rank))
    return max(0.0, 1 - ((rank - 1) / (max_rank - 1)))


def population_std(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5


def count_at_least(strengths: dict[str, float | None], threshold: float) -> int:
    return sum(1 for value in strengths.values() if value is not None and value >= threshold)


def mean_present(values: list[float | None]) -> float | str:
    present = [value for value in values if value is not None]
    return round(sum(present) / len(present), 4) if present else ""


def criteria_context(rows: list[dict[str, Any]]) -> dict[str, Any]:
    disagreements = [value for row in rows if (value := safe_float(row.get("disagreement"))) is not None]
    return {"low_disagreement_cutoff": percentile(disagreements, 0.25) if disagreements else 0.0}


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * quantile)))
    return ordered[index]


def prospective_criteria_specs() -> list[ProspectiveCriteria]:
    return [
        ProspectiveCriteria(
            criteria_id="CONSENSUS_2L_V1",
            title="Consensus x Consensus V1",
            filename="prospective_consensus_2l_v1.csv",
            description="Two players with broad cross-model agreement, requiring at least one short-term specialty model in the agreement.",
            hypothesis="Broad agreement across multiple independent model views can identify two HR candidates whose joint outcome beats market expectation.",
            candidate_filter_definition="At least 3 of 4 model strengths >= 0.90 and either Sequence or Matchup strength >= 0.90.",
            candidate_ranking_definition="Highest consensus, then most strong models, then lowest disagreement, then best Eye rank.",
            pairing_definition="Leg 1 is top qualified player; Leg 2 is next qualified player from a different game.",
            leg1_role="Highest Consensus",
            leg1_predicate=is_consensus_candidate,
            leg1_sort_key=consensus_sort_key,
            leg2_role="Second Highest Consensus",
            leg2_predicate=is_consensus_candidate,
            leg2_sort_key=consensus_sort_key,
        ),
        ProspectiveCriteria(
            criteria_id="STATE_MATCHUP_2L_V1",
            title="State/Matchup x State/Matchup V1",
            filename="prospective_state_matchup_2l_v1.csv",
            description="Two players with elite Sequence plus Matchup agreement and at least one broad-model confirmation.",
            hypothesis="A hitter in a strong temporal state and a strong pitcher-specific matchup state may be especially actionable today.",
            candidate_filter_definition="Sequence >= 0.90, Matchup >= 0.90, and Base GBM or Regression >= 0.75.",
            candidate_ranking_definition="Highest mean Sequence/Matchup strength, then consensus, then best Eye rank.",
            pairing_definition="Leg 1 is top state/matchup player; Leg 2 is next state/matchup player from a different game.",
            leg1_role="Best State/Matchup",
            leg1_predicate=is_state_matchup_candidate,
            leg1_sort_key=state_matchup_sort_key,
            leg2_role="Second State/Matchup",
            leg2_predicate=is_state_matchup_candidate,
            leg2_sort_key=state_matchup_sort_key,
        ),
        ProspectiveCriteria(
            criteria_id="ANCHOR_SPECIALIST_2L_V1",
            title="Consensus Anchor x Specialist V1",
            filename="prospective_anchor_specialist_2l_v1.csv",
            description="One low-disagreement consensus anchor paired with one specialized short-term signal player.",
            hypothesis="A stable anchor and a specialized conviction player may test complementary signal geometry better than two similar players.",
            candidate_filter_definition="Anchor: consensus >= 0.88, at least 3 models >= 0.85, and disagreement in today's bottom quartile. Specialist: a specialized model >= 0.95, another independent model >= 0.90, and consensus >= 0.70.",
            candidate_ranking_definition="Anchor: highest consensus then lowest disagreement. Specialist: highest best specialized strength, then state/matchup, then consensus.",
            pairing_definition="Leg 1 is strongest anchor; Leg 2 is strongest non-same-player specialist from a different game.",
            leg1_role="Consensus Anchor",
            leg1_predicate=is_anchor_candidate,
            leg1_sort_key=anchor_sort_key,
            leg2_role="Specialist",
            leg2_predicate=is_specialist_candidate,
            leg2_sort_key=specialist_sort_key,
        ),
        ProspectiveCriteria(
            criteria_id="QUALITY_REGRESSION_2L_V1",
            title="Quality/Regression x State Confirmation V1",
            filename="prospective_quality_regression_2l_v1.csv",
            description="Two hitters with strong base quality plus positive-regression support and short-term confirmation.",
            hypothesis="Base HR quality and positive regression may become more actionable when Sequence or Matchup confirms the player today.",
            candidate_filter_definition="Base GBM >= 0.90, Regression >= 0.90, and Sequence or Matchup >= 0.75.",
            candidate_ranking_definition="Highest mean Base/Regression strength, then highest Sequence/Matchup confirmation, then consensus.",
            pairing_definition="Leg 1 is top quality/regression player; Leg 2 is next quality/regression player from a different game.",
            leg1_role="Best Quality/Regression",
            leg1_predicate=is_quality_regression_candidate,
            leg1_sort_key=quality_regression_sort_key,
            leg2_role="Second Quality/Regression",
            leg2_predicate=is_quality_regression_candidate,
            leg2_sort_key=quality_regression_sort_key,
        ),
    ]


def select_prospective_ticket(
    rows: list[dict[str, Any]],
    spec: ProspectiveCriteria,
    context: dict[str, Any],
    *,
    slate_date: str,
    generated_timestamp: str,
    board_path: Path | None,
    input_folder: Path | None,
) -> dict[str, Any] | None:
    valid_rows = [row for row in rows if has_book_odds(row)]
    leg1_pool = sorted([row for row in valid_rows if spec.leg1_predicate(row, context)], key=spec.leg1_sort_key)
    if not leg1_pool:
        return None
    for leg1 in leg1_pool:
        leg2_pool = sorted(
            [
                row for row in valid_rows
                if row is not leg1
                and player_key(str(row.get("player") or "")) != player_key(str(leg1.get("player") or ""))
                and spec.leg2_predicate(row, context)
                and valid_pair(leg1, row, same_game_allowed=spec.same_game_allowed)
            ],
            key=spec.leg2_sort_key,
        )
        if leg2_pool:
            qualifying_count = len([row for row in valid_rows if spec.leg1_predicate(row, context) or spec.leg2_predicate(row, context)])
            return prospective_ticket_row(
                spec,
                [leg1, leg2_pool[0]],
                slate_date=slate_date,
                generated_timestamp=generated_timestamp,
                board_path=board_path,
                input_folder=input_folder,
                qualifying_count=qualifying_count,
            )
    return None


def prospective_ticket_row(
    spec: ProspectiveCriteria,
    legs: list[dict[str, Any]],
    *,
    slate_date: str,
    generated_timestamp: str,
    board_path: Path | None,
    input_folder: Path | None,
    qualifying_count: int,
) -> dict[str, Any]:
    odds_summary = correlated_parlay_odds(legs)
    implieds = [implied_probability(leg.get("book_american_odds")) or 0.0 for leg in legs]
    expected = round(product(implieds), 6)
    ticket_id = f"{slate_date}_{spec.criteria_id}"
    output: dict[str, Any] = {
        "ticket_id": ticket_id,
        "slate_date": slate_date,
        "criteria_id": spec.criteria_id,
        "criteria_version": CRITERIA_VERSION,
        "criteria_title": spec.title,
        "generated_timestamp": generated_timestamp,
        "status": "active",
        "hypothesis": spec.hypothesis,
        "description": spec.description,
        "candidate_filter_definition": spec.candidate_filter_definition,
        "candidate_ranking_definition": spec.candidate_ranking_definition,
        "pairing_definition": spec.pairing_definition,
        "same_game_allowed": str(spec.same_game_allowed),
        "max_tickets_per_day": spec.max_tickets_per_day,
        "record_locked_before_games": "1",
        "source_board_path": str(board_path or ""),
        "source_input_folder": str(input_folder or ""),
        "qualifying_count": qualifying_count,
        "leg1_role": spec.leg1_role,
        "leg2_role": spec.leg2_role,
        "naive_market_joint_probability": expected,
        "expected_wins": expected,
        **odds_summary,
        "stake_units": "1",
    }
    for index, leg in enumerate(legs, start=1):
        output.update(prefixed_prospective_leg(f"leg{index}", leg, role=spec.leg1_role if index == 1 else spec.leg2_role))
    return output


def prefixed_prospective_leg(prefix: str, row: dict[str, Any], *, role: str) -> dict[str, Any]:
    reason = qualification_reason(row)
    output = {f"{prefix}_qualification_reason": reason}
    for field in LEG_FIELDS:
        if field == "qualification_reason":
            continue
        output[f"{prefix}_{field}"] = row.get(field, "")
    return output


def criteria_candidate_rows(rows: list[dict[str, Any]], spec: ProspectiveCriteria, context: dict[str, Any], slate_date: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        role = ""
        if spec.leg1_predicate(row, context):
            role = spec.leg1_role
        if spec.leg2_predicate(row, context):
            role = f"{role}; {spec.leg2_role}" if role else spec.leg2_role
        if not role:
            continue
        output.append(
            {
                "slate_date": slate_date,
                "criteria_id": spec.criteria_id,
                "criteria_title": spec.title,
                "role": role,
                "player": row.get("player", ""),
                "bookmaker_used": row.get("bookmaker_used", ""),
                "book_american_odds": row.get("book_american_odds", ""),
                "dk_odds": row.get("dk_odds", ""),
                "fan_odds": row.get("fan_odds", ""),
                "365_odds": row.get("365_odds", ""),
                "implied_probability": row.get("implied_probability", ""),
                "G": row.get("G", ""),
                "R": row.get("R", ""),
                "S": row.get("S", ""),
                "M": row.get("M", ""),
                "consensus": row.get("consensus", ""),
                "disagreement": row.get("disagreement", ""),
                "state_matchup_strength": row.get("state_matchup_strength", ""),
                "quality_regression_strength": row.get("quality_regression_strength", ""),
                "eye_rank": row.get("eye_rank", ""),
                "team_abbrev": row.get("team_abbrev", ""),
                "opponent_abbrev": row.get("opponent_abbrev", ""),
                "qualification_reason": qualification_reason(row),
            }
        )
    return output


def prospective_candidate_columns() -> list[str]:
    return [
        "slate_date",
        "criteria_id",
        "criteria_title",
        "role",
        "player",
        "book_american_odds",
        "implied_probability",
        "G",
        "R",
        "S",
        "M",
        "consensus",
        "disagreement",
        "state_matchup_strength",
        "quality_regression_strength",
        "eye_rank",
        "team_abbrev",
        "opponent_abbrev",
        "qualification_reason",
    ]


def criteria_row(spec: ProspectiveCriteria) -> dict[str, Any]:
    return {
        "criteria_id": spec.criteria_id,
        "criteria_version": CRITERIA_VERSION,
        "title": spec.title,
        "created_at": "2026-08-16",
        "effective_start_date": "2026-08-16",
        "status": "active" if spec.active else "inactive",
        "description": spec.description,
        "hypothesis": spec.hypothesis,
        "candidate_filter_definition": spec.candidate_filter_definition,
        "candidate_ranking_definition": spec.candidate_ranking_definition,
        "pairing_definition": spec.pairing_definition,
        "same_game_allowed": str(spec.same_game_allowed),
        "max_tickets_per_day": spec.max_tickets_per_day,
    }


def is_consensus_candidate(row: dict[str, Any], context: dict[str, Any]) -> bool:
    return strong_models(row, 0.90) >= 3 and (strength(row, "S") >= 0.90 or strength(row, "M") >= 0.90)


def consensus_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (-strength(row, "consensus"), -strong_models(row, 0.90), strength(row, "disagreement", 999), num(row, "eye_rank", 999))


def is_state_matchup_candidate(row: dict[str, Any], context: dict[str, Any]) -> bool:
    return strength(row, "S") >= 0.90 and strength(row, "M") >= 0.90 and (strength(row, "G") >= 0.75 or strength(row, "R") >= 0.75)


def state_matchup_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (-strength(row, "state_matchup_strength"), -strength(row, "consensus"), num(row, "eye_rank", 999))


def is_anchor_candidate(row: dict[str, Any], context: dict[str, Any]) -> bool:
    return (
        strength(row, "consensus") >= 0.88
        and strong_models(row, 0.85) >= 3
        and strength(row, "disagreement", 999) <= float(context.get("low_disagreement_cutoff", 0.0))
    )


def anchor_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (-strength(row, "consensus"), strength(row, "disagreement", 999), num(row, "eye_rank", 999))


def is_specialist_candidate(row: dict[str, Any], context: dict[str, Any]) -> bool:
    specialized = [strength(row, "S"), strength(row, "M")]
    all_strengths = [strength(row, key) for key in ("G", "R", "S", "M")]
    return max(specialized) >= 0.95 and sum(1 for value in all_strengths if value >= 0.90) >= 2 and strength(row, "consensus") >= 0.70


def specialist_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (-max(strength(row, "S"), strength(row, "M")), -strength(row, "state_matchup_strength"), -strength(row, "consensus"), num(row, "eye_rank", 999))


def is_quality_regression_candidate(row: dict[str, Any], context: dict[str, Any]) -> bool:
    return strength(row, "G") >= 0.90 and strength(row, "R") >= 0.90 and (strength(row, "S") >= 0.75 or strength(row, "M") >= 0.75)


def quality_regression_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (-strength(row, "quality_regression_strength"), -max(strength(row, "S"), strength(row, "M")), -strength(row, "consensus"), num(row, "eye_rank", 999))


def strength(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    return safe_float(row.get(key)) if safe_float(row.get(key)) is not None else default


def strong_models(row: dict[str, Any], threshold: float) -> int:
    return sum(1 for key in ("G", "R", "S", "M") if strength(row, key) >= threshold)


def valid_pair(
    row_a: dict[str, Any],
    row_b: dict[str, Any],
    *,
    same_game_allowed: bool,
) -> bool:
    team_a = str(row_a.get("team_abbrev") or "").strip().upper()
    team_b = str(row_b.get("team_abbrev") or "").strip().upper()

    # Never pair two hitters from the same team.
    if team_a and team_b and team_a == team_b:
        return False

    if same_game_allowed:
        return True

    game_a = str(row_a.get("game_key") or "")
    game_b = str(row_b.get("game_key") or "")

    if not game_a or not game_b:
        return True

    return game_a != game_b


def game_key(row: dict[str, Any]) -> str:
    team = str(row.get("team_abbrev") or "").strip()
    opponent = str(row.get("opponent_abbrev") or "").strip()
    if not team or not opponent:
        return ""
    return "@".join(sorted([team, opponent]))


def has_book_odds(row: dict[str, Any]) -> bool:
    return parse_american_odds(row.get("book_american_odds")) is not None


def implied_probability(value: Any) -> float | None:
    odds = parse_american_odds(value)
    if odds is None or odds == 0:
        return None
    if odds > 0:
        return round(100 / (odds + 100), 6)
    return round(abs(odds) / (abs(odds) + 100), 6)


def decimal_odds_from_american(value: Any) -> float | None:
    odds = parse_american_odds(value)
    if odds is None or odds == 0:
        return None
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)


def product(values: Any) -> float:
    total = 1.0
    for value in values:
        total *= float(value)
    return total


def qualification_reason(row: dict[str, Any]) -> str:
    parts = []
    for key in ("G", "R", "S", "M"):
        value = safe_float(row.get(key))
        if value is not None:
            parts.append(f"{key}={value:.2f}")
    consensus = safe_float(row.get("consensus"))
    disagreement = safe_float(row.get("disagreement"))
    if consensus is not None:
        parts.append(f"consensus={consensus:.2f}")
    if disagreement is not None:
        parts.append(f"disagreement={disagreement:.2f}")
    return ", ".join(parts)


def infer_slate_date(rows: list[dict[str, Any]], generated_timestamp: str) -> str:
    dates = [str(row.get("game_date") or "")[:10] for row in rows if str(row.get("game_date") or "").strip()]
    if dates:
        return sorted(dates)[-1]
    return generated_timestamp[:10]


def safe_float(value: Any) -> float | None:
    parsed = parse_float(value)
    if parsed is None or parsed != parsed:
        return None
    return parsed
