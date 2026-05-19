# Grading Checklist

Quick reference: what we built and where to find it. Each section maps to 20% of the grade.

## Architecture (20%)

Clean FTI split, feature store, model registry, containerized deployment.

| What | Where |
|------|-------|
| Feature / Training / Inference split | `src/foehncast/feature_pipeline/`, `training_pipeline/`, `inference_pipeline/` |
| Airflow DAGs with asset triggers | `dags/feature_dag.py`, `training_dag.py`, `inference_dag.py` |
| Feature store (Feast) | `feature_repo/` |
| Model registry (MLflow) | Champion/candidate aliases in `training_pipeline/register.py` |
| 6 container services | `containers/` (Airflow, MLflow, app, UI, monitoring, dev) |
| Compose with overlay pattern | `docker-compose.yml` + `objectstore.yml` / `gcp.yml` |
| Local + cloud deployment | `scripts/bootstrap-local.sh`, `terraform/main.tf` |
| Storage abstraction | `feature_pipeline/store.py` switches between S3 and BigQuery |

**Docs**: [Architecture](architecture.md)

## Automation (20%)

Everything runs without manual steps after bootstrap.

| What | Where |
|------|-------|
| CI (7 jobs: shell, lint, terraform, dvc, compose, test, docs) | `.github/workflows/ci.yml` |
| Auto image publishing | Cloud Build triggers (GCP-native, path-filtered) |
| Infrastructure-as-code | `terraform/main.tf` + `terraform.yml` workflow |
| Asset-triggered training | Feature DAG → training-request asset → Training DAG |
| Asset-triggered inference | Model registered → Inference DAG runs batch predictions |
| Pre-commit hooks (8) | `.pre-commit-config.yaml` (ruff, whitespace, YAML, etc.) |
| Bootstrap scripts | `scripts/bootstrap-local.sh`, `scripts/bootstrap-gcp.sh` |
| Runtime release + rollback | Cloud Build triggers + Cloud Run probes (automatic rollback) |

**Docs**: [Delivery Workflow](delivery-and-operator-workflow.md)

## Reproducibility (20%)

Same results on any machine.

| What | Where |
|------|-------|
| DVC pipeline (curate + train) | `dvc.yaml`, `dvc.lock` |
| Tracked outputs | `data/`, `reports/train_metrics.json`, `reports/feature_importance.png` |
| Locked dependencies | `pyproject.toml` + `uv.lock` |
| Pinned containers | `python:3.12-slim`, multi-stage, `uv sync --frozen` |
| Config-driven (no magic numbers) | `config.yaml` has spots, model params, thresholds |
| Data lineage in MLflow | SHA-256 hash + git commit logged per run |
| Local smoke test = CI smoke test | `make smoke-local-evaluator` |

**Docs**: [Feature Pipeline](feature-pipeline.md), [Training Pipeline](training-pipeline.md)

## Code Quality (20%)

Static analysis, tests, and consistent structure.

| What | Where |
|------|-------|
| Linting + formatting | `ruff` via pre-commit and `make lint` |
| 447 tests, 88% coverage, ~4s | `tests/` (57 test files) |
| CI enforces everything | Lint, test, shell checks, terraform validate on every PR |
| Type annotations | `from __future__ import annotations` throughout |
| Clean package structure | Domain subpackages + shared utilities (`_bigquery.py`, etc.) |
| Shell validation | ShellCheck-style checks in CI |

**Docs**: [Repository](repository.md)

## Monitoring (20%)

Prometheus metrics, drift detection, alerting, and visualization.

| What | Where |
|------|-------|
| Custom Prometheus exporters | `monitoring/pipeline_prometheus.py`, `prediction_prometheus.py` |
| Combined `/metrics` endpoint | Feature + training + prediction + drift metrics |
| Drift detection (Evidently) | `monitoring/drift.py` — statistical tests per column |
| Hindcast validation | `monitoring/hindcast.py` — predicted vs. observed |
| Streamlit charts (Altair + PromQL) | `ui/app.py` — system health, drift, pipeline panels |
| 9 alert rules | `prometheus_config/alerting_rules.yml` |
| Prediction event log | `.state/monitoring/prediction-events.jsonl` (local), BigQuery (cloud) |
| Scrape config in version control | `prometheus_config/prometheus.yml` |

**Docs**: [Monitoring](monitoring.md)
