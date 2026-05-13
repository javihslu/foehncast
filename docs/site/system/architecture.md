# Architecture

FoehnCast keeps the same Feature-Training-Inference split in every runtime mode. What changes is the hosting around that split, not the application boundaries.

!!! note "How to read this page"

    The validated baseline is the local Compose stack.
    The active shared environment uses the hosted full-stack target.
    The hosted inference target remains a smaller optional path.
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

## Stable Pipeline Boundaries

| Layer | Responsibility | Current runtime surface |
|------|----------------|-------------------------|
| Feature pipeline | Collect data, engineer curated rows, validate them, and store the result | local Airflow DAG plus the configured storage backend |
| Training pipeline | Label data, train the model, evaluate it, and register a serving version | local Airflow DAG plus MLflow |
| Inference pipeline | Serve health, predict, rank, and spot-list responses | FastAPI app container |
| Online features | Surface curated fields through an online lookup route | Feast-backed service path plus demo page |
| Monitoring | Scrape runtime metrics, collect pushed gauges, and visualize starter alerts | Prometheus, StatsD exporter, and Grafana operator stack |

The orchestration layer now models the main data products as Airflow assets instead of only sequencing opaque tasks. In the validated local stack, the feature DAG publishes curated-feature, Feast-sync, and training-request assets, and the training DAG consumes the training request and emits MLflow training, evaluation, and registry assets.

## Deployment Targets

<div class="mermaid">
flowchart LR
    CORE[Shared Feature-Training-Inference boundaries]
    CORE --> LOCAL[Local evaluator target]
    CORE --> HOST[Hosted full-stack target today]
    CORE -. optional .-> RUN[Hosted inference target]
</div>

| Target | Deploys | Leaves out | Primary use |
|------|---------|------------|-------------|
| Local evaluator target | Airflow, MLflow, FastAPI, Prometheus, a StatsD exporter, Grafana, MinIO, the Feast Datastore emulator, and optional `development_env` tooling | shared GCP baseline | default development and evaluation |
| Hosted full-stack target | Airflow, MLflow, FastAPI, Prometheus, a StatsD exporter, and Grafana on one GCP host | `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | active shared environment |
| Hosted inference target | FastAPI only, backed by shared GCP services | Airflow, hosted MLflow container, `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | smaller API-only hosted surface |
| GitHub automation | image publishing and Terraform workflows | runtime services | shared cloud day-2 delivery, not a runtime target |

The hosted targets deploy runtime services only. Development assets, notebooks, docs build tooling, and local emulators stay local or CI-only. The hosted full-stack target exposes only the app on port `8000` by default. Airflow, MLflow, Prometheus, and Grafana stay private unless you open them on purpose for your own operator workflow.

The active shared environment uses the hosted full-stack target today. The hosted inference target stays available when only the API needs to be online.

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

## Hosted Runtime Detail

<div class="mermaid">
flowchart LR
    subgraph Host[Hosted full-stack target today]
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
    subgraph Run[Hosted inference target optional]
        RAPI[FastAPI]
    end
    BQ2[(BigQuery curated features)] --> RAPI
    DS2[(Datastore online store)] --> RAPI
    MLF2[(Reachable MLflow)] --> RAPI
    OME2[Open-Meteo] --> RAPI
    OSRM2[OSRM] --> RAPI
</div>

The hosted targets reuse the same application boundaries, but they deploy different runtime surfaces. The first diagram matches the active shared environment. The second remains the smaller optional API-only path. The cloud path does not ship the local development container, local objectstore, notebooks, docs build tooling, or the Datastore emulator.

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
- Feast layers on top of the same curated features instead of splitting the design.

## Storage Contract

- Raw landing is optional and stays separate from the curated feature store.
- The local default uses MinIO-backed object storage for curated features and MLflow artifacts, plus local Feast parquet and a Datastore-mode emulator for online serving.
- The local stack mirrors the hosted object-access layer as closely as possible without pretending BigQuery and Datastore are themselves object storage.
- In the cloud, raw landing fits object storage, while curated features fit native BigQuery tables.
- Retained prediction-event history is a monitoring fact store, not a rider-facing page or a substitute for live dashboards.
- Feast stays attached to the curated layer rather than becoming the primary ingestion or archive system.

See [Use Case and Data](use-case.md) for the rider-focused problem framing, [Cloud Mapping](cloud-mapping.md) for the hosted path details, and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the contributor and maintainer rollout split.
