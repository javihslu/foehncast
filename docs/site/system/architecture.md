# Architecture

FoehnCast keeps the same Feature-Training-Inference split in every runtime. The cloud path adds a public API lane on Cloud Run and a private operator lane for Airflow, MLflow, and monitoring. Image builds run through Cloud Build and orchestration runs on Cloud Composer.

!!! note "How to read this page"

    Start with the local Compose stack.
    In the cloud, Cloud Run is the public API lane.
    Cloud Composer is the hosted orchestration surface.
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

Grafana stays on the operator side. The rider-facing experience comes from the app layer. Public docs show rendered evidence or screenshots, not live embeds of private dashboards.

## Runtime Lanes

| Lane | Concrete target | State | Main role | Exposure |
|------|----------------|-------|-----------|----------|
| Local evaluator lane | local Compose stack | stable baseline | validate the full system on one machine | local-only |
| Shared API lane | hosted inference target on Cloud Run | active hosted target | serve the shared FastAPI product and service routes | public |
| Operator lane | Cloud Composer plus managed operator services | active hosted operator surface | provide the private operator surface for Airflow, MLflow, and monitoring | private by default |

## Stable Pipeline Boundaries

| Layer | Responsibility | Representative runtime surface |
|------|----------------|-------------------------|
| Feature pipeline | Collect data, engineer curated rows, validate them, and store the result | local Airflow DAG plus the configured storage backend |
| Training pipeline | Label data, train the model, evaluate it, and register a serving version | local Airflow DAG plus MLflow |
| Inference pipeline | Serve health, predict, rank, and spot-list responses | FastAPI app container |
| Orchestration | Schedule runtime DAGs, retries, backfills, and operator inspection | local Airflow in the local evaluator; Cloud Composer in the hosted environment |
| Online features | Surface curated fields through an online lookup route | Feast-backed service path plus demo page |
| Monitoring | Scrape runtime metrics, collect pushed gauges, and visualize starter alerts | Prometheus, StatsD exporter, and Grafana operator stack |

## DVC And Airflow

The same feature and training boundaries are driven by two different control paths.

- DVC is the reproducible path for local reruns and CI. It tracks file dependencies and outputs in `dvc.yaml`.
- Airflow is the runtime control plane. It schedules DAG runs, handles retries, and shows asset hand-offs.
- Inference is neither a DVC stage nor an Airflow DAG. The FastAPI app serves live requests from the registered model and online feature surfaces.

<div class="mermaid">
flowchart LR
    classDef ctl fill:#f5f5f5,stroke:#333
    classDef pipe fill:#e1f5fe,stroke:#01579b
    classDef store fill:#ececff,stroke:#9370db
    classDef serve fill:#fff8e1,stroke:#f57f17

    subgraph DVCPath ["DVC reproducibility path"]
        DVCY["dvc.yaml"]:::ctl --> DVCCLI["python -m foehncast.dvc_stages"]:::ctl
    end

    subgraph AirflowPath ["Airflow runtime path"]
        FDAG["feature_dag"]:::ctl --> FEAT["Feature pipeline"]:::pipe
        TDAG["training_dag"]:::ctl --> TRAIN["Training pipeline"]:::pipe
    end

    DVCCLI --> FEAT
    DVCCLI --> TRAIN
    FEAT --> CUR["Curated dataset"]:::store
    CUR --> TRAIN
    CUR --> FEAST["Feast serving prep"]:::store
    TRAIN --> REG["MLflow model + reports"]:::store
    FEAST --> API["FastAPI inference"]:::serve
    REG --> API
</div>

| Path | Main job | Main outputs |
|------|----------|--------------|
| DVC | repeatable offline reruns in local or CI contexts | `data/${dataset}`, `reports/train_metrics.json`, `reports/feature_importance.png` |
| Airflow | scheduled or asset-triggered runtime execution | curated-feature, Feast-sync, training-request, MLflow, evaluation, and registry assets |
| FastAPI | live serving | `/predict`, `/rank`, `/spots`, `/features/online`, `/metrics` |

The runtime orchestration layer models main data products as Airflow assets. The feature DAG publishes curated-feature, Feast-sync, and training-request assets. The training DAG consumes the training request and emits MLflow training, evaluation, and registry assets. DVC mirrors the offline feature and training boundaries for reproducible reruns but does not replace the Airflow asset graph.

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
        CMP["Cloud Composer"]:::cloud
        CB["Cloud Build"]:::cloud
    end

    CORE --> LocalTarget
    CORE --> HostedTargets
</div>

| Target | What runs | Main use |
|------|-----------|----------|
| Local evaluator target | Airflow, MLflow, FastAPI, Prometheus, StatsD exporter, Grafana, MinIO, Feast emulator, and optional `development_env` | default development and evaluation |
| Hosted inference target | FastAPI only, backed by shared GCP services | primary hosted API surface |
| Hosted operator target | Cloud Build for runtime images, Cloud Composer for hosted Airflow workloads, and managed operator services for MLflow and monitoring | hosted build, orchestration, and operator surface |
| GitHub automation | review, workflow dispatch, and Terraform workflows | shared cloud delivery control plane |

The hosted targets deploy runtime services only. Development assets, notebooks, docs tooling, and local emulators stay local or CI-only. Cloud Run owns the public API lane. Cloud Composer owns hosted orchestration. Operator services stay private by default.

See [Cloud Mapping](cloud-mapping.md) and [Hosted Full-Stack](hosted-full-stack.md) for the hosted topology and managed service boundaries.

## Shared Core Vs Runtime Differences

| Shared in every runtime | Local evaluator adds | Cloud path adds |
|------|----------------------|-----------------|
| Feature, training, and inference boundaries | one-machine validation with Airflow, MLflow, MinIO, Feast emulator, and monitoring | Cloud Run public API lane, private operator lane, and managed cloud services |
| FastAPI product and service contract | local app routes and local evaluation surfaces | public API serving on Cloud Run and private hosted app checks |
| Curated data, model registry, and Feast-backed feature path | local object-backed and emulator-backed support services | BigQuery, GCS, Datastore, and runtime identities |

Read the left column as the stable design. Read the other columns as deployment choices around that design.

## Hosted Orchestration

Cloud Composer runs the hosted Airflow surface used for scheduling, retries, backfills, and runtime release handoff. See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the delivery boundary.

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

The Airflow control plane reflects those hand-offs directly. The feature pipeline owns curated-row and Feast-sync publication, then emits a training-request asset. The training pipeline starts from that asset instead of a direct DAG-to-DAG trigger, so the Assets view shows the real dependency graph.

## Hosted Runtime Detail

<div class="mermaid">
flowchart LR
    classDef data fill:#ececff,stroke:#9370db
    classDef operator fill:#fff8e1,stroke:#f57f17

    subgraph DataPlane ["fab:fa-google Cloud data"]
        direction TB
        OPSDATA["GCS artifacts + BigQuery"]:::data
        APPDATA["BigQuery + Datastore"]:::data
    end

    subgraph ManagedOps ["fab:fa-google Managed ops"]
        direction TB
        CMP["Cloud Composer"]:::operator
        MLF["MLflow"]:::operator
        CMP --> MLF
    end

    OPSDATA --> CMP
    APPDATA --> CMP
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

The hosted lanes reuse the same application boundaries but deploy different runtime surfaces. The first diagram shows the private operator lane. The second shows the public API lane on Cloud Run. Changing the build and orchestration plane does not change the core pipeline split.

## Representative Validation

| Check | What it shows |
|-------|---------------|
| feature DAG run through Airflow | the feature path executes inside the orchestration layer |
| asset-triggered training DAG run through Airflow | the training path starts from the published training-request asset and executes inside the orchestration layer |
| API health and prediction routes | the app serves a real model-backed inference surface |
| Feast serving path | the curated features are surfaced through the required online-serving layer without changing the base pipeline split |
| container-side test suite | the local runtime remains reproducible after stack setup |

## Why This Architecture Holds Up

- Personalized ranking stays in the inference layer.
- Feature engineering and training are reusable across local and hosted paths.
- Hosted changes mostly affect storage, auth, orchestration, and image delivery.
- The retained operator lane supports the active hosted path but is not the desired long-term design.
- Feast layers on top of the same curated features instead of splitting the design.

## Storage Contract

- Raw landing is optional and stays separate from the curated feature store.
- The local default uses MinIO-backed object storage for curated features and MLflow artifacts, plus local Feast parquet and a Datastore-mode emulator for online serving.
- The local stack mirrors the hosted object-access layer as closely as possible without pretending BigQuery and Datastore are themselves object storage.
- In the cloud, raw landing fits object storage, while curated features fit native BigQuery tables.
- Retained prediction-event history is a monitoring fact store, not a rider-facing page or a substitute for dashboards.
- Feast stays attached to the curated layer rather than becoming the primary ingestion or archive system.

See [Use Case and Data](use-case.md) for the rider-focused problem framing, [Cloud Mapping](cloud-mapping.md) for the hosted path details, and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the contributor and maintainer rollout split.
