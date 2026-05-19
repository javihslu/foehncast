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
  orchestration/       # Airflow entry points
  spots/               # Spot metadata and ranking
dags/                  # Airflow DAG definitions
ui/                    # Streamlit dashboard
containers/            # Dockerfiles (6 services)
scripts/               # Bootstrap and helper scripts
terraform/             # GCP infrastructure-as-code
tests/                 # pytest test suite
docs/                  # MkDocs documentation source
config.yaml            # All tuneable parameters
dvc.yaml               # Reproducible pipeline stages
```

## Stats

| Metric | Value |
|--------|-------|
| Python source files | 63 |
| Lines of code | ~10,500 |
| Tests | 452 in ~4s |
| Coverage | 88% |
| Dockerfiles | 6 |
| Shell scripts | 18 |

## How It Fits Together

<div class="mermaid">
flowchart TD
  CODE[src/foehncast] --> APP[Feature + Training + Inference + Monitoring]
  DVC[dvc.yaml] --> REPRO[Reproducible pipelines]
  DAGS[dags] --> ORCH[Airflow scheduling]
  CNT[containers] --> PACK[Docker images]
  UI[ui] --> RIDER[Streamlit UI]
  OPS[scripts + terraform] --> DELIV[Deployment]
  TESTS[tests] --> VERIFY[Automated testing]
  DOCS[docs] --> SITE[This website]
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
| `orchestration/` | Airflow pipeline entry points (feature, training, inference, drift) |
| `monitoring/` | Prometheus exporters, drift detection, prediction logging |
| `spots/` | Spot metadata and ranking logic |

## DVC vs. Airflow

Same Python code, different runners:

| | DVC | Airflow |
|-|-----|---------|
| Purpose | Reproduce results | Schedule and monitor |
| Trigger | `dvc repro` (manual) | Cron or asset-triggered |
| Output tracking | File hashes in `dvc.lock` | Airflow task logs |
| Good for | CI, local experiments | Production scheduling |

## Conventions

- All application logic lives in `src/foehncast/`
- Configuration defaults live in `config.yaml`
- Deployment config lives in environment variables and Terraform
- Data files go under `data/`
- Tests mirror the source structure under `tests/`
