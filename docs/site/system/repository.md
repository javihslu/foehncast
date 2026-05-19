# Repository

The repository keeps runtime code, orchestration, tests, and public documentation separate so the same Feature-Training-Inference split stays visible in both the source tree and the deployment story.

## Main Layout

```text
dvc.yaml
src/foehncast/
  _bigquery.py
  _report_store.py
  config.py
  dvc_stages.py
  feature_pipeline/
  training_pipeline/
  inference_pipeline/
  monitoring/
  orchestration/
  spots/
dags/
containers/
ui/
scripts/
terraform/
feature_repo/
prometheus_config/
tests/
docs/
```

## Codebase Statistics

| Metric | Value |
|--------|-------|
| Source modules | 63 Python files in `src/foehncast/` |
| Source lines | ~10,500 |
| Test files | 43 test modules |
| Test functions | 415 |
| Test suite runtime | ~4 seconds |
| Test-to-source ratio | 1.15× |
| Shell scripts | 18 in `scripts/` |
| Container definitions | 6 Dockerfiles |
| Pre-commit hooks | 8 (trailing whitespace, EOF, YAML, large files, merge conflicts, private keys, ruff lint, ruff format) |

## Repository Roles

<div class="mermaid">
flowchart TD
  CODE[src/foehncast] --> APP[Feature + Training + Inference + Monitoring code]
  DVC[dvc.yaml + dvc_stages.py] --> REPRO[Reproducible feature + training reruns]
  DAGS[dags] --> ORCH[Airflow orchestration]
  CNT[containers] --> PACK[Containerized runtime packaging]
  UI[ui] --> RIDER[Streamlit rider console]
  OPS[scripts + terraform] --> DELIV[Bootstrap and hosted delivery]
  TESTS[tests] --> VERIFY[Regression validation]
  DOCS[docs] --> SITE[Public documentation]
</div>

## Where To Start

- `src/foehncast/`: the application modules for configuration, feature engineering, training, inference, monitoring, and spot metadata.
- `src/foehncast/dvc_stages.py`: the thin CLI entry point that exposes the DVC `curate` and `train` stages.
- `dvc.yaml`: the file-based reproducibility contract for offline feature and training reruns.
- `dags/`: Airflow entry points for the feature, training, and inference workflows.

| Area | What it holds |
|------|---------------|
| `src/foehncast/` | application code for configuration, features, training, inference, monitoring, and spot metadata |
| `dvc.yaml` and `src/foehncast/dvc_stages.py` | reproducible local and CI reruns of the offline feature and training path |
| `dags/` | Airflow entry points for feature, training, and inference workflows |
| `ui/` | Streamlit rider console application |
| `containers/`, `scripts/`, and `terraform/` | runtime packaging, bootstrap helpers, and deployment tooling |
| `feature_repo/` and `prometheus_config/` | Feast and operator-monitoring integration contracts |
| `tests/` and `docs/` | regression coverage and public explanation |

## Source Module Map

The `src/foehncast/` package is organized by domain with shared utilities at the top level:

| Module | Responsibility |
|--------|---------------|
| `config.py`, `env.py`, `paths.py` | Configuration loading, environment variable resolution, path conventions |
| `_bigquery.py` | Shared BigQuery SDK lazy-loading and helpers (used by `store.py` and `monitoring/`) |
| `_report_store.py` | GCS/local JSON report persistence (history, timestamped copies) |
| `_json.py`, `_time.py` | JSON parsing and timestamp utilities |
| `feature_pipeline/` | Ingest, engineer, validate, store curated weather features |
| `training_pipeline/` | Label, train, evaluate, register ML models |
| `inference_pipeline/` | FastAPI serving (predict, rank, spots, health, metrics) |
| `orchestration/` | Airflow pipeline entry points split by domain (feature, training, inference, drift) |
| `monitoring/` | Prometheus exporters, drift detection, prediction logging, pipeline contracts |
| `runtime_release.py` | Runtime release handoff normalization and persistence |
| `pipeline_state.py` | Shared pipeline execution state management |
| `spots/` | Spot metadata and ranking logic |

## DVC Vs Airflow

The repo keeps both because they solve different problems.

- DVC reruns the offline feature and training steps from tracked files.
- Airflow runs the real runtime orchestration with schedules, retries, and asset hand-offs.
- The FastAPI app remains the serving surface for inference instead of becoming another DAG.

## Design Rules

- Keep workload code inside `src/foehncast/`, but keep orchestration, infrastructure, delivery, tests, and docs beside it.
- Keep workload defaults in `config.yaml`, and keep deployment-specific wiring in environment variables and Terraform inputs.
- Keep workload data under `data/`, and keep runtime or integration state under `.state/`.
- Keep operator evidence such as `airflow/reports/` reviewable, but show rendered evidence in public docs instead of live private dashboards.

See [Configuration and Contracts](configuration-and-contracts.md) for configuration ownership, [Architecture](architecture.md) for the system split, and [Monitoring](monitoring.md) for operator evidence.
