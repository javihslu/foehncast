# Grading Checklist

This page maps each grading dimension to concrete evidence in the repository. Use the links to verify coverage directly.

## Architecture (20%)

FoehnCast follows a Feature-Training-Inference (FTI) split with clear module boundaries, a feature store, a model registry, and container-based deployment.

| Claim | Evidence |
|-------|----------|
| FTI pipeline separation | `src/foehncast/feature_pipeline/`, `src/foehncast/training_pipeline/`, `src/foehncast/inference_pipeline/` |
| Airflow orchestration with asset-based hand-offs | `dags/feature_dag.py`, `dags/training_dag.py`, `dags/inference_dag.py`, `dags/runtime_release_dag.py` |
| Feature store (Feast) | `feature_repo/feature_store.yaml`, `feature_repo/features.py` |
| Model registry (MLflow) | Champion/candidate alias promotion in `src/foehncast/training_pipeline/register.py` |
| Containerized services | 8 container definitions in `containers/` (Airflow, MLflow, app, UI, monitoring, development) |
| Modular Compose with includes | `docker-compose.yml` includes from `docker_includes/` and `containers/` |
| Local and cloud runtime lanes | `scripts/bootstrap-local.sh` (local), `scripts/bootstrap-gcp.sh` + Terraform (cloud) |
| Cloud Run serving + Cloud Composer orchestration | `terraform/main.tf`, `.github/workflows/publish-app-image.yml` |
| Storage abstraction (S3/BigQuery) | `src/foehncast/feature_pipeline/store.py` with backend selection |

**Docs**: [Architecture](architecture.md), [Cloud Mapping](cloud-mapping.md)

## Automation (20%)

CI/CD, infrastructure-as-code, and pipeline scheduling run without manual steps after initial bootstrap.

| Claim | Evidence |
|-------|----------|
| CI pipeline (7 jobs) | `.github/workflows/ci.yml` — shell, lint, terraform, dvc, compose, test, docs |
| Automated image publishing | `.github/workflows/publish-app-image.yml`, `publish-runtime-images.yml` |
| DAG bundle publishing to Composer | `.github/workflows/publish-composer-dags.yml` |
| Runtime release trigger | `.github/workflows/trigger-runtime-release.yml` |
| Infrastructure-as-code (Terraform) | `terraform/main.tf`, `terraform/providers.tf`, `terraform/outputs.tf`, `terraform/versions.tf` |
| Cloud Build configs | 4 configs in `cloudbuild/` |
| Bootstrap scripts | `scripts/bootstrap-local.sh`, `scripts/bootstrap-gcp.sh` (19 scripts total) |
| Asset-triggered training | Feature DAG publishes training-request asset → Training DAG auto-starts |
| Asset-triggered inference | Training DAG registers model → Inference DAG auto-runs |
| Pre-commit hooks | `.pre-commit-config.yaml` — 8 hooks including ruff lint and format |

**Docs**: [Delivery and Operator Workflow](delivery-and-operator-workflow.md), [Composer DAG Validation](composer-dag-validation.md)

## Reproducibility (20%)

DVC pipelines, locked dependencies, and container-based execution make runs repeatable across machines.

| Claim | Evidence |
|-------|----------|
| DVC pipeline with two stages | `dvc.yaml` — `curate` (features) and `train` (model) |
| Tracked data and metrics | `dvc.lock`, `data/`, `reports/train_metrics.json`, `reports/feature_importance.png` |
| Deterministic Python dependencies | `pyproject.toml` + `uv.lock` (uv package manager) |
| Container-pinned environments | `containers/*/Dockerfile` — `python:3.12-slim`, multi-stage builds, `uv sync --frozen` |
| Reproducible Make targets | `Makefile` — `make install`, `make dvc-validate`, `make bootstrap-local` |
| Data lineage in MLflow | `data_hash` (SHA-256), `git_commit` logged per training run |
| Config-driven workload | `config.yaml` owns spots, rider profile, model features, labeling bands, ranking weights |
| Seed and split ratio pinned | `model.seed` and `model.test_size` in `config.yaml` |
| Local smoke test | `make smoke-local-evaluator` runs in CI and locally |

**Docs**: [Feature Pipeline](feature-pipeline.md), [Training Pipeline](training-pipeline.md), [Configuration and Contracts](configuration-and-contracts.md)

## Code Quality (20%)

Static analysis, a large test suite, and consistent project structure enforce quality.

| Claim | Evidence |
|-------|----------|
| Linting and formatting | `ruff` configured in `pyproject.toml`, enforced via `make lint` and pre-commit |
| Test suite | 44 test files in `tests/` covering pipelines, orchestration, config, monitoring, and CI contracts |
| CI enforcement | `ci.yml` runs lint, test, shell checks, and Terraform validate on every push and PR |
| Type annotations | `from __future__ import annotations` throughout `src/foehncast/` |
| Clean package structure | `src/foehncast/` with dedicated subpackages per domain |
| Pre-commit hooks | Trailing whitespace, EOF fix, YAML check, merge conflict detection, private key detection, ruff lint, ruff format |
| Shell script validation | `ci.yml` shell job checks scripts with ShellCheck-style validation |
| Module docstrings | Each pipeline module documents its boundary and responsibility |

**Docs**: [Repository](repository.md)

## Monitoring (20%)

Prometheus metrics, Grafana dashboards, drift detection, hindcast validation, and alerting rules form a complete observability stack.

| Claim | Evidence |
|-------|----------|
| Custom Prometheus exporters | `src/foehncast/monitoring/pipeline_prometheus.py`, `prediction_prometheus.py` |
| Composed `/metrics` endpoint | Feature, training, prediction, sync, and hindcast metrics on one scrape target |
| Drift detection (Evidently) | `src/foehncast/monitoring/drift.py` — column-level statistical tests, StatsD export |
| Hindcast validation | `src/foehncast/monitoring/hindcast.py` — predictions vs. observed weather |
| 3 Grafana dashboards | `grafana_work/dashboards/` — Rider, Operations, ML Diagnostics |
| 9 Prometheus alert rules | `prometheus_config/alerting_rules.yml` — AppDown, HighRequestLatency, FeaturePipelineStageFailure, etc. |
| Prediction event history | `.state/monitoring/prediction-events.jsonl` (local), BigQuery `prediction_events` table (cloud) |
| Pipeline summary evidence | `airflow/reports/feature-pipeline-*-latest.json`, `training-pipeline-*-latest.json` |
| Scrape config version-controlled | `prometheus_config/prometheus.yml` — 4 scrape targets |

**Docs**: [Monitoring](monitoring.md)
