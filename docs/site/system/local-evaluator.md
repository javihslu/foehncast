# Local Evaluator

FoehnCast uses the local evaluator lane as the default contributor runtime. `bootstrap-local` starts the validated service subset, resets disposable local state, runs one end-to-end feature and training hand-off, prepares Feast serving state, and verifies the app and operator contracts before it reports success.

This page describes the default contributor runtime contract. It documents the supported baseline, not a migration plan.

!!! note "Scope"

    This page describes the validated local evaluator target.
    It is not a roadmap.
    Future changes belong here only after the target changes.

## Target Shape

<div class="mermaid">
flowchart LR
    classDef pipeline fill:#e1f5fe,stroke:#01579b
    classDef registry fill:#fff,stroke:#d32f2f
    classDef app fill:#222,stroke:#333,color:#fff
    classDef storage fill:#fff,stroke:#9370db
    classDef monitor fill:#fff,stroke:#f57f17

    subgraph LocalStack ["fab:fa-docker Local stack"]
        direction LR
        AIR["Airflow"]:::pipeline
        FEAT["Feature DAG"]:::pipeline
        CUR["Curated feature data"]:::storage
        REQ["Training-request asset"]:::pipeline
        TRN["Training DAG"]:::pipeline
        REG["MLflow registry"]:::registry
        FEAST["Feast emulator"]:::storage
        APP["FastAPI app"]:::app
        MON["Prometheus + StatsD + Grafana"]:::monitor
    end

    AIR --> FEAT
    AIR --> TRN
    FEAT --> CUR
    FEAT --> REQ
    CUR --> FEAST
    REQ --> TRN
    TRN --> REG
    REG --> APP
    FEAST --> APP
    APP --> MON
</div>

The local evaluator is a real runtime target, not a mock environment:

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

The bootstrap path resets disposable state, starts the validated service subset without the optional `development_env` container, waits for Airflow and Grafana health, runs the feature-to-training hand-off, prepares Feast local serving state, and verifies the live app plus `/metrics` before it reports success. The detailed proof path is listed below under [Verification Contract](#verification-contract).

If the preferred local ports are already occupied, the bootstrap moves the bindings to the next free ports and prints the resolved endpoints.

## Bootstrap, DVC, And The App

The local evaluator keeps three useful entry points available, but each one has a different job.

| Use this | When you want | What it covers |
|------|---------------|----------------|
| `./scripts/bootstrap-local.sh` | the full local runtime | Docker services, Airflow asset hand-off, MLflow, Feast, monitoring, and app validation |
| `dvc repro` | a reproducible offline rerun | `curate` and `train` from `dvc.yaml`, writing tracked outputs under `data/` and `reports/` |
| FastAPI or Streamlit | serving behavior | live prediction, ranking, and online-feature checks |

DVC is optional in the local evaluator. It is useful when you want a clean, file-based rerun of the offline feature and training path without driving the scheduler by hand. The checked-in DVC remote points at the local MinIO objectstore for cache storage, but DVC itself is not the runtime control plane and it does not replace the app, Airflow, or monitoring stack.

## Runtime Surfaces

| Surface | Role in the local evaluator | Must not become |
|------|--------------------------------------|-----------------|
| FastAPI app | serve `/health`, `/spots`, `/predict`, `/rank`, `/features/online`, and `/metrics` | a hidden training or operator control plane |
| Airflow plus Postgres metadata database | run feature and training orchestration with asset hand-offs | a notebook-only demo path |
| MLflow | track runs, registry versions, and local model loading | the rider-facing interface |
| MinIO objectstore | local object-access baseline for curated features and MLflow artifacts | a replacement for the online feature layer |
| Feast Datastore emulator | required local online-serving layer above the curated contract | the primary storage contract |
| Prometheus, StatsD exporter, and Grafana | operator monitoring and provisioning validation | the product UI |
| `development_env` | optional notebook and dev-shell helper surface | part of the default contributor path |

This keeps the local lane close to the hosted architecture. The object-access layer follows the same shape as the hosted artifact path, while Feast continues to provide the online-serving boundary instead of turning storage into a serving shortcut.

## Verification Contract

The local evaluator reports success only after the runtime proves several real contracts.

The verification path includes:

- Airflow component health checks for the webserver, dag-processor, scheduler, triggerer, and metadata database
- an Airflow API health payload check instead of treating `200 OK` alone as enough
- Grafana API checks for the checked-in dashboard, alert rules, contact point, and policies
- a real `feature_pipeline` DAG test run through Airflow
- a real asset-triggered `training_pipeline` success wait
- a live `/features/online` request against the running app
- app health and hosted-sync metric verification through `/metrics`

That makes the local lane more than a container smoke test. It exercises the same hand-offs the rest of the system pages describe.

## Disposable And Retained Local State

The local evaluator resets disposable state aggressively, but it still keeps the important contracts explicit.

The state split is:

- disposable Airflow metadata and logs are cleared by the bootstrap path
- curated features and MLflow artifacts use the MinIO-backed local objectstore baseline for the run
- retained prediction monitoring history lives under `.state/monitoring/` instead of mixing into `data/`
- pipeline summaries are rendered under `airflow/reports/`, with history copies under `airflow/reports/history/`

This boundary matters because reproducibility depends on resetting transient runtime state without pretending that monitoring history or rendered evidence are themselves product data.

## Local-Only Overrides

The checked-in Grafana configuration keeps deployable-safe defaults: anonymous access, public dashboard sharing, and embedding are disabled by default.

The local evaluator applies local-only access overrides so a fresh Docker run can still verify Grafana provisioning without extra manual setup. Grafana remains an operator surface, rider-facing evaluation stays with the Streamlit demo and API outputs, and public docs should keep preferring rendered evidence over live embeds of private dashboards.

## Why This Target Works

- it gives contributors a clone-and-run baseline instead of a partial demo stack
- it proves the feature-to-training hand-off through Airflow assets before declaring the stack ready
- it keeps the online feature contract real by preparing Feast state and calling the live route
- it keeps optional notebook tooling outside the default path so the supported baseline stays smaller and easier to reproduce

See [Architecture](architecture.md), [Delivery and Operator Workflow](delivery-and-operator-workflow.md), [Inference Pipeline](inference-pipeline.md), [Monitoring](monitoring.md), and [Cloud Mapping](cloud-mapping.md) for the surrounding runtime and deployment boundaries.
