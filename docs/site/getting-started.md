# Getting Started

This page keeps setup intentionally simple. The supported contributor path is the local evaluator flow with Docker. The shared cloud path is maintainer-only and documented separately.

## Local Evaluator

This is the default path for a fresh machine.

1. Install Docker.
2. Clone the repository.
3. Run `./scripts/bootstrap-local.sh`.

You do not need `gcloud`, Terraform, GitHub Actions variables, or a local compiler toolchain for this path.

The local evaluator path bundles MinIO for curated features and MLflow artifacts, the Datastore-mode emulator for Feast online serving, and the checked-in Prometheus, StatsD exporter, and Grafana stack. The bootstrap waits for the feature-to-training hand-off, verifies Grafana starter resources, and prints alternate endpoints automatically if the default ports are already busy. The optional `development_env` notebook container stays off unless you explicitly target notebook or dev-shell commands. See [Local Evaluator](system/local-evaluator.md) for the full runtime contract.

If you maintain the shared cloud environment, use [Delivery and Operator Workflow](system/delivery-and-operator-workflow.md). Contributors do not need the cloud path for normal work.

## Surface Roles

The local stack still keeps the same surface split as the wider docs: Streamlit and prediction responses are rider-facing evaluation surfaces, FastAPI routes are service surfaces, and `/metrics`, Prometheus, Grafana, Airflow, and MLflow stay on the operator side. The bootstrap also keeps retained monitoring history under `.state/monitoring/`, republishes persisted pipeline summaries through `/metrics`, and verifies the Airflow health payload plus Grafana provisioning before it reports success. For the full surface boundary, use [Interfaces and Surfaces](system/interfaces-and-surfaces.md).

After bootstrap completes, the main local endpoints are:

- App: `http://127.0.0.1:8000`
- App metrics: `http://127.0.0.1:8000/metrics`
- Airflow: `http://127.0.0.1:8080`
- MLflow: `http://127.0.0.1:5001`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000`
- Objectstore UI: printed by the bootstrap helper when the stack comes up
- Feast online store emulator: printed by the bootstrap helper when the stack comes up

The app and app-metrics routes are service surfaces. Airflow, MLflow, Prometheus, and Grafana are operator surfaces in this local evaluator path.

Example check:

```bash
curl -fsS -X POST http://127.0.0.1:8000/rank \
  -H 'content-type: application/json' \
  -d '{"spot_ids":["silvaplana","urnersee"]}'
```

## Shared Cloud Automation

The shared hosted environment is maintained separately from normal contributor setup. Contributors only need Docker and the local evaluator bootstrap, not local Terraform, `gcloud`, or `gh`. Maintainers should start with [Delivery and Operator Workflow](system/delivery-and-operator-workflow.md) for the bootstrap and remote Terraform path, and use `terraform/README.md` only when maintaining the shared cloud environment.

Hosted deployment keeps the runtime scope tight. The cloud targets deploy runtime services only; `development_env`, notebooks, docs build tooling, the local objectstore, and the local Datastore emulator stay local or CI-only.

## What Lives Where

See [Repository](system/repository.md) for the dedicated layout guide. The short version is: `src/foehncast/` holds the application code, `dags/` holds Airflow entry points, `scripts/` and `terraform/` hold maintainer tooling, and `docs/` plus `tests/` hold the public docs and regression coverage.

## Read Next

### Overview

- [Use Case and Data](system/use-case.md)
- [Repository](system/repository.md)
- [Configuration and Contracts](system/configuration-and-contracts.md)
- [Interfaces and Surfaces](system/interfaces-and-surfaces.md)

### Runtime and Deployment

- [Architecture](system/architecture.md)
- [Local Evaluator](system/local-evaluator.md)
- [Hosted Full-Stack](system/hosted-full-stack.md)
- [Cloud Mapping](system/cloud-mapping.md)
- [Delivery and Operator Workflow](system/delivery-and-operator-workflow.md)

### Pipelines and Modeling

- [Feature Pipeline](system/feature-pipeline.md)
- [Training Pipeline](system/training-pipeline.md)
- [Inference Pipeline](system/inference-pipeline.md)
- [Seasonality](system/seasonality.md)

### Operations

- [Monitoring](system/monitoring.md)
