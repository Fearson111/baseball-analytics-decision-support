from __future__ import annotations

from .daily_hub.visibility import filter_posting_rows, posting_filter_active

from pathlib import Path

import pandas as pd
from .table_display import dataframe as display_dataframe, display_value as table_value, display_name
import streamlit as st

from .retired_signals import without_retired_signals
from .edge_buckets import (
    EDGE_BUCKET_HISTORY_COLUMNS,
    build_edge_bucket_active_rows,
    build_edge_bucket_daily_stability_rows,
    build_edge_bucket_history_rows,
    build_edge_bucket_summary_rows,
    date_key_from_text,
    edge_bucket_signals,
    edge_bucket_stat_sentence,
)
from .profit_lenses import LENS_COLUMNS, lens_specs
from .profit_parlays import PARLAY_COLUMNS, PARLAY_HISTORY_COLUMNS, build_parlay_history_rows, four_leg_parlay_specs, movement_parlay_specs, parlay_specs, reinforced_parlay_specs, three_leg_parlay_specs
from .prospective_parlays import (
    PROSPECTIVE_HISTORY_COLUMNS,
    PROSPECTIVE_TICKET_COLUMNS,
    build_prospective_history_rows,
    prospective_criteria_specs,
)
from .regression_misprice import (
    REGRESSION_MISPRICE_COLUMNS,
    REGRESSION_MISPRICE_HISTORY_COLUMNS,
    build_regression_misprice_history_from_archives,
    regression_misprice_zones,
)
from .sequence_edge import (
    SEQUENCE_EDGE_COLUMNS,
    SEQUENCE_EDGE_SUMMARY_COLUMNS,
    build_sequence_edge_frames,
    write_sequence_edge_outputs,
)


TABLE_VERSION = "model_columns_v28"


DISPLAY_COLUMNS = [
    "player",
    "sportsbook_used",
    "sportsbook_odds",
    "model_hr_probability_percent",
    "edge_percent",
    "eye_rank",
    "eye_score",
    "accel_score",
    "stale_signal_status",
    "gbm_rank",
    "gbm_progression_rank",
    "sequence_rank",
    "pitcher_batter_rank",
    "team_abbrev",
    "opponent_abbrev",
    "lineup_status",
    "batting_order",
    "movement_summary",
    "reasoning",
]


HISTORY_COLUMNS = [
    "game_date",
    "lens",
    "player",
    "result",
    "void_reason",
    "actual_hr",
    "sportsbook_used",
    "sportsbook_odds",
    "profit_1u",
    "running_profit_1u",
    "eye_rank",
    "gbm_rank",
    "pitcher_batter_rank",
    "model_hr_probability_percent",
    "edge_percent",
    "eye_score",
    "accel_score",
    "stale_signal_status",
    "team_abbrev",
    "opponent_abbrev",
    "lineup_status",
    "batting_order",
]


PARLAY_DISPLAY_COLUMNS = [
    "leg1_player",
    "leg1_sportsbook_used",
    "leg1_sportsbook_odds",
    "leg2_player",
    "leg2_sportsbook_used",
    "leg2_sportsbook_odds",
    "parlay_decimal_odds",
]


THREE_LEG_PARLAY_DISPLAY_COLUMNS = [
    "leg1_player",
    "leg1_sportsbook_used",
    "leg1_sportsbook_odds",
    "leg2_player",
    "leg2_sportsbook_used",
    "leg2_sportsbook_odds",
    "leg3_player",
    "leg3_sportsbook_used",
    "leg3_sportsbook_odds",
    "parlay_decimal_odds",
]


FOUR_LEG_PARLAY_DISPLAY_COLUMNS = [
    "leg1_player",
    "leg1_sportsbook_used",
    "leg1_sportsbook_odds",
    "leg2_player",
    "leg2_sportsbook_used",
    "leg2_sportsbook_odds",
    "leg3_player",
    "leg3_sportsbook_used",
    "leg3_sportsbook_odds",
    "leg4_player",
    "leg4_sportsbook_used",
    "leg4_sportsbook_odds",
    "parlay_decimal_odds",
]


ACTIVE_PARLAY_EXPORT_COLUMNS = [
    "parlay_test_group",
    "leg1",
    "odds",
    "leg2",
    "odds",
    "leg3",
    "odds",
    "leg4",
    "odds",
    "parlay_odds",
]


STRAIGHT_BET_EXPORT_COLUMNS = [
    "signal",
    "player",
    "sportsbook",
    "odds",
    "signal_stats",
]


STRAIGHT_LENS_SIGNAL_LABELS = {
    "Daily Capped Eye Top 1": "Pitch-Fit Longshot + Best Eye Rank",
    "Daily Capped Edge Top 2": "Pitch-Fit Longshot + 2 Best Edge Reads",
    "Daily Capped Model HR Top 2": "Pitch-Fit Longshot + 2 Best Model HR %",
    "Sharper Pitch-Fit Longshot": "Sharp Fit 500 to 800 + Matchup Rank",
    "Sharper Pitch-Fit Eye Top 1": "Sharp Fit 500 to 800 + Best Eye Rank",
}


REGRESSION_MISPRICE_DISPLAY_COLUMNS = [
    "player",
    "sportsbook_used",
    "sportsbook_odds",
    "edge_percent",
    "reg_score",
    "regression_rank",
    "eye_rank",
    "gbm_rank",
    "gbm_progression_rank",
    "sequence_rank",
    "pitcher_batter_rank",
    "model_hr_probability_percent",
    "team_abbrev",
    "opponent_abbrev",
    "lineup_status",
]


REGRESSION_MISPRICE_HISTORY_DISPLAY_COLUMNS = [
    "game_date",
    "player",
    "result",
    "sportsbook_used",
    "sportsbook_odds",
    "profit_1u",
    "running_profit_1u",
    "edge_percent",
    "reg_score",
    "regression_rank",
    "eye_rank",
    "gbm_rank",
    "gbm_progression_rank",
    "sequence_rank",
    "pitcher_batter_rank",
    "model_hr_probability_percent",
    "team_abbrev",
    "opponent_abbrev",
    "lineup_status",
]


EDGE_BUCKET_ACTIVE_DISPLAY_COLUMNS = [
    "signal",
    "player",
    "sportsbook_used",
    "sportsbook_odds",
    "edge_percent",
    "model_american_odds",
    "model_hr_probability_percent",
    "reg_score",
    "regression_rank",
]


EDGE_BUCKET_HISTORY_DISPLAY_COLUMNS = [
    "game_date",
    "signal",
    "player",
    "result",
    "sportsbook_used",
    "sportsbook_odds",
    "profit_1u",
    "running_profit_1u",
    "model_top25_rank",
    "edge_percent",
    "model_american_odds",
    "model_hr_probability_percent",
    "reg_score",
    "regression_rank",
    "team_abbrev",
    "opponent_abbrev",
]


EDGE_BUCKET_STABILITY_DISPLAY_COLUMNS = [
    "game_date",
    "signal",
    "bets",
    "hr",
    "profit_1u",
    "running_profit_1u",
    "roi_percent",
]


SEQUENCE_EDGE_ACTIVE_DISPLAY_COLUMNS = [
    "signal",
    "player",
    "sportsbook_used",
    "sportsbook_odds",
    "edge_percent",
    "model_hr_probability_percent",
    "sequence_projection_rank",
    "sequence_hr_probability",
    "sequence_long5_motif_count",
    "sequence_long5_motif_max_lift",
    "eye_rank",
    "gbm_rank",
]


SEQUENCE_EDGE_HISTORY_DISPLAY_COLUMNS = [
    "game_date",
    "player",
    "result",
    "sportsbook_used",
    "sportsbook_odds",
    "profit_1u",
    "running_profit_1u",
    "edge_percent",
    "model_hr_probability_percent",
    "sequence_projection_rank",
    "sequence_hr_probability",
    "sequence_long5_motif_count",
    "sequence_long5_motif_max_lift",
    "eye_rank",
    "gbm_rank",
]


PARLAY_HISTORY_EXPORT_COLUMNS = [
    "game_date",
    "parlay",
    "leg1_player",
    "leg2_player",
    "leg3_player",
    "leg4_player",
    "parlay_result",
    "profit_1u",
    "running_profit_1u",
    "parlay_decimal_odds",
    "independent_parlay_decimal_odds",
    "correlation_factor",
    "correlation_note",
    "leg1_result",
    "leg2_result",
    "leg3_result",
    "leg4_result",
    "leg1_bookmaker_used",
    "leg2_bookmaker_used",
    "leg3_bookmaker_used",
    "leg4_bookmaker_used",
    "leg1_book_american_odds",
    "leg2_book_american_odds",
    "leg3_book_american_odds",
    "leg4_book_american_odds",
    "leg1_sportsbook_used",
    "leg1_sportsbook_odds",
    "leg2_sportsbook_used",
    "leg2_sportsbook_odds",
    "leg3_sportsbook_used",
    "leg3_sportsbook_odds",
    "leg4_sportsbook_used",
    "leg4_sportsbook_odds",
    "leg1_eye_rank",
    "leg2_eye_rank",
    "leg3_eye_rank",
    "leg4_eye_rank",
    "leg1_gbm_rank",
    "leg2_gbm_rank",
    "leg3_gbm_rank",
    "leg4_gbm_rank",
    "leg1_pitcher_batter_rank",
    "leg2_pitcher_batter_rank",
    "leg3_pitcher_batter_rank",
    "leg4_pitcher_batter_rank",
]


PARLAY_HISTORY_DISPLAY_COLUMNS = [
    "game_date",
    "leg1_player",
    "leg2_player",
    "leg3_player",
    "leg4_player",
    "parlay_result",
    "profit_1u",
    "running_profit_1u",
    "parlay_decimal_odds",
    "independent_parlay_decimal_odds",
    "correlation_factor",
    "correlation_note",
    "leg1_result",
    "leg2_result",
    "leg3_result",
    "leg4_result",
    "leg1_sportsbook_used",
    "leg1_sportsbook_odds",
    "leg2_sportsbook_used",
    "leg2_sportsbook_odds",
    "leg3_sportsbook_used",
    "leg3_sportsbook_odds",
    "leg4_sportsbook_used",
    "leg4_sportsbook_odds",
    "leg1_eye_rank",
    "leg2_eye_rank",
    "leg3_eye_rank",
    "leg4_eye_rank",
    "leg1_gbm_rank",
    "leg2_gbm_rank",
    "leg3_gbm_rank",
    "leg4_gbm_rank",
    "leg1_pitcher_batter_rank",
    "leg2_pitcher_batter_rank",
    "leg3_pitcher_batter_rank",
    "leg4_pitcher_batter_rank",
]


PROSPECTIVE_ACTIVE_DISPLAY_COLUMNS = [
    "criteria_id",
    "criteria_title",
    "leg1_player",
    "leg1_sportsbook_used",
    "leg1_sportsbook_odds",
    "leg2_player",
    "leg2_sportsbook_used",
    "leg2_sportsbook_odds",
    "parlay_decimal_odds",
    "correlation_note",
    "naive_market_joint_probability",
    "expected_wins",
    "qualifying_count",
    "status",
]

PROSPECTIVE_HISTORY_DISPLAY_COLUMNS = [
    "slate_date",
    "criteria_id",
    "leg1_player",
    "leg2_player",
    "leg1_result",
    "leg2_result",
    "ticket_hit",
    "profit_units",
    "running_profit_units",
    "expected_wins",
    "actual_minus_expected_wins",
    "actual_to_expected_ratio",
    "parlay_decimal_odds",
    "correlation_note",
    "leg1_sportsbook_used",
    "leg1_sportsbook_odds",
    "leg2_sportsbook_used",
    "leg2_sportsbook_odds",
]

PROSPECTIVE_HISTORY_EXPORT_COLUMNS = [
    "slate_date",
    "criteria_id",
    "criteria_version",
    "criteria_title",
    "leg1_player",
    "leg2_player",
    "leg1_result",
    "leg2_result",
    "ticket_hit",
    "profit_units",
    "running_profit_units",
    "expected_wins",
    "actual_minus_expected_wins",
    "actual_to_expected_ratio",
    "parlay_decimal_odds",
    "correlation_note",
    "naive_market_joint_probability",
    "leg1_book_american_odds",
    "leg2_book_american_odds",
    "leg1_G",
    "leg1_R",
    "leg1_S",
    "leg1_M",
    "leg1_consensus",
    "leg1_disagreement",
    "leg2_G",
    "leg2_R",
    "leg2_S",
    "leg2_M",
    "leg2_consensus",
    "leg2_disagreement",
    "hypothesis",
    "candidate_filter_definition",
    "candidate_ranking_definition",
    "pairing_definition",
    "generated_timestamp",
]


def render_app(root: Path | None = None, *, embedded: bool = False, daily_folder: Path | None = None) -> None:
    project_root = root or Path(__file__).resolve().parents[1]
    if not embedded:
        st.set_page_config(page_title="Model 4 Profit Lenses", layout="wide")
        from .theme import apply_theme
        apply_theme()
    st.title("Model 4 Profit Lenses")

    daily_root = project_root / "MODEL4_DAILY_READS"
    lens_folders = discover_lens_folders(daily_root)
    if not lens_folders:
        st.info("No profit lens folders found yet. Run Model 4 once from the menu to create them.")
        return

    if daily_folder is None:
        selected = st.sidebar.selectbox(
            "Daily lens folder",
            options=[str(path.relative_to(project_root)) for path in lens_folders],
            index=0,
        )
        lens_folder = project_root / selected
    else:
        lens_folder = daily_folder / "PROFIT_LENSES"
    parlay_folder = lens_folder.parent / "PROFIT_PARLAYS"
    prospective_folder = lens_folder.parent / "PROSPECTIVE_PARLAYS"
    regression_folder = lens_folder.parent / "REGRESSION_MISPRICE"
    st.caption(str(lens_folder.parent))

    specs = lens_specs()
    nav_items = [spec.title for spec in specs] + [
        "Combined",
        "Active Parlays",
        "Reinforced",
        "Regression Misprice",
        "Model 4 Edge Buckets",
        "Sequence Edge",
        "Prospective V1",
        "History",
        "Parlay History",
        "Reinforced History",
    ]
    selected_view = render_nav_buttons(nav_items, key="main_profit_lens_nav")
    st.divider()

    spec_by_title = {spec.title: spec for spec in specs}
    if selected_view in spec_by_title:
        spec = spec_by_title[selected_view]
        render_csv_editor(lens_folder / spec.filename, spec.title, spec.description, spec.backtest_note)
    elif selected_view == "Combined":
        render_csv_editor(
            lens_folder / "profit_lenses_combined.csv",
            "Combined Profit Lenses",
            "Deduped working sheet across the daily-capped and sharper pitch-fit lenses.",
            "",
        )
    elif selected_view == "Active Parlays":
        render_active_parlays(parlay_folder)
    elif selected_view == "Reinforced":
        render_reinforced_active(parlay_folder)
    elif selected_view == "Regression Misprice":
        render_regression_misprice_viewer(project_root, regression_folder)
    elif selected_view == "Model 4 Edge Buckets":
        render_edge_bucket_viewer(lens_folder.parent)
    elif selected_view == "Sequence Edge":
        render_sequence_edge_viewer(project_root, lens_folder.parent)
    elif selected_view == "Prospective V1":
        render_prospective_viewer(project_root, prospective_folder)
    elif selected_view == "History":
        render_history_viewer(project_root)
    elif selected_view == "Parlay History":
        render_parlay_history_viewer(project_root)
    elif selected_view == "Reinforced History":
        render_reinforced_history_viewer(project_root)

    if selected_view in straight_bet_download_views(specs):
        st.divider()
        render_straight_bets_download(project_root, lens_folder, regression_folder, lens_folder.parent)


def straight_bet_download_views(specs: list[object]) -> set[str]:
    return {spec.title for spec in specs} | {
        "Combined",
        "Regression Misprice",
        "Model 4 Edge Buckets",
        "Sequence Edge",
    }


def render_nav_buttons(options: list[str], *, key: str, columns_per_row: int = 4) -> str:
    if not options:
        return ""
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]

    selected = st.session_state[key]
    with st.container(key=f"{key}_container"):
        for start in range(0, len(options), columns_per_row):
            row_options = options[start:start + columns_per_row]
            columns = st.columns(columns_per_row)
            for offset, label in enumerate(row_options):
                columns[offset].button(
                    label,
                    key=f"{key}_{TABLE_VERSION}_{start + offset}",
                    type="primary" if selected == label else "secondary",
                    use_container_width=True,
                    on_click=select_nav_view,
                    args=(key, label),
                )
    st.caption(f"Viewing: {selected}")
    return selected


def select_nav_view(key: str, label: str) -> None:
    st.session_state[key] = label


def discover_lens_folders(daily_root: Path) -> list[Path]:
    if not daily_root.exists():
        return []
    folders = [
        path
        for path in daily_root.glob("*/PROFIT_LENSES")
        if path.is_dir()
    ]
    return sorted(folders, key=lambda path: path.parent.name, reverse=True)


def render_csv_editor(path: Path, title: str, description: str, note: str) -> None:
    st.subheader(title)
    if description:
        st.write(description)
    if note:
        st.caption(note)

    if not path.exists():
        st.warning(f"Missing CSV: {path.name}")
        return

    original = filter_posting_rows(pd.read_csv(path).fillna(""))
    for column in LENS_COLUMNS:
        if column not in original.columns:
            original[column] = ""
    for column in DISPLAY_COLUMNS:
        if column not in original.columns:
            original[column] = ""

    original = add_sportsbook_display_columns(original)
    visible_columns = [column for column in DISPLAY_COLUMNS if column in original.columns]
    frame = format_display_frame(original[visible_columns].copy())

    if posting_filter_active():
        display_dataframe(frame, width="stretch", hide_index=True, column_config=column_config())
        st.download_button("Download Posting CSV", original.to_csv(index=False).encode("utf-8-sig"),
                           path.name, "text/csv", key=f"posting_view_{path.name}")
        return

    edited = st.data_editor(
        frame,
        width="stretch",
        num_rows="dynamic",
        hide_index=True,
        column_config=column_config(),
        key=f"editor_{TABLE_VERSION}_{path.name}",
    )

    if st.button("Save CSV", key=f"save_{TABLE_VERSION}_{path.name}", type="primary"):
        save_frame = merge_visible_editor_changes(original, edited)
        save_columns = [column for column in LENS_COLUMNS if column in save_frame.columns]
        save_frame[save_columns].to_csv(path, index=False)
        st.success(f"Saved {path.name}")


def column_config() -> dict[str, object]:
    return {
        "player": st.column_config.TextColumn("Player", width="medium"),
        "sportsbook_used": st.column_config.TextColumn("Sportsbook"),
        "sportsbook_odds": st.column_config.TextColumn("Sportsbook Odds"),
        "book_american_odds": st.column_config.TextColumn("Book Odds"),
        "model_hr_probability_percent": st.column_config.TextColumn("Model HR%"),
        "edge_percent": st.column_config.TextColumn("Edge%"),
        "eye_rank": st.column_config.TextColumn("Eye Rank"),
        "eye_score": st.column_config.TextColumn("Eye Score"),
        "accel_score": st.column_config.TextColumn("Accel"),
        "stale_signal_status": st.column_config.TextColumn("Stale Signal", width="medium"),
        "gbm_rank": st.column_config.TextColumn("GBM"),
        "gbm_progression_rank": st.column_config.TextColumn("Progression"),
        "sequence_rank": st.column_config.TextColumn("Sequence"),
        "pitcher_batter_rank": st.column_config.TextColumn("Pitch Fit"),
        "team_abbrev": st.column_config.TextColumn("Team"),
        "opponent_abbrev": st.column_config.TextColumn("Opp"),
        "lineup_status": st.column_config.TextColumn("Lineup"),
        "batting_order": st.column_config.TextColumn("Bat Order"),
        "movement_summary": st.column_config.TextColumn("Movement", width="large"),
        "reasoning": st.column_config.TextColumn("Reasoning", width="large"),
    }


def render_straight_bets_download(project_root: Path, lens_folder: Path, regression_folder: Path, daily_folder: Path) -> None:
    export = build_active_straight_bets_export_frame(project_root, lens_folder, regression_folder, daily_folder)
    if export.empty:
        st.info("No active straight-bet rows available to download.")
        return
    run_date = daily_folder.name if daily_folder else "today"
    st.download_button(
        "Download All Straight Bets CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name=f"model4_all_active_straight_bets_{safe_filename(run_date)}.csv",
        mime="text/csv",
        key=f"all_active_straight_bets_export_{TABLE_VERSION}_{safe_filename(run_date)}",
    )


def build_active_straight_bets_export_frame(
    project_root: Path,
    lens_folder: Path,
    regression_folder: Path,
    daily_folder: Path,
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    rows.extend(active_profit_lens_export_rows(project_root, lens_folder))
    rows.extend(active_regression_misprice_export_rows(project_root, regression_folder))
    rows.extend(active_edge_bucket_export_rows(daily_folder))
    rows.extend(active_sequence_edge_export_rows(project_root, daily_folder))
    return pd.DataFrame(rows, columns=STRAIGHT_BET_EXPORT_COLUMNS)


def active_profit_lens_export_rows(project_root: Path, lens_folder: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    history = build_history_frame(project_root)
    stats_by_lens = stats_by_group(history, "lens") if not history.empty else {}
    for spec in lens_specs():
        path = lens_folder / spec.filename
        if not path.exists():
            continue
        frame = filter_posting_rows(pd.read_csv(path).fillna(""))
        label = STRAIGHT_LENS_SIGNAL_LABELS.get(spec.title, spec.title)
        stats = stats_by_lens.get(spec.title) or clean_stat_note(spec.backtest_note)
        rows.extend(straight_export_rows_from_frame(frame, label, stats))
    return rows


def active_regression_misprice_export_rows(project_root: Path, regression_folder: Path) -> list[dict[str, str]]:
    path = regression_folder / "regression_misprice_combined.csv"
    if not path.exists():
        return []
    active = filter_posting_rows(pd.read_csv(path).fillna(""))
    if active.empty:
        return []
    history = build_regression_misprice_history_frame(project_root)
    stats_by_signal = stats_by_group(history, "zone") if not history.empty else {}
    rows: list[dict[str, str]] = []
    for _, row in active.iterrows():
        signal = clean_export_text(row.get("zone", ""))
        stats = stats_by_signal.get(signal) or clean_stat_note(row.get("zone_note", ""))
        rows.append(straight_export_row(signal, row.get("player", ""), row, stats))
    return rows


def active_edge_bucket_export_rows(daily_folder: Path) -> list[dict[str, str]]:
    game_date = date_key_from_text(daily_folder.name) or ""
    if not game_date:
        return []
    active = pd.read_csv(daily_folder / "edge_active.csv").fillna("") if (daily_folder / "edge_active.csv").exists() else pd.DataFrame(build_edge_bucket_active_rows(game_date))
    active = without_retired_signals(active)
    active = filter_posting_rows(active)
    if active.empty:
        return []
    history = pd.DataFrame(build_edge_bucket_history_rows())
    stats_by_signal = stats_by_group(history, "signal") if not history.empty else {}
    rows: list[dict[str, str]] = []
    for _, row in active.iterrows():
        signal = clean_export_text(row.get("signal", ""))
        stats = stats_by_signal.get(signal) or clean_stat_note(row.get("signal_note", ""))
        rows.append(straight_export_row(signal, row.get("player", ""), row, stats))
    return rows


def active_sequence_edge_export_rows(project_root: Path, daily_folder: Path) -> list[dict[str, str]]:
    active, history, summary = build_sequence_edge_frames(project_root, daily_folder)
    active = filter_posting_rows(active)
    if active.empty:
        return []
    history_stats = stats_by_group(history, "signal") if not history.empty else {}
    summary_stats = stats_from_summary(summary) if not summary.empty else {}
    rows: list[dict[str, str]] = []
    for _, row in active.iterrows():
        signal = clean_export_text(row.get("signal", ""))
        stats = history_stats.get(signal) or summary_stats.get(signal) or clean_stat_note(row.get("signal_note", ""))
        rows.append(straight_export_row(signal, row.get("player", ""), row, stats))
    return rows


def straight_export_rows_from_frame(frame: pd.DataFrame, signal: str, stats: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for _, row in frame.iterrows():
        rows.append(straight_export_row(signal, row.get("player", ""), row, stats))
    return rows


def straight_export_row(signal: object, player: object, odds_source: object, stats: object) -> dict[str, str]:
    sportsbook = ""
    odds = odds_source
    if isinstance(odds_source, (pd.Series, dict)):
        sportsbook = sportsbook_display_label(odds_source)
        odds = selected_sportsbook_odds(odds_source)
    return {
        "signal": clean_export_text(signal),
        "player": clean_export_text(player),
        "sportsbook": clean_export_text(sportsbook),
        "odds": clean_value(odds),
        "signal_stats": clean_stat_note(stats),
    }


def is_void_record(row: dict[str, object] | pd.Series) -> bool:
    return str(row.get("is_void") or "").strip() == "1" or str(row.get("result") or "").strip().lower() == "void"


def nonvoid_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.get("result", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip().str.lower()
    is_void = frame.get("is_void", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip().eq("1")
    return frame[~(result.eq("void") | is_void)].copy()

def stats_by_group(history: pd.DataFrame, group_column: str) -> dict[str, str]:
    if history.empty or group_column not in history.columns:
        return {}
    output: dict[str, str] = {}
    for signal, frame in history.groupby(group_column, sort=False):
        graded = nonvoid_frame(frame)
        bets = len(graded)
        hrs = history_hr_count(graded)
        profit = pd.to_numeric(graded.get("profit_1u", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
        output[clean_export_text(signal)] = straight_stat_sentence(bets, hrs, float(profit))
    return output


def stats_from_summary(summary: pd.DataFrame) -> dict[str, str]:
    output: dict[str, str] = {}
    if summary.empty or "signal" not in summary.columns:
        return output
    for _, row in summary.iterrows():
        signal = clean_export_text(row.get("signal", ""))
        bets = int(float(row.get("n") or 0))
        hrs = int(float(row.get("hr") or 0))
        profit = float(row.get("profit_1u") or 0)
        output[signal] = straight_stat_sentence(bets, hrs, profit)
    return output


def history_hr_count(frame: pd.DataFrame) -> int:
    if "result" in frame.columns:
        result_hr = frame["result"].astype(str).str.strip().eq("HR")
    else:
        result_hr = pd.Series(False, index=frame.index)
    actual_hr = pd.to_numeric(frame.get("actual_hr", pd.Series(0, index=frame.index)), errors="coerce").fillna(0).gt(0)
    return int((result_hr | actual_hr).sum())


def straight_stat_sentence(bets: int, hrs: int, profit: float) -> str:
    roi = (profit / bets * 100) if bets else 0.0
    return f"{bets} bets, {hrs} HR, {profit:+.2f}u, {roi:+.2f}% ROI"


def clean_stat_note(value: object) -> str:
    text = clean_export_text(value)
    return text[:-1] if text.endswith(".") else text


def render_active_parlays(parlay_folder: Path) -> None:
    st.subheader("Active 2-Leg Parlays")
    st.write("Current-day parlay rules from the historical Model 4 study.")
    if not parlay_folder.exists():
        st.info("No parlay folder for this date yet. Run Model 4 again to create active parlay CSVs.")
        return

    combined_path = parlay_folder / "profit_parlays_combined.csv"
    render_parlay_table(combined_path, "Combined Active 2-Leg Parlays", PARLAY_DISPLAY_COLUMNS)

    for spec in parlay_specs():
        with st.expander(spec.title, expanded=False):
            st.caption(spec.backtest_note)
            render_stacked_parlay(parlay_folder / spec.filename)

    st.subheader("Active 3-Leg Parlays")
    three_leg_combined = parlay_folder / "profit_parlays_3leg_combined.csv"
    render_parlay_table(three_leg_combined, "Combined Active 3-Leg Parlays", THREE_LEG_PARLAY_DISPLAY_COLUMNS)

    for spec in three_leg_parlay_specs():
        with st.expander(spec.title, expanded=False):
            st.caption(spec.backtest_note)
            render_stacked_parlay(parlay_folder / spec.filename)

    st.subheader("Active 4-Leg Parlays")
    four_leg_combined = parlay_folder / "profit_parlays_4leg_combined.csv"
    render_parlay_table(four_leg_combined, "Combined Active 4-Leg Parlays", FOUR_LEG_PARLAY_DISPLAY_COLUMNS)

    for spec in four_leg_parlay_specs():
        with st.expander(spec.title, expanded=False):
            st.caption(spec.backtest_note)
            render_stacked_parlay(parlay_folder / spec.filename)

    st.subheader("Active Movement Parlays")
    movement_combined = parlay_folder / "profit_parlays_movement_combined.csv"
    render_parlay_table(movement_combined, "Combined Active Movement Parlays", THREE_LEG_PARLAY_DISPLAY_COLUMNS)

    for spec in movement_parlay_specs():
        with st.expander(spec.title, expanded=False):
            st.caption(spec.backtest_note)
            render_stacked_parlay(parlay_folder / spec.filename)

    st.subheader("Active Reinforced Parlays")
    render_reinforced_active(parlay_folder, include_header=False)

    st.divider()
    render_active_parlay_download(parlay_folder)


def render_active_parlay_download(parlay_folder: Path) -> None:
    export = build_active_parlay_export_frame(parlay_folder)
    if export.empty:
        st.info("No active parlay rows available to download.")
        return
    run_date = parlay_folder.parent.name if parlay_folder.parent else "today"
    st.download_button(
        "Download All Parlays CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name=f"model4_all_active_parlays_{safe_filename(run_date)}.csv",
        mime="text/csv",
        key=f"all_active_parlays_export_{TABLE_VERSION}_{safe_filename(run_date)}",
    )


def build_active_parlay_export_frame(parlay_folder: Path) -> pd.DataFrame:
    regular_two_leg_keys = active_parlay_ticket_keys(parlay_folder / "profit_parlays_combined.csv")
    sources = [
        ("active_4leg", parlay_folder / "profit_parlays_4leg_combined.csv", None),
        ("active_3leg", parlay_folder / "profit_parlays_3leg_combined.csv", None),
        ("active_movement", parlay_folder / "profit_parlays_movement_combined.csv", "leg_count_desc"),
        ("active_2leg", parlay_folder / "profit_parlays_combined.csv", None),
        ("active_reinforced", parlay_folder / "profit_parlays_reinforced_combined.csv", "unique_reinforced"),
    ]

    rows: list[list[str]] = []
    for group_name, path, mode in sources:
        if mode == "unique_reinforced":
            frame = filtered_active_parlay_frame(path, exclude_ticket_keys=regular_two_leg_keys, unique_by_ticket=True)
        else:
            frame = filtered_active_parlay_frame(path)
        if frame.empty:
            continue
        if mode == "leg_count_desc":
            frame = frame.copy()
            frame["_leg_count"] = frame.apply(active_parlay_leg_count, axis=1)
            frame["_source_order"] = range(len(frame))
            frame = frame.sort_values(["_leg_count", "_source_order"], ascending=[False, True]).drop(columns=["_leg_count", "_source_order"])
        for _, row in frame.iterrows():
            rows.append(compact_active_parlay_export_row(group_name, row))
    return pd.DataFrame(rows, columns=ACTIVE_PARLAY_EXPORT_COLUMNS)


def compact_active_parlay_export_row(group_name: str, row: pd.Series) -> list[str]:
    output: list[str] = [group_name]
    for index in range(1, 5):
        output.append(clean_export_text(row.get(f"leg{index}_player", "")))
        output.append(clean_value(row.get(f"leg{index}_book_american_odds", "")))
    output.append(parlay_decimal_to_export_american(row.get("parlay_decimal_odds", "")))
    return output


def active_parlay_leg_count(row: pd.Series) -> int:
    return sum(1 for index in range(1, 5) if clean_export_text(row.get(f"leg{index}_player", "")))


def clean_export_text(value: object) -> str:
    text = display_name(str(value or "").strip())
    if text.lower() in {"nan", "none"}:
        return ""
    return text


def parlay_decimal_to_export_american(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return ""
    try:
        decimal = float(text.replace("x", "").replace("+", ""))
    except ValueError:
        return text
    if decimal != decimal:
        return ""
    return f"+{int(round(round(decimal, 1) * 100))}"


def render_reinforced_active(parlay_folder: Path, *, include_header: bool = True) -> None:
    if include_header:
        st.subheader("Reinforced Active Parlays")
    if not parlay_folder.exists():
        st.info("No reinforced parlay folder for this date yet. Run Model 4 again to create active reinforced CSVs.")
        return

    regular_two_leg_keys = active_parlay_ticket_keys(parlay_folder / "profit_parlays_combined.csv")
    if regular_two_leg_keys:
        st.caption("Exact tickets already shown in Active 2-Leg Parlays are hidden here. Saved CSVs and history still keep every research row.")

    combined_path = parlay_folder / "profit_parlays_reinforced_combined.csv"
    render_parlay_table(
        combined_path,
        "Unique Active Reinforced Parlays",
        PARLAY_DISPLAY_COLUMNS,
        exclude_ticket_keys=regular_two_leg_keys,
        unique_by_ticket=True,
        empty_message="No unique reinforced tickets after hiding overlap with Active 2-Leg Parlays.",
    )

    detail_seen_keys = set(regular_two_leg_keys)
    for spec in reinforced_parlay_specs():
        path = parlay_folder / spec.filename
        preview = filtered_active_parlay_frame(path, exclude_ticket_keys=detail_seen_keys, unique_by_ticket=True)
        if preview.empty:
            continue
        with st.expander(spec.title, expanded=False):
            st.caption(spec.backtest_note)
            render_stacked_parlay(path, exclude_ticket_keys=detail_seen_keys, seen_ticket_keys=detail_seen_keys)


def render_parlay_table(
    path: Path,
    title: str,
    display_columns: list[str],
    *,
    exclude_ticket_keys: set[tuple[str, ...]] | None = None,
    unique_by_ticket: bool = False,
    empty_message: str = "No active ticket for this rule today.",
) -> set[tuple[str, ...]]:
    st.markdown(f"**{title}**")
    frame = filtered_active_parlay_frame(path, exclude_ticket_keys=exclude_ticket_keys, unique_by_ticket=unique_by_ticket)
    if frame.empty:
        if not path.exists():
            st.warning(f"Missing CSV: {path.name}")
        else:
            st.info(empty_message)
        return set()
    for column in display_columns:
        if column not in frame.columns:
            frame[column] = ""
    frame = add_sportsbook_display_columns(frame, leg_prefixes=("leg1", "leg2", "leg3", "leg4"))
    display = format_display_frame(
        frame[[column for column in display_columns if column in frame.columns]].copy(),
        parlay_odds_columns={"parlay_decimal_odds", "independent_parlay_decimal_odds"},
    )
    display_dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config=parlay_column_config(),
    )
    return {key for _, row in frame.iterrows() if (key := parlay_ticket_key(row))}


def render_stacked_parlay(
    path: Path,
    *,
    exclude_ticket_keys: set[tuple[str, ...]] | None = None,
    seen_ticket_keys: set[tuple[str, ...]] | None = None,
) -> set[tuple[str, ...]]:
    frame = filtered_active_parlay_frame(
        path,
        exclude_ticket_keys=exclude_ticket_keys,
        seen_ticket_keys=seen_ticket_keys,
        unique_by_ticket=seen_ticket_keys is not None,
    )
    if frame.empty:
        if not path.exists():
            st.warning(f"Missing CSV: {path.name}")
        else:
            st.info("No unique active ticket for this rule today after overlap cleanup.")
        return set()

    displayed_keys: set[tuple[str, ...]] = set()
    for display_index, (_, row_series) in enumerate(frame.iterrows(), start=1):
        row = row_series.to_dict()
        key = parlay_ticket_key(row)
        if key:
            displayed_keys.add(key)
        if len(frame) > 1:
            st.markdown(f"**Ticket {display_index}**")
        st.metric("Parlay Odds", clean_value(row.get("parlay_decimal_odds", ""), parlay_odds=True))
        note = clean_value(row.get("correlation_note", ""))
        if note and note != "No same-game correlation adjustment":
            st.caption(note)
        render_leg_block("Leg 1", row, "leg1")
        render_leg_block("Leg 2", row, "leg2")
        if str(row.get("leg3_player", "")).strip():
            render_leg_block("Leg 3", row, "leg3")
        if str(row.get("leg4_player", "")).strip():
            render_leg_block("Leg 4", row, "leg4")
    return displayed_keys


def read_active_parlay_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=PARLAY_COLUMNS)
    frame = filter_posting_rows(pd.read_csv(path).fillna(""))
    for column in PARLAY_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame


def parlay_ticket_key(row: dict[str, object] | pd.Series) -> tuple[str, ...]:
    players: list[str] = []
    for index in range(1, 5):
        player = str(row.get(f"leg{index}_player", "") or "").strip().lower()
        if player and player not in {"nan", "none"}:
            players.append(player)
    if len(players) < 2:
        return ()
    return tuple(sorted(players))


def active_parlay_ticket_keys(path: Path) -> set[tuple[str, ...]]:
    frame = read_active_parlay_frame(path)
    return {key for _, row in frame.iterrows() if (key := parlay_ticket_key(row))}


def filtered_active_parlay_frame(
    path: Path,
    *,
    exclude_ticket_keys: set[tuple[str, ...]] | None = None,
    seen_ticket_keys: set[tuple[str, ...]] | None = None,
    unique_by_ticket: bool = False,
) -> pd.DataFrame:
    frame = read_active_parlay_frame(path)
    if frame.empty:
        return frame
    excluded = exclude_ticket_keys or set()
    seen = seen_ticket_keys if seen_ticket_keys is not None else set()
    kept_rows: list[pd.Series] = []
    for _, row in frame.iterrows():
        key = parlay_ticket_key(row)
        if key and key in excluded:
            continue
        if unique_by_ticket and key and key in seen:
            continue
        kept_rows.append(row)
        if unique_by_ticket and key:
            seen.add(key)
    if not kept_rows:
        return frame.iloc[0:0].copy()
    return pd.DataFrame(kept_rows, columns=frame.columns).reset_index(drop=True)


def render_leg_block(title: str, row: dict[str, object], prefix: str) -> None:
    fields = {
        "Player": row.get(f"{prefix}_player", ""),
        "Sportsbook": sportsbook_display_label(row, prefix=prefix),
        "Sportsbook Odds": selected_sportsbook_odds(row, prefix=prefix),
        "Eye Rank": row.get(f"{prefix}_eye_rank", ""),
        "Eye Score": row.get(f"{prefix}_eye_score", ""),
        "Accel": row.get(f"{prefix}_accel_score", ""),
        "Stale Signal": row.get(f"{prefix}_stale_signal_status", ""),
        "GBM": row.get(f"{prefix}_gbm_rank", ""),
        "Progression": row.get(f"{prefix}_gbm_progression_rank", ""),
        "Sequence": row.get(f"{prefix}_sequence_rank", ""),
        "Pitch Fit": row.get(f"{prefix}_pitcher_batter_rank", ""),
        "Model HR%": row.get(f"{prefix}_model_hr_probability_percent", ""),
        "Edge%": row.get(f"{prefix}_edge_percent", ""),
        "Team": row.get(f"{prefix}_team_abbrev", ""),
        "Opp": row.get(f"{prefix}_opponent_abbrev", ""),
        "Lineup": row.get(f"{prefix}_lineup_status", ""),
        "Bat Order": row.get(f"{prefix}_batting_order", ""),
    }
    visible_name = clean_value(fields["Player"])
    st.markdown(f"**{title}: {visible_name}**")

    details = {key: value for key, value in fields.items() if key != "Player"}
    display = pd.DataFrame(
        [{"Field": key, "Value": clean_value(value)} for key, value in details.items()]
    )
    with st.expander(f"{title} details", expanded=False):
        display_dataframe(display, width="stretch", hide_index=True)


def merge_visible_editor_changes(original: pd.DataFrame, edited: pd.DataFrame) -> pd.DataFrame:
    save_frame = original.copy()
    for column in edited.columns:
        if column in {"sportsbook_used", "sportsbook_odds"}:
            continue
        if column in save_frame.columns:
            values = edited[column].copy()
            if "player" in column.lower():
                for index in values.index.intersection(original.index):
                    if values.loc[index] == table_value(original.loc[index, column], column):
                        values.loc[index] = original.loc[index, column]
            save_frame[column] = values
    if "sportsbook_used" in edited.columns and "bookmaker_used" in save_frame.columns:
        save_frame["bookmaker_used"] = edited["sportsbook_used"]
    if "sportsbook_odds" in edited.columns and "book_american_odds" in save_frame.columns:
        save_frame["book_american_odds"] = edited["sportsbook_odds"]
    return save_frame


SPORTSBOOK_ODDS_COLUMNS = {
    "dk": "dk_odds",
    "fan": "fan_odds",
    "365": "365_odds",
}


def add_sportsbook_display_columns(frame: pd.DataFrame, *, leg_prefixes: tuple[str, ...] = ()) -> pd.DataFrame:
    output = frame.copy()
    if leg_prefixes:
        for prefix in leg_prefixes:
            set_display_column(output, f"{prefix}_sportsbook_used", lambda row, prefix=prefix: sportsbook_display_label(row, prefix=prefix))
            set_display_column(output, f"{prefix}_sportsbook_odds", lambda row, prefix=prefix: selected_sportsbook_odds(row, prefix=prefix))
        return output

    set_display_column(output, "sportsbook_used", sportsbook_display_label)
    set_display_column(output, "sportsbook_odds", selected_sportsbook_odds)
    return output


def set_display_column(output: pd.DataFrame, column: str, getter: object) -> None:
    if output.empty:
        output[column] = pd.Series([], index=output.index, dtype="object")
        return
    output[column] = output.apply(getter, axis=1).astype("object")


def sportsbook_display_label(row: pd.Series | dict[str, object], *, prefix: str = "") -> str:
    raw = row.get(prefixed_column(prefix, "bookmaker_used"), "") or row.get(prefixed_column(prefix, "sportsbook_used"), "")
    code = sportsbook_code(raw)
    if code == "dk":
        return "DK"
    if code == "fan":
        return "Fan"
    if code == "365":
        return "365"
    return clean_export_text(raw)


def selected_sportsbook_odds(row: pd.Series | dict[str, object], *, prefix: str = "") -> object:
    raw_book = row.get(prefixed_column(prefix, "bookmaker_used"), "") or row.get(prefixed_column(prefix, "sportsbook_used"), "")
    code = sportsbook_code(raw_book)
    if code:
        odds_column = prefixed_column(prefix, SPORTSBOOK_ODDS_COLUMNS[code])
        odds = row.get(odds_column, "")
        if clean_export_text(odds):
            return odds
    return row.get(prefixed_column(prefix, "book_american_odds"), "")


def prefixed_column(prefix: str, column: str) -> str:
    return f"{prefix}_{column}" if prefix else column


def sportsbook_code(value: object) -> str:
    text = clean_export_text(value).lower().replace(" ", "").replace("_", "").replace("-", "")
    if not text:
        return ""
    if "draftkings" in text or text == "dk" or text.startswith("dk"):
        return "dk"
    if "fanatics" in text or text == "fan" or text.startswith("fan"):
        return "fan"
    if "bet365" in text or "365" in text:
        return "365"
    return ""


def format_display_frame(frame: pd.DataFrame, parlay_odds_columns: set[str] | None = None) -> pd.DataFrame:
    parlay_odds_columns = parlay_odds_columns or set()
    output = frame.copy()
    for column in output.columns:
        output[column] = output[column].map(
            lambda value, column=column: clean_value(value, parlay_odds=True) if column in parlay_odds_columns else table_value(value, column)
        ).astype("object")
    return output


def clean_value(value: object, *, parlay_odds: bool = False) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none"}:
        return ""
    try:
        number = float(text.replace("+", ""))
    except ValueError:
        return text
    if number != number:
        return ""
    if parlay_odds:
        return f"{number:.1f}x"
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}"


def parlay_column_config() -> dict[str, object]:
    return {
        "parlay": st.column_config.TextColumn("Parlay", width="large"),
        "status": st.column_config.TextColumn("Status"),
        "leg1_player": st.column_config.TextColumn("Leg 1", width="medium"),
        "leg1_sportsbook_used": st.column_config.TextColumn("L1 Book"),
        "leg1_sportsbook_odds": st.column_config.TextColumn("L1 Sportsbook Odds"),
        "leg1_book_american_odds": st.column_config.TextColumn("L1 Odds"),
        "leg1_eye_rank": st.column_config.TextColumn("L1 Eye"),
        "leg1_gbm_rank": st.column_config.TextColumn("L1 GBM"),
        "leg1_pitcher_batter_rank": st.column_config.TextColumn("L1 Pitch"),
        "leg2_player": st.column_config.TextColumn("Leg 2", width="medium"),
        "leg2_sportsbook_used": st.column_config.TextColumn("L2 Book"),
        "leg2_sportsbook_odds": st.column_config.TextColumn("L2 Sportsbook Odds"),
        "leg2_book_american_odds": st.column_config.TextColumn("L2 Odds"),
        "leg2_eye_rank": st.column_config.TextColumn("L2 Eye"),
        "leg2_gbm_rank": st.column_config.TextColumn("L2 GBM"),
        "leg2_pitcher_batter_rank": st.column_config.TextColumn("L2 Pitch"),
        "leg3_player": st.column_config.TextColumn("Leg 3", width="medium"),
        "leg3_sportsbook_used": st.column_config.TextColumn("L3 Book"),
        "leg3_sportsbook_odds": st.column_config.TextColumn("L3 Sportsbook Odds"),
        "leg3_book_american_odds": st.column_config.TextColumn("L3 Odds"),
        "leg3_eye_rank": st.column_config.TextColumn("L3 Eye"),
        "leg3_gbm_rank": st.column_config.TextColumn("L3 GBM"),
        "leg3_pitcher_batter_rank": st.column_config.TextColumn("L3 Pitch"),
        "leg4_player": st.column_config.TextColumn("Leg 4", width="medium"),
        "leg4_sportsbook_used": st.column_config.TextColumn("L4 Book"),
        "leg4_sportsbook_odds": st.column_config.TextColumn("L4 Sportsbook Odds"),
        "leg4_book_american_odds": st.column_config.TextColumn("L4 Odds"),
        "leg4_eye_rank": st.column_config.TextColumn("L4 Eye"),
        "leg4_gbm_rank": st.column_config.TextColumn("L4 GBM"),
        "leg4_pitcher_batter_rank": st.column_config.TextColumn("L4 Pitch"),
        "parlay_decimal_odds": st.column_config.TextColumn("Parlay Odds"),
        "independent_parlay_decimal_odds": st.column_config.TextColumn("Raw Independent"),
        "correlation_factor": st.column_config.TextColumn("Correlation"),
        "correlation_note": st.column_config.TextColumn("Correlation Note", width="large"),
        "parlay_note": st.column_config.TextColumn("Backtest", width="large"),
    }


def render_history_viewer(project_root: Path) -> None:
    st.subheader("Profit Lens History")
    history = build_history_frame(project_root)
    if history.empty:
        st.info("No graded profit lens history found yet. Run the rank tracker after completed results are available.")
        return

    lens_options = ["All"] + sorted(history["lens"].dropna().unique().tolist())
    selected_lens = st.selectbox("Lens", lens_options, key="history_lens_select")
    view = history.copy()
    if selected_lens != "All":
        view = view[view["lens"].eq(selected_lens)].copy()

    render_running_profit_chart(view, selected_lens)

    graded_view = nonvoid_frame(view)
    total_bets = len(graded_view)
    total_hr = int(pd.to_numeric(graded_view["actual_hr"], errors="coerce").fillna(0).gt(0).sum())
    profit = pd.to_numeric(graded_view["profit_1u"], errors="coerce").fillna(0).sum()
    roi = (profit / total_bets * 100) if total_bets else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bets", f"{total_bets}")
    c2.metric("HR", f"{total_hr}")
    c3.metric("Profit/Loss", f"{profit:+.2f}u")
    c4.metric("ROI", f"{roi:+.2f}%")

    view = add_sportsbook_display_columns(view)
    display = format_display_frame(view[HISTORY_COLUMNS].copy())
    display_dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config=history_column_config(),
    )


def render_running_profit_chart(view: pd.DataFrame, selected_lens: str) -> None:
    if view.empty:
        st.info("No history rows for this lens yet.")
        return

    chart = view.copy()
    chart["game_date"] = pd.to_datetime(chart["game_date"], errors="coerce")
    chart["running_profit_1u"] = pd.to_numeric(chart["running_profit_1u"], errors="coerce")
    chart = chart.dropna(subset=["game_date", "running_profit_1u"])
    if chart.empty:
        st.info("No running P/L values available for this lens yet.")
        return

    if selected_lens == "All":
        chart = chart.sort_values(["lens", "game_date"])
        pivot = chart.pivot_table(
            index="game_date",
            columns="lens",
            values="running_profit_1u",
            aggfunc="last",
        ).ffill()
        st.line_chart(pivot, height=320)
    else:
        chart = chart.sort_values("game_date")
        series = chart.groupby("game_date", as_index=True)["running_profit_1u"].last()
        st.line_chart(series, height=320)


def build_history_frame(project_root: Path) -> pd.DataFrame:
    results = load_tracking_with_components(project_root)
    if results.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    numeric_columns = [
        "eye_rank",
        "eye_score",
        "accel_score",
        "book_american_odds",
        "model_hr_probability_percent",
        "edge_percent",
        "actual_hr",
        "did_hr",
        "profit_1u",
        "gbm_rank",
        "gbm_progression_rank",
        "sequence_rank",
        "pitcher_batter_rank",
        "batting_order",
    ]
    for column in numeric_columns:
        if column in results.columns:
            results[column] = pd.to_numeric(results[column], errors="coerce")

    results = results[results.get("result_available", "").astype(str).eq("1")].copy()
    results = results[results["book_american_odds"].notna()].copy()

    history_rows = []
    for spec in lens_specs():
        for game_date, day_frame in results.groupby("game_date", sort=True):
            records = day_frame.to_dict("records")
            candidates = [row for row in records if spec.predicate(row)]
            candidates = sorted(candidates, key=spec.sort_key)
            if spec.limit is not None:
                candidates = candidates[: spec.limit]
            for order, row in enumerate(candidates, start=1):
                output = {column: row.get(column, "") for column in HISTORY_COLUMNS}
                for hidden_column in ("bookmaker_used", "book_american_odds", "dk_odds", "fan_odds", "365_odds"):
                    output[hidden_column] = row.get(hidden_column, "")
                is_void = is_void_record(row)
                actual_hr = int(row.get("actual_hr") or 0) if not is_void else 0
                output["game_date"] = game_date
                output["lens"] = spec.title
                output["result"] = "Void" if is_void else ("HR" if actual_hr > 0 else "No HR")
                output["void_reason"] = row.get("void_reason", "") if is_void else ""
                output["profit_1u"] = 0 if is_void else row.get("profit_1u", 0)
                output["candidate_order"] = order
                history_rows.append(output)

    history = pd.DataFrame(history_rows)
    if history.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    history["profit_1u"] = pd.to_numeric(history["profit_1u"], errors="coerce").fillna(0)
    history = history.sort_values(["lens", "game_date", "candidate_order"]).copy()
    history["running_profit_1u"] = history.groupby("lens")["profit_1u"].cumsum().round(2)
    history["profit_1u"] = history["profit_1u"].round(2)
    history = history.sort_values(["game_date", "lens", "candidate_order"]).copy()
    for column in HISTORY_COLUMNS:
        if column not in history.columns:
            history[column] = ""
    return history


def render_parlay_history_viewer(project_root: Path) -> None:
    st.subheader("Parlay History")
    history = build_parlay_history_frame(project_root)
    for title, group in active_parlay_history_groups(history):
        st.subheader(title)
        curve = parlay_profit_curve(group)
        if curve.empty:
            st.info("No graded tickets for this group yet.")
        else:
            st.line_chart(curve, x="Date", y="Cumulative P/L (u)", height=280,
                          color="#848463")
    render_parlay_history_table(history, "parlay_history_select", "parlay_history_export")


def active_parlay_history_groups(history: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    groups = [
        ("Active 2-Leg Cumulative P/L", parlay_specs()),
        ("Active 3-Leg Cumulative P/L", three_leg_parlay_specs()),
        ("Active 4-Leg Cumulative P/L", four_leg_parlay_specs()),
    ]
    return [
        (title, history[history["parlay"].isin({spec.title for spec in specs})].copy()
         if not history.empty else history.copy())
        for title, specs in groups
    ]


def render_reinforced_history_viewer(project_root: Path) -> None:
    st.subheader("Reinforced History")
    history = build_parlay_history_frame(project_root)
    reinforced_titles = {spec.title for spec in reinforced_parlay_specs()}
    history = history[history["parlay"].isin(reinforced_titles)].copy() if not history.empty else history
    render_parlay_history_table(history, "reinforced_history_select", "reinforced_history_export", show_chart=True)


def parlay_profit_curve(view: pd.DataFrame) -> pd.DataFrame:
    chart = view.reindex(columns=["game_date", "profit_1u"]).copy()
    chart["game_date"] = pd.to_datetime(chart["game_date"], errors="coerce").dt.normalize()
    chart["profit_1u"] = pd.to_numeric(chart["profit_1u"], errors="coerce")
    chart = chart.dropna(subset=["game_date", "profit_1u"])
    if chart.empty:
        return pd.DataFrame(columns=["Date", "Cumulative P/L (u)"])
    daily = chart.groupby("game_date")["profit_1u"].sum().sort_index()
    opening = daily.index.min() - pd.Timedelta(days=1)
    daily = daily.reindex(pd.date_range(opening, daily.index.max(), freq="D"), fill_value=0)
    return daily.cumsum().rename("Cumulative P/L (u)").rename_axis("Date").reset_index()


def render_parlay_history_table(history: pd.DataFrame, select_key: str, export_key: str, *, show_chart: bool = False) -> None:
    if history.empty:
        st.info("No graded parlay history found yet. Run the rank tracker after completed results are available.")
        return

    parlay_options = ["All"] + sorted(history["parlay"].dropna().unique().tolist())
    selected_parlay = st.selectbox("Parlay", parlay_options, key=select_key)
    view = history.copy()
    if selected_parlay != "All":
        view = view[view["parlay"].eq(selected_parlay)].copy()

    tickets = len(view)
    hits = int(view["parlay_result"].eq("Hit").sum())
    profit = pd.to_numeric(view["profit_1u"], errors="coerce").fillna(0).sum()
    roi = (profit / tickets * 100) if tickets else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tickets", f"{tickets}")
    c2.metric("Wins", f"{hits}")
    c3.metric("Profit/Loss", f"{profit:+.2f}u")
    c4.metric("ROI", f"{roi:+.2f}%")

    if show_chart:
        st.subheader("Cumulative Profit/Loss")
        curve = parlay_profit_curve(view)
        if curve.empty:
            st.info("No dated profit/loss results available yet.")
        else:
            st.line_chart(curve, x="Date", y="Cumulative P/L (u)", height=280,
                          color="#848463")

    export_view = add_sportsbook_display_columns(view, leg_prefixes=("leg1", "leg2", "leg3", "leg4"))
    export = format_display_frame(export_view[available_columns(export_view, PARLAY_HISTORY_EXPORT_COLUMNS)].copy())
    st.download_button(
        "Save Research CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name=f"model4_parlay_history_{safe_filename(selected_parlay)}.csv",
        mime="text/csv",
        key=f"{export_key}_{safe_filename(selected_parlay)}",
    )

    display_view = add_sportsbook_display_columns(view, leg_prefixes=("leg1", "leg2", "leg3", "leg4"))
    display = format_display_frame(display_view[PARLAY_HISTORY_DISPLAY_COLUMNS].copy())
    display_dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config=parlay_history_column_config(),
    )


def safe_filename(value: object) -> str:
    text = str(value or "all").strip().lower()
    cleaned = "".join(char if char.isalnum() else "_" for char in text)
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "all"


def build_parlay_history_frame(project_root: Path) -> pd.DataFrame:
    results = load_tracking_with_components(project_root, require_book_odds=False)
    if results.empty:
        return pd.DataFrame(columns=PARLAY_HISTORY_COLUMNS)
    rows = build_parlay_history_rows(results.to_dict("records"))
    history = pd.DataFrame(rows)
    if history.empty:
        return pd.DataFrame(columns=PARLAY_HISTORY_COLUMNS)
    for column in PARLAY_HISTORY_COLUMNS:
        if column not in history.columns:
            history[column] = ""
    return history


def parlay_history_column_config() -> dict[str, object]:
    return {
        "game_date": st.column_config.TextColumn("Date"),
        "parlay": st.column_config.TextColumn("Parlay", width="large"),
        "leg1_player": st.column_config.TextColumn("Leg 1", width="medium"),
        "leg1_result": st.column_config.TextColumn("L1 Result"),
        "leg1_sportsbook_used": st.column_config.TextColumn("L1 Book"),
        "leg1_sportsbook_odds": st.column_config.TextColumn("L1 Sportsbook Odds"),
        "leg1_book_american_odds": st.column_config.TextColumn("L1 Odds"),
        "leg1_eye_rank": st.column_config.TextColumn("L1 Eye"),
        "leg1_gbm_rank": st.column_config.TextColumn("L1 GBM"),
        "leg1_pitcher_batter_rank": st.column_config.TextColumn("L1 Pitch"),
        "leg2_player": st.column_config.TextColumn("Leg 2", width="medium"),
        "leg2_result": st.column_config.TextColumn("L2 Result"),
        "leg2_sportsbook_used": st.column_config.TextColumn("L2 Book"),
        "leg2_sportsbook_odds": st.column_config.TextColumn("L2 Sportsbook Odds"),
        "leg2_book_american_odds": st.column_config.TextColumn("L2 Odds"),
        "leg2_eye_rank": st.column_config.TextColumn("L2 Eye"),
        "leg2_gbm_rank": st.column_config.TextColumn("L2 GBM"),
        "leg2_pitcher_batter_rank": st.column_config.TextColumn("L2 Pitch"),
        "leg3_player": st.column_config.TextColumn("Leg 3", width="medium"),
        "leg3_result": st.column_config.TextColumn("L3 Result"),
        "leg3_sportsbook_used": st.column_config.TextColumn("L3 Book"),
        "leg3_sportsbook_odds": st.column_config.TextColumn("L3 Sportsbook Odds"),
        "leg3_book_american_odds": st.column_config.TextColumn("L3 Odds"),
        "leg3_eye_rank": st.column_config.TextColumn("L3 Eye"),
        "leg3_gbm_rank": st.column_config.TextColumn("L3 GBM"),
        "leg3_pitcher_batter_rank": st.column_config.TextColumn("L3 Pitch"),
        "leg4_player": st.column_config.TextColumn("Leg 4", width="medium"),
        "leg4_result": st.column_config.TextColumn("L4 Result"),
        "leg4_sportsbook_used": st.column_config.TextColumn("L4 Book"),
        "leg4_sportsbook_odds": st.column_config.TextColumn("L4 Sportsbook Odds"),
        "leg4_book_american_odds": st.column_config.TextColumn("L4 Odds"),
        "leg4_eye_rank": st.column_config.TextColumn("L4 Eye"),
        "leg4_gbm_rank": st.column_config.TextColumn("L4 GBM"),
        "leg4_pitcher_batter_rank": st.column_config.TextColumn("L4 Pitch"),
        "parlay_result": st.column_config.TextColumn("Parlay"),
        "profit_1u": st.column_config.TextColumn("P/L"),
        "running_profit_1u": st.column_config.TextColumn("Running P/L"),
        "parlay_decimal_odds": st.column_config.TextColumn("Parlay Odds"),
        "independent_parlay_decimal_odds": st.column_config.TextColumn("Raw Independent"),
        "correlation_factor": st.column_config.TextColumn("Correlation"),
        "correlation_note": st.column_config.TextColumn("Correlation Note", width="large"),
    }


def load_tracking_with_components(project_root: Path, require_book_odds: bool = True) -> pd.DataFrame:
    results_path = project_root / "MODEL4_RANK_TRACKING" / "model4_rank_results.csv"
    if not results_path.exists():
        return pd.DataFrame()

    results = pd.read_csv(results_path).fillna("")
    if results.empty:
        return pd.DataFrame()
    results["game_date"] = pd.to_datetime(results["game_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    boards = load_daily_board_components(project_root / "MODEL4_DAILY_READS")
    if not boards.empty:
        shared_columns = [
            column
            for column in boards.columns
            if column in results.columns and column not in {"game_date", "eye_rank", "player"}
        ]
        board_columns = {column: f"{column}_board" for column in shared_columns}
        boards = boards.rename(columns=board_columns)
        results = results.merge(boards, on=["game_date", "eye_rank", "player"], how="left")
        for column in shared_columns:
            board_column = f"{column}_board"
            if board_column not in results.columns:
                continue
            results[column] = results[column].replace("", pd.NA).fillna(results[board_column])
            results = results.drop(columns=[board_column])

    numeric_columns = [
        "eye_rank",
        "eye_score",
        "accel_score",
        "book_american_odds",
        "model_hr_probability_percent",
        "edge_percent",
        "actual_hr",
        "did_hr",
        "profit_1u",
        "gbm_rank",
        "gbm_progression_rank",
        "sequence_rank",
        "pitcher_batter_rank",
        "batting_order",
    ]
    for column in numeric_columns:
        if column in results.columns:
            results[column] = pd.to_numeric(results[column], errors="coerce")

    results = results[results.get("result_available", "").astype(str).eq("1")].copy()
    if require_book_odds:
        results = results[results["book_american_odds"].notna()].copy()
    return results


def load_daily_board_components(daily_root: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(daily_root.glob("*/MODEL4_*_BOARD.csv")):
        date_key = path.parent.name
        frame = pd.read_csv(path).fillna("")
        frame["game_date"] = date_key
        keep = [
            "game_date",
            "eye_rank",
            "player",
            "gbm_rank",
            "gbm_progression_rank",
            "sequence_rank",
            "pitcher_batter_rank",
            "stale_signal_status",
            "layers_present",
            "movement_summary",
            "reasoning",
            "bookmaker_used",
            "book_american_odds",
            "dk_odds",
            "fan_odds",
            "365_odds",
        ]
        frames.append(frame[[column for column in keep if column in frame.columns]])
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(["game_date", "eye_rank", "player"])



def render_edge_bucket_viewer(daily_folder: Path) -> None:
    game_date = date_key_from_text(daily_folder.name) or ""
    st.subheader("Model 4 Edge Buckets")
    st.caption("Full daily HR projection board study: top 25 by model odds, joined to completed daily results when available.")
    if not game_date:
        st.warning("Could not detect the selected daily folder date.")
        return

    active = pd.read_csv(daily_folder / "edge_active.csv").fillna("") if (daily_folder / "edge_active.csv").exists() else pd.DataFrame(build_edge_bucket_active_rows(game_date))
    active = without_retired_signals(active)
    active = filter_posting_rows(active)
    history_rows = build_edge_bucket_history_rows()
    history = pd.DataFrame(history_rows)

    render_edge_bucket_daily_watch(active, game_date)
    st.divider()
    render_edge_bucket_summary(history)
    st.divider()
    render_edge_bucket_primary_sections(active, history)
    st.divider()
    render_edge_bucket_stability(history)


def render_edge_bucket_daily_watch(active: pd.DataFrame, game_date: str) -> None:
    st.markdown("**Daily Watch List**")
    if active.empty:
        st.info(f"No Model 4 Edge Bucket qualifiers for {game_date}.")
        render_edge_bucket_rule_reference()
        return

    signal_options = ["All"] + sorted(active["signal"].dropna().unique().tolist())
    selected_signal = st.selectbox("Daily Signal", signal_options, key="edge_bucket_daily_signal")
    view = active.copy() if selected_signal == "All" else active[active["signal"].eq(selected_signal)].copy()
    c1, c2 = st.columns(2)
    c1.metric("Qualified Rows", f"{len(view)}")
    c2.metric("Selected Date", game_date)
    view = add_sportsbook_display_columns(view)
    display = format_display_frame(view[available_columns(view, EDGE_BUCKET_ACTIVE_DISPLAY_COLUMNS)].copy())
    display_dataframe(display, width="stretch", hide_index=True, column_config=edge_bucket_column_config())
    st.download_button(
        "Save Today’s Edge Bucket CSV",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name=f"model4_edge_buckets_{safe_filename(selected_signal)}_{game_date}.csv",
        mime="text/csv",
        key=f"edge_bucket_active_export_{safe_filename(selected_signal)}",
    )


def render_edge_bucket_summary(history: pd.DataFrame) -> None:
    st.markdown("**Best Combo Signal Table**")
    if history.empty:
        st.info("No graded signal history yet.")
        render_edge_bucket_rule_reference()
        return

    combo_summary = pd.DataFrame(build_edge_bucket_summary_rows(history.to_dict("records")))
    total = int(pd.to_numeric(combo_summary["n"], errors="coerce").fillna(0).sum())
    hrs = int(pd.to_numeric(combo_summary["hr"], errors="coerce").fillna(0).sum())
    profit = pd.to_numeric(combo_summary["profit_1u"], errors="coerce").fillna(0).sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Signal Bets", f"{total}")
    c2.metric("HR", f"{hrs}")
    c3.metric("Profit/Loss", f"{profit:+.2f}u")
    c4.metric("ROI", f"{(profit / total * 100):+.2f}%" if total else "+0.00%")

    display_dataframe(format_display_frame(combo_summary), width="stretch", hide_index=True, column_config=edge_bucket_column_config())


def render_edge_bucket_primary_sections(active: pd.DataFrame, history: pd.DataFrame) -> None:
    title = "Primary Mid-Price Edge Rule"
    st.markdown(f"**{title}**")
    signal = next((item for item in edge_bucket_signals() if item.title == title), None)
    active_view = active[active["signal"].eq(title)].copy() if not active.empty else pd.DataFrame()
    history_view = history[history["signal"].eq(title)].copy() if not history.empty else pd.DataFrame()
    bets = len(history_view)
    hrs = int(history_view["result"].eq("HR").sum()) if not history_view.empty else 0
    profit = pd.to_numeric(history_view.get("profit_1u", pd.Series(dtype=float)), errors="coerce").fillna(0).sum() if not history_view.empty else 0.0
    if signal:
        st.caption(signal.definition)
    st.caption(edge_bucket_stat_sentence(bets, hrs, float(profit)))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Today", f"{len(active_view)}")
    c2.metric("History Bets", f"{bets}")
    c3.metric("HR", f"{hrs}")
    c4.metric("ROI", f"{(profit / bets * 100):+.2f}%" if bets else "+0.00%")
    if active_view.empty:
        st.info("No active qualifiers on the selected slate.")
    else:
        active_view = add_sportsbook_display_columns(active_view)
        display = format_display_frame(active_view[available_columns(active_view, EDGE_BUCKET_ACTIVE_DISPLAY_COLUMNS)].copy())
        display_dataframe(display, width="stretch", hide_index=True, column_config=edge_bucket_column_config())
    with st.expander(f"{title} History", expanded=False):
        if history_view.empty:
            st.info("No graded rows yet.")
        else:
            history_view = add_sportsbook_display_columns(history_view)
            display = format_display_frame(history_view[available_columns(history_view, EDGE_BUCKET_HISTORY_DISPLAY_COLUMNS)].copy())
            display_dataframe(display, width="stretch", hide_index=True, column_config=edge_bucket_column_config())
    with st.expander("Rule Reference", expanded=False):
        render_edge_bucket_rule_reference()


def render_edge_bucket_stability(history: pd.DataFrame) -> None:
    st.markdown("**Historical Daily Stability**")
    if history.empty:
        st.info("No history rows to stabilize yet.")
        return
    signal_options = sorted(history["signal"].dropna().unique().tolist())
    selected_signal = st.selectbox("Stability Signal", signal_options, index=signal_options.index("Primary Mid-Price Edge Rule") if "Primary Mid-Price Edge Rule" in signal_options else 0, key="edge_bucket_stability_signal")
    stability = pd.DataFrame(build_edge_bucket_daily_stability_rows(history.to_dict("records"), selected_signal))
    if stability.empty:
        st.info("No daily stability rows for this signal yet.")
        return
    chart = stability.copy()
    chart["game_date"] = pd.to_datetime(chart["game_date"], errors="coerce")
    chart["running_profit_1u"] = pd.to_numeric(chart["running_profit_1u"], errors="coerce")
    chart = chart.dropna(subset=["game_date", "running_profit_1u"])
    if not chart.empty:
        st.line_chart(chart.set_index("game_date")["running_profit_1u"])
    display = format_display_frame(stability[available_columns(stability, EDGE_BUCKET_STABILITY_DISPLAY_COLUMNS)].copy())
    display_dataframe(display, width="stretch", hide_index=True, column_config=edge_bucket_column_config())


def render_edge_bucket_rule_reference() -> None:
    rows = [
        {"signal": signal.title, "section": signal.section, "rule": signal.definition, "read": signal.backtest_note}
        for signal in edge_bucket_signals()
    ]
    display_dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, column_config=edge_bucket_column_config())


def edge_bucket_column_config() -> dict[str, object]:
    return {
        "signal": st.column_config.TextColumn("Signal", width="large"),
        "section": st.column_config.TextColumn("Section"),
        "bucket": st.column_config.TextColumn("Bucket", width="large"),
        "read": st.column_config.TextColumn("Read", width="large"),
        "signal_note": st.column_config.TextColumn("Backtest", width="large"),
        "rule": st.column_config.TextColumn("Rule", width="large"),
        "game_date": st.column_config.TextColumn("Date"),
        "player": st.column_config.TextColumn("Player", width="medium"),
        "result": st.column_config.TextColumn("Result"),
        "sportsbook_used": st.column_config.TextColumn("Sportsbook"),
        "sportsbook_odds": st.column_config.TextColumn("Sportsbook Odds"),
        "void_reason": st.column_config.TextColumn("Void Reason", width="large"),
        "actual_hr": st.column_config.TextColumn("HR"),
        "n": st.column_config.TextColumn("n"),
        "hr": st.column_config.TextColumn("HR"),
        "hr_percent": st.column_config.TextColumn("HR%"),
        "profit_1u": st.column_config.TextColumn("P/L"),
        "running_profit_1u": st.column_config.TextColumn("Running P/L"),
        "roi_percent": st.column_config.TextColumn("ROI%"),
        "bets": st.column_config.TextColumn("Bets"),
        "model_top25_rank": st.column_config.TextColumn("Model Top 25"),
        "original_model_rank": st.column_config.TextColumn("Orig Rank"),
        "model_american_odds": st.column_config.TextColumn("Model Odds"),
        "book_american_odds": st.column_config.TextColumn("Book Odds"),
        "edge_percent": st.column_config.TextColumn("Edge%"),
        "model_hr_probability_percent": st.column_config.TextColumn("Model HR%"),
        "reg_score": st.column_config.TextColumn("Reg Score"),
        "regression_rank": st.column_config.TextColumn("Reg Rank"),
        "team_abbrev": st.column_config.TextColumn("Team"),
        "opponent_abbrev": st.column_config.TextColumn("Opp"),
        "lineup_status": st.column_config.TextColumn("Lineup"),
        "batting_order": st.column_config.TextColumn("Order"),
    }



def render_sequence_edge_viewer(project_root: Path, daily_folder: Path) -> None:
    game_date = date_key_from_text(daily_folder.name) or ""
    st.subheader("Sequence Edge")
    st.caption("Cross-model watch list: selected Sequence Model 2 5-step/contact-quality signals crossed with Model 4 odds, edge, and screenshot bucket signals.")
    if not game_date:
        st.warning("Could not detect the selected daily folder date.")
        return

    if st.button("Refresh Sequence Edge files", key="sequence_edge_refresh"):
        destination = write_sequence_edge_outputs(project_root, daily_folder)
        st.success(f"Sequence Edge CSVs refreshed: {destination}")

    active, history, summary = build_sequence_edge_frames(project_root, daily_folder)
    active = filter_posting_rows(active)
    render_sequence_edge_top_metrics(active, history, summary, game_date)

    tabs = st.tabs(["Summary", "Active", "History"])
    with tabs[0]:
        render_sequence_edge_summary(summary)
    with tabs[1]:
        render_sequence_edge_active(active, game_date)
    with tabs[2]:
        render_sequence_edge_history(history)


def render_sequence_edge_top_metrics(active: pd.DataFrame, history: pd.DataFrame, summary: pd.DataFrame, game_date: str) -> None:
    active_count = len(active)
    bets = len(history)
    hrs = int(history["result"].eq("HR").sum()) if not history.empty else 0
    profit = pd.to_numeric(history.get("profit_1u", pd.Series(dtype=float)), errors="coerce").fillna(0).sum() if not history.empty else 0.0
    roi = (profit / bets * 100) if bets else 0.0
    strongest = "None"
    if not summary.empty:
        ranked = summary.sort_values(["active", "roi_percent"], ascending=[False, False])
        strongest = str(ranked.iloc[0].get("signal", "None")) if not ranked.empty else "None"
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Selected Date", game_date)
    c2.metric("Active", f"{active_count}")
    c3.metric("History Bets", f"{bets}")
    c4.metric("P/L", f"{profit:+.2f}u")
    c5.metric("ROI", f"{roi:+.2f}%")
    st.caption(f"Most active/strongest current signal: {strongest}")


def render_sequence_edge_summary(summary: pd.DataFrame) -> None:
    st.markdown("**Sequence Edge Signal Summary**")
    if summary.empty:
        st.info("No Sequence Edge summary available yet.")
        return
    display = format_display_frame(summary[available_columns(summary, SEQUENCE_EDGE_SUMMARY_COLUMNS)].copy())
    display_dataframe(display, width="stretch", hide_index=True, column_config=sequence_edge_column_config())
    st.download_button(
        "Save Sequence Edge Summary CSV",
        data=summary.to_csv(index=False).encode("utf-8"),
        file_name="model4_sequence_edge_summary.csv",
        mime="text/csv",
        key="sequence_edge_summary_export",
    )


def render_sequence_edge_active(active: pd.DataFrame, game_date: str) -> None:
    st.markdown("**Today's Sequence Edge Qualifiers**")
    if active.empty:
        st.info(f"No Sequence Edge qualifiers for {game_date}.")
        return
    signal_options = ["All"] + sorted(active["signal"].dropna().unique().tolist())
    selected_signal = st.selectbox("Active Signal", signal_options, key="sequence_edge_active_signal")
    view = active.copy() if selected_signal == "All" else active[active["signal"].eq(selected_signal)].copy()
    view = add_sportsbook_display_columns(view)
    display = format_display_frame(view[available_columns(view, SEQUENCE_EDGE_ACTIVE_DISPLAY_COLUMNS)].copy())
    display_dataframe(display, width="stretch", hide_index=True, column_config=sequence_edge_column_config())
    st.download_button(
        "Save Today's Sequence Edge CSV",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name=f"model4_sequence_edge_{safe_filename(selected_signal)}_{game_date}.csv",
        mime="text/csv",
        key=f"sequence_edge_active_export_{safe_filename(selected_signal)}",
    )


def render_sequence_edge_history(history: pd.DataFrame) -> None:
    st.markdown("**Sequence Edge History**")
    if history.empty:
        st.info("No graded Sequence Edge history yet.")
        return
    signal_options = ["All"] + sorted(history["signal"].dropna().unique().tolist())
    selected_signal = st.selectbox("History Signal", signal_options, key="sequence_edge_history_signal")
    view = history.copy() if selected_signal == "All" else history[history["signal"].eq(selected_signal)].copy()
    bets = len(view)
    hrs = int(view["result"].eq("HR").sum()) if not view.empty else 0
    profit = pd.to_numeric(view.get("profit_1u", pd.Series(dtype=float)), errors="coerce").fillna(0).sum() if not view.empty else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bets", f"{bets}")
    c2.metric("HR", f"{hrs}")
    c3.metric("Profit/Loss", f"{profit:+.2f}u")
    c4.metric("ROI", f"{(profit / bets * 100):+.2f}%" if bets else "+0.00%")
    export = format_display_frame(view[available_columns(view, SEQUENCE_EDGE_COLUMNS)].copy())
    st.download_button(
        "Save Sequence Edge History CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name=f"model4_sequence_edge_history_{safe_filename(selected_signal)}.csv",
        mime="text/csv",
        key=f"sequence_edge_history_export_{safe_filename(selected_signal)}",
    )
    view = add_sportsbook_display_columns(view)
    display = format_display_frame(view[available_columns(view, SEQUENCE_EDGE_HISTORY_DISPLAY_COLUMNS)].copy())
    display_dataframe(display, width="stretch", hide_index=True, column_config=sequence_edge_column_config())


def sequence_edge_column_config() -> dict[str, object]:
    return {
        "signal": st.column_config.TextColumn("Signal", width="large"),
        "game_date": st.column_config.TextColumn("Date"),
        "player": st.column_config.TextColumn("Player", width="medium"),
        "sportsbook_used": st.column_config.TextColumn("Sportsbook"),
        "sportsbook_odds": st.column_config.TextColumn("Sportsbook Odds"),
        "team_abbrev": st.column_config.TextColumn("Team"),
        "opponent_abbrev": st.column_config.TextColumn("Opp"),
        "book_american_odds": st.column_config.TextColumn("Book Odds"),
        "edge_percent": st.column_config.TextColumn("Edge%"),
        "eye_rank": st.column_config.TextColumn("Eye"),
        "eye_score": st.column_config.TextColumn("Eye Score"),
        "model_hr_probability_percent": st.column_config.TextColumn("Model HR%"),
        "sequence_projection_rank": st.column_config.TextColumn("Seq Rank"),
        "sequence_hr_probability": st.column_config.TextColumn("Seq HR%"),
        "risk_tier": st.column_config.TextColumn("Tier"),
        "sequence_long5_motif_count": st.column_config.TextColumn("5-Step"),
        "sequence_long5_motif_max_lift": st.column_config.TextColumn("5-Step Lift"),
        "sequence_long5_motif_notes": st.column_config.TextColumn("5-Step Notes", width="large"),
        "projection_notes": st.column_config.TextColumn("Sequence Notes", width="large"),
        "result": st.column_config.TextColumn("Result"),
        "actual_hr": st.column_config.TextColumn("HR"),
        "sportsbook_used": st.column_config.TextColumn("Sportsbook"),
        "sportsbook_odds": st.column_config.TextColumn("Sportsbook Odds"),
        "profit_1u": st.column_config.TextColumn("P/L"),
        "running_profit_1u": st.column_config.TextColumn("Running P/L"),
        "signal_note": st.column_config.TextColumn("Read", width="large"),
        "active": st.column_config.TextColumn("Active"),
        "n": st.column_config.TextColumn("n"),
        "hr": st.column_config.TextColumn("HR"),
        "hr_percent": st.column_config.TextColumn("HR%"),
        "profit_1u": st.column_config.TextColumn("P/L"),
        "roi_percent": st.column_config.TextColumn("ROI%"),
        "read": st.column_config.TextColumn("Read", width="large"),
        "n": st.column_config.TextColumn("n"),
        "hr": st.column_config.TextColumn("HR"),
        "hr_percent": st.column_config.TextColumn("HR%"),
        "roi_percent": st.column_config.TextColumn("ROI%"),
        "read": st.column_config.TextColumn("Read", width="large"),
        "rule": st.column_config.TextColumn("Rule", width="large"),
    }

def render_regression_misprice_viewer(project_root: Path, regression_folder: Path) -> None:
    st.subheader("Regression Misprice")
    st.caption("High regression pressure where market price and model edge disagree. This uses the progression input file you already enter during the daily run.")
    render_regression_misprice_active(regression_folder)
    render_regression_misprice_history(project_root)


def render_regression_misprice_active(regression_folder: Path) -> None:
    st.markdown("**Today’s Regression Misprice Zones**")
    if not regression_folder.exists():
        st.info("No Regression Misprice folder for this date yet. Run Model 4 again to create it.")
        render_regression_misprice_rule_reference()
        return

    combined_path = regression_folder / "regression_misprice_combined.csv"
    if not combined_path.exists():
        st.warning("Missing regression_misprice_combined.csv")
        render_regression_misprice_rule_reference()
        return

    active = filter_posting_rows(pd.read_csv(combined_path).fillna(""))
    if active.empty:
        st.info("No Regression Misprice players qualified for this slate.")
    else:
        selected_zone = st.selectbox("Active Zone", ["All"] + sorted(active["zone"].dropna().unique().tolist()), key="regression_misprice_active_zone")
        view = active.copy() if selected_zone == "All" else active[active["zone"].eq(selected_zone)].copy()
        view = add_sportsbook_display_columns(view)
        display = format_display_frame(view[available_columns(view, REGRESSION_MISPRICE_DISPLAY_COLUMNS)].copy())
        display_dataframe(
            display,
            width="stretch",
            hide_index=True,
            column_config=regression_misprice_column_config(),
        )
        st.download_button(
            "Save Today’s Regression Misprice CSV",
            data=view.to_csv(index=False).encode("utf-8"),
            file_name=f"model4_regression_misprice_{safe_filename(selected_zone)}_today.csv",
            mime="text/csv",
            key=f"regression_misprice_active_export_{safe_filename(selected_zone)}",
        )

    for zone in regression_misprice_zones():
        with st.expander(zone.title, expanded=False):
            st.markdown(f"**Rule:** {zone.definition}")
            st.caption(zone.backtest_note)
            path = regression_folder / zone.filename
            if not path.exists():
                st.warning(f"Missing CSV: {path.name}")
                continue
            frame = filter_posting_rows(pd.read_csv(path).fillna(""))
            if frame.empty:
                st.info("No qualifiers today.")
                continue
            frame = add_sportsbook_display_columns(frame)
            display = format_display_frame(frame[available_columns(frame, REGRESSION_MISPRICE_DISPLAY_COLUMNS)].copy())
            display_dataframe(display, width="stretch", hide_index=True, column_config=regression_misprice_column_config())


def render_regression_misprice_rule_reference() -> None:
    rows = [
        {
            "zone": zone.title,
            "rule": zone.definition,
            "read": zone.backtest_note,
        }
        for zone in regression_misprice_zones()
    ]
    display_dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def render_regression_misprice_history(project_root: Path) -> None:
    st.markdown("**Regression Misprice History**")
    history = build_regression_misprice_history_frame(project_root)
    if history.empty:
        st.info("No graded Regression Misprice history yet.")
        return

    zone_options = ["All"] + sorted(history["zone"].dropna().unique().tolist())
    selected_zone = st.selectbox("History Zone", zone_options, key="regression_misprice_history_zone")
    view = history.copy()
    if selected_zone != "All":
        view = view[view["zone"].eq(selected_zone)].copy()

    bets = len(view)
    hrs = int(view["result"].eq("HR").sum())
    profit = pd.to_numeric(view["profit_1u"], errors="coerce").fillna(0).sum()
    roi = (profit / bets * 100) if bets else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bets", f"{bets}")
    c2.metric("HR", f"{hrs}")
    c3.metric("Profit/Loss", f"{profit:+.2f}u")
    c4.metric("ROI", f"{roi:+.2f}%")

    export = format_display_frame(view[available_columns(view, REGRESSION_MISPRICE_HISTORY_COLUMNS)].copy())
    st.download_button(
        "Save Regression Misprice History CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name=f"model4_regression_misprice_history_{safe_filename(selected_zone)}.csv",
        mime="text/csv",
        key=f"regression_misprice_history_export_{safe_filename(selected_zone)}",
    )

    view = add_sportsbook_display_columns(view)
    display = format_display_frame(view[available_columns(view, REGRESSION_MISPRICE_HISTORY_DISPLAY_COLUMNS)].copy())
    display_dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config=regression_misprice_column_config(),
    )


def build_regression_misprice_history_frame(project_root: Path) -> pd.DataFrame:
    rows = build_regression_misprice_history_from_archives()
    history = pd.DataFrame(rows)
    if history.empty:
        return pd.DataFrame(columns=REGRESSION_MISPRICE_HISTORY_COLUMNS)
    for column in REGRESSION_MISPRICE_HISTORY_COLUMNS:
        if column not in history.columns:
            history[column] = ""
    return history


def regression_misprice_column_config() -> dict[str, object]:
    return {
        "game_date": st.column_config.TextColumn("Date"),
        "zone": st.column_config.TextColumn("Zone", width="medium"),
        "player": st.column_config.TextColumn("Player", width="medium"),
        "result": st.column_config.TextColumn("Result"),
        "actual_hr": st.column_config.TextColumn("HR"),
        "sportsbook_used": st.column_config.TextColumn("Sportsbook"),
        "sportsbook_odds": st.column_config.TextColumn("Sportsbook Odds"),
        "book_american_odds": st.column_config.TextColumn("Book Odds"),
        "edge_percent": st.column_config.TextColumn("Edge%"),
        "reg_score": st.column_config.TextColumn("Reg Score"),
        "regression_rank": st.column_config.TextColumn("Reg Rank"),
        "profit_1u": st.column_config.TextColumn("P/L"),
        "running_profit_1u": st.column_config.TextColumn("Running P/L"),
        "eye_rank": st.column_config.TextColumn("Eye"),
        "eye_score": st.column_config.TextColumn("Eye Score"),
        "accel_score": st.column_config.TextColumn("Accel"),
        "gbm_rank": st.column_config.TextColumn("GBM"),
        "gbm_progression_rank": st.column_config.TextColumn("Progression"),
        "sequence_rank": st.column_config.TextColumn("Sequence"),
        "pitcher_batter_rank": st.column_config.TextColumn("Pitch"),
        "model_hr_probability_percent": st.column_config.TextColumn("Model HR%"),
        "team_abbrev": st.column_config.TextColumn("Team"),
        "opponent_abbrev": st.column_config.TextColumn("Opp"),
        "lineup_status": st.column_config.TextColumn("Lineup"),
        "zone_note": st.column_config.TextColumn("Read", width="large"),
    }


def render_prospective_viewer(project_root: Path, prospective_folder: Path) -> None:
    st.subheader("Prospective Parlays V1")
    st.caption("Forward-only shadow tickets: frozen criteria, deterministic selection, different-game pairing, and market-implied expected wins.")

    render_prospective_active_section(prospective_folder)
    render_prospective_history_section(project_root)


def render_prospective_active_section(prospective_folder: Path) -> None:
    st.markdown("**Today's Prospective V1 Tickets**")
    if not prospective_folder.exists():
        st.info("No prospective parlay folder for this date yet. Run Model 4 again to create the V1 shadow tickets.")
        render_prospective_criteria_reference()
        return

    combined_path = prospective_folder / "prospective_parlays_combined.csv"
    if not combined_path.exists():
        st.warning("Missing prospective_parlays_combined.csv")
        render_prospective_criteria_reference()
        return

    active = filter_posting_rows(pd.read_csv(combined_path).fillna(""))
    if active.empty:
        st.info("No Prospective V1 tickets qualified for this slate.")
    else:
        active = add_sportsbook_display_columns(active, leg_prefixes=("leg1", "leg2"))
        active_display = format_prospective_frame(active[available_columns(active, PROSPECTIVE_ACTIVE_DISPLAY_COLUMNS)].copy())
        display_dataframe(
            active_display,
            width="stretch",
            hide_index=True,
            column_config=prospective_column_config(),
        )
        st.download_button(
            "Save Today's Prospective CSV",
            data=active.to_csv(index=False).encode("utf-8"),
            file_name="model4_prospective_v1_today.csv",
            mime="text/csv",
            key="prospective_active_export",
        )

    for spec in prospective_criteria_specs():
        with st.expander(spec.title, expanded=False):
            st.markdown(f"**Hypothesis:** {spec.hypothesis}")
            st.caption(spec.candidate_filter_definition)
            st.caption(spec.candidate_ranking_definition)
            render_prospective_ticket_stack(prospective_folder / spec.filename)

    candidates_path = prospective_folder / "prospective_qualifying_players.csv"
    if candidates_path.exists():
        candidates = filter_posting_rows(pd.read_csv(candidates_path).fillna(""))
        if not candidates.empty:
            st.markdown("**Qualifying Players By Criteria**")
            candidates = add_sportsbook_display_columns(candidates)
            display = format_prospective_frame(candidates.copy())
            display_dataframe(display, width="stretch", hide_index=True, column_config=prospective_column_config())


def render_prospective_criteria_reference() -> None:
    st.markdown("**Frozen V1 Criteria**")
    rows = []
    for spec in prospective_criteria_specs():
        rows.append(
            {
                "criteria_id": spec.criteria_id,
                "title": spec.title,
                "filter": spec.candidate_filter_definition,
                "ranking": spec.candidate_ranking_definition,
                "pairing": spec.pairing_definition,
            }
        )
    display_dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def render_prospective_ticket_stack(path: Path) -> None:
    if not path.exists():
        st.warning(f"Missing CSV: {path.name}")
        return
    frame = filter_posting_rows(pd.read_csv(path).fillna(""))
    if frame.empty:
        st.info("No active ticket for this criterion today.")
        return
    row = frame.iloc[0].to_dict()
    c1, c2, c3 = st.columns(3)
    c1.metric("Parlay Odds", clean_value(row.get("parlay_decimal_odds", ""), parlay_odds=True))
    c2.metric("Market Expected", percent_value(row.get("expected_wins", "")))
    note = clean_value(row.get("correlation_note", ""))
    if note and note != "No same-game correlation adjustment":
        st.caption(note)
    c3.metric("Qualifiers", clean_value(row.get("qualifying_count", "")))
    render_prospective_leg_block("Leg 1", row, "leg1")
    render_prospective_leg_block("Leg 2", row, "leg2")


def render_prospective_leg_block(title: str, row: dict[str, object], prefix: str) -> None:
    player = clean_value(row.get(f"{prefix}_player", ""))
    role_key = "leg1_role" if prefix == "leg1" else "leg2_role"
    role = clean_value(row.get(role_key, ""))
    st.markdown(f"**{title}: {player}**")
    if role:
        st.caption(role)
    fields = {
        "Sportsbook": sportsbook_display_label(row, prefix=prefix),
        "Sportsbook Odds": selected_sportsbook_odds(row, prefix=prefix),
        "Implied Probability": percent_value(row.get(f"{prefix}_implied_probability", "")),
        "G": row.get(f"{prefix}_G", ""),
        "R": row.get(f"{prefix}_R", ""),
        "S": row.get(f"{prefix}_S", ""),
        "M": row.get(f"{prefix}_M", ""),
        "Consensus": row.get(f"{prefix}_consensus", ""),
        "Disagreement": row.get(f"{prefix}_disagreement", ""),
        "State/Matchup": row.get(f"{prefix}_state_matchup_strength", ""),
        "Quality/Regression": row.get(f"{prefix}_quality_regression_strength", ""),
        "Eye Rank": row.get(f"{prefix}_eye_rank", ""),
        "Team": row.get(f"{prefix}_team_abbrev", ""),
        "Opp": row.get(f"{prefix}_opponent_abbrev", ""),
        "Reason": row.get(f"{prefix}_qualification_reason", ""),
    }
    with st.expander(f"{title} model-state details", expanded=False):
        display = pd.DataFrame([{"Field": key, "Value": clean_value(value)} for key, value in fields.items()])
        display_dataframe(display, width="stretch", hide_index=True)


def render_prospective_history_section(project_root: Path) -> None:
    st.markdown("**Forward Performance Ledger**")
    history = build_prospective_history_frame(project_root)
    if history.empty:
        st.info("No saved prospective tickets have been graded yet. The ledger starts from the first slate generated after Prospective V1 was added.")
        return

    criteria_options = ["All"] + sorted(history["criteria_id"].dropna().unique().tolist())
    selected = st.selectbox("Prospective Criterion", criteria_options, key="prospective_history_select")
    view = history.copy()
    if selected != "All":
        view = view[view["criteria_id"].eq(selected)].copy()

    completed = view[view["ticket_hit"].astype(str).isin(["0", "1"])].copy()
    tickets = len(completed)
    wins = int(pd.to_numeric(completed.get("ticket_hit", 0), errors="coerce").fillna(0).sum()) if not completed.empty else 0
    expected = pd.to_numeric(completed.get("expected_wins", 0), errors="coerce").fillna(0).sum() if not completed.empty else 0.0
    profit = pd.to_numeric(completed.get("profit_units", 0), errors="coerce").fillna(0).sum() if not completed.empty else 0.0
    roi = (profit / tickets * 100) if tickets else 0.0
    actual_expected = (wins / expected) if expected else 0.0
    average_odds = pd.to_numeric(completed.get("parlay_decimal_odds", 0), errors="coerce").replace(0, pd.NA).dropna().mean() if not completed.empty else 0.0
    median_odds = pd.to_numeric(completed.get("parlay_decimal_odds", 0), errors="coerce").replace(0, pd.NA).dropna().median() if not completed.empty else 0.0
    largest_win = pd.to_numeric(completed.get("profit_units", 0), errors="coerce").fillna(0).max() if not completed.empty else 0.0
    loss_streak = longest_loss_streak(completed)
    profit_without_largest = profit - max(largest_win, 0.0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tickets", f"{tickets}")
    c2.metric("Wins", f"{wins}")
    c3.metric("Expected Wins", f"{expected:.2f}")
    c4.metric("Actual / Expected", f"{actual_expected:.2f}x" if expected else "")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Profit/Loss", f"{profit:+.2f}u")
    c6.metric("ROI", f"{roi:+.2f}%")
    c7.metric("Avg / Median Odds", f"{average_odds:.1f}x / {median_odds:.1f}x" if tickets else "")
    c8.metric("Longest Loss Streak", f"{loss_streak}")
    st.caption(f"Largest win: {largest_win:+.2f}u | Profit without largest win: {profit_without_largest:+.2f}u")

    export = view[available_columns(view, PROSPECTIVE_HISTORY_EXPORT_COLUMNS)].copy()
    st.download_button(
        "Save Prospective History CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name=f"model4_prospective_history_{safe_filename(selected)}.csv",
        mime="text/csv",
        key=f"prospective_history_export_{safe_filename(selected)}",
    )

    view = add_sportsbook_display_columns(view, leg_prefixes=("leg1", "leg2"))
    display = format_prospective_frame(view[available_columns(view, PROSPECTIVE_HISTORY_DISPLAY_COLUMNS)].copy())
    display_dataframe(display, width="stretch", hide_index=True, column_config=prospective_column_config())


def build_prospective_history_frame(project_root: Path) -> pd.DataFrame:
    rows = build_prospective_history_rows(project_root)
    if not rows:
        return pd.DataFrame(columns=PROSPECTIVE_HISTORY_COLUMNS)
    frame = pd.DataFrame(rows)
    for column in PROSPECTIVE_HISTORY_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame


def available_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return [column for column in columns if column in frame.columns]


def format_prospective_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    percent_columns = {
        "naive_market_joint_probability",
        "expected_wins",
        "implied_probability",
        "leg1_implied_probability",
        "leg2_implied_probability",
    }
    parlay_columns = {"parlay_decimal_odds", "independent_parlay_decimal_odds"}
    strength_columns = {"G", "R", "S", "M", "leg1_G", "leg1_R", "leg1_S", "leg1_M", "leg2_G", "leg2_R", "leg2_S", "leg2_M", "consensus", "disagreement", "leg1_consensus", "leg2_consensus", "leg1_disagreement", "leg2_disagreement"}
    for column in output.columns:
        if column in percent_columns:
            output[column] = output[column].map(percent_value)
        elif column in parlay_columns:
            output[column] = output[column].map(lambda value: clean_value(value, parlay_odds=True))
        elif column in strength_columns:
            output[column] = output[column].map(lambda value: decimal_value(value, places=1))
        else:
            output[column] = output[column].map(lambda value: table_value(value, column))
    return output


def percent_value(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return ""
    try:
        number = float(text.replace("%", ""))
    except ValueError:
        return text
    if number != number:
        return ""
    if number > 1:
        return f"{number:.1f}%"
    return f"{number * 100:.1f}%"


def decimal_value(value: object, *, places: int = 2) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    if number != number:
        return ""
    return f"{number:.{places}f}"


def longest_loss_streak(frame: pd.DataFrame) -> int:
    longest = 0
    current = 0
    for value in frame.get("ticket_hit", []):
        if str(value) == "1":
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def prospective_column_config() -> dict[str, object]:
    return {
        "criteria_id": st.column_config.TextColumn("Criteria", width="medium"),
        "criteria_title": st.column_config.TextColumn("Title", width="large"),
        "leg1_player": st.column_config.TextColumn("Leg 1", width="medium"),
        "leg2_player": st.column_config.TextColumn("Leg 2", width="medium"),
        "parlay_decimal_odds": st.column_config.TextColumn("Parlay Odds"),
        "independent_parlay_decimal_odds": st.column_config.TextColumn("Raw Independent"),
        "correlation_factor": st.column_config.TextColumn("Correlation"),
        "correlation_note": st.column_config.TextColumn("Correlation Note", width="large"),
        "naive_market_joint_probability": st.column_config.TextColumn("Market Joint"),
        "expected_wins": st.column_config.TextColumn("Expected Wins"),
        "qualifying_count": st.column_config.TextColumn("Qualifiers"),
        "status": st.column_config.TextColumn("Status"),
        "slate_date": st.column_config.TextColumn("Date"),
        "ticket_hit": st.column_config.TextColumn("Hit"),
        "profit_units": st.column_config.TextColumn("P/L"),
        "running_profit_units": st.column_config.TextColumn("Running P/L"),
        "actual_minus_expected_wins": st.column_config.TextColumn("Actual - Expected"),
        "actual_to_expected_ratio": st.column_config.TextColumn("Actual / Expected"),
        "leg1_result": st.column_config.TextColumn("L1 Result"),
        "leg2_result": st.column_config.TextColumn("L2 Result"),
        "leg1_sportsbook_used": st.column_config.TextColumn("L1 Book"),
        "leg1_sportsbook_odds": st.column_config.TextColumn("L1 Sportsbook Odds"),
        "leg1_book_american_odds": st.column_config.TextColumn("L1 Odds"),
        "leg2_sportsbook_used": st.column_config.TextColumn("L2 Book"),
        "leg2_sportsbook_odds": st.column_config.TextColumn("L2 Sportsbook Odds"),
        "leg2_book_american_odds": st.column_config.TextColumn("L2 Odds"),
        "player": st.column_config.TextColumn("Player", width="medium"),
        "sportsbook_used": st.column_config.TextColumn("Sportsbook"),
        "sportsbook_odds": st.column_config.TextColumn("Sportsbook Odds"),
        "role": st.column_config.TextColumn("Role", width="medium"),
        "qualification_reason": st.column_config.TextColumn("Why", width="large"),
    }


def history_column_config() -> dict[str, object]:
    return {
        "game_date": st.column_config.TextColumn("Date"),
        "lens": st.column_config.TextColumn("Lens", width="medium"),
        "player": st.column_config.TextColumn("Player", width="medium"),
        "result": st.column_config.TextColumn("Result"),
        "actual_hr": st.column_config.TextColumn("HR"),
        "sportsbook_used": st.column_config.TextColumn("Sportsbook"),
        "sportsbook_odds": st.column_config.TextColumn("Sportsbook Odds"),
        "book_american_odds": st.column_config.TextColumn("Book Odds"),
        "profit_1u": st.column_config.TextColumn("P/L"),
        "running_profit_1u": st.column_config.TextColumn("Running P/L"),
        "eye_rank": st.column_config.TextColumn("Eye"),
        "gbm_rank": st.column_config.TextColumn("GBM"),
        "pitcher_batter_rank": st.column_config.TextColumn("Pitch Fit"),
        "model_hr_probability_percent": st.column_config.TextColumn("Model HR%"),
        "edge_percent": st.column_config.TextColumn("Edge%"),
        "eye_score": st.column_config.TextColumn("Eye Score"),
        "accel_score": st.column_config.TextColumn("Accel"),
        "team_abbrev": st.column_config.TextColumn("Team"),
        "opponent_abbrev": st.column_config.TextColumn("Opp"),
        "lineup_status": st.column_config.TextColumn("Lineup"),
        "batting_order": st.column_config.TextColumn("Bat Order"),
    }


if __name__ == "__main__":
    render_app()


