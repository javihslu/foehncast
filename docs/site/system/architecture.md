# Architecture

FoehnCast keeps the same Feature-Training-Inference split in every runtime mode. What changes is the supporting delivery and operator lane around that split. Today the shared cloud path has a public API lane on Cloud Run and a private operator lane on a retained host. That operator lane is transitional while hosted image builds move toward Cloud Build and hosted orchestration moves toward Cloud Composer.

!!! note "How to read this page"

    The validated baseline is the local Compose stack.
    The shared cloud path today splits into a public API lane on Cloud Run and a private retained operator lane.
    The intended hosted direction keeps Cloud Run as the public API, moves hosted image builds to Cloud Build, and moves hosted orchestration to Cloud Composer.
    The hosted paths use the same feature, training, and inference modules, but move storage, auth, and runtime services onto GCP in different ways.
    The rider-facing demo and prediction outputs are not the same thing as operator dashboards, and Grafana is not treated as the main product UI.

## System In One View

<div class="mermaid">
flowchart LR
    subgraph Feature[Feature pipeline]
        ING[Ingest forecasts]
        ENG[Engineer features]
        VAL[Validate rows]
        STO[Store curated features]
        ING --> ENG --> VAL --> STO
    end

    subgraph Training[Training pipeline]
        LAB[Label rows]
        TRN[Train and evaluate]
        REG[Register in MLflow]
        LAB --> TRN --> REG
    end

    subgraph Inference[Inference pipeline]
        API[FastAPI service]
        RANK[Predict and rank]
        API --> RANK
    end

    STO --> LAB
    REG --> API
    OME[Open-Meteo] --> ING
    OME --> API
    OSRM[OSRM] --> API
    STO --> FEAST[Feast serving layer]
    FEAST --> API
</div>

## Surface Boundaries

See [Interfaces and Surfaces](interfaces-and-surfaces.md) for the dedicated public overview of this boundary.

| Surface class | Primary audience | Exposure | Current examples |
|------|------------------|----------|------------------|
| Rider-facing demo surface | rider, reviewer, contributor | public-safe when shown as screenshots or rendered examples | Streamlit rider console and the online-features demo page |
| Service endpoints | clients, smoke tests, support services | service-only | `/health`, `/spots`, `/predict`, `/rank`, `/features/online`, and `/metrics` |
| Operator dashboards and control planes | maintainer or deployment operator | internal-only by default | Airflow, MLflow, Prometheus, and Grafana |
| Public docs and rendered evidence | course reviewer, fork reader, maintainer | public-safe | docs pages, evaluation markdown, summary JSON-derived charts, and screenshots |

Grafana stays on the operator side of that boundary. The rider-facing experience is the ranking and demo surface served from the application layer. Public docs should therefore show rendered evidence or screenshots rather than live iframe embeds of private operational dashboards.

## Runtime Lanes

| Lane | Current target | State | Main role | Exposure |
|------|----------------|-------|-----------|----------|
| Local evaluator lane | local Compose stack | stable baseline | validate the full system on one machine | local-only |
| Shared API lane | hosted inference target on Cloud Run | active hosted target | serve the shared FastAPI product and service routes | public |
| Operator lane | hosted full-stack target on one GCP host | active but transitional | keep Airflow, MLflow, monitoring, and private app checks online while the hosted control plane is simplified | private by default |

## Stable Pipeline Boundaries

| Layer | Responsibility | Current runtime surface |
|------|----------------|-------------------------|
| Feature pipeline | Collect data, engineer curated rows, validate them, and store the result | local Airflow DAG plus the configured storage backend |
| Training pipeline | Label data, train the model, evaluate it, and register a serving version | local Airflow DAG plus MLflow |
| Inference pipeline | Serve health, predict, rank, and spot-list responses | FastAPI app container |
| Orchestration | Schedule runtime DAGs, retries, backfills, and operator inspection | local Airflow today; retained-host Airflow today; Cloud Composer is the target hosted orchestrator |
| Online features | Surface curated fields through an online lookup route | Feast-backed service path plus demo page |
| Monitoring | Scrape runtime metrics, collect pushed gauges, and visualize starter alerts | Prometheus, StatsD exporter, and Grafana operator stack |

The orchestration layer now models the main data products as Airflow assets instead of only sequencing opaque tasks. In the validated local stack, the feature DAG publishes curated-feature, Feast-sync, and training-request assets, and the training DAG consumes the training request and emits MLflow training, evaluation, and registry assets.

## Deployment Targets

<div class="mermaid">
flowchart LR
    CORE[Shared Feature-Training-Inference boundaries]
    CORE --> LOCAL[Local evaluator target]
    CORE --> HOST[Operator host lane]
    CORE --> RUN[Cloud Run API lane]
</div>

| Target | Deploys | Leaves out | Primary use |
|------|---------|------------|-------------|
| Local evaluator target | Airflow, MLflow, FastAPI, Prometheus, a StatsD exporter, Grafana, MinIO, the Feast Datastore emulator, and optional `development_env` tooling | shared GCP baseline | default development and evaluation |
| Hosted full-stack target (transitional operator lane) | Airflow, MLflow, FastAPI, Prometheus, a StatsD exporter, and Grafana on one GCP host | `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | keep current operator duties online while the hosted build and orchestration contracts are cleaned up |
| Hosted inference target (API lane) | FastAPI only, backed by shared GCP services | Airflow, hosted MLflow container, `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | primary hosted API surface |
| Managed hosted direction | Cloud Build for hosted runtime images and Cloud Composer for hosted Airflow workloads | VM-owned orchestration and host-built image responsibility | intended steady hosted build and orchestration path |
| GitHub automation | review, workflow dispatch, and Terraform workflows | runtime services | shared cloud delivery control plane, not a runtime target |

The hosted targets deploy runtime services only. Development assets, notebooks, docs build tooling, and local emulators stay local or CI-only. Cloud Run already owns the public API lane. The retained host stays private by default and is treated as a transitional operator surface, not as the desired long-term hosted control plane.

See [Cloud Mapping](cloud-mapping.md) and [Hosted Full-Stack](hosted-full-stack.md) for the current hosted topology, the transitional retained-host contract, and the intended managed direction.

## Hosted Orchestration Direction

Today the private operator lane still runs the hosted Airflow surface used for scheduling, retries, backfills, and runtime release handoff. That is the current operational contract.

The target hosted control plane is Cloud Composer. The managed cutover should replace host-owned Airflow responsibilities without changing the core feature, training, and inference split. The detailed current-versus-target boundary stays in [Delivery and Operator Workflow](delivery-and-operator-workflow.md).

## Current Local Architecture

<div class="mermaid">
flowchart TD
    OME[Open-Meteo] --> FEAT
    FEAT --> PAR[(MinIO curated features)]
    PAR --> TRAIN[Training DAG]
    TRAIN --> MLF[(MLflow registry)]

    OME --> APP[FastAPI app]
    OSRM[OSRM] --> APP
    MLF --> APP

    PAR --> OFF[Feast offline export]
    OFF --> FEAST[(Datastore-mode emulator)]
    FEAST --> APP
    APP --> MON[Prometheus + StatsD exporter + Grafana]
</div>

The Airflow control plane reflects those hand-offs directly. The feature pipeline owns the curated-row and Feast-sync publication steps, then emits a training-request asset. The training pipeline is scheduled from that asset rather than a direct DAG-to-DAG trigger, so the Assets view shows the real dependency graph between feature persistence, Feast serving preparation, model training, evaluation, and registration.

## Hosted Runtime Detail Today

<div class="mermaid">
flowchart LR
    subgraph Host[Operator host lane]
        HAF[Airflow]
        HML[MLflow]
        HAPI[FastAPI]
    end
    GCS[(GCS)] --> HAF
    GCS --> HML
    BQ[(BigQuery curated features)] --> HAF
    BQ --> HAPI
    HML --> HAPI
    DS[(Datastore online store)] --> HAPI
</div>

<div class="mermaid">
flowchart LR
    subgraph Run[Cloud Run API lane]
        RAPI[FastAPI]
    end
    BQ2[(BigQuery curated features)] --> RAPI
    DS2[(Datastore online store)] --> RAPI
    MLF2[(Reachable MLflow)] --> RAPI
    OME2[Open-Meteo] --> RAPI
    OSRM2[OSRM] --> RAPI
</div>

The hosted lanes reuse the same application boundaries, but they deploy different runtime surfaces. The first diagram shows the retained private operator lane that exists today. The second shows the public API lane on Cloud Run. The managed hosted direction changes the build and orchestration plane around those diagrams; it does not change the core pipeline split.

## Representative Validation

| Check | What it shows |
|-------|---------------|
| feature DAG run through Airflow | the feature path executes inside the orchestration layer |
| asset-triggered training DAG run through Airflow | the training path starts from the published training-request asset and executes inside the orchestration layer |
| API health and prediction routes | the app serves a real model-backed inference surface |
| Feast serving path | the curated features are surfaced through the required online-serving layer without changing the base pipeline split |
| container-side test suite | the local runtime remains reproducible after stack setup |

## Why This Architecture Holds Up

- The personalized ranking logic stays in the inference layer.
- Feature engineering and training remain reusable across local and hosted paths.
- Hosted changes mostly affect storage, auth, orchestration, and image delivery.
- The retained operator lane is a support structure for the current hosted path, not the desired long-term hosted design.
- Feast layers on top of the same curated features instead of splitting the design.

## Storage Contract

- Raw landing is optional and stays separate from the curated feature store.
- The local default uses MinIO-backed object storage for curated features and MLflow artifacts, plus local Feast parquet and a Datastore-mode emulator for online serving.
- The local stack mirrors the hosted object-access layer as closely as possible without pretending BigQuery and Datastore are themselves object storage.
- In the cloud, raw landing fits object storage, while curated features fit native BigQuery tables.
- Retained prediction-event history is a monitoring fact store, not a rider-facing page or a substitute for live dashboards.
- Feast stays attached to the curated layer rather than becoming the primary ingestion or archive system.

See [Use Case and Data](use-case.md) for the rider-focused problem framing, [Cloud Mapping](cloud-mapping.md) for the hosted path details, and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the contributor and maintainer rollout split.
