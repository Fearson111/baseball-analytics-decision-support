# Model 3: Pitcher/Batter Matchup

## What the Model Does

The matchup model evaluates hitters against the pitcher they are expected to
face that day. It looks at how a hitter's strengths fit the opposing pitcher's
pitch characteristics and weaknesses, incorporating fixed park factors, pitcher
vulnerability, handedness, and batter power.

The goal is not simply to find the best overall matchup, but to identify
situations where those factors create an opportunity for a home run.

Its board provides another perspective alongside the GBM's projections and the
Sequence model's current-form signals. Those rankings feed into All-Seeing Eye
to help identify players with support across the models.

The matchup score is a ranking measure, not a home-run probability.

## Inputs and Outputs

The hub reads `hr_edge_board_DATE.csv` and prepares `pitcher_batter_top80.csv`.
The hub matchup input limit is 150 despite the legacy filename.
Player/rank are required; optional strengths include matchup score, pitch shape,
batter fit, pitcher weakness, and HR edge score.

## Method and Evaluation Status

The interface exposes pitcher/batter or pitch-fit context. Complete feature
construction, estimator, training data, and fitted artifacts are outside this
repository. The upstream model cannot be independently reproduced from this
integration alone. A matchup strength is not necessarily a probability.

## Limitations and References

Pitcher changes and doubleheaders need game-specific alignment. The hub avoids
reusing conflicting matchup context and permits at most one eligible game per
hitter in the name-keyed Eye at a time.

See [runner.py](../../all_seeing_eye/daily_hub/runner.py),
[boards.py](../../all_seeing_eye/boards.py), and
[matchup input tests](../../tests/test_hub_matchup_input.py).
These tests support integration behavior, not predictive accuracy.
