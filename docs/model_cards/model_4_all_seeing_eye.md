# Model 4: All-Seeing Eye

## Purpose and Status

An implemented heuristic ranking system that prioritizes human review based on
changes across model boards. It is not a separately trained home-run classifier.

## Inputs and Outputs

Four current boards are required. Optional prior-day and historical boards add
movement and persistence context. Outputs are `all_seeing_eye_board.csv` and
`all_seeing_eye_reasoning.md`, with ranks, Eye/acceleration scores, review
priority, signal status, and explanations.

## Method

Rank strength and recognized optional scores combine with movement, new-entry,
convergence, disagreement, and persistence logic. Newly forming evidence can
matter without universal agreement. Persistent obvious signals can be discounted.
See [scoring.py](../../all_seeing_eye/scoring.py) and
[boards.py](../../all_seeing_eye/boards.py) for rules and weights.

GBM and progression share one source layer for coverage. Different layers can
still contain correlated information.

## Evaluation and Limitations

[Scoring tests](../../tests/test_scoring.py) and the
[offline example](../daily_workflow.md) make behavior inspectable.
They do not establish that top-ranked players outperform a baseline.

Scores are review priorities, not probabilities. Name-based joins need one player
per board and care with doubleheaders. Without prior snapshots, movement context
is limited. CLI callers must exclude future/current dates from historical inputs.
