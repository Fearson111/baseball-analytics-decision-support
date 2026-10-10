# Baseball Analytics & Decision Support

An MLB home-run research project that turns several model outputs into an
explainable review board, a daily dashboard, and an auditable decision history.
Its central question is: **What changed today that deserves attention?**

The All-Seeing Eye highlights rank acceleration, new entrants, emerging agreement,
and disagreement. A separate financial research layer evaluates probability,
price, uncertainty, and exposure.

## See the Application

![Financial portfolio showing four recorded positions, stakes, remaining budget, and modeled expected ROI](docs/images/financial-portfolio.png)

The financial portfolio groups recorded positions by game and shows stake,
remaining budget, and concentration. The displayed +43.09% is **modeled expected
ROI**, not realized profit; the four positions shown are unsettled.

[Explore all four screenshots](docs/screenshots.md) for the daily signal board,
pitcher/batter matchups, and positive-regression rankings, with notes on how to
interpret their scores and historical statistics.

## Project Ownership and Development

This is my personal baseball analytics project, developed with AI coding
assistance. I use this portfolio to present the baseball questions being explored,
the implemented analysis workflow, and the evidence behind its limitations.
AI assistance has contributed to implementation, testing, research analysis,
and documentation; this is not a claim that I hand-wrote every module.

The work represented here includes integrating model outputs, making rankings
explainable, preserving pregame observations, and separating experimental signals
from price-aware decisions and recorded outcomes. One research lesson is that
strong historical pattern lift does not necessarily survive later evaluation.
Another is that repeated forecasts for the same future game require careful
handling when splitting training and evaluation data.

The source and linked model cards make those decisions inspectable. This repository
contains Model 4 and its downstream tools; the full upstream models are separate
projects. Third-party libraries provide the underlying statistical, data, and UI
components.

## Explore the Work

| Guide | What you will find |
| --- | --- |
| [Application screenshots](docs/screenshots.md) | Four actual interface/export examples with interpretation notes |
| [Model overview](docs/model_overview.md) | Architecture, scope, and code map |
| [Daily workflow](docs/daily_workflow.md) | Runnable example and full local workflow |
| [Data sources](docs/data_sources.md) | CSV contracts, provenance, and limitations |
| [Financial decision system](docs/financial_decision_system.md) | Uncertainty, evaluation, and accounting |
| [Model 1: GBM](docs/model_cards/model_1_gbm.md) | Projection and progression interfaces |
| [Model 2: Sequence](docs/model_cards/model_2_sequence.md) | 14-day Statcast trends, ordered motifs, prediction, and scouting ranks |
| [Model 3: Matchup](docs/model_cards/model_3_matchup_regression.md) | Pitcher/batter signals |
| [Model 4: All-Seeing Eye](docs/model_cards/model_4_all_seeing_eye.md) | Review-priority scoring |
| [The Closer](docs/model_cards/closer.md) | Candidate review after the Eye |
| [Financial model card](docs/model_cards/financial_system.md) | Probability estimation, price checks, risk limits, and audited histories |

## Run a Small Example

From the repository root, using Python 3.13:

```bash
python3 -m all_seeing_eye --today examples/today --yesterday examples/yesterday --out outputs/example
```

This offline example needs only Python's standard library. It uses fictional
players and synthetic ranks, with no credentials or downloads. Read
`outputs/example/all_seeing_eye_reasoning.md` for explanations or inspect
`outputs/example/all_seeing_eye_board.csv`.

The example contrasts rising, consistently prominent, newly appearing, and
mixed-support players. It demonstrates behavior, not predictive accuracy.

## Engineering and Analysis

- Integrates four ranked CSV boards with optional numeric and contextual fields.
- Separates review priority from probability and price-based decisions.
- Preserves snapshots and distinguishes retrospective research, forward
  observations, and recorded wagers.
- Handles missing quotes, lineup changes, and ambiguous game identities.
- Includes unit and regression tests for scoring, history, accounting, and UI.

Models 1-3 run in external projects whose training code and fitted artifacts are
not included here. Their cards document the interfaces visible in this repository.
The Eye and Closer are heuristic rankings, not calibrated home-run probabilities.
This portfolio makes no independently verified predictive-performance or
profitability claim.

## Development Setup

The dashboard and complete test suite need additional packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -q
```

The GitHub workflow runs the tests and example on Ubuntu with Python 3.13.
The full daily runner uses Unix file locking and configurable upstream paths;
see the [workflow guide](docs/daily_workflow.md) for integration requirements.

## Repository Layout

```text
Model_4/
  README.md
  docs/
    model_overview.md
    daily_workflow.md
    financial_decision_system.md
    data_sources.md
    model_cards/
      model_1_gbm.md
      model_2_sequence.md
      model_3_matchup_regression.md
      model_4_all_seeing_eye.md
      closer.md
      financial_system.md
  all_seeing_eye/       # Source code
  scripts/             # Launchers and maintenance scripts
  tests/               # Unit and regression tests
  examples/            # Small synthetic CSVs only
  .github/workflows/tests.yml
  .gitignore
  requirements.txt
```

Existing detailed operating references remain in
[Daily Baseball](DAILY_BASEBALL_README.md) and
[Financial Decision System](FINANCIAL_DECISION_SYSTEM.md).
Local archives, personal ledgers, and generated outputs are excluded from Git.
