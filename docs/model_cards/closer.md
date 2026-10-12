# The Closer

## What It Does

The Closer takes a second look at All-Seeing Eye's leading candidates to narrow
the list for further home-run bet research.

It combines each player's Eye score with their GBM, positive-regression,
Sequence, and matchup signals, then applies adjustments for available lineup
information, price, and ranking movement.

By default, it reviews the top 40 Eye candidates and returns up to 20 players,
with a conviction score, reasons for their placement, and any remaining checks.

The Closer helps decide which players deserve a closer look. The separate
financial system evaluates whether the available odds justify a bet and how
much to stake. The Closer's conviction score is a ranking measure, not a
home-run probability.

## Inputs and Outputs

Inputs are an Eye board and its four model CSVs. Results are saved as
`closer_board.csv` and `closer_recommendations.md`. Conviction scores range
from 0 to 99.

## Evaluation and Limitations

[closer.py](../../all_seeing_eye/closer.py) defines the method;
[test_closer.py](../../tests/test_closer.py) checks rules.
Weights are heuristic. Calibration and profitability are not established here.
Results depend on the initial Eye pool, and missing context needs further review.

This is distinct from the financial uncertainty/risk workflow. Run it through
option 3 of `python3 -m all_seeing_eye.menu`.
