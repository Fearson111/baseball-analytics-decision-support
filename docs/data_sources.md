# Data Sources and Input Contracts

## Model Boards

Four CSVs are supplied by external model projects.

| Filename | Role | Optional score fields |
| --- | --- | --- |
| `gbm_top80.csv` | Model 1 projection | `gbm_probability`, `probability`, `score` |
| `gbm_progression_top80.csv` | Model 1 progression | `progression_score`, `gbm_probability`, `probability`, `score` |
| `sequence_top150.csv` | Model 2 sequence | `motif_score`, `motif_confidence`, `sequence_score`, `hr_probability`, `score` |
| `pitcher_batter_top80.csv` | Model 3 matchup | `matchup_score`, `pitch_shape_score`, `batter_fit`, `pitcher_weakness`, `hr_edge_score`, `score` |

Each file needs player and rank columns. Headers are normalized for case, spaces,
and hyphens. Name/rank aliases are defined in [io.py](../all_seeing_eye/io.py).
Prepare positive integer ranks and one row per player per board.
The parser accepts additional numeric formats; producers remain responsible for
input quality. Missing required files or invalid ranks raise errors, and blank
player rows are skipped.

Optional fields have board-specific meanings. Refer to
[boards.py](../all_seeing_eye/boards.py) and
[scoring.py](../all_seeing_eye/scoring.py) for aliases and normalization.
Normalized strength must not be relabeled as calibrated probability.

## Identity and Timing

The standalone Eye joins on normalized names, not player-game IDs. Duplicate
identities in a board can overwrite earlier entries during merging.
The hub handles doubleheaders by admitting at most one eligible game per hitter
at a time and checking matchup context.

Evaluation needs source timestamps, game/player IDs, and pregame status.
Saved model predictions and refreshed prices can have different observation times.

## Implemented Live Sources

The code includes MLB Stats API schedule/box-score integration and odds adapters
for public comparison, The Odds API, OddsBlaze, and OddsPapi. Public comparison
references ScoresAndOdds and JediBets. This inventory describes code, not verified
current provider availability or guaranteed market coverage.

Missing, expired, and ambiguous observations remain explicit. Credentials use
environment variables or macOS Keychain via
[credentials.py](../all_seeing_eye/daily_hub/credentials.py).
See [markets.py](../all_seeing_eye/daily_hub/markets.py) and adjacent adapters.

## Public Samples and Local Data

All files under `examples/` are hand-authored synthetic CSVs with fictional names.
They contain no licensed feed extracts, personal wagers, or measured results.

Inputs, daily runs, ledgers, rank history, generated research, and caches are
excluded by `.gitignore`. Ignoring files does not delete or back them up, or
remove them from an already published Git history. Source redistribution rights
are not conferred by this repository; real public examples need source-term
review and removal of credentials and personal records.
