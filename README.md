# Baseball Analytics & Decision Support

I built this project to bring several approaches to home-run prediction into one
daily workflow. A gradient-boosted model produces player projections and a
positive-regression board. A separate Sequence model examines 14 days of hitting
data for changes in contact quality and recurring plate-appearance patterns,
while a matchup model evaluates hitters against opposing pitchers.

Those outputs feed into **All-Seeing Eye**, which compares the rankings, tracks
movement between days, and highlights players whose signals are strengthening
or disagreeing across models.

A downstream **financial decision system** combines model probabilities,
historical signal results, and available sportsbook odds to identify potential
home-run bets. It estimates uncertainty, checks whether the price supports a bet,
and sizes qualifying positions within bankroll and exposure limits.

The dashboard brings the model boards, daily signals, financial decisions, and
recorded results into one place.

## See the Application

![Financial portfolio showing four recorded positions, stakes, remaining budget, and modeled expected ROI](docs/images/financial-portfolio.png)

The portfolio view shows recorded bets, stakes, remaining budget, and exposure
by game. Expected ROI is a model estimate, not a realized return.

[View the daily signal, matchup, and positive-regression boards.](docs/screenshots.md)

## Development

I built this project gradually throughout the 2026 baseball season, adding and
refining its models and tools piece by piece. AI coding assistance supported
implementation, testing, research analysis, and documentation.

## Explore the Work

| Guide | What you will find |
| --- | --- |
| [Screenshots](docs/screenshots.md) | Dashboard and daily board examples |
| [Project overview](docs/model_overview.md) | How the models connect |
| [Running the project](docs/daily_workflow.md) | Setup, sample inputs, and daily workflow |
| [Data sources](docs/data_sources.md) | Where the data comes from and how it is used |
| [Financial system walkthrough](docs/financial_decision_system.md) | How a potential bet is evaluated, with a worked example |
| [Model 1: GBM](docs/model_cards/model_1_gbm.md) | Home-run projections and positive regression |
| [Model 2: Sequence](docs/model_cards/model_2_sequence.md) | Recent hitting trends and recurring plate-appearance patterns |
| [Model 3: Matchup](docs/model_cards/model_3_matchup_regression.md) | Hitter rankings against opposing pitchers |
| [Model 4: All-Seeing Eye](docs/model_cards/model_4_all_seeing_eye.md) | Changes and agreement across model rankings |
| [The Closer](docs/model_cards/closer.md) | A closer review of the Eye's top candidates |
| [Financial model](docs/model_cards/financial_system.md) | Probability estimates, bet selection, stake sizing, and results tracking |

## Run a Small Example

Run the included sample with Python 3.13 from the project folder:

```bash
python3 -m all_seeing_eye --today examples/today --yesterday examples/yesterday --out outputs/example
```

The sample uses fictional players to show how All-Seeing Eye compares rankings
across two days. It runs offline with no additional packages.

Results are saved in `outputs/example/` as a ranked CSV and a Markdown file
explaining each player's ranking.

## What's Included

This repository contains All-Seeing Eye, The Closer, the daily dashboard, the
financial decision system, and their tests.

The GBM, Sequence, and matchup models run in separate projects. Their descriptions
are included here, but their training code and fitted models are not.

## Development Setup

Install the packages and run the tests:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -q
```

GitHub also runs the tests automatically. See
[Running the project](docs/daily_workflow.md) for dashboard setup and connecting
the upstream models. The full daily workflow supports macOS and Linux.

## Repository Layout

```text
all_seeing_eye/    Model 4, dashboard, and financial system
docs/             Model descriptions, guides, and screenshots
scripts/          Launchers and maintenance tools
tests/            Automated tests
examples/         Small sample CSVs
requirements.txt  Python dependencies
```

Detailed operating notes: [Daily Baseball](DAILY_BASEBALL_README.md) ·
[Financial Decision System](FINANCIAL_DECISION_SYSTEM.md)

Daily archives, personal ledgers, and generated outputs are kept locally and are
not included here.
