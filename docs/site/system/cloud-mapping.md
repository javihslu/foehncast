# Cloud Mapping

FoehnCast has two hosted targets: a hosted full-stack target on one GCP host and an inference-only Cloud Run target. This page explains how the validated local stack maps onto GCP without changing the core Feature-Training-Inference boundaries.

!!! note "What this page does and does not claim"

    The shared GCP baseline and the hosted entry points exist today.
    Not every longer-term managed service is finished yet, so this page distinguishes between what is implemented now and what remains a transition target.
    The current shared environment uses the hosted full-stack target. The inference-only Cloud Run path is implemented, but it is not the active shared deployment surface today.

## Cloud Paths In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Shared GCP baseline</strong></p>
<p>Terraform can provision APIs, Artifact Registry, a GCS artifact bucket, BigQuery storage, and GitHub OIDC identities.</p>
</li>
<li>
<p><strong>Hosted full-stack target</strong></p>
<p>A single Compute Engine host can run Airflow, MLflow, and the API from the same repository.</p>
</li>
<li>
<p><strong>Hosted inference target</strong></p>
<p>The FastAPI inference service can also be deployed as an inference-only Cloud Run surface.</p>
</li>
<li>
<p><strong>Managed direction</strong></p>
<p>Later milestones can replace parts of the host-based path with more managed orchestration and monitoring services.</p>
</li>
</ul>
</div>

## Mapping Principle

- Local Docker proves that the pipelines run together.
- Local and cloud are parallel deployment targets, not upstream and downstream environments.
- Cloud deployment keeps the same pipeline boundaries.
- Cloud services replace the local support services used for evaluation and development.
- Hosted deployment keeps development-only assets, notebooks, docs build tooling, and local emulators out of the runtime surface.
- The app remains a deployable container because inference is a service, not a DAG.

## Current Hosted Topology

<div class="mermaid">
flowchart LR
    TF[Terraform baseline] --> GCP[Shared GCP resources]
    GCP --> HOST[Hosted full-stack target]
    GCP -. optional .-> RUN[Hosted inference target]
    TF --> GH[GitHub OIDC delivery]
    HOST --> STACK[Airflow + MLflow + API]
    RUN --> API[Inference API only]
    GH --> HOST
    GH -. app image publish .-> RUN
</div>

## What Exists Today

| Surface | Deploys | Leaves out | Current state |
|--------|---------|------------|---------------|
| Shared GCP baseline | APIs, Artifact Registry, GCS, BigQuery, Datastore, and OIDC identities | app containers | implemented as Terraform inputs and resources |
| Hosted full-stack target | Airflow, MLflow, and the API on one Compute Engine host | `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | implemented as a Terraform path and active in the shared environment |
| Hosted inference target | the FastAPI inference API on Cloud Run | Airflow, hosted MLflow container, `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | implemented as a Terraform and image-delivery path, currently disabled in the shared environment |
| GitHub delivery | image publishing and remote Terraform runs | runtime services | implemented and bootstrapped for the shared environment |

The hosted paths deploy runtime services only. Development assets stay local or CI-only.
| BigQuery backend support | implemented in the application | local and hosted runtimes can point the storage backend at BigQuery |

Today the shared environment uses the hosted full-stack target because it keeps Airflow and MLflow co-located with the API. The Cloud Run path remains the smaller optional API-only surface for a later or separate deployment slice.

## Honest Mapping From Local To Cloud

| Local component | Current hosted path | Longer-term managed direction |
|----------------|---------------------|-------------------------------|
| `app` container | hosted full-stack target or hosted inference target | keep inference as a deployable service |
| Airflow containers | hosted full-stack target today | managed Airflow / Cloud Composer later |
| MLflow local service | hosted full-stack target today with GCS-backed artifacts | possibly a separate hosted MLflow service later |
| Local feature storage | BigQuery backend already available | BigQuery remains the cloud data target |
| Local MLflow artifact volume | GCS artifact destination on the hosted compose path | GCS-backed artifacts stay the direction |
| `development_env` container | local and CI only | not intended as a cloud runtime |
| Feast serving path | sits on top of the same curated data | can point the feature view at BigQuery |

## Cloud Pipeline Shape

<div class="mermaid">
flowchart TD
    OME[Open-Meteo] --> RAW[(GCS raw landing)]
    RAW --> FEAT[Feature job]
    FEAT --> BQ[(BigQuery curated features)]
    BQ --> TRAIN[Training job]
    TRAIN --> MLF[(MLflow)]
    MLF --> RUN[Hosted inference target]
    OME --> RUN
    OSRM[OSRM] --> RUN
    BQ --> FEAST[Feast view]
    FEAST --> RUN
</div>

| Layer | Cloud direction |
|------|-----------------|
| Raw landing | keep immutable API payloads in GCS when a landing layer is needed |
| Feature pipeline | transform landed or live inputs and write curated rows to BigQuery |
| Training pipeline | read curated rows, train, evaluate, and register through MLflow |
| Inference pipeline | serve the API on the hosted full-stack target or through the inference-only Cloud Run target |
| Feast serving path | point the same logical feature view at BigQuery instead of local parquet |

## Storage Layering In Cloud

The current cloud direction works best when storage is split by role rather than by forcing every layer into one system.

| Data role | Recommended cloud surface | Why |
|----------|---------------------------|-----|
| Raw landing and archive | GCS | cheap retention, append-friendly, and flexible when upstream payloads drift |
| Curated analytical features | BigQuery native tables | query-friendly, partitionable, clusterable, and well suited to training plus Feast offline reads |
| Feast registry and staging | GCS | metadata and staging artifacts fit object storage better than warehouse tables |
| Feast offline source | BigQuery table or view | same curated layer used by analytics and training |

External tables still have a place for raw or staging access, but they are not the preferred primary store for repeatedly queried curated features.

## Cloud Storage Control Surface

The cloud path stays coherent because it is driven by explicit application and infrastructure surfaces rather than by a vague translation of the local setup.

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

In practical terms, GCS owns raw landing and registry-style metadata for the cloud path, BigQuery owns the curated analytical layer for the cloud path, and Feast reads the curated layer instead of redefining it. The local path uses the bundled MinIO surface as its default object-access layer while keeping the hosted-only BigQuery and Datastore roles separate.

## Runtime Differences That Matter

| Area | Local baseline | Hosted path |
|------|----------------|-------------|
| Storage | MinIO-backed curated objects plus local Feast parquet and a Datastore-mode emulator | GCS holds raw landing and artifacts; BigQuery becomes the shared curated cloud data surface |
| Artifacts | MinIO-backed MLflow artifact path | GCS bucket |
| Auth | local `.env` plus developer credentials | runtime service accounts and GitHub OIDC |
| Image source | local builds | GHCR runtime images or Artifact Registry app image |
| Public exposure | local ports on the developer machine | the hosted full-stack target exposes only the app by default; Cloud Run exposes only the inference service |

## What Is Already In Place

- Terraform already covers the first cloud runtime slice.
- The repo already contains a Cloud Run deployment path and Artifact Registry publishing flow.
- The application already supports a `bigquery` storage backend through the shared feature-store abstraction.
- Local container runs can already mount ADC for BigQuery-based checks.

## Current Gaps

- The current online path still keeps MLflow on the compose host rather than a separate managed service.
- Managed Airflow provisioning and DAG deployment are not yet fully automated in the same way as the local stack.
- Monitoring is still lighter than the final MS4 target.
- The two hosted paths solve different needs today: one keeps the full stack online, the other isolates inference as a service.

## Why This Fits The Project Brief

The project brief asks for cloud-ready pipelines and cloud orchestration. This mapping keeps the backend already validated in MS2, but replaces the local support stack with cloud services that can run autonomously after deployment.

See [Architecture](architecture.md) for the current runtime view. The repository root also includes a Terraform README with the deployment details.
