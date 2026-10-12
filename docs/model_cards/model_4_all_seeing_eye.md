# Model 4: All-Seeing Eye

## What the Model Does

All-Seeing Eye brings together the GBM projections, positive-regression board,
Sequence model, and matchup rankings to see how each player's signals are
developing across the models.

It compares current rankings with those from the previous three days, looking
for upward movement, new entries, agreement, and disagreement. A player does
not need to rank highly on every board to stand out; emerging support or a
meaningful change can also raise their priority for review.

Because the GBM tends to rank the strongest players near the top each day,
All-Seeing Eye limits how much that consistently high rank alone influences its
score. The goal is to surface a wider range of names with meaningful signals,
giving the user interesting players to investigate rather than repeatedly
showing the same top hitters.

The output is a ranked board with explanations of what drove each player's
score. Those results appear in the daily dashboard and contribute to the
signals evaluated by the financial system.

All-Seeing Eye uses scoring rules rather than a separately trained prediction
model. Its score reflects review priority, not a home-run probability.

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
