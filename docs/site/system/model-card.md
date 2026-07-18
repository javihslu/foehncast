# Model Card: foehncast-quality

`foehncast-quality` is the regression model behind FoehnCast's spot ranking. It predicts a ride-quality score (0–5) per spot and forecast hour from weather features. This card describes what the model is, what it is for, and where its limits are.

## Model Details

| Item | Value |
|------|-------|
| Type | `RandomForestRegressor` (scikit-learn), 200 trees |
| Algorithm switch | `model.algorithm` in `config.yaml` (`random_forest` or `gradient_boosting`) |
| Target | `quality_index`, continuous 0–5 |
| Registry | MLflow model `foehncast-quality` |
| Aliases | `candidate` (pre-live), `champion` (live) |

All feature and training settings live in the `model` section of `config.yaml`.

## Intended Use

The model ranks the six configured Swiss kiteboarding spots up to 14 hours ahead, as decision support for "is the drive worth it". Its score is one input to the final ranking, combined with drive time and rider preferences.

Out of scope:

- Safety decisions. The model does not replace checking conditions on site.
- Spots or regions beyond the configured Swiss lake spots.
- Horizons beyond 14 hours.

## Training Data and Labels

Training data comes from Open-Meteo weather forecasts, engineered into features by the feature pipeline and versioned as parquet with DVC.

Labels are synthetic: a rule set computes `quality_index` from wind speed, gusts, steadiness, and shore alignment. Dangerous conditions (extreme gusts) force the label to 0. There is no human annotation. All labeling thresholds live in the `labeling` section of `config.yaml`.

## Features

The model uses 14 features, selected in `config.yaml`:

- Raw forecast: `wind_speed_10m`, `wind_speed_80m`, `wind_gusts_10m`, `temperature_2m`, `relative_humidity_2m`
- Cyclic time encodings: `hour_of_day_sin`/`_cos`, `day_of_year_sin`/`_cos`
- Wind direction encodings: `wind_direction_10m_sin`/`_cos`
- Engineered: `wind_steadiness`, `gust_excess_10m`, `shore_alignment`

## Evaluation

Each training run holds out 20% of the data (`test_size: 0.2`, fixed random seed) and logs MAE, RMSE, R², and quality-bucket accuracy to MLflow. DVC snapshots the same metrics in `reports/train_metrics.json`.

All estimator and split randomness flows from `model.random_state` in `config.yaml`: it seeds the forest and boosting estimators, `train_test_split`, and numpy's global RNG at both training entry points. No code uses Python's `random` module, `PYTHONHASHSEED=0` is pinned at the process boundaries (the DVC stage command and the Airflow image), and provenance hashing is SHA-256, so it is independent of hash randomization. Two runs with the same seed on the same curated data produce identical training metrics.

For current numbers, check the run behind the `champion` alias in MLflow rather than any single snapshot. Because labels are rule-based, a training window with little wind variation produces near-constant labels and trivially good metrics; judging model quality requires looking at the data window a run was trained on. The committed July 2026 snapshot is such a window: 1007 of its 1008 curated rows share one label, so the snapshot's error metrics collapse to zero.

Beyond held-out metrics, a registered `candidate` is shadow-scored against the `champion` on live inference batches, so its divergence from the served model is visible before any promotion.

## Versioning and Lineage

Every MLflow run logs `dataset`, `data_hash` (SHA-256 of the training DataFrame), and `git_commit`. DVC versions the data, MLflow versions the model, and the shared hash links the two. New versions register as `candidate`; the first version ever also bootstraps `champion` so serving can start. After that, promotion from `candidate` to `champion` is a manual operator action, described in the [Training Pipeline](training-pipeline.md) and the [Operator Runbook](delivery-and-operator-workflow.md).

## Limitations

- The model learns the labeling rules' view of quality, not observed ride quality. It is only as good as those rules.
- It is trained per the six configured spots and will not generalize to other locations without new spot data and retraining.
- Predictions inherit forecast errors from the weather API.
- Hindcast validation (see [Monitoring](monitoring.md)) compares past predictions against later observations, which partially checks the rules against reality.
