# Repository

The repository keeps runtime code, orchestration, tests, and public documentation separate so the same Feature-Training-Inference split stays visible in both the source tree and the deployment story.

## Main Layout

```text
dvc.yaml
src/foehncast/
  config.py
  dvc_stages.py
  feature_pipeline/
  training_pipeline/
  inference_pipeline/
  monitoring/
  spots/
dags/
containers/
scripts/
terraform/
feature_repo/
prometheus_config/
grafana_work/
tests/
docs/
```

## Repository Roles

<div class="mermaid">
flowchart TD
  CODE[src/foehncast] --> APP[Feature + Training + Inference + Monitoring code]
  DVC[dvc.yaml + dvc_stages.py] --> REPRO[Reproducible feature + training reruns]
  DAGS[dags] --> ORCH[Airflow orchestration]
  CNT[containers] --> PACK[Containerized runtime packaging]
  OPS[scripts + terraform] --> DELIV[Bootstrap and hosted delivery]
  TESTS[tests] --> VERIFY[Regression validation]
  DOCS[docs] --> SITE[Public documentation]
</div>

## Where To Start

- `src/foehncast/`: the application modules for configuration, feature engineering, training, inference, monitoring, and spot metadata.
- `src/foehncast/dvc_stages.py`: the thin CLI entry point that exposes the DVC `curate` and `train` stages.
- `dvc.yaml`: the file-based reproducibility contract for offline feature and training reruns.
- `dags/`: Airflow entry points for the feature and training workflows.

| Area | What it holds |
|------|---------------|
| `src/foehncast/` | application code for configuration, features, training, inference, monitoring, and spot metadata |
| `dvc.yaml` and `src/foehncast/dvc_stages.py` | reproducible local and CI reruns of the offline feature and training path |
| `dags/` | Airflow entry points for feature and training workflows |
| `containers/`, `scripts/`, and `terraform/` | runtime packaging, bootstrap helpers, and deployment tooling |
| `feature_repo/`, `prometheus_config/`, and `grafana_work/` | Feast and operator-monitoring integration contracts |
| `tests/` and `docs/` | regression coverage and public explanation |

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
