# Getting Started

This page keeps setup intentionally simple. The supported contributor path is the local evaluator flow with Docker.

## Local Evaluator

This is the default path for a fresh machine.

1. Install Docker.
2. Clone the repository.
3. Run `./scripts/bootstrap-local.sh`.

You do not need `gcloud`, Terraform, GitHub Actions variables, or a local compiler toolchain for this path.

The local evaluator path uses the bundled MinIO surface as the default object-access layer for curated feature persistence and MLflow artifacts, while Feast uses the bundled Datastore-mode emulator as the required online-serving layer on top of the curated contract. If the preferred local host ports are already occupied, the bootstrap helper moves the bindings to the next free ports and prints the chosen endpoints.

Prediction requests also append flattened local inference rows to `.state/monitoring/prediction-log.jsonl`, so the monitoring layer can compare recent model outputs against earlier outputs from the same model version without mixing runtime state into `data/`.

After bootstrap completes, the main local endpoints are:

- App: `http://127.0.0.1:8000`
- Airflow: `http://127.0.0.1:8080`
- MLflow: `http://127.0.0.1:5001`
- Objectstore UI: printed by the bootstrap helper when the stack comes up
- Feast online store emulator: printed by the bootstrap helper when the stack comes up

Example check:

```bash
curl -fsS -X POST http://127.0.0.1:8000/rank \
  -H 'content-type: application/json' \
  -d '{"spot_ids":["silvaplana","urnersee"]}'
```

## Shared Cloud Automation

The shared hosted environment is maintained separately from normal contributor setup.

- Contributors only need Docker and the local evaluator bootstrap.
- Contributors do not need local Terraform, `gcloud`, or `gh`.
- Maintainers use a one-time Cloud Shell bootstrap and then let GitHub Actions own the shared cloud path.

See `terraform/README.md` only if you maintain the shared cloud environment.

Hosted deployment keeps the runtime scope tight. The cloud targets deploy runtime services only; `development_env`, notebooks, docs build tooling, the local objectstore, and the local Datastore emulator stay local or CI-only.

## What Lives Where

- `src/foehncast/`: application code for feature engineering, training, inference, monitoring, and configuration
- `dags/`: Airflow workflow entry points
- `scripts/`: local bootstrap plus maintainer utilities
- `terraform/`: maintainer cloud infrastructure definition and reference
- `feature_repo/`: Feast integration surface and config repo
- `tests/`: regression coverage for the pipeline and API behavior
- `docs/`: GitHub Pages source for the public documentation

## Read Next

- [Architecture](system/architecture.md)
- [Feature Pipeline](system/feature-pipeline.md)
- [Cloud Mapping](system/cloud-mapping.md)
- [Repository](system/repository.md)
- [Milestones](milestones/index.md)
