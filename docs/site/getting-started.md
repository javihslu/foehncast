# Getting Started

This page keeps setup intentionally simple. The supported contributor path is the local evaluator flow with Docker.

## Local Evaluator

This is the default path for a fresh machine.

1. Install Docker.
2. Clone the repository.
3. Run `./scripts/bootstrap-local.sh`.

You do not need `gcloud`, Terraform, GitHub Actions variables, or a local compiler toolchain for this path.

The local evaluator path uses the bundled MinIO surface as the default object-access layer for curated feature persistence and MLflow artifacts, while Feast uses the bundled Datastore-mode emulator as the required online-serving layer on top of the curated contract. The same local stack now includes Prometheus, a StatsD exporter, and Grafana from checked-in monitoring config, Airflow uses a bundled Postgres metadata database instead of a host-mounted SQLite file, the bootstrap helper waits for the feature DAG to publish a training-request asset and for the resulting asset-triggered training run to finish on a real registry version, and it verifies that Grafana loaded its starter resources before reporting success. If the preferred local host ports are already occupied, the bootstrap helper moves the bindings to the next free ports and prints the chosen endpoints.
The optional `development_env` notebook container stays off by default and only starts when you explicitly target the notebook or dev-shell Makefile commands.

## Surface Roles

| Surface | Use it for | Do not treat it as |
|------|------------|--------------------|
| Streamlit demo and prediction responses | rider-facing evaluation and public-safe screenshots | an operator dashboard |
| FastAPI routes such as `/predict`, `/rank`, and `/features/online` | service integration, smoke checks, and demo calls | a documentation publishing surface |
| `/metrics`, Prometheus, Grafana, Airflow, and MLflow | operator validation, monitoring, and debugging | the product UI or a public embed target |
| Docs pages and rendered evidence | public-safe explanation and review material | a live runtime control plane |

Prediction requests also append flattened local inference rows to `.state/monitoring/prediction-log.jsonl` as a bounded working set and to `.state/monitoring/prediction-events.jsonl` as the retained history contract. That keeps restart-sensitive runtime counters separate from the retained monitoring history and keeps both out of `data/`.

Feature-pipeline dashboard panels are driven from the latest summary JSON under `airflow/reports/`. The app republishes that summary through `/metrics`, so Prometheus and Grafana read the same persisted run summary that the bootstrap path produces. The Airflow Assets view also shows the current local hand-off graph: curated feature rows, Feast synchronization, the training request, the MLflow training run, the evaluation report, and the registry update.

Grafana is present in the local stack so the bootstrap can verify provisioning and so operators can inspect metrics and alert rules. It is not the primary rider-facing interface, and the docs site should prefer screenshots or rendered artifacts over live Grafana embeds.

The bootstrap reset also removes stale local Airflow metadata files and logs, and the bootstrap verifies the Airflow health payload itself instead of treating a `200 OK` response from `/api/v2/monitor/health` as sufficient.

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
- [Use Case and Data](system/use-case.md)
