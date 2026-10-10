from __future__ import annotations

from pathlib import Path
import shutil
import unicodedata

import pandas as pd

from .edge_buckets import build_edge_bucket_active_rows, build_edge_bucket_history_rows, date_key_from_text
from .retired_signals import without_retired_signals
from .tracker import parse_american_odds, parse_float, profit_for_1u
from .paths import SEQUENCE


SEQUENCE_PROJECT_ROOT = SEQUENCE
SEQUENCE_PROCESSED_DIR = SEQUENCE_PROJECT_ROOT / 'data' / 'processed'
SEQUENCE_TARGET = 'target_hr_next_game'
HIGH_LIFT_5_STEP_FLOOR = 3.0

SIGNAL_401_500 = '5-step + contact quality + book +401 to +500'
SIGNAL_301_500_NEG_EDGE = '5-step + contact quality + book +301 to +500 + edge -10% to -5%'
SIGNAL_DEDUP_BUCKETS_HIGH_LIFT = 'Dedup screenshot buckets + high-lift 5-step'
SIGNAL_HIGH_LIFT_GBM_1_10_ODDS_301_400 = 'High-lift 5 + GBM rank 1-10 + odds +301 to +400'
SIGNAL_HIGH_LIFT_GBM_1_25_EDGE_NEG10_0 = 'High-lift 5 + GBM rank 1-25 + edge -10% to 0%'

SIGNAL_RULES = [
    {
        'signal': SIGNAL_401_500,
        'definition': 'Sequence model has an exact 5-step motif, contact quality is ahead of box score, and Model 4 book odds sit from +401 to +500.',
        'research_note': 'Research read: 8 bets, 5 HR, +19.94u, +249.25% ROI in the initial cross-model study.',
        'research_n': 8,
        'research_hr': 5,
        'research_profit_1u': 19.94,
        'research_roi_percent': 249.25,
    },
    {
        'signal': SIGNAL_301_500_NEG_EDGE,
        'definition': 'Sequence model has an exact 5-step motif, contact quality is ahead of box score, Model 4 book odds sit from +301 to +500, and Model 4 edge is -10% to -5%.',
        'research_note': 'Research read: 6 bets, 4 HR, +15.49u, +258.17% ROI. Negative edge is treated as book confirmation inside this sequence pool.',
        'research_n': 6,
        'research_hr': 4,
        'research_profit_1u': 15.49,
        'research_roi_percent': 258.17,
    },
    {
        'signal': SIGNAL_DEDUP_BUCKETS_HIGH_LIFT,
        'definition': 'Player qualifies for any of the screenshot Model 4 edge buckets, counted once per player/day, and the sequence side has a high-lift exact 5-step motif.',
        'research_note': 'Research read: deduped screenshot-bucket overlay with high-lift 5-step evidence, about +12.37u and +123.7% ROI in the initial study.',
        'research_n': 10,
        'research_hr': 5,
        'research_profit_1u': 12.37,
        'research_roi_percent': 123.70,
    },
    {
        'signal': SIGNAL_HIGH_LIFT_GBM_1_10_ODDS_301_400,
        'definition': 'Sequence model has a high-lift exact 5-step motif, Model 4 GBM rank is 1-10, and book odds sit from +301 to +400.',
        'research_note': 'Research read: 11 bets, 5 HR, +11.00u, +100.0% ROI in the GBM top-25 cross-model audit.',
        'research_n': 11,
        'research_hr': 5,
        'research_profit_1u': 11.00,
        'research_roi_percent': 100.00,
    },
    {
        'signal': SIGNAL_HIGH_LIFT_GBM_1_25_EDGE_NEG10_0,
        'definition': 'Sequence model has a high-lift exact 5-step motif, Model 4 GBM rank is 1-25, and Model 4 edge is -10% to 0%.',
        'research_note': 'Research read: 31 bets, 11 HR, +14.49u, +46.7% ROI in the GBM top-25 cross-model audit.',
        'research_n': 31,
        'research_hr': 11,
        'research_profit_1u': 14.49,
        'research_roi_percent': 46.70,
    },
]

SEQUENCE_EDGE_COLUMNS = [
    'signal',
    'game_date',
    'player',
    'team_abbrev',
    'opponent_abbrev',
    'bookmaker_used',
    'book_american_odds',
    'dk_odds',
    'fan_odds',
    '365_odds',
    'edge_percent',
    'eye_rank',
    'gbm_rank',
    'eye_score',
    'model_hr_probability_percent',
    'sequence_projection_rank',
    'sequence_hr_probability',
    'risk_tier',
    'sequence_long5_motif_count',
    'sequence_long5_motif_max_lift',
    'sequence_long5_motif_notes',
    'projection_notes',
    'result',
    'actual_hr',
    'profit_1u',
    'running_profit_1u',
    'signal_note',
]

SEQUENCE_EDGE_SUMMARY_COLUMNS = [
    'signal',
    'active',
    'n',
    'hr',
    'hr_percent',
    'profit_1u',
    'roi_percent',
    'read',
]


def sequence_project_available() -> bool:
    return SEQUENCE_PROCESSED_DIR.exists()


def player_key(value: object) -> str:
    text = str(value or '').strip().casefold()
    normalized = unicodedata.normalize('NFKD', text)
    ascii_text = ''.join(char for char in normalized if not unicodedata.combining(char))
    cleaned = ''.join(char if char.isalnum() else ' ' for char in ascii_text)
    return ' '.join(cleaned.split())


def finite_float(value: object, default: float | None = None) -> float | None:
    parsed = parse_float(value)
    if parsed is None or parsed != parsed:
        return default
    return float(parsed)


def bool_series(frame: pd.DataFrame, column: str, default: bool = False) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index)
    values = frame[column]
    if values.dtype == bool:
        return values.fillna(default)
    text = values.fillna('').astype(str).str.strip().str.lower()
    return text.isin({'1', 'true', 'yes', 'y', 'hr'})


def numeric_series(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index)
    return pd.to_numeric(frame[column], errors='coerce').fillna(default)


def projection_path_for_date(game_date: str) -> Path:
    return SEQUENCE_PROCESSED_DIR / f'hr_projection_{SEQUENCE_TARGET}_{game_date}.csv'


def sequence_history_path() -> Path:
    return SEQUENCE_PROCESSED_DIR / f'projection_results_players_{SEQUENCE_TARGET}_all.csv'


def load_sequence_projection(game_date: str) -> pd.DataFrame:
    path = projection_path_for_date(game_date)
    if not path.exists():
        return empty_sequence_frame()
    return prepare_sequence_frame(pd.read_csv(path, low_memory=False), include_results=False)


def load_sequence_history() -> pd.DataFrame:
    path = sequence_history_path()
    if not path.exists():
        return empty_sequence_frame()
    return prepare_sequence_frame(pd.read_csv(path, low_memory=False), include_results=True)


def empty_sequence_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=['game_date', 'player_key', 'player_name'])


def prepare_sequence_frame(frame: pd.DataFrame, *, include_results: bool) -> pd.DataFrame:
    output = frame.copy().infer_objects(copy=False).fillna('')
    if 'prediction_date' in output.columns:
        output['game_date'] = pd.to_datetime(output['prediction_date'], errors='coerce').dt.strftime('%Y-%m-%d')
    elif 'game_date' in output.columns:
        output['game_date'] = pd.to_datetime(output['game_date'], errors='coerce').dt.strftime('%Y-%m-%d')
    else:
        output['game_date'] = ''
    if 'player_name' not in output.columns:
        output['player_name'] = output.get('player', '')
    output['player_key'] = output['player_name'].map(player_key)
    output['sequence_projection_rank'] = numeric_series(output, 'projection_rank')
    output['sequence_hr_probability'] = numeric_series(output, 'hr_probability')
    output['sequence_long5_motif_count'] = numeric_series(output, 'sequence_long5_motif_count')
    output['sequence_long5_motif_max_lift'] = numeric_series(output, 'sequence_long5_motif_max_lift')
    notes = output.get('projection_notes', pd.Series('', index=output.index)).fillna('').astype(str).str.lower()
    output['has_5_step_motif'] = output['sequence_long5_motif_count'].gt(0)
    output['has_contact_quality_note'] = notes.str.contains('contact quality is ahead of box-score results', regex=False, na=False)
    output['has_high_lift_5_step'] = output['sequence_long5_motif_max_lift'].ge(HIGH_LIFT_5_STEP_FLOOR)
    if include_results:
        output['evaluated'] = bool_series(output, 'evaluated') if 'evaluated' in output.columns else True
        output['actual_hr'] = numeric_series(output, 'actual_hr', 0.0)
        if 'actual_hit_hr' in output.columns:
            output['did_hr'] = numeric_series(output, 'actual_hit_hr', 0.0).gt(0)
        else:
            output['did_hr'] = output['actual_hr'].gt(0)
    return output


def load_board(project_root: Path, game_date: str) -> pd.DataFrame:
    path = project_root / 'MODEL4_DAILY_READS' / game_date / f'MODEL4_{game_date}_BOARD.csv'
    if not path.exists():
        return empty_board_frame()
    return prepare_board_frame(pd.read_csv(path, low_memory=False), game_date=game_date)


def load_all_boards(project_root: Path) -> pd.DataFrame:
    # Sequence-edge rules need original board ranks plus the cleaned odds/results
    # that the tracker adds later. Merge them instead of choosing one source.
    frames = []
    for path in sorted((project_root / 'MODEL4_DAILY_READS').glob('*/MODEL4_*_BOARD.csv')):
        game_date = date_key_from_text(path.parent.name) or path.parent.name
        frames.append(prepare_board_frame(pd.read_csv(path, low_memory=False), game_date=game_date))
    if not frames:
        return empty_board_frame()
    boards = pd.concat(frames, ignore_index=True)
    tracker = load_rank_tracker_board_rows(project_root)
    if tracker.empty:
        return boards

    tracker_cols = [
        'game_date', 'player_key', 'book_american_odds', 'dk_odds', 'fan_odds', '365_odds', 'edge_percent', 'model_hr_probability_percent',
        'model_american_odds', 'bookmaker_used', 'odds_source', 'odds_last_update', 'result_available',
        'result', 'is_void', 'void_reason', 'actual_hr', 'did_hr', 'profit_1u', 'result_source',
    ]
    tracker_cols = [column for column in tracker_cols if column in tracker.columns]
    merged = boards.merge(
        tracker[tracker_cols].drop_duplicates(['game_date', 'player_key']),
        on=['game_date', 'player_key'],
        how='left',
        suffixes=('', '_tracker'),
    )
    for column in tracker_cols:
        if column in {'game_date', 'player_key'}:
            continue
        tracker_column = f'{column}_tracker'
        if tracker_column not in merged.columns:
            continue
        if column not in merged.columns:
            merged[column] = merged[tracker_column]
        else:
            current = merged[column]
            replacement = merged[tracker_column]
            current_blank = current.isna() | current.astype(str).str.strip().isin({'', 'nan', 'None'})
            merged[column] = current.where(~current_blank, replacement)
        merged = merged.drop(columns=[tracker_column])
    return merged


def load_rank_tracker_board_rows(project_root: Path) -> pd.DataFrame:
    path = project_root / 'MODEL4_RANK_TRACKING' / 'model4_rank_results.csv'
    if not path.exists():
        return empty_board_frame()
    frame = pd.read_csv(path, low_memory=False).fillna('')
    if frame.empty or 'game_date' not in frame.columns:
        return empty_board_frame()
    if 'result_available' in frame.columns:
        frame = frame[frame['result_available'].astype(str).eq('1')].copy()
    frame['game_date'] = pd.to_datetime(frame['game_date'], errors='coerce').dt.strftime('%Y-%m-%d')
    frames = []
    for game_date, day in frame.dropna(subset=['game_date']).groupby('game_date', sort=True):
        frames.append(prepare_board_frame(day, game_date=str(game_date)))
    if not frames:
        return empty_board_frame()
    return pd.concat(frames, ignore_index=True)


def empty_board_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=['game_date', 'player', 'player_key'])


def prepare_board_frame(frame: pd.DataFrame, *, game_date: str) -> pd.DataFrame:
    output = frame.copy().infer_objects(copy=False).fillna('')
    output['game_date'] = game_date
    if 'player' not in output.columns:
        output['player'] = output.get('player_name', '')
    output['player_key'] = output['player'].map(player_key)
    for column in ['book_american_odds', 'edge_percent', 'eye_rank', 'eye_score', 'model_hr_probability_percent']:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors='coerce')
    return output


def join_sequence_to_board(sequence: pd.DataFrame, board: pd.DataFrame) -> pd.DataFrame:
    if sequence.empty or board.empty:
        return pd.DataFrame(columns=[*SEQUENCE_EDGE_COLUMNS, 'has_5_step_motif', 'has_contact_quality_note', 'has_high_lift_5_step'])
    seq_cols = [
        'game_date', 'player_key', 'player_name', 'sequence_projection_rank', 'sequence_hr_probability', 'risk_tier',
        'sequence_long5_motif_count', 'sequence_long5_motif_max_lift', 'sequence_long5_motif_notes', 'projection_notes',
        'has_5_step_motif', 'has_contact_quality_note', 'has_high_lift_5_step', 'evaluated', 'actual_hr', 'did_hr'
    ]
    seq_cols = [column for column in seq_cols if column in sequence.columns]
    joined = board.merge(sequence[seq_cols], on=['game_date', 'player_key'], how='inner', suffixes=('', '_sequence'))
    if 'player_name' in joined.columns:
        joined['sequence_player_name'] = joined['player_name']
    return joined


def book_between(frame: pd.DataFrame, low: int, high: int) -> pd.Series:
    odds = pd.to_numeric(frame.get('book_american_odds', pd.Series(index=frame.index)), errors='coerce')
    return odds.ge(low) & odds.le(high)


def edge_between(frame: pd.DataFrame, low: float, high: float) -> pd.Series:
    edge = pd.to_numeric(frame.get('edge_percent', pd.Series(index=frame.index)), errors='coerce')
    return edge.ge(low) & edge.le(high)


def rank_between(frame: pd.DataFrame, column: str, low: int, high: int) -> pd.Series:
    rank = pd.to_numeric(frame.get(column, pd.Series(index=frame.index)), errors='coerce')
    return rank.ge(low) & rank.le(high)


def signal_note(signal: str) -> str:
    return next((row['research_note'] for row in SIGNAL_RULES if row['signal'] == signal), '')


def attach_signal_fields(frame: pd.DataFrame, signal: str) -> pd.DataFrame:
    output = frame.copy()
    output['signal'] = signal
    output['signal_note'] = signal_note(signal)
    if 'result' not in output.columns:
        output['result'] = ''
    if 'actual_hr' not in output.columns:
        output['actual_hr'] = ''
    if 'profit_1u' not in output.columns:
        output['profit_1u'] = ''
    return output


def active_signal_rows(project_root: Path, game_date: str, *, board_override: pd.DataFrame | None = None,
                       bucket_override: pd.DataFrame | None = None) -> pd.DataFrame:
    sequence = load_sequence_projection(game_date)
    board = load_board(project_root, game_date) if board_override is None else prepare_board_frame(board_override, game_date=game_date)
    joined = join_sequence_to_board(sequence, board)
    rows = []
    if not joined.empty:
        base_pool = joined['has_5_step_motif'] & joined['has_contact_quality_note']
        high_lift = joined['has_high_lift_5_step']
        gbm_top10 = rank_between(joined, 'gbm_rank', 1, 10)
        gbm_top25 = rank_between(joined, 'gbm_rank', 1, 25)
        rows.append(attach_signal_fields(joined[base_pool & book_between(joined, 401, 500)], SIGNAL_401_500))
        rows.append(attach_signal_fields(joined[base_pool & book_between(joined, 301, 500) & edge_between(joined, -10, -5)], SIGNAL_301_500_NEG_EDGE))
        rows.append(attach_signal_fields(joined[high_lift & gbm_top10 & book_between(joined, 301, 400)], SIGNAL_HIGH_LIFT_GBM_1_10_ODDS_301_400))
        rows.append(attach_signal_fields(joined[high_lift & gbm_top25 & edge_between(joined, -10, 0)], SIGNAL_HIGH_LIFT_GBM_1_25_EDGE_NEG10_0))

    bucket_rows = active_dedup_bucket_high_lift_rows(sequence, game_date, bucket_override=bucket_override)
    rows.append(bucket_rows)
    rows = [row for row in rows if row is not None and not row.empty]
    if not rows:
        return pd.DataFrame(columns=SEQUENCE_EDGE_COLUMNS)
    active = pd.concat(rows, ignore_index=True)
    active = normalize_output(active, include_running=False)
    return active.sort_values(['signal', 'eye_rank', 'book_american_odds'], ascending=[True, True, True])


def active_dedup_bucket_high_lift_rows(sequence: pd.DataFrame, game_date: str, *, bucket_override: pd.DataFrame | None = None) -> pd.DataFrame:
    if sequence.empty:
        return pd.DataFrame()
    bucket_active = pd.DataFrame(build_edge_bucket_active_rows(game_date)) if bucket_override is None else bucket_override
    if bucket_active.empty:
        return pd.DataFrame()
    bucket_active = bucket_active.copy().fillna('')
    bucket_active['game_date'] = game_date
    bucket_active['player_key'] = bucket_active['player'].map(player_key)
    dedup = bucket_active.sort_values(['game_date', 'player_key', 'signal']).drop_duplicates(['game_date', 'player_key'])
    high_lift = sequence[sequence['has_high_lift_5_step']].copy()
    joined = dedup.merge(high_lift, on=['game_date', 'player_key'], how='inner', suffixes=('', '_sequence'))
    return attach_signal_fields(joined, SIGNAL_DEDUP_BUCKETS_HIGH_LIFT) if not joined.empty else pd.DataFrame()


def historical_signal_rows(project_root: Path) -> pd.DataFrame:
    sequence = load_sequence_history()
    if sequence.empty:
        return pd.DataFrame(columns=SEQUENCE_EDGE_COLUMNS)
    sequence = sequence[sequence.get('evaluated', pd.Series(True, index=sequence.index)).astype(bool)].copy()
    board = load_all_boards(project_root)
    joined = join_sequence_to_board(sequence, board)
    rows = []
    if not joined.empty:
        base_pool = joined['has_5_step_motif'] & joined['has_contact_quality_note']
        high_lift = joined['has_high_lift_5_step']
        gbm_top10 = rank_between(joined, 'gbm_rank', 1, 10)
        gbm_top25 = rank_between(joined, 'gbm_rank', 1, 25)
        rows.append(attach_signal_fields(joined[base_pool & book_between(joined, 401, 500)], SIGNAL_401_500))
        rows.append(attach_signal_fields(joined[base_pool & book_between(joined, 301, 500) & edge_between(joined, -10, -5)], SIGNAL_301_500_NEG_EDGE))
        rows.append(attach_signal_fields(joined[high_lift & gbm_top10 & book_between(joined, 301, 400)], SIGNAL_HIGH_LIFT_GBM_1_10_ODDS_301_400))
        rows.append(attach_signal_fields(joined[high_lift & gbm_top25 & edge_between(joined, -10, 0)], SIGNAL_HIGH_LIFT_GBM_1_25_EDGE_NEG10_0))
    rows.append(historical_dedup_bucket_high_lift_rows(sequence))
    rows = [row for row in rows if row is not None and not row.empty]
    if not rows:
        return pd.DataFrame(columns=SEQUENCE_EDGE_COLUMNS)
    history = pd.concat(rows, ignore_index=True)
    history = normalize_output(history, include_running=True)
    return history.sort_values(['game_date', 'signal', 'player']).reset_index(drop=True)


def historical_dedup_bucket_high_lift_rows(sequence: pd.DataFrame) -> pd.DataFrame:
    bucket_history = pd.DataFrame(build_edge_bucket_history_rows())
    if bucket_history.empty:
        return pd.DataFrame()
    bucket_history = bucket_history.copy().fillna('')
    bucket_history['player_key'] = bucket_history['player'].map(player_key)
    dedup = bucket_history.sort_values(['game_date', 'player_key', 'signal']).drop_duplicates(['game_date', 'player_key'])
    high_lift = sequence[sequence['has_high_lift_5_step']].copy()
    joined = dedup.merge(high_lift, on=['game_date', 'player_key'], how='inner', suffixes=('', '_sequence'))
    return attach_signal_fields(joined, SIGNAL_DEDUP_BUCKETS_HIGH_LIFT) if not joined.empty else pd.DataFrame()


def normalize_output(frame: pd.DataFrame, *, include_running: bool) -> pd.DataFrame:
    output = frame.copy()
    if 'player' not in output.columns:
        output['player'] = output.get('player_name', output.get('player_name_sequence', ''))
    if 'team_abbrev' not in output.columns:
        output['team_abbrev'] = output.get('player_team', '')
    if 'opponent_abbrev' not in output.columns:
        output['opponent_abbrev'] = output.get('opponent', '')
    if 'sequence_long5_motif_notes' not in output.columns and 'sequence_long5_motif_notes_sequence' in output.columns:
        output['sequence_long5_motif_notes'] = output['sequence_long5_motif_notes_sequence']
    if 'projection_notes' not in output.columns and 'projection_notes_sequence' in output.columns:
        output['projection_notes'] = output['projection_notes_sequence']
    if 'risk_tier' not in output.columns:
        output['risk_tier'] = output.get('risk_tier_sequence', '')
    output['actual_hr'] = numeric_series(output, 'actual_hr', 0.0)
    did_hr = output['actual_hr'].gt(0)
    if 'did_hr' in output.columns:
        did_hr = did_hr | bool_series(output, 'did_hr')
    output['result'] = output.get('result', '')
    output.loc[did_hr, 'result'] = 'HR'
    output.loc[~did_hr & output['actual_hr'].notna() & output.get('evaluated', pd.Series(True, index=output.index)).astype(bool), 'result'] = output.loc[~did_hr & output['actual_hr'].notna() & output.get('evaluated', pd.Series(True, index=output.index)).astype(bool), 'result'].replace('', 'No HR')
    if 'profit_1u' not in output.columns or output['profit_1u'].replace('', pd.NA).isna().all():
        output['profit_1u'] = output.apply(lambda row: row_profit(row, bool(did_hr.loc[row.name])), axis=1)
    else:
        output['profit_1u'] = pd.to_numeric(output['profit_1u'], errors='coerce').fillna(output.apply(lambda row: row_profit(row, bool(did_hr.loc[row.name])), axis=1))
    if include_running and not output.empty:
        output = output.sort_values(['signal', 'game_date', 'player']).copy()
        output['running_profit_1u'] = output.groupby('signal')['profit_1u'].cumsum().round(2)
    else:
        output['running_profit_1u'] = ''
    for column in SEQUENCE_EDGE_COLUMNS:
        if column not in output.columns:
            output[column] = ''
    return output[SEQUENCE_EDGE_COLUMNS]


def row_profit(row: pd.Series, did_hr: bool) -> float:
    odds = parse_american_odds(row.get('book_american_odds'))
    if odds is None:
        return 0.0
    return round(profit_for_1u(odds, did_hr), 2)


def summary_rows(active: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rule in SIGNAL_RULES:
        signal = rule['signal']
        hist = history[history['signal'].eq(signal)].copy() if not history.empty else pd.DataFrame()
        active_count = int(active['signal'].eq(signal).sum()) if not active.empty and 'signal' in active.columns else 0
        if not hist.empty:
            bets = len(hist)
            hrs = int(hist['result'].eq('HR').sum())
            profit = pd.to_numeric(hist.get('profit_1u', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()
            roi_percent = round((float(profit) / bets * 100), 2) if bets else 0.0
            read = sequence_stat_sentence(bets, hrs, float(profit))
        elif 'research_n' in rule:
            bets = int(rule['research_n'])
            hrs = int(rule['research_hr'])
            profit = float(rule['research_profit_1u'])
            roi_percent = float(rule['research_roi_percent'])
            read = sequence_stat_sentence(bets, hrs, profit)
        else:
            bets = 0
            hrs = 0
            profit = 0.0
            roi_percent = 0.0
            read = sequence_stat_sentence(bets, hrs, profit)
        rows.append({
            'signal': signal,
            'active': active_count,
            'n': bets,
            'hr': hrs,
            'hr_percent': round((hrs / bets * 100), 2) if bets else 0.0,
            'profit_1u': round(float(profit), 2),
            'roi_percent': roi_percent,
            'read': read,
        })
    return pd.DataFrame(rows, columns=SEQUENCE_EDGE_SUMMARY_COLUMNS)


def sequence_stat_sentence(bets: int, hrs: int, profit: float) -> str:
    roi = (profit / bets * 100) if bets else 0.0
    return f"{bets} bets, {hrs} HR, {profit:+.2f}u, {roi:+.2f}% ROI"


def build_sequence_edge_frames(project_root: Path, daily_folder: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    game_date = date_key_from_text(daily_folder.name) or ''
    saved_active = daily_folder / "sequence_active.csv"
    active = pd.read_csv(saved_active).fillna("") if saved_active.exists() else (active_signal_rows(project_root, game_date) if game_date else pd.DataFrame(columns=SEQUENCE_EDGE_COLUMNS))
    active = without_retired_signals(active)
    history = historical_signal_rows(project_root)
    summary = summary_rows(active, history)
    return active, history, summary


def write_sequence_edge_outputs(project_root: Path, daily_folder: Path, output_folder: Path | None = None) -> Path:
    active, history, summary = build_sequence_edge_frames(project_root, daily_folder)
    destination = (output_folder or daily_folder / 'SEQUENCE_EDGE')
    destination.mkdir(parents=True, exist_ok=True)
    active.to_csv(destination / 'sequence_edge_active.csv', index=False)
    history.to_csv(destination / 'sequence_edge_history.csv', index=False)
    summary.to_csv(destination / 'sequence_edge_summary.csv', index=False)
    pd.DataFrame(SIGNAL_RULES).to_csv(destination / 'sequence_edge_rule_reference.csv', index=False)
    return destination


def build_daily_sequence_edge(output_folder: Path, *, project_root: Path | None = None) -> Path | None:
    project_root = project_root or Path.cwd()
    board = output_folder / 'all_seeing_eye_board.csv'
    if not board.exists() or not sequence_project_available():
        return None
    run_date = pd.Timestamp.now().strftime('%Y-%m-%d')
    daily_folder = project_root / 'MODEL4_DAILY_READS' / run_date
    output = output_folder / 'sequence_edge'
    return write_sequence_edge_outputs(project_root, daily_folder, output)


def save_sequence_edge_daily_copy(sequence_edge_folder: Path) -> Path:
    run_date = pd.Timestamp.now().strftime('%Y-%m-%d')
    daily_folder = Path('MODEL4_DAILY_READS') / run_date / 'SEQUENCE_EDGE'
    daily_folder.mkdir(parents=True, exist_ok=True)
    for source in sequence_edge_folder.glob('*.csv'):
        shutil.copyfile(source, daily_folder / source.name)
    return daily_folder
