# Local Evaluator

FoehnCast uses the local evaluator target as the default contributor runtime. The `bootstrap-local` path starts the validated service subset, resets disposable local state, runs one end-to-end feature and training hand-off, prepares Feast serving state, and verifies the main app and operator contracts before it reports success.

This page records the current local runtime contract that is validated by the bootstrap path and by the runtime-stack and monitoring-stack tests. It describes the current baseline, not a future migration plan.

!!! note "Scope"

    This page describes the current validated local evaluator target.
    It is not a roadmap.
    Future changes should be documented after they are chosen and implemented.

## Target Shape

<div class="mermaid">
flowchart LR
    BOOT[./scripts/bootstrap-local.sh] --> AIR[Airflow plus Postgres metadata]
    BOOT --> APP[FastAPI app]
    BOOT --> MLF[MLflow]
    BOOT --> OBJ[MinIO objectstore]
    BOOT --> FEAST[Feast Datastore emulator]
    BOOT --> MON[Prometheus plus StatsD exporter plus Grafana]

    AIR --> FEAT[feature_pipeline DAG]
    FEAT --> CUR[(Curated feature data)]
    FEAT --> REQ[training-request asset]
    REQ --> TRN[training_pipeline DAG]
    TRN --> REG[(MLflow registry)]
    REG --> APP
    CUR --> FEAST
    APP --> MET[/metrics]
    MET --> MON
</div>

The important point is that the local evaluator is a real runtime target, not a mock environment:

- the same feature, training, inference, and monitoring modules run inside the local stack
- the bootstrap waits for a real asset-triggered training run instead of stopping after container startup
- Feast serving state is prepared after curated features exist instead of being treated as an optional afterthought
- rider-facing and operator-facing surfaces stay separate even in local mode

## Bootstrap Responsibilities

The default contributor entrypoint is still simple:

1. Install Docker.
2. Clone the repository.
3. Run `./scripts/bootstrap-local.sh`.

You do not need local `gcloud`, Terraform, GitHub Actions variables, or a compiler toolchain for this path.

The bootstrap path owns these responsibilities:

- reset Docker volumes, local Airflow metadata, and disposable runtime artifacts so each run starts clean
- start the validated service subset without enabling the optional `development_env` container
- wait for Airflow component health checks and the Airflow API health payload
- verify Grafana provisioning before any pipeline run starts
- run the feature pipeline for the selected date
- wait for the asset-triggered training pipeline to finish successfully
- prepare Feast local serving state and verify the live `/features/online` route
- wait for app health and verify hosted-sync metrics on `/metrics`

If the preferred local ports are already occupied, the bootstrap moves the bindings to the next free ports and prints the resolved endpoints.

## Runtime Surfaces

| Surface | Current role in the local evaluator | Must not become |
|------|--------------------------------------|-----------------|
| FastAPI app | serve `/health`, `/spots`, `/predict`, `/rank`, `/features/online`, and `/metrics` | a hidden training or operator control plane |
| Airflow plus Postgres metadata database | run feature and training orchestration with asset hand-offs | a notebook-only demo path |
| MLflow | track runs, registry versions, and local model loading | the rider-facing interface |
| MinIO objectstore | local object-access baseline for curated features and MLflow artifacts | a replacement for the online feature layer |
| Feast Datastore emulator | required local online-serving layer above the curated contract | the primary storage contract |
| Prometheus, StatsD exporter, and Grafana | operator monitoring and provisioning validation | the product UI |
| `development_env` | optional notebook and dev-shell helper surface | part of the default contributor path |

This keeps the local target close to the hosted architecture. The object-access layer follows the same shape as the hosted artifact path, while Feast continues to provide the online-serving boundary instead of turning storage into a serving shortcut.

## Verification Contract

The local evaluator reports success only after the runtime proves several real contracts.

The current verification path includes:

- Airflow component health checks for the webserver, dag-processor, scheduler, triggerer, and metadata database
- an Airflow API health payload check instead of treating `200 OK` alone as enough
- Grafana API checks for the checked-in dashboard, alert rules, contact point, and policies
- a real `feature_pipeline` DAG test run through Airflow
- a real asset-triggered `training_pipeline` success wait
- a live `/features/online` request against the running app
- app health and hosted-sync metric verification through `/metrics`

That makes the local target more than a container smoke test. It exercises the same hand-offs the rest of the system pages describe.

## Disposable And Retained Local State

The local evaluator resets disposable state aggressively, but it still keeps the important contracts explicit.

The current split is:

- disposable Airflow metadata and logs are cleared by the bootstrap path
- curated features and MLflow artifacts use the MinIO-backed local objectstore baseline for the run
- retained prediction monitoring history lives under `.state/monitoring/` instead of mixing into `data/`
- pipeline summaries are rendered under `airflow/reports/`, with history copies under `airflow/reports/history/`

This boundary matters because reproducibility depends on resetting transient runtime state without pretending that monitoring history or rendered evidence are themselves product data.

## Local-Only Overrides

The checked-in Grafana configuration keeps deployable-safe defaults: anonymous access, public dashboard sharing, and embedding are disabled by default.

The local evaluator applies local-only access overrides so a fresh Docker run can still verify Grafana provisioning without extra manual setup. That keeps the public and hosted surface policy intact:

- Grafana remains an operator surface
- rider-facing evaluation still belongs to the Streamlit demo and API outputs
- public docs should keep preferring rendered evidence over live embeds of private dashboards

## Why This Target Works

- it gives contributors a clone-and-run baseline instead of a partial demo stack
- it proves the feature-to-training hand-off through Airflow assets before declaring the stack ready
- it keeps the online feature contract real by preparing Feast state and calling the live route
- it keeps optional notebook tooling outside the default path so the supported baseline stays smaller and easier to reproduce

See [Architecture](architecture.md), [Delivery and Operator Workflow](delivery-and-operator-workflow.md), [Inference Pipeline](inference-pipeline.md), [Monitoring](monitoring.md), and [Cloud Mapping](cloud-mapping.md) for the surrounding runtime and deployment boundaries.
