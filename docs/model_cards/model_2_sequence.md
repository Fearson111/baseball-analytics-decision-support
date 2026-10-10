# Model 2: Rolling 14-Day Home Run Sequence Lab

## What the Model Tries to Detect

The Sequence model asks: **Does the order and recent direction of a hitter's
contact and plate-appearance results contain information about a home run in
their next game?**

Two hitters can have similar two-week totals but reach them differently. One
might be producing harder airborne contact in recent days, while another's best
contact occurred early in the window. The model represents that timing, looks
for recurring ordered patterns, and combines those signals with an aggregate
power baseline.

Its research hypothesis is that improving contact quality can sometimes precede
visible home-run production. It does not assume a hitter is "due" simply because
they have gone without a home run.

This description is based on inspection of the local Sequence Lab source on
October 9, 2026. The upstream training code, data, and fitted artifacts remain
outside this Model 4 repository.

## Prediction Target and Observation Window

The lead target, `target_hr_next_game`, is binary: did the hitter hit at least
one home run in their next observed game on or after the prediction date?
It is not a next-plate-appearance prediction or an expected home-run count.
The target builder also supports next-three-game and next-five-game horizons,
but those are not the lead configuration described here.

Features use the preceding 14 calendar days of Statcast observations:

- `sequence_d01_*` represents the most recent completed day.
- `sequence_d02_*` represents the day before that.
- `sequence_d14_*` represents the oldest day in the window.

This is a 14-day window, not necessarily 14 games or 14 days with appearances.
Within it, plate appearances are ordered so that both daily trends and
consecutive event patterns can be examined.

## What It Measures

The feature-building system creates several complementary descriptions of a
hitter. Not every available research feature is used in the lead estimator.

| Feature family | What it represents | Role |
| --- | --- | --- |
| Aggregate power baseline | Plate appearances, batted balls, barrels, hard-hit and air-ball rates, pulled air contact, exit velocity, launch angle, distance, and recent HR production | Establishes recent power and sample size without requiring event order |
| Swing trends | Changes in available swing measurements, including bat speed and attack angle | Captures direction of recent mechanics-related measurements |
| Daily contact and result trends | Day-by-day result points, contact quality, airborne exit velocity, and their slopes | Supplies context about improvement or deterioration |
| Hidden-power features | Strong contact that did not become a home run, including non-HR barrels and hard airborne outs | Describes contact quality that the result alone can obscure |
| Compact motifs | Selected short ordered plate-appearance patterns and daily-state patterns | Encodes recurring sequences found in historical research |
| Five-step motifs | Selected sequences of five consecutive plate appearances | Tests a longer ordered context |
| Soft production-ramp rules | Selected combinations of three- or four-day production/contact conditions without an HR in the segment | Captures short developing patterns without demanding one exact PA sequence |

"Hidden power" is an engineered feature name, not a measured reserve of future
home runs. Contact-quality points and rule thresholds are modeling choices.
A rising attack-angle measurement alone is not proof of better hitting.

## How a Sequence Pattern Works

A motif is a recurring ordered pattern. For example, one saved five-step
definition examined in the September audit was:

```text
single -> strikeout -> strikeout -> good-air out -> strikeout
```

The model searches a hitter's ordered plate appearances for a matching sequence.
A "good-air out" is determined by the feature code's contact-quality rules, not
a subjective description of the play. The pattern is an input to the research
system; matching it does not guarantee a home run.

During discovery, candidate patterns are compared using historical support
(the number of matching windows) and future-HR lift relative to a baseline.
Selected patterns are then materialized as model features. The no-prior-HR
motif families exclude a home run **inside the matched pattern**, not necessarily
from the hitter's entire 14-day history.

The September 12 audit recorded 25 compact definitions: 24 exact four-PA
patterns and one three-day state pattern, plus 20 exact five-PA definitions.
Those counts describe the audited dictionaries, not a permanent requirement.

### Recency Matters

The inspected motif code weights matches by age using `exp(-0.28 * age_days)`
and gives zero scoring weight to completions older than eight days. It also
records age/freshness information and whether a motif is newly appearing.
An old match in the 14-day window therefore need not carry the same influence
as a match completed yesterday.

Historical lift is a discovery statistic. It is not a multiplier that can safely
be applied to a player's true probability.

## How the Prediction Is Built

The inspected lead variant is
`baseline_plus_swing_compact_long5_soft_rules`. It uses aggregate baseline,
swing-slope, compact-motif, five-step-motif, and selected soft-rule feature blocks.
The older upstream README names a smaller feature stack; this card follows the
projection script's selected variant.

1. Build historical player-date features and attach next-game outcomes.
2. Select labeled rows with prediction dates before the date being scored.
3. Split those dates chronologically, reserving the most recent 20% by default
   for probability calibration.
4. Fit a median-imputation pipeline with a histogram gradient-boosted classifier.
   The inspected settings use 250 iterations, learning rate 0.035, at most 15
   leaves, L2 regularization 0.10, and random seed 42.
5. Attempt sigmoid calibration on the later segment. If calibration fails,
   the script falls back to uncalibrated probabilities and records that status.
6. Apply probability caps for certain weak-power or small-sample profiles,
   then add a separate scouting-score adjustment and rank the output.

The projection script refits the selected estimator when generating projections.
That is separate from rediscovering the saved motif dictionary.
This is a tree-based model using engineered sequence features, not a recurrent
neural network or transformer.

## Probability Versus Scouting Rank

The output has an important naming distinction:

| Field | Meaning in the inspected projection script |
| --- | --- |
| `calibrated_hr_probability` | Model output after the probability guardrails; calibration may have fallen back, so fit metadata must be checked |
| `sequence_pop_score` | A 0-100 heuristic measure combining fresh motif and contact/trend evidence |
| `sequence_scout_score` | Probability-based score plus sequence/upside bonuses and profile penalties |
| `hr_probability` | Overwritten with `sequence_scout_score` for the final export |
| `projection_rank` | Rank after sorting that final adjusted score |

The pre-scout value is already subject to guardrail caps. The final
`hr_probability` column should therefore **not be described as an untouched,
validated calibrated probability**. Displaying it as a percentage does not
establish calibration after the adjustments.

Scouting adjustments favor fresh sequence evidence and some improving
contact profiles, while damping certain power-only, stale-motif, or
weak-contact profiles. These are explicit heuristics layered on the estimator.

## What an Analyst Receives

The default export contains up to 150 ranked hitters from teams scheduled to
play, with player/team context, score fields, motif matches and freshness,
trend fields, risk tiers, guardrail notes, and readable projection notes.
A scheduled-team filter does not by itself confirm a hitter's starting lineup.

For an illustrative hitter with improving airborne exit velocity, a recent
five-step match, and little recent HR production, the analyst can inspect all
three facts instead of seeing only a rank. The model may increase their scouting
priority, but the magnitude depends on the other features and adjustments.
This example explains behavior; it is not a measured successful prediction.

The hub reads `hr_projection_target_hr_next_game_DATE.csv` and prepares
`sequence_top150.csv`. Model 4 uses the resulting rank and recognized optional
fields as one source of evidence alongside the other boards. It does not retrain
Sequence Lab. See [Data sources](../data_sources.md) for the ingestion contract.

## Evaluation and What Has Been Learned

The saved September 12, 2026 research audit compared motif feature blocks with
an aggregate-plus-swing baseline using distinct player-game observations and
chronological evaluation. Its reported finding was that the old motif families
did not clearly improve recent out-of-sample probability accuracy. Original
discovery lifts weakened after the early discovery period, and no newly mined
pattern passed the audit's complete promotion screen.

The audit also identified repeated next-game targets in calendar-day rows and
target overlap across the inspected production fit/calibration boundary.
Different forecast dates can still refer to the same future game, so splitting
on forecast date alone does not ensure independent target outcomes. These were
documented evaluation concerns; the research audit did not deploy a production
fix or replacement model.

The audit script available here is
[sequence_motif_audit.py](../../scripts/sequence_motif_audit.py).
It includes unique-game filtering, chronological model comparisons, date-block
uncertainty estimates, support requirements, multiple-testing adjustment, and
an exploratory comparison of event order versus the same event counts.
[Helper tests](../../tests/test_sequence_motif_audit.py) cover alignment,
duplicate rejection, and statistical guard behavior.

These findings summarize the saved local audit, not a newly rerun study.
Its underlying datasets and generated report are excluded from this public
repository. Full reproduction needs Sequence Lab and those source artifacts;
the code alone does not provide independently reproducible performance results.

## Source Map and Reproduction Boundary

The following filenames are in the separately stored Sequence Lab project's
`scripts/` directory. They are listed for traceability, not linked as files
included in this repository.

| Upstream script | Responsibility |
| --- | --- |
| `build_sequence_features.py` | Statcast flags, contact/result points, ordered events, trends |
| `build_rolling_14d_sequence_features.py` | Rolling window feature generation |
| `build_sequence_targets.py` | Future-game labels |
| `build_compact_motif_training_features.py` | Selected compact motifs and recency |
| `build_long_motif_training_features.py` | Five-step motif features |
| `build_soft_ramp_rule_features.py` | Selected production-ramp rules |
| `train_sequence_challenger_models.py` | Feature variants and estimators |
| `generate_projection_output.py` | Fit, calibration, guardrails, scouting rank, and exports |

The broader lab includes experimental feature families beyond the lead variant.
Their existence should not be read as evidence that every experiment is deployed
or that sequence order has been shown to add predictive value.
