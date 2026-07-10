# Training Pipeline

The training pipeline reads curated features, generates synthetic quality labels, trains a model, evaluates it, and registers the result in MLflow.

## Steps

<div class="mermaid">
flowchart TD
    CUR["Curated features"] --> LAB["Label quality"]
    LAB --> TRN["Train model"]
    TRN --> EVA["Evaluate"]
    EVA --> REG["Register in MLflow"]
    REG --> ALS["Assign alias (candidate/champion)"]
</div>

| Step | What it does |
|------|-------------|
| Label | Computes synthetic `quality_index` (0–5) from wind + shore features |
| Train | Fits a tree-based model (random forest or gradient boosting) |
| Evaluate | Logs MAE, RMSE, R², bucket accuracy to MLflow |
| Register | Creates versioned model in MLflow registry |
| Alias | Assigns `candidate` or `champion` alias |

## Labeling

Labels are synthetic — no human annotation. The rules use:

- `wind_speed_10m`, `wind_gusts_10m` (rider weight → min rideable wind)
- `wind_steadiness`, `gust_factor` (quality constraints)
- `shore_alignment` (spot-specific wind direction fit)

Dangerous conditions (extreme gusts) force quality to 0. The output is a continuous 0–5 score. All thresholds live in `config.yaml`.

## Data Lineage

Every MLflow run logs where its data came from:

| Logged param | What it tells you |
|-------------|------------------|
| `dataset` | Which named dataset was used |
| `data_hash` | SHA-256 of the training DataFrame |
| `git_commit` | Which code version produced the run |

This bridges DVC → MLflow: DVC versions the parquet, MLflow versions the model, both carry a content hash.

## Model Registry

- Model name: `foehncast-quality`
- Pre-live alias: `candidate`
- Live alias: `champion`
- Promotion/rollback: separate operator controls, not automatic

## DVC Mapping

```yaml
train:
  cmd: python -m foehncast.dvc_stages train
  metrics: [reports/train_metrics.json]
  plots: [reports/feature_importance.png]
```

DVC proves training is reproducible. Alias promotion stays outside DVC — that's an operator action.

## Airflow Integration

The training DAG starts from the feature pipeline's `training-request` asset (not a direct trigger):

<div class="mermaid">
flowchart TD
    FEAT["Feature DAG"] -->|publishes| REQ["training-request asset"]
    REQ -->|triggers| TRAIN["Training DAG"]
    TRAIN -->|emits| REG["registry asset"]
    REG -->|triggers| INF["Inference DAG"]
</div>

This makes the dependency graph visible in Airflow's Assets view.
