# Model 1: Home-Run Projections and Positive Regression

The gradient-boosted model provides the starting point for the daily analysis:
player home-run projections and a separate positive-regression board.

It uses Statcast CSV data going back up to three years. Built-in player-level
adjustments are designed to let rankings respond to meaningful changes while
limiting how much a small sample can shift the model's view of a player.

The projection board ranks players by their estimated home-run probability.
The positive-regression board highlights players whose underlying indicators
suggest more home-run potential than their recent results show.

Both boards feed into All-Seeing Eye, where they are compared with the Sequence
and matchup rankings. The financial system also uses the GBM's home-run
probabilities when evaluating sportsbook prices.

The GBM runs in a separate project. This repository contains the code that
imports and uses its daily outputs, but not its training code or fitted model.

## How Positive-Regression Scoring Works

The regression board looks for hitters whose contact quality and power profile
suggest more home-run potential than their recent results show. It uses a
separate, rule-based score rather than simply repeating the GBM projection order.

The score combines:

- **Power and underperformance:** the player's projected and established
  home-run ability, plus the gap between predicted and actual home-run rates.
- **Contact without matching results:** recent barrels, hard-hit balls, and
  batted-ball distance compared with home-run production over the last 14 days.
- **Improving contact:** expected slugging on contact and changes across
  three-, seven-, and 14-day windows, along with improving barrel, fly-ball,
  and air-ball rates.
- **Pitcher context:** the opposing pitcher's contact vulnerability and recent
  rates of barrels, fly balls, and air balls allowed.

For example, four or more barrels with no home runs in the last 14 days adds
10 points to the barrel-pressure component before other adjustments. No barrels
and no home runs subtracts three points from that component: a drought alone
is not enough to make a hitter a strong candidate.

Several recent-contact components are scaled by plate appearances, reaching
full weight at 35 plate appearances over 14 days. Component caps limit how much
one signal can contribute. Cooling contact and cold streaks in players with
limited history can lower the score.

The board also responds as results change. A home run yesterday reduces some
of the regression credit, while repeated appearances near the top of the board
receive less weight unless fresh contact evidence supports them.

The final score adds these components and subtracts the penalties, then ranks
eligible hitters. It is a scouting score, not a home-run probability or a claim
that a player is "due." Sportsbook price is evaluated separately by the
financial system.

## Daily Outputs

The dashboard imports `daily_hr_projections_DATE.csv` and
`daily_positive_regression_targets_DATE.csv` as `gbm_top80.csv` and
`gbm_progression_top80.csv`. Both boards come from the GBM, not two independent
models. The filenames are retained for compatibility; full lists are accepted.

See [data sources](../data_sources.md) for input fields and
[runner.py](../../all_seeing_eye/daily_hub/runner.py) for the import workflow.
