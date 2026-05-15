# Cloud Mapping

FoehnCast keeps one public hosted lane and one private operator lane. Cloud Run carries the shared API, while the hosted full-stack target stays online on one Compute Engine host for Airflow, MLflow, and monitoring. That retained host is current, not the intended long-term orchestration authority. This page maps the validated local stack onto those GCP lanes without changing the core Feature-Training-Inference boundaries.

!!! note "What this page covers"

    The shared GCP baseline and both hosted lanes already exist.
    Cloud Run is the shared public API lane.
    The hosted full-stack target stays online as the private operator lane.
    Cloud Composer is the target managed orchestration direction.

## Cloud Paths In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Shared GCP baseline</strong></p>
<p>Terraform provisions APIs, Artifact Registry, GCS, BigQuery, and GitHub OIDC.</p>
</li>
<li>
<p><strong>Hosted full-stack target</strong></p>
<p>One Compute Engine host runs Airflow, MLflow, monitoring, and private app checks.</p>
</li>
<li>
<p><strong>Hosted inference target</strong></p>
<p>Cloud Run serves the promoted FastAPI API.</p>
</li>
<li>
<p><strong>Operator delivery</strong></p>
<p>Maintainers bootstrap once, then GitHub Actions advances reviewed changes.</p>
</li>
</ul>
</div>

## Hosted Lanes At A Glance

| Lane | Concrete target | Default exposure | Main job |
|------|-----------------|------------------|----------|
| Shared API lane | hosted inference target on Cloud Run | public | serve the FastAPI product and service routes |
| Operator lane | hosted full-stack target on Compute Engine | private by default | run Airflow, MLflow, monitoring, and private app checks |
| Managed orchestration direction | Cloud Composer | private or platform-only | run hosted Airflow workloads without VM-owned orchestration |
| Delivery lane | GitHub Actions plus Terraform plus OIDC | not a runtime surface | publish reviewed artifacts and apply reviewed infrastructure changes |

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
    GCP --> RUN[Hosted inference target]
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
| Hosted full-stack target (operator lane) | Airflow, MLflow, and the API on one Compute Engine host | `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | implemented and retained for operator control-plane duties |
| Hosted inference target (API lane) | the FastAPI inference API on Cloud Run | Airflow, hosted MLflow container, `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | implemented and promoted as the primary hosted API path |
| GitHub delivery | image publishing and remote Terraform runs | runtime services | implemented and bootstrapped for the shared environment |
| BigQuery backend support | support for a BigQuery storage backend in the app | none | available in both local and hosted runtimes |

The hosted targets deploy runtime services only. Development assets stay local or CI-only. Cloud Run is the only promoted public API path. The hosted full-stack target stays private by default and keeps Airflow, MLflow, Prometheus, and Grafana together on the operator side.

## Active Shared Deployment Path

Today the shared environment keeps a stable split: Cloud Run carries the shared public API URL, one Compute Engine host stays online as the private operator lane for Airflow, MLflow, monitoring, and private app checks, and GitHub Actions plus remote Terraform advance reviewed day-2 changes after maintainer bootstrap.

Today the retained operator host still owns hosted orchestration. The target managed orchestration direction is Cloud Composer once DAG packaging, Python dependency delivery, secret and runtime-config injection, network and API reachability, and runtime release entry no longer depend on the retained host. See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the detailed current-versus-target boundary and [Configuration and Contracts](configuration-and-contracts.md) for the reviewed value-surface inventory.

## Managed Orchestration Direction

Cloud Composer is the target managed orchestration direction.

Before a later cutover, the repo needs:

- a DAG packaging path that does not depend on a VM checkout
- a Python dependency bundle for hosted Airflow
- secret and runtime-config delivery for the managed orchestrator
- network and API reachability that does not depend on VM SSH
- a reviewed runtime release entry that reaches the managed Airflow surface directly

## Honest Mapping From Local To Cloud

| Local component | Current hosted path |
|----------------|---------------------|
| `app` container | Cloud Run API lane for shared traffic, plus the private operator lane for host-local checks |
| Airflow containers | operator lane today |
| MLflow local service | operator lane today with GCS-backed artifacts |
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
    MLF --> HOST[Operator host lane]
    MLF --> RUN[Cloud Run API lane]
    OME --> HOST
    OME --> RUN
    OSRM[OSRM] --> HOST
    OSRM --> RUN
    BQ --> FEAST[Feast view]
    FEAST --> HOST
    FEAST --> RUN
</div>

| Layer | Cloud direction |
|------|-----------------|
| Raw landing | keep immutable API payloads in GCS when a landing layer is needed |
| Feature pipeline | transform landed or live inputs and write curated rows to BigQuery |
| Training pipeline | read curated rows, train, evaluate, and register through MLflow |
| Inference pipeline | serve the public API on Cloud Run while keeping the operator-host app available for private checks |
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
- The application already supports a `bigquery` storage backend through the shared feature-store abstraction.
- Local container runs can already mount ADC for BigQuery-based checks.

## Current Tradeoffs

- MLflow stays on the compose host in the active shared environment.
- Airflow stays on the compose host, while the sync timer, retained sync state, and monitoring stack make that host observable.
- Cloud Run stays on the public API lane, and the hosted full-stack target keeps the broader private operator stack online.
- The monitoring stack stays intentionally small and reviewable through checked-in dashboards, alert rules, and scrape config.

## Why This Fits The Project Brief

The goal is cloud-ready pipelines and cloud orchestration. This mapping keeps the validated backend design, but replaces the local support stack with cloud services that can run after deployment.

See [Architecture](architecture.md) for the current runtime view and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the maintainer path that bootstraps and advances these hosted targets. The repository root also includes a Terraform README with the deployment details.
