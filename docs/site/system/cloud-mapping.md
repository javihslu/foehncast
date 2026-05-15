# Cloud Mapping

FoehnCast has one public hosted lane and one private operator lane. Cloud Run serves the shared API. A private operator surface carries Airflow, MLflow, monitoring, and private app checks. In the active shared environment that surface is implemented by a retained Compute Engine host, while the intended managed direction moves image builds toward Cloud Build and orchestration toward Cloud Composer. This page maps the cloud lanes without changing the core Feature-Training-Inference boundaries.

!!! note "What this page covers"

    The shared GCP baseline defines one public API lane and one private operator lane.
    Cloud Run is the shared public API lane.
    The hosted full-stack target is the active implementation of the private operator lane.
    Cloud Build and Cloud Composer are the intended managed hosted direction.

## Cloud Paths In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Shared GCP baseline</strong></p>
<p>Terraform provisions APIs, Artifact Registry, GCS, BigQuery, and GitHub OIDC.</p>
</li>
<li>
<p><strong>Active operator lane</strong></p>
<p>One Compute Engine host runs Airflow, MLflow, monitoring, and private app checks in the shared environment.</p>
</li>
<li>
<p><strong>Managed hosted direction</strong></p>
<p>Cloud Build and Cloud Composer are the intended hosted build and orchestration targets.</p>
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
| Operator lane | hosted full-stack target on Compute Engine | implemented on retained host | private by default | provide the private operator surface for Airflow, MLflow, monitoring, and private app checks |
| Managed hosted control plane | Cloud Build and Cloud Composer | target direction | private or platform-only | build hosted images and run hosted Airflow workloads without VM-owned orchestration |
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

## Active Hosted Topology

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
            HOST["Compute Engine host"]:::operator
            OPS["Airflow + MLflow + metrics + app checks"]:::operator
            HOST --> OPS
        end

        BASE --> RUN
        BASE --> HOST
    end

    TF --> BASE
    GH -- "Deploy" --> RUN
    GH -- "Refresh" --> HOST
</div>

## Managed Direction

<div class="mermaid">
flowchart LR
        classDef managed fill:#fff8e1,stroke:#f57f17
        classDef git fill:#f4f1ea,stroke:#f05032
        classDef store fill:#ececff,stroke:#9370db

        GH["fab:fa-github GitHub Actions"]:::git

        subgraph ManagedGCP ["fab:fa-google Managed plane"]
            direction LR
            CB["Cloud Build"]:::managed --> CRUN["Cloud Run API"]:::managed
            CMP["Cloud Composer"]:::managed --> DATA["BigQuery + GCS"]:::store
        end

        GH -- "Build" --> CB
</div>

The managed direction keeps the same storage and API surfaces, but it changes two supporting planes: image builds move into Cloud Build, and orchestration moves into Cloud Composer. The retained host should then shrink to only the services that still need it.

## Implemented Hosted Surfaces

| Surface | Deploys | Leaves out | Implementation status |
|--------|---------|------------|---------------|
| Shared GCP baseline | APIs, Artifact Registry, GCS, BigQuery, Datastore, and OIDC identities | app containers | implemented through Terraform |
| Hosted full-stack target (operator lane) | Airflow, MLflow, and the API on one Compute Engine host | `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | implemented as the active operator surface |
| Hosted inference target (API lane) | the FastAPI inference API on Cloud Run | Airflow, hosted MLflow container, `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | implemented and promoted as the primary hosted API path |
| GitHub delivery | image publishing and remote Terraform runs | runtime services | implemented and bootstrapped for the shared environment |
| Hosted runtime image publishing | app image in Artifact Registry, other runtime images still mixed | n/a | partial; not yet one managed build contract |
| BigQuery backend support | support for a BigQuery storage backend in the app | none | available in both local and hosted runtimes |

The hosted targets deploy runtime services only. Development assets stay local or CI-only. Cloud Run is the only promoted public API path. The hosted full-stack target stays private by default and keeps Airflow, MLflow, Prometheus, and Grafana together on the operator side.

## Active Shared Deployment Path

The shared environment keeps a stable split: Cloud Run carries the shared public API URL, one Compute Engine host stays online as the private operator lane for Airflow, MLflow, monitoring, and private app checks, and GitHub Actions plus remote Terraform advance reviewed day-2 changes after maintainer bootstrap. This is the active operating contract, not the desired end state.

The intended hosted direction keeps Cloud Run as the public API, moves hosted image builds to Cloud Build, and moves hosted orchestration to Cloud Composer. See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the detailed active-versus-target delivery boundary and [Configuration and Contracts](configuration-and-contracts.md) for the reviewed value-surface inventory.

## Managed Orchestration Direction

Cloud Composer is the target managed orchestration direction, and Terraform can now provision a Cloud Composer environment for readiness work.

Before a later cutover, DAG packaging, Python dependency delivery, secret and runtime-config injection, network and API reachability, and a reviewed runtime release entry that reaches the managed Airflow surface directly still need to stop depending on the retained operator host. The retained host remains the active orchestration authority until those boundaries move. See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the detailed active-versus-target delivery boundary and [Configuration and Contracts](configuration-and-contracts.md) for the reviewed value-surface inventory.

## Active And Target Hosted Mapping

| Concern | Active hosted path | Target hosted direction |
|---------|---------------------|-------------------------|
| FastAPI app | Cloud Run API lane for shared traffic, plus the private operator lane for host-local checks | Cloud Run remains the only shared public API lane |
| Hosted image builds | GitHub-hosted workflows publish an app image to Artifact Registry and other runtime images through a mixed path | Cloud Build publishes all hosted runtime images to Artifact Registry |
| Airflow orchestration | retained operator lane in the active shared environment | Cloud Composer |
| MLflow tracking | operator lane in the active shared environment with GCS-backed artifacts | stays on a separate operator surface until a later decision changes it |
| Monitoring | operator lane in the active shared environment | stays private on an operator surface, whether retained-host or later replacement |
| Curated storage | BigQuery backend already available | stays on BigQuery |
| Feast serving path | sits on top of the same curated data | keeps the same logical feature view against cloud storage |

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
| Inference pipeline | serve the public API on Cloud Run while keeping the operator-host app available for private checks |
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
| Image source | local builds | mixed GitHub-hosted image publication in the active shared environment; target is Cloud Build plus Artifact Registry for all hosted runtime images |
| Public exposure | local ports on the developer machine | Cloud Run is the shared hosted API surface; the operator lane stays private by default; dashboards stay private unless you deliberately publish them |

## Recovery Evidence In Cloud

Operators should be able to prove what changed after a retry, replay, or rollback request.

The stable evidence surfaces are:

- `airflow/reports/feature-pipeline-<dataset>-latest.json` and its history copy for feature retries or backfills
- `airflow/reports/training-pipeline-<dataset>-latest.json` and its history copy for training follow-up
- `airflow/reports/runtime-release-latest.json` and its history copy for reviewed deploy, promote, or rollback handoffs
- `.state/online-compose-sync/last-success.json` for the retained host refresh state
- `/metrics` and the checked-in Grafana panels for post-recovery operator verification

## What Is Already In Place

- Terraform already covers the first cloud runtime slice.
- The repo already contains a Cloud Run deployment path and Artifact Registry publishing flow.
- Terraform can now provision an optional Cloud Composer environment for managed-Airflow readiness work.
- The application already supports a `bigquery` storage backend through the shared feature-store abstraction.
- Local container runs can already mount ADC for BigQuery-based checks.

## Remaining Hosted Simplifications

- MLflow stays on the retained operator lane in the active shared environment.
- Airflow still runs on the retained operator lane as the operational authority, so runtime release, retries, and backfills still depend on VM-backed orchestration even when a Cloud Composer environment is provisioned.
- Cloud Run already owns the public API lane and should keep that role.
- Hosted image delivery is still split between GitHub-hosted execution and mixed registries; the target is Cloud Build plus Artifact Registry.
- The monitoring stack stays intentionally small and reviewable through checked-in dashboards, alert rules, and scrape config.

## Why This Fits The Project Brief

The goal is cloud-ready pipelines and cloud orchestration. This mapping keeps the validated backend design, makes the retained-host dependency explicit, and points the hosted path toward Google-managed build and orchestration services without discarding the working local baseline.

See [Architecture](architecture.md) for the runtime view and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the maintainer path that bootstraps and advances these hosted targets. The repository root also includes a Terraform README with the deployment details.
