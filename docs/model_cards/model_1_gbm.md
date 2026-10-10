# Model 1: GBM

## Role and Availability

An upstream home-run projection system called GBM by the integration. Its source
project and fitted artifacts are external. This card documents the observable
interface, not a verified training architecture.

## Inputs and Outputs

The hub reads dated `daily_hr_projections_DATE.csv` and
`daily_positive_regression_targets_DATE.csv`. They become `gbm_top80.csv` and
`gbm_progression_top80.csv`. Both belong to the GBM layer, not two independent
models. Full lists are accepted despite the legacy filenames.

Player/rank are required; optional probabilities and scores are described in
[Data sources](../data_sources.md). Available base probabilities also support
downstream financial research.

## Method and Evaluation Status

Training features, estimator configuration, training dates, label definition,
and model-level validation are not established by this repository.
Those require upstream documentation before claiming reproducible training or
accuracy. Integration tests do not validate probability calibration.

## Limitations and References

Market refreshes reuse predictions with their original observation time.
Missing base probability blocks financial BET eligibility.
See [runner.py](../../all_seeing_eye/daily_hub/runner.py) and
[boards.py](../../all_seeing_eye/boards.py).
