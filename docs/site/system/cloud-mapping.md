# Cloud Mapping

FoehnCast has one public hosted lane and one private operator lane. Cloud Run serves the shared API. Cloud Composer owns hosted orchestration. Cloud Build publishes runtime images. MLflow, monitoring, and private app checks run as managed operator services. This page maps the cloud lanes without changing the core Feature-Training-Inference boundaries.

!!! note "What this page covers"

    The shared GCP baseline defines one public API lane and one private operator lane.
    Cloud Run is the shared public API lane.
    Cloud Composer is the hosted orchestration surface.
    Cloud Build is the hosted image build surface.

## Cloud Paths In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Shared GCP baseline</strong></p>
<p>Terraform provisions APIs, Artifact Registry, GCS, BigQuery, and GitHub OIDC.</p>
</li>
<li>
<p><strong>Hosted operator lane</strong></p>
<p>Cloud Composer runs hosted Airflow workloads. MLflow and monitoring run as managed operator services.</p>
</li>
<li>
<p><strong>Hosted build surface</strong></p>
<p>Cloud Build publishes reviewed runtime images to Artifact Registry.</p>
</li>
<li>
<p><strong>Hosted inference target</strong></p>
<p>Cloud Run serves the promoted FastAPI API and remains the public surface.</p>
</li>
</ul>
</div>

## Hosted Lanes At A Glance

| Lane | Concrete target | State | Default exposure | Main job |
|------|-----------------|-------|------------------|----------|
| Shared API lane | hosted inference target on Cloud Run | active | public | serve the FastAPI product and service routes |
| Operator lane | Cloud Composer plus managed operator services | active | private by default | provide the hosted orchestration, tracking, and monitoring surface |
| Build surface | Cloud Build | active | private or platform-only | publish reviewed hosted runtime images to Artifact Registry |
| Delivery lane | GitHub Actions plus Terraform plus OIDC | active review gate | not a runtime surface | publish reviewed artifacts and apply reviewed infrastructure changes |

## Shared Core And Deployment Differences

<div class="mermaid">
flowchart TD
    %% Colors
    classDef core fill:#f5f5f5,stroke:#333
    classDef local fill:#e1f5fe,stroke:#01579b
    classDef cloud fill:#fff8e1,stroke:#f57f17

    CORE["Shared core and pipeline boundaries"]:::core

    subgraph LocalSurface ["fab:fa-docker Local lane"]
        direction LR
        LSUP["Airflow + MLflow + metrics"]:::local
        LAPP["MinIO + Feast + app"]:::local
        LSUP --> LAPP
    end

    subgraph CloudSurface ["fab:fa-google Cloud lane"]
        direction LR
        CDATA["BigQuery + GCS + Datastore"]:::cloud
        CAPI["Cloud Run API"]:::cloud
        COPS["Operator lane"]:::cloud
        CDATA --> CAPI
        CDATA --> COPS
    end

    CORE --> LocalSurface
    CORE --> CloudSurface
</div>

The shared core stays the same. Local and cloud differ mainly in the support surfaces around that core.

## Mapping Principle

- Local Docker proves that the pipelines run together.
- Local and cloud are parallel deployment targets, not upstream and downstream environments.
- Cloud deployment keeps the same pipeline boundaries.
- Cloud services replace the local support services used for evaluation and development.
- Hosted deployment keeps development-only assets, notebooks, docs build tooling, and local emulators out of the runtime surface.
- The app remains a deployable container because inference is a service, not a DAG.

## Surface Exposure In Cloud

| Surface | Intended audience | Default exposure |
|------|-------------------|------------------|
| FastAPI app routes | riders, service clients, smoke tests | exposed by the active hosted app target |
| `/metrics` and scrape targets | Prometheus and operators | service-only |
| Airflow, MLflow, Prometheus, and Grafana | operators | private by default |
| Public docs and review artifacts | reviewer, course audience, fork reader | public-safe when rendered from snapshots, markdown, or screenshots |

This boundary matters because the hosted app is the product and service surface. Grafana remains an operator dashboard, and public docs should prefer rendered evidence over live embeds of private hosted tools.

## Hosted Topology

<div class="mermaid">
flowchart LR
    %% Styling
    classDef infra fill:#f5f5f5,stroke:#333
    classDef runner fill:#f4f1ea,stroke:#f05032
    classDef platform fill:#fff,stroke:#4285F4
    classDef operator fill:#fff8e1,stroke:#f57f17

    TF["Terraform baseline"]:::infra
    GH["fab:fa-github Delivery + OIDC"]:::runner

    subgraph GCP ["fab:fa-google Hosted environment"]
        direction TB
        BASE["IAM + Registry + GCS + BigQuery"]:::platform

        subgraph PublicLane ["API lane"]
            RUN["Cloud Run API"]:::platform
        end

        subgraph PrivateLane ["Ops lane"]
            CMP["Cloud Composer"]:::operator
            CB["Cloud Build"]:::operator
            OPS["MLflow + monitoring"]:::operator
        end

        BASE --> RUN
        BASE --> CMP
    end

    TF --> BASE
    GH -- "Deploy" --> RUN
    GH -- "Build" --> CB
    GH -- "DAGs" --> CMP
</div>

## Implemented Hosted Surfaces

| Surface | Deploys | Leaves out | Implementation status |
|--------|---------|------------|---------------|
| Shared GCP baseline | APIs, Artifact Registry, GCS, BigQuery, Datastore, and OIDC identities | app containers | implemented through Terraform |
| Cloud Composer (operator lane) | hosted Airflow DAGs, orchestration, and runtime release handoff | `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | active hosted orchestration surface |
| Hosted inference target (API lane) | the FastAPI inference API on Cloud Run | Airflow, hosted MLflow container, `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | active public API path |
| Cloud Build | reviewed runtime image publishing to Artifact Registry | n/a | active hosted build surface |
| GitHub delivery | image publishing and remote Terraform runs | runtime services | implemented and bootstrapped for the shared environment |
| BigQuery backend support | support for a BigQuery storage backend in the app | none | available in both local and hosted runtimes |

The hosted targets deploy runtime services only. Development assets stay local or CI-only. Cloud Run is the only promoted public API path. Cloud Composer and the operator services stay private by default.

## Hosted Deployment Path

The shared environment keeps a stable split: Cloud Run carries the shared public API URL, Cloud Composer owns hosted orchestration for scheduling, retries, and runtime release handoff, and GitHub Actions plus remote Terraform advance reviewed day-2 changes after maintainer bootstrap.

See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the delivery boundary and [Configuration and Contracts](configuration-and-contracts.md) for the reviewed value-surface inventory.

## Hosted Orchestration

Cloud Composer is the hosted orchestration surface. Terraform provisions the Cloud Composer environment.

A reviewed DAG and source bundle syncs to the Composer DAG bucket. Terraform seeds the reviewed PyPI baseline required by the checked-in DAG bundle and merges extra `cloud_composer_pypi_packages` overrides on top. The repo exposes a reviewed runtime release entry that reaches the Composer Airflow API, plus a reviewed Secret Manager-backed env-ref path for Composer. See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the delivery boundary and [Configuration and Contracts](configuration-and-contracts.md) for the reviewed value-surface inventory.

## Hosted Service Mapping

| Concern | Hosted implementation |
|---------|----------------------|
| FastAPI app | Cloud Run API lane for shared traffic |
| Hosted image builds | GitHub-reviewed workflows submit Cloud Build builds that publish app, Airflow, and MLflow runtime images to Artifact Registry |
| Airflow orchestration | Cloud Composer |
| MLflow tracking | managed operator surface with GCS-backed artifacts |
| Monitoring | private operator surface |
| Curated storage | BigQuery |
| Feast serving path | same logical feature view against cloud storage |

## Cloud Pipeline Shape

<div class="mermaid">
flowchart LR
    classDef source fill:#f5f5f5,stroke:#333
    classDef process fill:#e1f5fe,stroke:#01579b
    classDef data fill:#ececff,stroke:#9370db
    classDef serving fill:#fff8e1,stroke:#f57f17

    WX["Forecasts"]:::source --> RAW
    RAW[(GCS landing)]:::data --> FEAT
    FEAT["Feature job"]:::process --> BQ
    BQ[(BigQuery curated features)]:::data --> TRAIN
    TRAIN["Training job"]:::process --> MLF
    MLF[(MLflow registry)]:::data --> HOST
    MLF --> RUN
    BQ --> FEAST
    FEAST["Feast layer"]:::data --> HOST
    FEAST --> RUN
    ROUTE["OSRM API"]:::source --> LIVE
    WX --> LIVE
    LIVE["Live inputs"]:::source --> HOST
    LIVE --> RUN

    subgraph Serving ["fab:fa-google Serving lane"]
        direction TB
        HOST["Operator lane"]:::serving
        RUN["Cloud Run API"]:::serving
    end
</div>

| Layer | Cloud direction |
|------|-----------------|
| Raw landing | keep immutable API payloads in GCS when a landing layer is needed |
| Feature pipeline | transform landed or live inputs and write curated rows to BigQuery |
| Training pipeline | read curated rows, train, evaluate, and register through MLflow |
| Inference pipeline | serve the public API on Cloud Run |
| Feast serving path | point the same logical feature view at BigQuery instead of local parquet |

## Storage Layering In Cloud

The cloud design works best when storage is split by role.

| Data role | Recommended cloud surface | Why |
|----------|---------------------------|-----|
| Raw landing and archive | GCS | cheap retention, append-friendly, and flexible when upstream payloads drift |
| Curated analytical features | BigQuery native tables | query-friendly, partitionable, clusterable, and well suited to training plus Feast offline reads |
| Feast registry and staging | GCS | metadata and staging artifacts fit object storage better than warehouse tables |
| Feast offline source | BigQuery table or view | same curated layer used by analytics and training |

External tables still make sense for raw or staging access, but they are not the preferred main store for curated features that are queried often.

## Cloud Storage Control Surface

The cloud path stays clear because it is built from explicit application and infrastructure surfaces, not from a loose translation of the local setup.

| Surface | Cloud-facing implementation | Why it matters |
|------|-----------------------------|----------------|
| Backend selection | `storage.backend=bigquery` plus configured project, dataset, and table | switches curated persistence onto BigQuery without changing the upstream pipeline stages |
| Curated warehouse target | `BigQueryFeatureStoreBackend` | keeps the same feature-store abstraction in place while using a query-friendly cloud store and preserving rerun-safe slice replacement |
| Raw landing target | Terraform-managed GCS bucket | keeps immutable raw capture separate from curated analytical writes |
| Feast runtime binding | Terraform and cloud bootstrap inject the Feast env contract that renders `.state/feast/feature_store.runtime.yaml` | keeps local and hosted runtimes on the same logical Feast configuration surface |
| Feast offline cloud source | BigQuery table or view referenced by the rendered Feast runtime config | keeps Feast downstream from curated storage instead of parallel to it |
| Feast registry and staging | GCS paths from the cloud Feast config | keeps registry metadata and staging artifacts out of warehouse tables |
| Feast online path | Terraform-managed Firestore Datastore-mode database from the cloud Feast config | keeps online feature serving separate from offline analytical storage |
| Terraform baseline | Terraform-managed GCS, BigQuery, and Datastore-mode Firestore surfaces | supplies the bucket and warehouse baseline without taking ownership of feature semantics |
| Local object-store baseline | S3-compatible backend plus the bundled MinIO service back the local operator path | keeps the local object-access layer aligned with the cloud bucket/artifact pattern |

In practice, GCS stores raw landing data and registry-style metadata for the cloud path. BigQuery stores the curated analytical layer. Feast reads that curated layer instead of creating a separate one. The local path uses the bundled MinIO service as its default object-access layer, while BigQuery and Datastore stay hosted-only surfaces.

## Runtime Differences That Matter

| Area | Local baseline | Hosted path |
|------|----------------|-------------|
| Storage | MinIO-backed curated objects plus local Feast parquet and a Datastore-mode emulator | GCS holds raw landing and artifacts; BigQuery becomes the shared curated cloud data surface |
| Artifacts | MinIO-backed MLflow artifact path | GCS bucket |
| Auth | local `.env` plus developer credentials | runtime service accounts and GitHub OIDC |
| Image source | local builds | reviewed GitHub workflows submit Cloud Build builds that publish hosted runtime images to Artifact Registry |
| Public exposure | local ports on the developer machine | Cloud Run is the shared hosted API surface; the operator lane stays private by default; dashboards stay private unless you deliberately publish them |

## Recovery Evidence In Cloud

Operators should be able to prove what changed after a retry, replay, or rollback request.

The stable evidence surfaces are:

- `airflow/reports/feature-pipeline-<dataset>-latest.json` and its history copy for feature retries or backfills
- `airflow/reports/training-pipeline-<dataset>-latest.json` and its history copy for training follow-up
- the configured runtime release summary target and its history copy for reviewed deploy, promote, or rollback handoffs; the Composer path reads the durable `gs://...` report contract derived from the artifact bucket
- `.state/hosted-sync/last-success.json` for the hosted sync state
- `/metrics` and the checked-in Grafana panels for post-recovery operator verification

On hosted surfaces, Terraform points `FOEHNCAST_PIPELINE_REPORT_DIR` at the durable `gs://<artifact-bucket>/airflow/reports` prefix so Cloud Composer, Cloud Run `/metrics`, and operator tools can read the same feature and training summary evidence.

## What Is Already In Place

- Terraform covers the cloud runtime slice.
- The repo contains a Cloud Run deployment path and Artifact Registry publishing flow.
- Cloud Composer is provisioned as the hosted orchestration surface.
- Runtime release acknowledgements use durable GCS storage.
- The application supports a `bigquery` storage backend through the shared feature-store abstraction.
- Local container runs can already mount ADC for BigQuery-based checks.

## Remaining Work

- Cloud Run already owns the public API lane.
- Hosted image delivery already uses Cloud Build plus Artifact Registry; follow-up work is about provenance, signing, and trigger refinement.
- The monitoring stack stays intentionally small and reviewable through checked-in dashboards, alert rules, and scrape config.

## Why This Fits The Project Brief

The goal is cloud-ready pipelines and cloud orchestration. This mapping keeps the validated backend design and uses Google-managed build and orchestration services without discarding the working local baseline.

See [Architecture](architecture.md) for the runtime view and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the maintainer path that bootstraps and advances these hosted targets. The repository root also includes a Terraform README with the deployment details.
