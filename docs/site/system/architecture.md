# Architecture

FoehnCast keeps the same Feature-Training-Inference split in every runtime. The cloud path adds a public API lane on Cloud Run and a private operator lane for Airflow, MLflow, monitoring, and private app checks. In the active shared environment that operator lane is implemented on a retained host, while image builds move to Cloud Build and orchestration moves to Cloud Composer.

!!! note "How to read this page"

    Start with the local Compose stack.
    In the cloud, Cloud Run is the public API lane.
    The retained host is the active implementation of the private operator lane.
    The target hosted direction keeps Cloud Run and moves build and orchestration into managed services.
    Rider-facing screens are separate from operator dashboards.

## System In One View

<div class="mermaid">
flowchart LR
    %% Styling
    classDef cloud fill:#f5f5f5,stroke:#333
    classDef pipe fill:#e1f5fe,stroke:#01579b
    classDef store fill:#ececff,stroke:#9370db
    classDef app fill:#222,stroke:#333,color:#fff

    EXT["External inputs"]:::cloud

    subgraph FeatureP ["Feature path"]
        direction TB
        ING[Ingest] --> ENG[Engineer] --> VAL[Validate] --> STO[Store]
    end

    subgraph TrainingP ["Training path"]
        direction TB
        LAB[Label] --> TRN[Train] --> EVAL[Eval] --> REG[Register]
    end

    subgraph InferenceP ["Serving path"]
        direction TB
        API[API Endpoint] --> PRED[Predict] --> RANK[Rank]
    end

    FEAST["Feast layer"]:::store
    MLF["Registry"]:::store

    EXT --> ING
    STO --> LAB
    STO --> FEAST
    REG --> MLF

    FEAST --> API
    MLF --> API
    EXT --> API
</div>

## Surface Boundaries

See [Interfaces and Surfaces](interfaces-and-surfaces.md) for the dedicated public overview of this boundary.

| Surface class | Primary audience | Exposure | Example surfaces |
|------|------------------|----------|------------------|
| Rider-facing demo surface | rider, reviewer, contributor | public-safe when shown as screenshots or rendered examples | Streamlit rider console and the online-features demo page |
| Service endpoints | clients, smoke tests, support services | service-only | `/health`, `/spots`, `/predict`, `/rank`, `/features/online`, and `/metrics` |
| Operator dashboards and control planes | maintainer or deployment operator | internal-only by default | Airflow, MLflow, Prometheus, and Grafana |
| Public docs and rendered evidence | course reviewer, fork reader, maintainer | public-safe | docs pages, evaluation markdown, summary JSON-derived charts, and screenshots |

Grafana stays on the operator side. The rider-facing experience comes from the app layer. Public docs should therefore show rendered evidence or screenshots, not live embeds of private dashboards.

## Runtime Lanes

| Lane | Concrete target | State | Main role | Exposure |
|------|----------------|-------|-----------|----------|
| Local evaluator lane | local Compose stack | stable baseline | validate the full system on one machine | local-only |
| Shared API lane | hosted inference target on Cloud Run | active hosted target | serve the shared FastAPI product and service routes | public |
| Operator lane | hosted full-stack target on one GCP host | implemented on retained host | provide the private operator surface for Airflow, MLflow, monitoring, and private app checks | private by default |

## Stable Pipeline Boundaries

| Layer | Responsibility | Representative runtime surface |
|------|----------------|-------------------------|
| Feature pipeline | Collect data, engineer curated rows, validate them, and store the result | local Airflow DAG plus the configured storage backend |
| Training pipeline | Label data, train the model, evaluate it, and register a serving version | local Airflow DAG plus MLflow |
| Inference pipeline | Serve health, predict, rank, and spot-list responses | FastAPI app container |
| Orchestration | Schedule runtime DAGs, retries, backfills, and operator inspection | local Airflow in the local evaluator; retained-host Airflow in the active shared environment; Cloud Composer is the target hosted orchestrator |
| Online features | Surface curated fields through an online lookup route | Feast-backed service path plus demo page |
| Monitoring | Scrape runtime metrics, collect pushed gauges, and visualize starter alerts | Prometheus, StatsD exporter, and Grafana operator stack |

The orchestration layer models the main data products as Airflow assets. In the validated local stack, the feature DAG publishes curated-feature, Feast-sync, and training-request assets. The training DAG consumes the training request and emits MLflow training, evaluation, and registry assets.

## Deployment Targets

<div class="mermaid">
flowchart LR
    classDef core fill:#f5f5f5,stroke:#333
    classDef local fill:#e1f5fe,stroke:#01579b
    classDef cloud fill:#fff8e1,stroke:#f57f17

    CORE["Shared pipeline boundaries"]:::core

    subgraph LocalTarget ["fab:fa-docker Local lane"]
        direction TB
        LFLOW["Airflow + MLflow + app"]:::local
        LDATA["MinIO + Feast + metrics"]:::local
    end

    subgraph HostedTargets ["fab:fa-google Hosted lanes"]
        direction TB
        RUN["Cloud Run API"]:::cloud
        HOST["Operator lane"]:::cloud
        MGD["Managed plane"]:::cloud
    end

    CORE --> LocalTarget
    CORE --> HostedTargets
</div>

| Target | What runs | Main use |
|------|-----------|----------|
| Local evaluator target | Airflow, MLflow, FastAPI, Prometheus, StatsD exporter, Grafana, MinIO, Feast emulator, and optional `development_env` | default development and evaluation |
| Hosted full-stack target | Airflow, MLflow, FastAPI, Prometheus, StatsD exporter, and Grafana on one GCP host | provide the active operator surface while the managed hosted control plane is not yet in place |
| Hosted inference target | FastAPI only, backed by shared GCP services | primary hosted API surface |
| Managed hosted direction | Cloud Build for runtime images and Cloud Composer for hosted Airflow workloads | intended steady hosted build and orchestration path |
| GitHub automation | review, workflow dispatch, and Terraform workflows | shared cloud delivery control plane |

The hosted targets deploy runtime services only. Development assets, notebooks, docs build tooling, and local emulators stay local or CI-only. Cloud Run owns the public API lane. The retained host stays private by default and is treated as a retained operator surface, not as the long-term hosted control plane.

See [Cloud Mapping](cloud-mapping.md) and [Hosted Full-Stack](hosted-full-stack.md) for the active hosted topology, the retained-host contract, and the intended managed direction.

## Shared Core Vs Runtime Differences

| Shared in every runtime | Local evaluator adds | Cloud path adds |
|------|----------------------|-----------------|
| Feature, training, and inference boundaries | one-machine validation with Airflow, MLflow, MinIO, Feast emulator, and monitoring | Cloud Run public API lane, private operator lane, and managed cloud services |
| FastAPI product and service contract | local app routes and local evaluation surfaces | public API serving on Cloud Run and private hosted app checks |
| Curated data, model registry, and Feast-backed feature path | local object-backed and emulator-backed support services | BigQuery, GCS, Datastore, and runtime identities |

Read the left column as the stable design. Read the other columns as deployment choices around that design.

## Hosted Orchestration Direction

The private operator lane runs the hosted Airflow surface used for scheduling, retries, backfills, and runtime release handoff in the active shared environment. The target hosted control plane is Cloud Composer. See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the active-versus-target boundary.

## Local Evaluator Architecture

<div class="mermaid">
flowchart LR
    %% Stylings
    classDef infra fill:#f5f5f5,stroke:#333
    classDef pipeline fill:#e1f5fe,stroke:#01579b
    classDef registry fill:#fff,stroke:#d32f2f
    classDef app fill:#222,stroke:#333,color:#fff
    classDef storage fill:#fff,stroke:#9370db
    classDef monitor fill:#fff,stroke:#f57f17

    EXT["External APIs"]:::infra

    subgraph LocalStack ["fab:fa-docker Local stack"]
        direction LR
        FEAT["Feature DAG"]:::pipeline
        MIN["MinIO curated store"]:::storage
        TRAIN["Training DAG"]:::pipeline
        MLF["MLflow registry"]:::registry
        FEAST["Feast layer"]:::storage
        APP["FastAPI API"]:::app
        MON["Monitoring stack"]:::monitor
    end

    EXT --> FEAT
    FEAT -- "Persist rows" --> MIN
    FEAT -- "Emit request" --> TRAIN
    MIN --> TRAIN
    TRAIN --> MLF
    MIN --> FEAST
    FEAST --> APP
    MLF --> APP
    APP --> MON
</div>

The Airflow control plane reflects those hand-offs directly. The feature pipeline owns curated-row and Feast-sync publication, then emits a training-request asset. The training pipeline starts from that asset instead of a direct DAG-to-DAG trigger, so the Assets view shows the real dependency graph between feature persistence, Feast serving preparation, model training, evaluation, and registration.

## Active Hosted Runtime Detail

<div class="mermaid">
flowchart LR
    classDef data fill:#ececff,stroke:#9370db
    classDef operator fill:#fff8e1,stroke:#f57f17

    subgraph DataPlane ["fab:fa-google Cloud data"]
        direction TB
        OPSDATA["GCS artifacts + BigQuery"]:::data
        APPDATA["BigQuery + Datastore"]:::data
    end

    subgraph Host ["fab:fa-google Ops lane"]
        direction TB
        HOPS["Airflow + MLflow"]:::operator
        HAPI["FastAPI app"]:::operator
        HOPS --> HAPI
    end

    OPSDATA --> HOPS
    APPDATA --> HAPI
</div>

<div class="mermaid">
flowchart LR
    classDef input fill:#f5f5f5,stroke:#333
    classDef data fill:#ececff,stroke:#9370db
    classDef serve fill:#fff8e1,stroke:#f57f17

    LIVE["Forecast + drive-time inputs"]:::input
    DATA["BigQuery + Datastore + MLflow"]:::data

    subgraph Run ["fab:fa-google Cloud Run API"]
        direction TB
        RAPI["FastAPI app"]:::serve
    end

    LIVE --> RAPI
    DATA --> RAPI
</div>

The hosted lanes reuse the same application boundaries, but they deploy different runtime surfaces. The first diagram shows the retained private operator lane used in the active shared environment. The second shows the public API lane on Cloud Run. The managed hosted direction changes the build and orchestration plane around those diagrams; it does not change the core pipeline split.

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
- The retained operator lane supports the active hosted path, but it is not the desired long-term hosted design.
- Feast layers on top of the same curated features instead of splitting the design.

## Storage Contract

- Raw landing is optional and stays separate from the curated feature store.
- The local default uses MinIO-backed object storage for curated features and MLflow artifacts, plus local Feast parquet and a Datastore-mode emulator for online serving.
- The local stack mirrors the hosted object-access layer as closely as possible without pretending BigQuery and Datastore are themselves object storage.
- In the cloud, raw landing fits object storage, while curated features fit native BigQuery tables.
- Retained prediction-event history is a monitoring fact store, not a rider-facing page or a substitute for dashboards.
- Feast stays attached to the curated layer rather than becoming the primary ingestion or archive system.

See [Use Case and Data](use-case.md) for the rider-focused problem framing, [Cloud Mapping](cloud-mapping.md) for the hosted path details, and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the contributor and maintainer rollout split.
