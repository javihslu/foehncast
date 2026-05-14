# Cloud Mapping

FoehnCast has two hosted targets, but the active shared environment uses the hosted full-stack target on one GCP host. The inference-only Cloud Run target remains available as a smaller alternative. This page explains how the validated local stack maps onto GCP without changing the core Feature-Training-Inference boundaries.

!!! note "What this page does and does not claim"

    The shared GCP baseline and the hosted entry points already exist.
    The current shared environment uses the hosted full-stack target. The inference-only Cloud Run path exists, but it is not the active shared deployment path today.

## Cloud Paths In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Shared GCP baseline</strong></p>
<p>Terraform can provision APIs, Artifact Registry, a GCS artifact bucket, BigQuery storage, and GitHub OIDC identities.</p>
</li>
<li>
<p><strong>Hosted full-stack target</strong></p>
<p>A single Compute Engine host can run Airflow, MLflow, and the API from the same repository. This is the active shared deployment path today.</p>
</li>
<li>
<p><strong>Hosted inference target</strong></p>
<p>The FastAPI inference service can also run as an inference-only Cloud Run target when a smaller API-only surface is enough.</p>
</li>
<li>
<p><strong>Operator delivery</strong></p>
<p>Maintainers bootstrap once, then GitHub Actions advances the shared cloud path.</p>
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

## Surface Exposure In Cloud

| Surface | Intended audience | Default exposure |
|------|-------------------|------------------|
| FastAPI app routes | riders, service clients, smoke tests | exposed by the active hosted app target |
| `/metrics` and scrape targets | Prometheus and operators | service-only |
| Airflow, MLflow, Prometheus, and Grafana | operators | private by default |
| Public docs and review artifacts | reviewer, course audience, fork reader | public-safe when rendered from snapshots, markdown, or screenshots |

This boundary matters because the hosted app is the product and service surface. Grafana remains an operator dashboard, and public docs should prefer rendered evidence over live embeds of private hosted tools.

## Current Hosted Topology

<div class="mermaid">
flowchart LR
    TF[Terraform baseline] --> GCP[Shared GCP resources]
    GCP --> HOST[Hosted full-stack target]
    GCP -. optional .-> RUN[Hosted inference target]
    TF --> GH[GitHub OIDC delivery]
    HOST --> STACK[Airflow + MLflow + API + monitoring]
    RUN --> API[Inference API only]
    GH --> HOST
    GH -. app image publish .-> RUN
</div>

## What Exists Today

| Surface | Deploys | Leaves out | Current state |
|--------|---------|------------|---------------|
| Shared GCP baseline | APIs, Artifact Registry, GCS, BigQuery, Datastore, and OIDC identities | app containers | implemented through Terraform |
| Hosted full-stack target | Airflow, MLflow, and the API on one Compute Engine host | `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | implemented and active in the shared environment |
| Hosted inference target | the FastAPI inference API on Cloud Run | Airflow, hosted MLflow container, `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | implemented, but not active in the shared environment |
| GitHub delivery | image publishing and remote Terraform runs | runtime services | implemented and bootstrapped for the shared environment |
| BigQuery backend support | support for a BigQuery storage backend in the app | none | available in both local and hosted runtimes |

The hosted paths deploy runtime services only. Development assets stay local or CI-only. The hosted full-stack target keeps Airflow, MLflow, Prometheus, and Grafana on the operator side unless you intentionally publish them yourself.

The shared environment uses the hosted full-stack target because it keeps Airflow, MLflow, and the API together. The Cloud Run path stays available as a smaller API-only option.

## Shared Hosted App Contract

The two hosted targets differ in runtime size, not in their core app surface.

- both hosted targets serve the same FastAPI routes for `/health`, `/spots`, and `/metrics`
- both hosted targets rely on the same app-side storage and Feast runtime assumptions injected by Terraform
- the compose-host path adds extra sync-freshness signals to `/metrics` because it owns the repo-sync timer, but that is an operator extension on top of the same app contract

## Active Shared Deployment Path

The shared environment currently follows one hosted lane:

- maintainers bootstrap once from Google Cloud Shell and seed the remote Terraform plus repository-variable contract
- GitHub Actions remote Terraform applies handle day-2 infrastructure changes after bootstrap
- one Compute Engine host keeps Airflow, MLflow, the API, and the monitoring stack online together
- the inference-only Cloud Run target remains implemented, but it is not the main shared deployment target today

This is why the shared environment docs keep centering the compose-host path even though the Cloud Run path is real and supported.

## Honest Mapping From Local To Cloud

| Local component | Current hosted path |
|----------------|---------------------|
| `app` container | hosted full-stack target today, or the hosted inference target when a smaller API-only surface is enough |
| Airflow containers | hosted full-stack target today |
| MLflow local service | hosted full-stack target today with GCS-backed artifacts |
| Local feature storage | BigQuery backend already available |
| Local MLflow artifact volume | GCS artifact destination on the hosted compose path |
| `development_env` container | local and CI only |
| Feast serving path | sits on top of the same curated data |

## Cloud Pipeline Shape

<div class="mermaid">
flowchart TD
    OME[Open-Meteo] --> RAW[(GCS raw landing)]
    RAW --> FEAT[Feature job]
    FEAT --> BQ[(BigQuery curated features)]
    BQ --> TRAIN[Training job]
    TRAIN --> MLF[(MLflow)]
    MLF --> HOST[Hosted full-stack target today]
    MLF -. optional smaller target .-> RUN[Hosted inference target]
    OME --> HOST
    OME --> RUN
    OSRM[OSRM] --> HOST
    OSRM --> RUN
    BQ --> FEAST[Feast view]
    FEAST --> HOST
    FEAST -. optional .-> RUN
</div>

| Layer | Cloud direction |
|------|-----------------|
| Raw landing | keep immutable API payloads in GCS when a landing layer is needed |
| Feature pipeline | transform landed or live inputs and write curated rows to BigQuery |
| Training pipeline | read curated rows, train, evaluate, and register through MLflow |
| Inference pipeline | serve the API on the active hosted full-stack target, or optionally through the inference-only Cloud Run target for a smaller surface |
| Feast serving path | point the same logical feature view at BigQuery instead of local parquet |

## Storage Layering In Cloud

The current cloud design works best when storage is split by role instead of forcing every layer into one system.

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
| Image source | local builds | GHCR runtime images or Artifact Registry app image |
| Public exposure | local ports on the developer machine | the active shared environment uses the hosted full-stack target and exposes only the app by default; Cloud Run exposes only the inference service when used; operator dashboards stay private unless you deliberately publish them |

## What Is Already In Place

- Terraform already covers the first cloud runtime slice.
- The repo already contains a Cloud Run deployment path and Artifact Registry publishing flow.
- The application already supports a `bigquery` storage backend through the shared feature-store abstraction.
- Local container runs can already mount ADC for BigQuery-based checks.

## Current Tradeoffs

- MLflow stays on the compose host in the active shared environment.
- Airflow also stays on the compose host, while the sync timer, retained sync state, and monitoring stack make that host observable.
- The two hosted paths solve different needs: one keeps the full stack online, the other narrows hosting to the API.
- The monitoring stack stays intentionally small and reviewable through checked-in dashboards, alert rules, and scrape config.

## Why This Fits The Project Brief

The goal is cloud-ready pipelines and cloud orchestration. This mapping keeps the validated backend design, but replaces the local support stack with cloud services that can run after deployment.

See [Architecture](architecture.md) for the current runtime view and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the maintainer path that bootstraps and advances these hosted targets. The repository root also includes a Terraform README with the deployment details.
