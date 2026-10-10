# Daily Workflow

## Offline Example

From the repository root with Python 3.13:

```bash
python3 -m all_seeing_eye --today examples/today --yesterday examples/yesterday --out outputs/example
```

The eight CSVs use fictional players and synthetic ranks. Avery Rising improves
across boards, Morgan Steady remains prominent, Jordan New enters the boards,
Casey Mixed has uneven support, and Sam Previous appears only yesterday.
Read the generated reasoning to inspect their treatment.

Outputs are `outputs/example/all_seeing_eye_board.csv` and
`outputs/example/all_seeing_eye_reasoning.md`. They are ignored by Git.
The example includes no real outcomes and is not a backtest.

## Your Own Inputs

Create a folder with the four CSVs in [Data sources](data_sources.md).
Each needs `player` and `rank`; optional recognized fields enrich scoring.

```bash
python3 -m all_seeing_eye --today inputs/today --out outputs
python3 -m all_seeing_eye --today inputs/today --yesterday inputs/yesterday --out outputs
python3 -m all_seeing_eye --today inputs/today --history inputs/history --out outputs
```

History uses chronologically sortable dated subfolders containing the same
filenames. Without explicit yesterday inputs, the newest history folder supplies
the prior snapshot. Include only dates before the target date: the standalone
loader sorts folders but does not enforce that boundary. The hub separately uses
the three most recent complete prior input days.

Legacy `top80` names are not row limits. Strength anchors remain in
`boards.py`; the CLI output limit defaults to 120 after scoring.

```bash
python3 -m all_seeing_eye.menu
```

The menu supports input selection. Option 3 runs The Closer against an existing
Eye board and its four source CSVs, writing `closer_board.csv` and
`closer_recommendations.md`.

## Full Daily Dashboard

Install [requirements.txt](../requirements.txt), then launch:

```bash
python scripts/launch_daily_baseball.py
```

The launcher chooses an available local port from 8510 through 8529.
Full live runs also need the external GBM, Sequence, and Model 3 projects.
Installing this repository alone does not install those models.
The runner uses Unix file locking; full integration targets macOS/Linux.

### Configure External Projects

Locations are shared through [paths.py](../all_seeing_eye/paths.py). By default,
the app looks for sibling directories named `Homerun_Predictor`,
`sequence_home_run_lab`, and `Model_3` beside this repository. Existing legacy
locations under the user's home directory are detected if the corresponding
sibling is absent, preserving the original local setup.

For other layouts, export absolute paths before starting the app:

```bash
export MODEL4_GBM_DIR="/path/to/Homerun_Predictor"
export MODEL4_SEQUENCE_DIR="/path/to/sequence_home_run_lab"
export MODEL4_MATCHUP_DIR="/path/to/Model_3"
python scripts/launch_daily_baseball.py
```

Replace the example paths with installed project directories. Settings are read
at process startup, so restart an existing dashboard/worker after changing them.
Environment variables take precedence over automatic discovery. A `.env` file
is not loaded automatically.

The dashboard and its background worker use the active Python interpreter.
External model commands also use it by default; if those projects need their
own environment, set `MODEL4_UPSTREAM_PYTHON` to that Python executable's absolute
path. This setting covers upstream commands from both the daily runner and
the tracker. External projects still need their own dependencies and data.

The macOS `Open Daily Baseball.command` launcher resolves this repository from
its own location, preferring `.venv/bin/python`, then `python3` on PATH. For custom
environment settings, launching from the configured terminal is simplest.

Excel export uses `openpyxl` from the installed requirements. For the existing
local setup only, a detected bundled Codex Python remains a fallback. An explicit
`MODEL4_EXCEL_PYTHON` can select another interpreter with `openpyxl`; no bundled
runtime is required for a normal installation.

1. Select a slate date and run daily predictions.
2. Review boards, missing quotes, lineup status, and saved run details.
3. Refresh lineups and odds for new market observations. This reuses saved model
   predictions rather than rerunning upstream models.
4. Inspect financial research separately from raw rankings.
5. Grade final results and retain original pregame observations.

Build From Saved Inputs is a preview, not a new live observation. Posting
visibility is distinct from eligibility and frozen history.
See the [operating reference](../DAILY_BASEBALL_README.md) for all controls.

## Development Checks

```bash
python -B -m unittest discover -s tests -q
```

Requirements cover dashboard/export and test imports. The full sequence audit
also requires external Sequence Lab code/data. The optional tracker
`--use-pybaseball` fallback needs a separate `pybaseball` installation.
Neither is required by the offline example.
Dependency pins reflect the inspected environment, not a full transitive lockfile
or a guarantee of compatibility with external models.
