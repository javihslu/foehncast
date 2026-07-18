# Repository

This page explains how the code is organized and where to find things.

## Layout

```text
src/foehncast/         # All application code
  config.py            # Central config loader
  dvc_stages.py        # DVC CLI entry point
  feature_pipeline/    # Ingest → Engineer → Validate → Store
  training_pipeline/   # Label → Train → Evaluate → Register
  inference_pipeline/  # FastAPI app (predict, rank, health)
  monitoring/          # Prometheus metrics, drift detection
  orchestration/       # Pipeline entry points + control-plane abstraction
  spots/               # Spot metadata and ranking
dags/                  # Airflow DAG definitions
ui/                    # Streamlit dashboard
containers/            # Dockerfiles (6 services)
scripts/               # Bootstrap and helper scripts
terraform/             # GCP infrastructure-as-code
tests/                 # pytest test suite
notebooks/             # feat_01_ingest_validation.ipynb — ingest and validation exploration
docs/                  # MkDocs documentation source
config.yaml            # All tuneable parameters
dvc.yaml               # Reproducible pipeline stages
```

## How It Fits Together

Everything converges on `src/foehncast`: the orchestrators invoke it, the containers package it, and the tests cover it.

<div class="mermaid">
flowchart LR
  classDef ctl fill:#f1f5f9,stroke:#475569
  classDef code fill:#e6f4f1,stroke:#0f766e

  DAGS["dags/ (Airflow)"]:::ctl -->|invokes| CODE["src/foehncast"]:::code
  DVC["dvc.yaml (DVC)"]:::ctl -->|invokes| CODE
  UI["ui/ (Streamlit)"]:::ctl -->|imports| CODE
  TESTS["tests/"]:::ctl -->|cover| CODE
  CODE -->|packaged by| CNT["containers/ (Docker images)"]:::ctl
</div>

## Module Map

| Module | What it does |
|--------|-------------|
| `config.py`, `env.py`, `paths.py` | Load config, resolve env vars, path helpers |
| `_bigquery.py` | Shared BigQuery client and helpers |
| `_report_store.py` | Save/load JSON reports (local or GCS) |
| `feature_pipeline/` | Fetch weather data, engineer wind features, validate, store |
| `training_pipeline/` | Label quality, train model, evaluate, register in MLflow |
| `inference_pipeline/` | FastAPI routes: `/predict`, `/rank`, `/spots`, `/health`, `/metrics` |
| `orchestration/` | Pipeline entry points (feature, training, inference, drift) plus the control-plane abstraction over Airflow and Cloud Workflows that the serve API uses to trigger runs and read history |
| `monitoring/` | Prometheus exporters, drift detection, prediction logging |
| `spots/` | Spot metadata and ranking logic |

## DVC vs. Airflow

Same Python code, different runners: DVC reproduces results, Airflow schedules and monitors. The comparison lives on the [Architecture](architecture.md#dvc-vs-airflow) page.

## Conventions

- All application logic lives in `src/foehncast/`
- Configuration defaults live in `config.yaml`
- Deployment config lives in environment variables and Terraform
- Data files go under `data/`
- Tests mirror the source structure under `tests/`
