# The Closer

## Purpose and Status

An implemented heuristic step that reranks Eye candidates for further home-run
wager investigation. It does not train a probability model or execute wagers.

## Inputs and Outputs

Inputs are an Eye board and its four model CSVs. Defaults review the top 40 Eye
rows and return up to 20 candidates. `closer_board.csv` and
`closer_recommendations.md` include conviction, decision labels, reasons, and
remaining checks.

## Method

Eye score and GBM, progression, sequence, and matchup strengths are combined
with lineup, price, and movement adjustments. Conviction is bounded from 0 to 99;
80 is not an 80% home-run probability.

## Evaluation and Limitations

[closer.py](../../all_seeing_eye/closer.py) defines the method;
[test_closer.py](../../tests/test_closer.py) checks rules.
Weights are heuristic. Calibration and profitability are not established here.
Results depend on the initial Eye pool, and missing context needs further review.

This is distinct from the financial uncertainty/risk workflow. Run it through
option 3 of `python3 -m all_seeing_eye.menu`.
