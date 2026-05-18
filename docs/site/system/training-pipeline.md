# Training Pipeline

FoehnCast keeps training downstream from the curated feature store. The training path reads stored curated rows, rebuilds schema-derived features when needed, generates synthetic rideability labels, trains the configured regressor, writes evaluation evidence, and registers a versioned model in MLflow without pushing training concerns back into the feature pipeline.

This page describes what each stage owns and what remains an explicit operator control rather than an automatic side effect.

!!! note "Scope"

    This page describes the validated training-path contract.
    It focuses on what the training path owns.
    Hosted orchestration may move, but the training contract described here stays the same.

## Pipeline Shape

<div class="mermaid">
flowchart TD
    CUR["Curated feature store asset"] --> LAB["Label curated rows"]
    REQ["Training-request asset"] --> LAB
    LAB --> TRN["Train model"]
    TRN --> EVA["Generate evaluation report"]
    EVA --> REG["Register model version"]
    REG --> ALS["Assign requested alias"]
    OPS["Promote and rollback controls"] --> ALS
</div>

The training path stays explicit:

- curated features arrive from the feature pipeline instead of being rebuilt from raw ingest
- labeling owns the synthetic target definition
- training owns model fitting and metric logging
- evaluation owns reviewable reporting
- registration owns versioning and alias assignment in MLflow
- promotion and rollback stay separate operator controls even though they reuse the same registry aliases

## Runtime Role

| Runtime mode | Training role |
|------|---------------------|
| Local evaluator | local Airflow and MLflow run labeling, training, evaluation, and registration |
| Active shared environment | the hosted full-stack operator lane runs the same Airflow and MLflow contract online |
| Hosted inference target | serves a registered alias; it does not run training |

## DVC Mapping

For reproducible local and CI runs, DVC models the offline training path as one `train` stage.

| DVC stage | Covers | Writes |
|------|--------|--------|
| `train` | label, train, and evaluate | `reports/train_metrics.json` and `reports/feature_importance.png` |

Model registration, alias movement, and rollback stay outside `dvc repro`. Those remain MLflow- and operator-controlled runtime steps.

## Stage Responsibilities

| Stage | Main responsibility | Must not become |
|------|----------------------|-----------------|
| Label | turn curated feature rows into a synthetic `quality_index` target | a replacement for feature engineering or a hidden scoring service |
| Train | fit the configured model and log reproducible run metrics | a place where registry promotion or serving logic leaks in |
| Evaluate | write reviewable metrics and report artifacts for one run | a second training stage or a silent model selector |
| Register | create a versioned MLflow model and assign the requested alias | a broad deployment control plane |
| Promote and rollback | move explicit aliases between validated model versions | retraining, relabeling, or feature regeneration |

## Label Boundary

### Data Lineage

Every MLflow training run logs provenance params so the model can be traced back to its input data:

| Param | Source | What it tells you |
|-------|--------|-------------------|
| `dataset` | config argument | which named dataset split was used |
| `data_hash` | SHA-256 of the training DataFrame | whether the data content changed between runs |
| `git_commit` | `git rev-parse --short HEAD` | which code version produced the run |

The DVC path in `dvc_stages.py` writes `data_hash` and `git_commit` into the `reports/train_metrics.json` file for the same traceability outside MLflow.

This bridges the DVC→MLflow lineage gap: DVC versions the curated parquet files, MLflow versions the model, and both carry a content hash so you can match them without inspecting local DVC state.

## Label Boundary

Labeling is synthetic and physics-driven, not human-curated. The label contract depends on curated wind and shoreline features that already exist in the stored dataset:

- `wind_speed_10m`
- `wind_gusts_10m`
- `wind_steadiness`
- `gust_factor`
- `shore_alignment`

The label rules combine rider profile settings with configured wind bands from `config.yaml`.

The important design choices are:

- dangerous wind and gust conditions are forced to the non-rideable bucket
- the minimum rideable wind threshold depends on rider weight
- high-quality windows depend on both wind range and quality constraints such as gust factor, shoreline fit, and steadiness
- the output stays a stable `0` to `5` `quality_index` target that downstream training and evaluation can compare directly

This means labeling is part of the training contract, not part of the inference service. The app serves predictions from a trained model; it does not recompute the synthetic label rules on demand.

## Training Boundary

Training reads stored curated feature rows by spot and dataset, then labels them directly. The curated storage contract is expected to already include the engineered columns required by labeling and the configured model feature list.

The training contract is:

- the input comes from stored curated features, not raw forecast payloads
- stored curated rows must already satisfy the validated feature schema used by labeling and training
- training does not rebuild missing derived columns from partial stored slices
- the configured feature list and target column remain explicit in `config.yaml`
- the supported model families are tree-based, with `random_forest` and `gradient_boosting` as the supported algorithms
- one MLflow run records parameters, regression metrics, class-bucket accuracy metrics, row counts, feature counts, and a feature-importance plot when the estimator exposes importances

Training should stay narrow. It fits a model and records one reproducible run. It should not decide traffic rollout or silently rewrite registry aliases beyond the requested registration stage.

## Evaluation Boundary

Evaluation resumes the same MLflow run after training and turns its metrics into a reviewable artifact.

The evaluation contract is:

- regression metrics include `mae`, `rmse`, and `r2`
- rounded class-bucket accuracy is logged alongside the regression metrics
- the markdown evaluation report is written under `airflow/reports/` as `evaluation-<run_id>.md`
- the same report is logged back into MLflow as an artifact

This keeps evaluation visible outside the notebook path. Reviewers and operators can inspect a persisted markdown report instead of depending on an ad hoc interactive session.

## Registration Boundary

Registration converts one logged MLflow run into a named registry version and assigns the requested alias.

The registry contract is:

- the registered model name is `foehncast-quality`
- the validated pre-live alias is `candidate`
- the live-serving alias is `champion`
- training summaries persist run-level metrics, row counts, report paths, stage durations, and the registered version so the monitoring surface can expose the latest training state

Manual training runs default to the `Candidate` stage. Asset-triggered runs from the feature pipeline can request `Production`, which lets the asset flow produce a live-ready registration path without changing the training code itself.

## Airflow Hand-Off

The training DAG is scheduled from the feature pipeline's published training-request asset instead of a direct DAG-to-DAG trigger.

That keeps the orchestration boundary visible:

- the feature DAG publishes curated-feature and training-request assets after persistence succeeds
- the training DAG consumes the curated feature store and the training request
- the training DAG emits MLflow training-run, evaluation-report, and model-registry assets
- dataset and stage can still be overridden through DAG config when needed

This makes the Airflow Assets view reflect the real dependency graph between curated feature persistence, training, evaluation, and registration. The local evaluator runs those steps directly in Airflow, while the hosted cloud path preserves the same training-stage ownership even when serving and scheduled automation move onto Cloud Run and Cloud Workflows.

## Alias Controls Outside The DAG

Promotion and rollback are explicit controls layered on top of the registry aliases, not hidden inside normal training.

The operator controls are:

- `foehncast.training_pipeline.promote` can move an explicit version or the `candidate` alias to the production stage
- `foehncast.training_pipeline.rollback` can restore the `champion` alias to an explicit previous version
- the same alias contract is reused by the shared cloud operator workflows and by the serving path that loads the live alias

That separation is deliberate. Training can succeed without immediately changing the live serving version, and rollback can happen without retraining.

## Why This Structure Works

- it keeps training downstream from the curated feature contract instead of duplicating feature logic
- it preserves reviewable evidence through MLflow runs and markdown evaluation reports
- it keeps candidate and champion semantics explicit in the registry rather than buried in deployment scripts
- it makes automatic retraining visible in Airflow through asset hand-offs instead of opaque trigger chains
- it keeps the training contract stable even while the hosted orchestration surface is being simplified

See [Architecture](architecture.md), [Feature Pipeline](feature-pipeline.md), [Monitoring](monitoring.md), and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the surrounding system boundaries.
