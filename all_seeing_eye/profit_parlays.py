from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .parlay_odds import correlated_parlay_odds, decimal_odds_from_american
from .profit_lenses import enrich_rows_from_input_folder, num
from .tracker import parse_float


MAX_PARLAY_LEGS = 4
MIN_TWO_LEG_PARLAY_DECIMAL_ODDS = 10.0


@dataclass(frozen=True)
class ParlaySpec:
    parlay_id: str
    title: str
    filename: str
    description: str
    backtest_note: str
    leg1_label: str
    leg1_predicate: Callable[[dict[str, Any]], bool]
    leg1_sort_key: Callable[[dict[str, Any]], tuple[Any, ...]]
    leg2_label: str
    leg2_predicate: Callable[[dict[str, Any]], bool]
    leg2_sort_key: Callable[[dict[str, Any]], tuple[Any, ...]]
    leg3_label: str | None = None
    leg3_predicate: Callable[[dict[str, Any]], bool] | None = None
    leg3_sort_key: Callable[[dict[str, Any]], tuple[Any, ...]] | None = None
    leg4_label: str | None = None
    leg4_predicate: Callable[[dict[str, Any]], bool] | None = None
    leg4_sort_key: Callable[[dict[str, Any]], tuple[Any, ...]] | None = None
    skip_day_one_history: bool = False
    max_tickets_per_day: int = 1


LEG_COLUMNS = [
    "label",
    "player",
    "bookmaker_used",
    "book_american_odds",
    "dk_odds",
    "fan_odds",
    "365_odds",
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
]


PARLAY_COLUMNS = [
    "parlay",
    "parlay_note",
    "status",
    *[f"leg{index}_{column}" for index in range(1, MAX_PARLAY_LEGS + 1) for column in LEG_COLUMNS],
    "independent_parlay_decimal_odds",
    "correlation_factor",
    "correlation_note",
    "parlay_decimal_odds",
]


PARLAY_HISTORY_COLUMNS = [
    "game_date",
    *PARLAY_COLUMNS,
    *[item for index in range(1, MAX_PARLAY_LEGS + 1) for item in (f"leg{index}_result", f"leg{index}_actual_hr")],
    "parlay_result",
    "profit_1u",
    "running_profit_1u",
]


def build_profit_parlays_from_run(board_path: Path, input_folder: Path, output_folder: Path) -> dict[str, Path]:
    rows = enrich_rows_from_input_folder(read_csv_rows(board_path), input_folder)
    return write_profit_parlays(rows, output_folder)


def write_profit_parlays(rows: list[dict[str, Any]], output_folder: Path) -> dict[str, Path]:
    rows = add_movement_features(rows)
    output_folder.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    combined = write_parlay_group(rows, parlay_specs(), output_folder, written)
    combined_path = output_folder / "profit_parlays_combined.csv"
    write_csv(combined_path, PARLAY_COLUMNS, combined)
    written["combined"] = combined_path

    three_leg_combined = write_parlay_group(rows, three_leg_parlay_specs(), output_folder, written)
    three_leg_combined_path = output_folder / "profit_parlays_3leg_combined.csv"
    write_csv(three_leg_combined_path, PARLAY_COLUMNS, three_leg_combined)
    written["three_leg_combined"] = three_leg_combined_path

    four_leg_combined = write_parlay_group(rows, four_leg_parlay_specs(), output_folder, written)
    four_leg_combined_path = output_folder / "profit_parlays_4leg_combined.csv"
    write_csv(four_leg_combined_path, PARLAY_COLUMNS, four_leg_combined)
    written["four_leg_combined"] = four_leg_combined_path

    movement_combined = write_parlay_group(rows, movement_parlay_specs(), output_folder, written)
    movement_combined_path = output_folder / "profit_parlays_movement_combined.csv"
    write_csv(movement_combined_path, PARLAY_COLUMNS, movement_combined)
    written["movement_combined"] = movement_combined_path

    reinforced_combined = write_parlay_group(rows, reinforced_parlay_specs(), output_folder, written)
    reinforced_combined_path = output_folder / "profit_parlays_reinforced_combined.csv"
    write_csv(reinforced_combined_path, PARLAY_COLUMNS, reinforced_combined)
    written["reinforced_combined"] = reinforced_combined_path
    return written


def write_parlay_group(
    rows: list[dict[str, Any]],
    specs: list[ParlaySpec],
    output_folder: Path,
    written: dict[str, Path],
) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    for spec in specs:
        ticket_rows = select_tickets(rows, spec)
        path = output_folder / spec.filename
        write_csv(path, PARLAY_COLUMNS, ticket_rows)
        written[spec.parlay_id] = path
        combined.extend(ticket_rows)
    return combined


def build_parlay_history_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = add_movement_features(rows)
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        date_key = str(row.get("game_date") or "")
        if date_key:
            by_date.setdefault(date_key, []).append(row)

    history: list[dict[str, Any]] = []
    running: dict[str, float] = {}
    for date_key in sorted(by_date):
        for spec in all_parlay_specs():
            if spec.skip_day_one_history and date_key == "2026-06-17":
                continue
            for ticket in select_tickets(by_date[date_key], spec):
                if ticket_has_void_leg(ticket):
                    continue
                profit = parlay_profit(ticket)
                running[spec.title] = running.get(spec.title, 0.0) + profit
                row = {
                    "game_date": date_key,
                    **ticket,
                    "parlay_result": "Hit" if profit > 0 else "Miss",
                    "profit_1u": round(profit, 2),
                    "running_profit_1u": round(running[spec.title], 2),
                }
                for index in range(1, MAX_PARLAY_LEGS + 1):
                    prefix = f"leg{index}"
                    row[f"{prefix}_result"] = leg_result(ticket, prefix)
                    row[f"{prefix}_actual_hr"] = ticket.get(f"{prefix}_actual_hr", "")
                history.append(row)
    return history


def select_ticket(rows: list[dict[str, Any]], spec: ParlaySpec) -> dict[str, Any] | None:
    tickets = select_tickets(rows, spec)
    return tickets[0] if tickets else None


def select_tickets(rows: list[dict[str, Any]], spec: ParlaySpec) -> list[dict[str, Any]]:
    valid_rows = [row for row in rows if has_book_odds(row)]
    if spec.max_tickets_per_day > 1:
        return [ticket for ticket in select_basket_tickets(valid_rows, spec) if is_playable_parlay(ticket)]

    selectors = spec_selectors(spec)
    selected: list[dict[str, Any]] = []
    selected_players: set[str] = set()

    for leg_index, (predicate, sort_key) in enumerate(selectors):
        pool = sorted(
            [
                row for row in valid_rows
                if predicate(row)
                and str(row.get("player")) not in selected_players
                and not (
                    len(selectors) == 2
                    and leg_index == 1
                    and selected
                    and same_team(selected[0], row)
                )
            ],
            key=sort_key,
        )
        if not pool:
            return []

        selected.append(pool[0])
        selected_players.add(str(pool[0].get("player")))

    ticket = parlay_row(spec, selected)
    return [ticket] if is_playable_parlay(ticket) else []


def select_basket_tickets(rows: list[dict[str, Any]], spec: ParlaySpec) -> list[dict[str, Any]]:
    selectors = spec_selectors(spec)
    if len(selectors) != 2:
        selected = select_ticket(rows, spec)
        return [selected] if selected else []

    (anchor_predicate, anchor_sort), (partner_predicate, partner_sort) = selectors
    anchor_pool = sorted([row for row in rows if anchor_predicate(row)], key=anchor_sort)
    if not anchor_pool:
        return []

    anchor = anchor_pool[0]
    partner_pool = sorted(
        [
            row
            for row in rows
            if partner_predicate(row)
            and str(row.get("player")) != str(anchor.get("player"))
            and not same_team(anchor, row)
        ],
        key=partner_sort,
    )
    return [parlay_row(spec, [anchor, partner]) for partner in partner_pool[: spec.max_tickets_per_day]]

def same_team(row_a: dict[str, Any], row_b: dict[str, Any]) -> bool:
    team_a = str(row_a.get("team_abbrev") or "").strip().upper()
    team_b = str(row_b.get("team_abbrev") or "").strip().upper()
    return bool(team_a and team_b and team_a == team_b)

def is_playable_parlay(ticket: dict[str, Any]) -> bool:
    leg_count = sum(
        1
        for index in range(1, MAX_PARLAY_LEGS + 1)
        if ticket.get(f"leg{index}_player")
    )

    if leg_count != 2:
        return True

    team_1 = str(ticket.get("leg1_team_abbrev") or "").strip().upper()
    team_2 = str(ticket.get("leg2_team_abbrev") or "").strip().upper()

    if team_1 and team_2 and team_1 == team_2:
        return False

    odds = parse_float(ticket.get("parlay_decimal_odds"))
    return odds is not None and odds >= MIN_TWO_LEG_PARLAY_DECIMAL_ODDS

def spec_selectors(spec: ParlaySpec) -> list[tuple[Callable[[dict[str, Any]], bool], Callable[[dict[str, Any]], tuple[Any, ...]]]]:
    selectors = [
        (spec.leg1_predicate, spec.leg1_sort_key),
        (spec.leg2_predicate, spec.leg2_sort_key),
    ]
    if spec.leg3_predicate and spec.leg3_sort_key:
        selectors.append((spec.leg3_predicate, spec.leg3_sort_key))
    if spec.leg4_predicate and spec.leg4_sort_key:
        selectors.append((spec.leg4_predicate, spec.leg4_sort_key))
    return selectors


def all_parlay_specs() -> list[ParlaySpec]:
    return [
        *parlay_specs(),
        *three_leg_parlay_specs(),
        *four_leg_parlay_specs(),
        *movement_parlay_specs(),
        *reinforced_parlay_specs(),
    ]


def reinforced_parlay_specs() -> list[ParlaySpec]:
    return [
        ParlaySpec(
            parlay_id="reinforced_eye_2_10_gbmprog_3model_top20",
            title="Reinforced: Eye 2-10 GBM/Prog Guard + 3-Model Top20",
            filename="parlay_reinforced_eye_2_10_gbmprog_3model_top20.csv",
            description="Top-10 Eye player with GBM/progression identity paired with a 3-model top-20 proxy.",
            backtest_note="7/50 hits, +35.44u, +70.9% ROI. Strong identity/reinforcement rule.",
            leg1_label="Eye 2-10 GBM/Prog Guard",
            leg1_predicate=is_eye_2_10_gbmprog_guard,
            leg1_sort_key=lambda row: (gbmprog_best(row), num(row, "eye_rank", 999)),
            leg2_label="3-Model Top20 Proxy",
            leg2_predicate=is_three_model_top20_proxy,
            leg2_sort_key=lambda row: (num(row, "eye_rank", 999), -num(row, "book_american_odds", -999)),
        ),
        ParlaySpec(
            parlay_id="reinforced_3model_top20_gbmprog_identity_top20",
            title="Reinforced: 3-Model Top20 + GBM/Prog Identity Top20",
            filename="parlay_reinforced_3model_top20_gbmprog_identity_top20.csv",
            description="3-model top-20 proxy paired with the best GBM/progression identity top-20 bat.",
            backtest_note="7/54 hits, +34.43u, +63.8% ROI. Cleaner than pitch-only partner logic.",
            leg1_label="3-Model Top20 Proxy",
            leg1_predicate=is_three_model_top20_proxy,
            leg1_sort_key=lambda row: (num(row, "eye_rank", 999), -num(row, "book_american_odds", -999)),
            leg2_label="GBM/Prog Identity Top20",
            leg2_predicate=is_gbmprog_identity_top20,
            leg2_sort_key=lambda row: (gbmprog_best(row), num(row, "eye_rank", 999)),
        ),
        ParlaySpec(
            parlay_id="reinforced_3model_elite_top2_balanced_long",
            title="Reinforced: 3-Model Elite + Top2 Balanced Long",
            filename="parlay_reinforced_3model_elite_top2_balanced_long.csv",
            description="Best 3-model elite anchor paired with the top two balanced long partners.",
            backtest_note="10/108 hits, +86.47u, +80.1% ROI. Best broad structure.",
            leg1_label="3-Model Elite",
            leg1_predicate=is_three_model_top20_proxy,
            leg1_sort_key=lambda row: (num(row, "eye_rank", 999), -num(row, "book_american_odds", -999)),
            leg2_label="Balanced Long Partner",
            leg2_predicate=is_balanced_long_partner,
            leg2_sort_key=lambda row: (-model_top_count(row, 30), num(row, "eye_rank", 999)),
            max_tickets_per_day=2,
        ),
        ParlaySpec(
            parlay_id="reinforced_3model_elite_top2_adell_accel",
            title="Reinforced: 3-Model Elite + Top2 Adell-Type Accel",
            filename="parlay_reinforced_3model_elite_top2_adell_accel.csv",
            description="Best 3-model elite anchor paired with the top two acceleration/identity partners.",
            backtest_note="9/108 hits, +76.68u, +71.0% ROI. Captures Adley/Adell-type acceleration better.",
            leg1_label="3-Model Elite",
            leg1_predicate=is_three_model_top20_proxy,
            leg1_sort_key=lambda row: (num(row, "eye_rank", 999), -num(row, "book_american_odds", -999)),
            leg2_label="Adell-Type Accel Partner",
            leg2_predicate=is_adell_looser_accel_partner,
            leg2_sort_key=lambda row: (-num(row, "accel_score", -999), num(row, "eye_rank", 999)),
            max_tickets_per_day=2,
        ),
        ParlaySpec(
            parlay_id="reinforced_3model_elite_top3_adley_pitch12",
            title="Reinforced: 3-Model Elite + Top3 Adley-Type Pitch12",
            filename="parlay_reinforced_3model_elite_top3_adley_pitch12.csv",
            description="Best 3-model elite anchor paired with the top three pitch-top-12 long partners.",
            backtest_note="9/144 hits, +93.91u, +65.2% ROI. Uses pitch fit, but with elite anchor reinforcement.",
            leg1_label="3-Model Elite",
            leg1_predicate=is_three_model_top20_proxy,
            leg1_sort_key=lambda row: (num(row, "eye_rank", 999), -num(row, "book_american_odds", -999)),
            leg2_label="Adley-Type Pitch12 Partner",
            leg2_predicate=is_adley_pitch12_partner,
            leg2_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            max_tickets_per_day=3,
        ),
        ParlaySpec(
            parlay_id="reinforced_deep_3model_elite_top2_adley_pitch12",
            title="Reinforced: Deep 3-Model Elite + Top2 Adley-Type Pitch12",
            filename="parlay_reinforced_deep_3model_elite_top2_adley_pitch12.csv",
            description="Deep-board 3-model elite anchor paired with the top two pitch-top-12 long partners.",
            backtest_note="7/99 hits, +72.44u, +73.2% ROI. Most directly like Murakami plus quality partner.",
            leg1_label="Deep 3-Model Elite",
            leg1_predicate=is_deep_three_model_elite,
            leg1_sort_key=lambda row: (-model_top_count(row, 30), num(row, "eye_rank", 999)),
            leg2_label="Adley-Type Pitch12 Partner",
            leg2_predicate=is_adley_pitch12_partner,
            leg2_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            max_tickets_per_day=2,
        ),
        ParlaySpec(
            parlay_id="reinforced_deep_3model_elite_top3_progression_top10",
            title="Reinforced: Deep 3-Model Elite + Top3 Progression Top10 Long",
            filename="parlay_reinforced_deep_3model_elite_top3_progression_top10.csv",
            description="Deep-board 3-model elite anchor paired with the top three progression-top-10 long partners.",
            backtest_note="8/121 hits, +63.57u, +52.5% ROI. This is the Jo Adell lane.",
            leg1_label="Deep 3-Model Elite",
            leg1_predicate=is_deep_three_model_elite,
            leg1_sort_key=lambda row: (-model_top_count(row, 30), num(row, "eye_rank", 999)),
            leg2_label="Progression Top10 Long Partner",
            leg2_predicate=is_progression_top10_long_partner,
            leg2_sort_key=lambda row: (num(row, "eye_rank", 999), -num(row, "book_american_odds", -999)),
            max_tickets_per_day=3,
        ),
    ]


def parlay_specs() -> list[ParlaySpec]:
    return [
        ParlaySpec(
            parlay_id="persistent_elite_pitchfit",
            title="Persistent Elite + Pitch-Fit Longshot",
            filename="parlay_persistent_elite_pitchfit.csv",
            description="A stale-elite protected or reinforced anchor paired with the best H4 pitcher-fit longshot.",
            backtest_note="Forward-tracked stale elite V1 rule; designed to keep obvious elite repeated bats alive without flooding the card.",
            leg1_label="Persistent Elite",
            leg1_predicate=is_persistent_elite,
            leg1_sort_key=lambda row: (stale_status_order(row), num(row, "eye_rank", 999), -num(row, "book_american_odds", -999)),
            leg2_label="Best H4 Pitch Fit",
            leg2_predicate=is_h4_broad,
            leg2_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
        ),
        ParlaySpec(
            parlay_id="anchor_deep_comp_best_eye",
            title="Rank #1 + Deep Comp Best Eye",
            filename="parlay_rank1_deep_comp_best_eye.csv",
            description="Eye #1 paired with the best Eye-ranked deep-comp longshot from the lower board.",
            backtest_note="48 parlays, 5 wins, +101.57u, +211.60% ROI.",
            leg1_label="Eye #1",
            leg1_predicate=is_eye_rank_one,
            leg1_sort_key=lambda row: (num(row, "eye_rank", 999),),
            leg2_label="Deep Comp Best Eye",
            leg2_predicate=is_deep_comp_moonshot,
            leg2_sort_key=lambda row: (num(row, "eye_rank", 999), num(row, "sequence_rank", 999)),
        ),
        ParlaySpec(
            parlay_id="anchor_pitch15_best_sequence",
            title="Rank #1 + Pitch<=15 Best Sequence",
            filename="parlay_rank1_pitch15_best_sequence.csv",
            description="Eye #1 paired with the best sequence-ranked strong pitch-fit longshot.",
            backtest_note="47 parlays, 4 wins, +69.12u, +147.06% ROI.",
            leg1_label="Eye #1",
            leg1_predicate=is_eye_rank_one,
            leg1_sort_key=lambda row: (num(row, "eye_rank", 999),),
            leg2_label="Pitch<=15 Best Sequence",
            leg2_predicate=is_pitch15_sequence_longshot,
            leg2_sort_key=lambda row: (num(row, "sequence_rank", 999), num(row, "pitcher_batter_rank", 999)),
        ),
        ParlaySpec(
            parlay_id="anchor_h4_pitchfit",
            title="Rank #1 + H4 Pitch-Fit Longshot",
            filename="parlay_rank1_h4_pitchfit.csv",
            description="Eye #1 paired with the best H4 pitcher-fit longshot.",
            backtest_note="45 parlays, 3 wins, +47.69u, +105.98% ROI.",
            leg1_label="Eye #1",
            leg1_predicate=is_eye_rank_one,
            leg1_sort_key=lambda row: (num(row, "eye_rank", 999),),
            leg2_label="Best H4 Pitch Fit",
            leg2_predicate=is_h4_broad,
            leg2_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
        ),
        ParlaySpec(
            parlay_id="mid_board_pitch_11_15_16_20",
            title="Ranks 11-15 Pitch + Ranks 16-20 Pitch",
            filename="parlay_11_15_pitch_16_20_pitch.csv",
            description="Best pitcher-fit candidate in ranks 11-15 paired with best pitcher-fit candidate in ranks 16-20.",
            backtest_note="54 parlays, 5 wins, +110.87u, +205.31% ROI.",
            leg1_label="Best Pitch Fit 11-15",
            leg1_predicate=is_eye_11_15,
            leg1_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            leg2_label="Best Pitch Fit 16-20",
            leg2_predicate=is_eye_16_20,
            leg2_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
        ),
        ParlaySpec(
            parlay_id="early_pitch_2_5_21_25",
            title="Ranks 2-5 Pitch + Ranks 21-25 Pitch",
            filename="parlay_2_5_pitch_21_25_pitch.csv",
            description="Best pitcher-fit candidate in ranks 2-5 paired with best pitcher-fit candidate in ranks 21-25.",
            backtest_note="54 parlays, 4 wins, +93.50u, +173.15% ROI.",
            leg1_label="Best Pitch Fit 2-5",
            leg1_predicate=lambda row: between(num(row, "eye_rank"), 2, 5),
            leg1_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            leg2_label="Best Pitch Fit 21-25",
            leg2_predicate=is_eye_21_25,
            leg2_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
        ),
        ParlaySpec(
            parlay_id="long_odds_6_10_36_50",
            title="Ranks 6-10 Longest Odds + Ranks 36-50 Longest Odds",
            filename="parlay_6_10_longest_36_50_longest.csv",
            description="Longest odds in ranks 6-10 paired with longest odds in ranks 36-50.",
            backtest_note="54 parlays, 3 wins, +141.90u, +262.78% ROI.",
            leg1_label="Longest Odds 6-10",
            leg1_predicate=lambda row: between(num(row, "eye_rank"), 6, 10),
            leg1_sort_key=lambda row: (-num(row, "book_american_odds", -999), num(row, "pitcher_batter_rank", 999)),
            leg2_label="Longest Odds 36-50",
            leg2_predicate=lambda row: between(num(row, "eye_rank"), 36, 50),
            leg2_sort_key=lambda row: (-num(row, "book_american_odds", -999), num(row, "pitcher_batter_rank", 999)),
        ),
    ]


def three_leg_parlay_specs() -> list[ParlaySpec]:
    return [
        ParlaySpec(
            parlay_id="three_leg_anchor_deep_pitch15_sequence",
            title="Eye #1 + Deep Comp Best Eye + Pitch<=15 Best Sequence",
            filename="parlay_3leg_rank1_deep_comp_pitch15_sequence.csv",
            description="Eye #1 with a deep-comp lower-board longshot and the best sequence-ranked pitch-fit longshot.",
            backtest_note="46 tickets, 3 wins, +506.66u, +1101.40% ROI, excluding 6/17 day-one test.",
            leg1_label="Eye #1",
            leg1_predicate=is_eye_rank_one,
            leg1_sort_key=lambda row: (num(row, "eye_rank", 999),),
            leg2_label="Deep Comp Best Eye",
            leg2_predicate=is_deep_comp_moonshot,
            leg2_sort_key=lambda row: (num(row, "eye_rank", 999), num(row, "sequence_rank", 999)),
            leg3_label="Pitch<=15 Best Sequence",
            leg3_predicate=is_pitch15_sequence_longshot,
            leg3_sort_key=lambda row: (num(row, "sequence_rank", 999), num(row, "pitcher_batter_rank", 999)),
            skip_day_one_history=True,
        ),
        ParlaySpec(
            parlay_id="three_leg_11_15_16_20_sharper_eye",
            title="Ranks 11-15 Pitch + Ranks 16-20 Pitch + Sharper Best Eye",
            filename="parlay_3leg_11_15_16_20_sharper_eye.csv",
            description="Best pitch fits from ranks 11-15 and 16-20 with the best Eye-ranked sharper pitch-fit longshot.",
            backtest_note="30 tickets, 3 wins, +532.00u, +1773.33% ROI, excluding 6/17 day-one test.",
            leg1_label="Best Pitch Fit 11-15",
            leg1_predicate=is_eye_11_15,
            leg1_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            leg2_label="Best Pitch Fit 16-20",
            leg2_predicate=is_eye_16_20,
            leg2_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            leg3_label="Sharper Best Eye",
            leg3_predicate=is_sharper_pitchfit,
            leg3_sort_key=lambda row: (num(row, "eye_rank", 999), num(row, "pitcher_batter_rank", 999)),
            skip_day_one_history=True,
        ),
    ]


def four_leg_parlay_specs() -> list[ParlaySpec]:
    return [
        ParlaySpec(
            parlay_id="four_leg_11_15_eye_pitch_sharper_top25_pitch",
            title="Ranks 11-15 Eye + Ranks 11-15 Pitch + Sharper Best Eye + Top25 Pitch",
            filename="parlay_4leg_11_15_eye_pitch_sharper_top25_pitch.csv",
            description="Raw all-days leader: two 11-15 looks, the sharper Eye longshot, and the best pitch-fit top-25 longshot.",
            backtest_note="30 tickets, 4 wins, +4230.85u, +14102.83% ROI.",
            leg1_label="11-15 Best Eye",
            leg1_predicate=is_eye_11_15,
            leg1_sort_key=lambda row: (num(row, "eye_rank", 999),),
            leg2_label="11-15 Best Pitch",
            leg2_predicate=is_eye_11_15,
            leg2_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            leg3_label="Sharper Best Eye",
            leg3_predicate=is_sharper_pitchfit,
            leg3_sort_key=lambda row: (num(row, "eye_rank", 999), num(row, "pitcher_batter_rank", 999)),
            leg4_label="Top25 Best Pitch",
            leg4_predicate=is_top25_longshot,
            leg4_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
        ),
        ParlaySpec(
            parlay_id="four_leg_11_15_eye_pitch_h4long_top25_pitch",
            title="Ranks 11-15 Eye + Ranks 11-15 Pitch + H4 Longest + Top25 Pitch",
            filename="parlay_4leg_11_15_eye_pitch_h4long_top25_pitch.csv",
            description="Cleaner no-6/17 structure: two 11-15 looks, longest H4 longshot, and the best pitch-fit top-25 longshot.",
            backtest_note="50 tickets, 3 wins, +2873.80u, +5747.60% ROI, excluding 6/17 day-one test.",
            leg1_label="11-15 Best Eye",
            leg1_predicate=is_eye_11_15,
            leg1_sort_key=lambda row: (num(row, "eye_rank", 999),),
            leg2_label="11-15 Best Pitch",
            leg2_predicate=is_eye_11_15,
            leg2_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            leg3_label="H4 Longest",
            leg3_predicate=is_h4_broad,
            leg3_sort_key=lambda row: (-num(row, "book_american_odds", -999), num(row, "eye_rank", 999)),
            leg4_label="Top25 Best Pitch",
            leg4_predicate=is_top25_longshot,
            leg4_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            skip_day_one_history=True,
        ),
        ParlaySpec(
            parlay_id="four_leg_mid_pitch_ladder_sharper_eye",
            title="Ranks 11-15 Pitch + Ranks 16-20 Pitch + Ranks 21-25 Pitch + Sharper Best Eye",
            filename="parlay_4leg_mid_pitch_ladder_sharper_eye.csv",
            description="Mid-board pitch ladder with one sharper Eye longshot.",
            backtest_note="28 tickets, 2 wins, +1431.04u, +5110.86% ROI, excluding 6/17 day-one test.",
            leg1_label="Best Pitch Fit 11-15",
            leg1_predicate=is_eye_11_15,
            leg1_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            leg2_label="Best Pitch Fit 16-20",
            leg2_predicate=is_eye_16_20,
            leg2_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            leg3_label="Best Pitch Fit 21-25",
            leg3_predicate=is_eye_21_25,
            leg3_sort_key=lambda row: (num(row, "pitcher_batter_rank", 999), num(row, "eye_rank", 999)),
            leg4_label="Sharper Best Eye",
            leg4_predicate=is_sharper_pitchfit,
            leg4_sort_key=lambda row: (num(row, "eye_rank", 999), num(row, "pitcher_batter_rank", 999)),
            skip_day_one_history=True,
        ),
    ]


def movement_parlay_specs() -> list[ParlaySpec]:
    return [
        ParlaySpec(
            parlay_id="movement_progression_pitch_sequence_burst",
            title="Movement: Progression Accel + Pitch/Sequence Burst",
            filename="parlay_movement_progression_pitch_sequence_burst.csv",
            description="Best progression-rank accelerator paired with the strongest pitch-or-sequence movement burst.",
            backtest_note="54 tickets, 5 wins, +79.47u, +147.17% ROI.",
            leg1_label="Progression Accel",
            leg1_predicate=is_progression_accel,
            leg1_sort_key=progression_accel_sort_key,
            leg2_label="Pitch/Sequence Burst",
            leg2_predicate=is_pitch_or_sequence_burst,
            leg2_sort_key=pitch_or_sequence_burst_sort_key,
        ),
        ParlaySpec(
            parlay_id="movement_gbm_accel_eye_riser",
            title="Movement: GBM Accel + Eye Riser",
            filename="parlay_movement_gbm_accel_eye_riser.csv",
            description="Best GBM-rank accelerator paired with the strongest Eye-rank riser.",
            backtest_note="54 tickets, 4 wins, +59.61u, +110.39% ROI.",
            leg1_label="GBM Accel",
            leg1_predicate=is_gbm_accel,
            leg1_sort_key=gbm_accel_sort_key,
            leg2_label="Eye Riser",
            leg2_predicate=is_eye_riser,
            leg2_sort_key=eye_riser_sort_key,
        ),
        ParlaySpec(
            parlay_id="movement_best_best_sequence_accel",
            title="Movement: Best Movement + Best Movement + Sequence Accel",
            filename="parlay_movement_best_best_sequence_accel.csv",
            description="Two strongest top-25 movement-score players paired with the best sequence accelerator.",
            backtest_note="54 tickets, 3 wins, +229.91u, +425.76% ROI.",
            leg1_label="Best Movement",
            leg1_predicate=is_best_movement,
            leg1_sort_key=best_movement_sort_key,
            leg2_label="Best Movement",
            leg2_predicate=is_best_movement,
            leg2_sort_key=best_movement_sort_key,
            leg3_label="Sequence Accel",
            leg3_predicate=is_sequence_accel,
            leg3_sort_key=sequence_accel_sort_key,
        ),
    ]


def model_top_count(row: dict[str, Any], rank_cutoff: int) -> int:
    return sum(
        1
        for column in ("gbm_rank", "gbm_progression_rank", "sequence_rank", "pitcher_batter_rank")
        if num(row, column, 999) <= rank_cutoff
    )


def gbmprog_best(row: dict[str, Any]) -> float:
    return min(num(row, "gbm_rank", 999), num(row, "gbm_progression_rank", 999))


def is_eye_2_10_gbmprog_guard(row: dict[str, Any]) -> bool:
    return between(num(row, "eye_rank"), 2, 10) and gbmprog_best(row) <= 40


def is_three_model_top20_proxy(row: dict[str, Any]) -> bool:
    return model_top_count(row, 20) >= 3


def is_gbmprog_identity_top20(row: dict[str, Any]) -> bool:
    return gbmprog_best(row) <= 20


def is_balanced_long_partner(row: dict[str, Any]) -> bool:
    return model_top_count(row, 30) >= 2 and num(row, "book_american_odds") >= 350


def is_adell_looser_accel_partner(row: dict[str, Any]) -> bool:
    return (
        num(row, "eye_rank", 999) <= 40
        and num(row, "accel_score") >= 45
        and num(row, "book_american_odds") >= 350
        and gbmprog_best(row) <= 80
    )


def is_adley_pitch12_partner(row: dict[str, Any]) -> bool:
    return (
        num(row, "eye_rank", 999) <= 35
        and num(row, "pitcher_batter_rank", 999) <= 12
        and num(row, "book_american_odds") >= 400
    )


def is_deep_three_model_elite(row: dict[str, Any]) -> bool:
    return (
        num(row, "eye_rank", 999) >= 20
        and model_top_count(row, 30) >= 3
        and num(row, "book_american_odds") >= 200
    )


def is_progression_top10_long_partner(row: dict[str, Any]) -> bool:
    return (
        num(row, "eye_rank", 999) <= 30
        and num(row, "gbm_progression_rank", 999) <= 10
        and num(row, "book_american_odds") >= 300
    )


def is_eye_rank_one(row: dict[str, Any]) -> bool:
    return int(num(row, "eye_rank", 999)) == 1


def is_eye_11_15(row: dict[str, Any]) -> bool:
    return between(num(row, "eye_rank"), 11, 15)


def is_eye_16_20(row: dict[str, Any]) -> bool:
    return between(num(row, "eye_rank"), 16, 20)


def is_eye_21_25(row: dict[str, Any]) -> bool:
    return between(num(row, "eye_rank"), 21, 25)


def is_deep_comp_moonshot(row: dict[str, Any]) -> bool:
    component_best = min(
        num(row, "gbm_rank", 999),
        num(row, "gbm_progression_rank", 999),
        num(row, "sequence_rank", 999),
        num(row, "pitcher_batter_rank", 999),
    )
    return (
        between(num(row, "eye_rank"), 40, 80)
        and num(row, "book_american_odds") >= 500
        and component_best <= 30
        and num(row, "edge_percent", -999) > -10
    )


def is_pitch15_sequence_longshot(row: dict[str, Any]) -> bool:
    return (
        num(row, "pitcher_batter_rank", 999) <= 15
        and num(row, "book_american_odds") >= 450
    )


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


def is_top25_longshot(row: dict[str, Any]) -> bool:
    return between(num(row, "eye_rank"), 1, 25) and num(row, "book_american_odds") >= 450


def is_persistent_elite(row: dict[str, Any]) -> bool:
    return str(row.get("stale_signal_status") or "").strip().lower() in {
        "persistent_elite_protected",
        "persistent_elite_reinforced",
    }


def stale_status_order(row: dict[str, Any]) -> int:
    status = str(row.get("stale_signal_status") or "").strip().lower()
    if status == "persistent_elite_reinforced":
        return 0
    if status == "persistent_elite_protected":
        return 1
    return 9


MOVEMENT_LABELS = {
    "GBM Top 80": "gbm",
    "GBM Progression Top 80": "progression",
    "Sequence Top 150": "sequence",
    "Pitcher/Batter Top 80": "pitch",
}


def add_movement_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = [dict(row) for row in rows]
    add_movement_metadata(enriched)
    date_keys = {str(row.get("game_date") or "") for row in enriched if row.get("game_date")}
    single_day_mode = len(date_keys) <= 1
    if single_day_mode:
        add_summary_movement_features(enriched)
    else:
        add_day_over_day_eye_features(enriched)
    for row in enriched:
        row["_movement_single_day"] = single_day_mode
        row["_movement_score"] = movement_score(row)
    return enriched


def add_movement_metadata(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        summary = str(row.get("movement_summary") or "")
        row["_summary_accel_mentions"] = summary.count("accelerated from rank")
        row["_layers_count"] = layer_count(row.get("layers_present"))


def add_summary_movement_features(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        summary = str(row.get("movement_summary") or "")
        for label, key in MOVEMENT_LABELS.items():
            row[f"_{key}_delta"] = max(parsed_accel_deltas(summary, label) or [0.0])
            row[f"_{key}_new_rank"] = parsed_new_rank(summary, label)


def layer_count(value: Any) -> int:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return 0
    return len([part for part in text.split(",") if part.strip()])


def add_day_over_day_eye_features(rows: list[dict[str, Any]]) -> None:
    dated_rows = [row for row in rows if row.get("game_date")]
    if not dated_rows:
        return

    by_date: dict[str, dict[str, dict[str, Any]]] = {}
    for row in dated_rows:
        by_date.setdefault(str(row.get("game_date")), {})[str(row.get("player"))] = row

    rank_columns = {
        "eye": "eye_rank",
        "gbm": "gbm_rank",
        "progression": "gbm_progression_rank",
        "sequence": "sequence_rank",
        "pitch": "pitcher_batter_rank",
    }
    previous_date: str | None = None
    for date_key in sorted(by_date):
        if previous_date is None:
            previous_date = date_key
            continue
        previous_players = by_date[previous_date]
        for player, row in by_date[date_key].items():
            previous_row = previous_players.get(player)
            if previous_row:
                row["_layer_delta"] = layer_count(row.get("layers_present")) - layer_count(previous_row.get("layers_present"))
            for key, column in rank_columns.items():
                current_rank = parse_float(row.get(column))
                if current_rank is None:
                    continue
                previous_rank = parse_float(previous_row.get(column)) if previous_row else None
                if previous_rank is not None:
                    row[f"_{key}_delta"] = previous_rank - current_rank
                elif key != "eye":
                    row[f"_{key}_new_rank"] = current_rank
        previous_date = date_key


def parsed_accel_deltas(summary: str, label: str) -> list[float]:
    pattern = rf"{re.escape(label)} accelerated from rank ([0-9.]+) to ([0-9.]+)"
    deltas = []
    for old_text, new_text in re.findall(pattern, summary):
        old_rank = parse_float(old_text)
        new_rank = parse_float(new_text)
        if old_rank is not None and new_rank is not None:
            deltas.append(old_rank - new_rank)
    return deltas


def parsed_new_rank(summary: str, label: str) -> float | None:
    pattern = rf"New entrant on {re.escape(label)} at rank ([0-9.]+)"
    match = re.search(pattern, summary)
    if not match:
        return None
    return parse_float(match.group(1))


def finite_float(value: Any) -> float | None:
    parsed = parse_float(value)
    if parsed is None or parsed != parsed:
        return None
    return parsed


def movement_delta(row: dict[str, Any], key: str) -> float:
    value = finite_float(row.get(f"_{key}_delta"))
    return value if value is not None else 0.0


def movement_new_rank(row: dict[str, Any], key: str) -> float | None:
    return finite_float(row.get(f"_{key}_new_rank"))


def movement_score(row: dict[str, Any]) -> float:
    parsed_deltas = [max(0.0, movement_delta(row, key)) for key in ("gbm", "progression", "sequence", "pitch")]
    jump_total = sum(min(delta, 100.0) for delta in parsed_deltas)
    accel_count = sum(1 for delta in parsed_deltas if delta > 0)
    big_count = sum(1 for delta in parsed_deltas if delta >= 20)
    new_count = sum(1 for key in ("gbm", "progression", "sequence", "pitch") if movement_new_rank(row, key) is not None)
    eye_delta = max(0.0, finite_float(row.get("_eye_delta")) or 0.0)
    layer_delta = finite_float(row.get("_layer_delta")) or 0.0
    summary_accel_mentions = finite_float(row.get("_summary_accel_mentions")) or 0.0
    text_score = (
        eye_delta * 1.2
        + jump_total * 0.8
        + accel_count * 12
        + big_count * 10
        + layer_delta * 15
        + min(new_count, 3) * 10
        + min(summary_accel_mentions, 4) * 5
    )
    return round(text_score, 2)


def is_best_movement(row: dict[str, Any]) -> bool:
    return movement_score(row) >= 35 and num(row, "eye_rank", 999) <= 25


def best_movement_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (-movement_score(row), -movement_jump_total(row), -num(row, "book_american_odds", -999))


def movement_jump_total(row: dict[str, Any]) -> float:
    return sum(max(0.0, movement_delta(row, key)) for key in ("gbm", "progression", "sequence", "pitch"))


def is_progression_accel(row: dict[str, Any]) -> bool:
    new_rank = movement_new_rank(row, "progression")
    return movement_delta(row, "progression") >= 20 or (new_rank is not None and new_rank <= 120)


def progression_accel_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    new_rank = movement_new_rank(row, "progression")
    jump = movement_delta(row, "progression") if movement_delta(row, "progression") > 0 else (35 if new_rank is not None else 0)
    return (-jump, -movement_score(row))


def is_pitch_or_sequence_burst(row: dict[str, Any]) -> bool:
    pitch_new_rank = movement_new_rank(row, "pitch")
    return (
        movement_delta(row, "pitch") >= 25
        or movement_delta(row, "sequence") >= 40
        or (pitch_new_rank is not None and pitch_new_rank <= 20)
    )


def pitch_or_sequence_burst_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    jump = max(movement_delta(row, "pitch"), movement_delta(row, "sequence"))
    return (-jump, -movement_score(row))


def is_gbm_accel(row: dict[str, Any]) -> bool:
    new_rank = movement_new_rank(row, "gbm")
    return movement_delta(row, "gbm") >= 25 or (new_rank is not None and new_rank <= 120)


def gbm_accel_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    new_rank = movement_new_rank(row, "gbm")
    jump = movement_delta(row, "gbm") if movement_delta(row, "gbm") > 0 else (35 if new_rank is not None else 0)
    return (-jump, -movement_score(row))


def is_eye_riser(row: dict[str, Any]) -> bool:
    eye_delta = finite_float(row.get("_eye_delta"))
    if eye_delta is not None and eye_delta >= 8:
        return True
    return bool(row.get("_movement_single_day")) and (finite_float(row.get("accel_score")) or 0) >= 70 and movement_score(row) >= 35


def eye_riser_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    eye_delta = finite_float(row.get("_eye_delta")) or 0.0
    return (-eye_delta, -movement_score(row))


def is_sequence_accel(row: dict[str, Any]) -> bool:
    new_rank = movement_new_rank(row, "sequence")
    return movement_delta(row, "sequence") >= 25 or (new_rank is not None and new_rank <= 90)


def sequence_accel_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    new_rank = movement_new_rank(row, "sequence")
    jump = movement_delta(row, "sequence") if movement_delta(row, "sequence") > 0 else (35 if new_rank is not None else 0)
    return (-jump, -movement_score(row))


def parlay_row(spec: ParlaySpec, legs: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [spec.leg1_label, spec.leg2_label, spec.leg3_label or "", spec.leg4_label or ""]
    output: dict[str, Any] = {
        "parlay": spec.title,
        "parlay_note": spec.backtest_note,
        "status": "active",
    }
    for index, row in enumerate(legs, start=1):
        output[f"leg{index}_label"] = labels[index - 1]
        output.update(prefixed_leg(f"leg{index}", row))
    output.update(correlated_parlay_odds(legs))
    return output


def prefixed_leg(prefix: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        f"{prefix}_player": row.get("player", ""),
        f"{prefix}_bookmaker_used": row.get("bookmaker_used", ""),
        f"{prefix}_book_american_odds": row.get("book_american_odds", ""),
        f"{prefix}_dk_odds": row.get("dk_odds", ""),
        f"{prefix}_fan_odds": row.get("fan_odds", ""),
        f"{prefix}_365_odds": row.get("365_odds", ""),
        f"{prefix}_eye_rank": row.get("eye_rank", ""),
        f"{prefix}_eye_score": row.get("eye_score", ""),
        f"{prefix}_accel_score": row.get("accel_score", ""),
        f"{prefix}_stale_signal_status": row.get("stale_signal_status", ""),
        f"{prefix}_gbm_rank": row.get("gbm_rank", ""),
        f"{prefix}_gbm_progression_rank": row.get("gbm_progression_rank", ""),
        f"{prefix}_sequence_rank": row.get("sequence_rank", ""),
        f"{prefix}_pitcher_batter_rank": row.get("pitcher_batter_rank", ""),
        f"{prefix}_model_hr_probability_percent": row.get("model_hr_probability_percent", ""),
        f"{prefix}_edge_percent": row.get("edge_percent", ""),
        f"{prefix}_team_abbrev": row.get("team_abbrev", ""),
        f"{prefix}_opponent_abbrev": row.get("opponent_abbrev", ""),
        f"{prefix}_lineup_status": row.get("lineup_status", ""),
        f"{prefix}_batting_order": row.get("batting_order", ""),
        f"{prefix}_actual_hr": row.get("actual_hr", ""),
        f"{prefix}_result": row.get("result", ""),
        f"{prefix}_is_void": row.get("is_void", ""),
        f"{prefix}_void_reason": row.get("void_reason", ""),
    }


def ticket_has_void_leg(ticket: dict[str, Any]) -> bool:
    for index in range(1, MAX_PARLAY_LEGS + 1):
        prefix = f"leg{index}"
        if not ticket.get(f"{prefix}_player"):
            continue
        result = str(ticket.get(f"{prefix}_result") or "").strip().lower()
        is_void = str(ticket.get(f"{prefix}_is_void") or "").strip() == "1"
        if is_void or result == "void":
            return True
    return False


def parlay_profit(ticket: dict[str, Any]) -> float:
    leg_prefixes = [f"leg{index}" for index in range(1, MAX_PARLAY_LEGS + 1) if ticket.get(f"leg{index}_player")]
    if not all(int(parse_float(ticket.get(f"{prefix}_actual_hr")) or 0) > 0 for prefix in leg_prefixes):
        return -1.0
    return float(ticket.get("parlay_decimal_odds") or 0) - 1.0


def leg_result(ticket: dict[str, Any], prefix: str) -> str:
    if not ticket.get(f"{prefix}_player"):
        return ""
    if str(ticket.get(f"{prefix}_is_void") or "").strip() == "1" or str(ticket.get(f"{prefix}_result") or "").strip().lower() == "void":
        return "Void"
    return "HR" if int(parse_float(ticket.get(f"{prefix}_actual_hr")) or 0) > 0 else "No HR"


def decimal_odds(row: dict[str, Any]) -> float:
    return decimal_odds_from_american(row.get("book_american_odds")) or 0


def product(values: Any) -> float:
    total = 1.0
    for value in values:
        total *= float(value)
    return total


def has_book_odds(row: dict[str, Any]) -> bool:
    odds = finite_float(row.get("book_american_odds"))
    return odds is not None and odds != 0


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
