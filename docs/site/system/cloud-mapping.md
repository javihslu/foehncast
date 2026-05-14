# Cloud Mapping

FoehnCast has two hosted targets. The shared environment uses the inference-only Cloud Run target as the only promoted public API path, while the hosted full-stack target stays online on one GCP host for operator tooling. This page explains how the validated local stack maps onto GCP without changing the core Feature-Training-Inference boundaries.

!!! note "What this page does and does not claim"

    The shared GCP baseline and the hosted entry points already exist.
    The current shared environment uses Cloud Run as the shared hosted API path while retaining the hosted full-stack target for operator tooling.

## Cloud Paths In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Shared GCP baseline</strong></p>
<p>Terraform can provision APIs, Artifact Registry, a GCS artifact bucket, BigQuery storage, and GitHub OIDC identities.</p>
</li>
<li>
<p><strong>Hosted full-stack target</strong></p>
<p>A single Compute Engine host runs Airflow, MLflow, monitoring, and the retained operator stack from the same repository.</p>
</li>
<li>
<p><strong>Hosted inference target</strong></p>
<p>The FastAPI inference service runs as the promoted primary hosted API path on Cloud Run.</p>
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
| Hosted full-stack target | Airflow, MLflow, and the API on one Compute Engine host | `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | implemented and retained for operator control-plane duties |
| Hosted inference target | the FastAPI inference API on Cloud Run | Airflow, hosted MLflow container, `development_env`, notebooks, docs build tooling, local MinIO, and local emulators | implemented and promoted as the primary hosted API path |
| GitHub delivery | image publishing and remote Terraform runs | runtime services | implemented and bootstrapped for the shared environment |
| BigQuery backend support | support for a BigQuery storage backend in the app | none | available in both local and hosted runtimes |

The hosted paths deploy runtime services only. Development assets stay local or CI-only. The hosted full-stack target keeps Airflow, MLflow, Prometheus, and Grafana on the operator side unless you intentionally publish them yourself.

The shared environment uses Cloud Run as the only promoted public API path. The hosted full-stack target stays online because it keeps Airflow, MLflow, and monitoring together.

## Active Shared Deployment Path

The shared environment currently follows one promoted hosted lane plus one retained operator lane:

- maintainers bootstrap once from Google Cloud Shell and seed the remote Terraform plus repository-variable contract
- GitHub Actions remote Terraform applies handle day-2 infrastructure changes after bootstrap
- Cloud Run carries the primary shared hosted API URL
- one Compute Engine host keeps Airflow, MLflow, the API, and the monitoring stack online together as the retained operator surface

This is why the shared environment docs now center Cloud Run as the first hosted API URL while still keeping the compose-host path visible as the retained control plane.

Rollback for the shared API now means retrying the reviewed runtime release handoff, not reopening the VM app publicly or mutating runtime state directly from GitHub. `.github/workflows/publish-app-image.yml` stops at image publication, `.github/workflows/trigger-runtime-release.yml` sends the reviewed deploy, promote, or rollback request into the hosted Airflow receiver, and the runtime side records the acknowledgement under `airflow/reports/runtime-release-latest.json`. The remaining retirement gate is whether the operator lane can later shrink without blurring the Airflow and MLflow control-plane boundary.

## Orchestration Surface Of Record

The runtime orchestration surface of record is the current hosted Airflow control plane on the retained operator host.

| Option | Fit against current scope | Decision |
|------|---------------------------|----------|
| Current hosted Airflow control plane | Reuses the validated local Airflow DAG and asset model, keeps retries and backfills on the same operator surface, and avoids introducing another platform migration before the boundary cleanup lands | chosen now |
| Composer | Offers a stronger managed-service story, but adds service cost, IAM work, and migration churn before the team has finished clarifying the GitHub-versus-runtime split | deferred |
| Lighter managed trigger model | Could narrow the hosted footprint, but would replace Airflow-owned runtime behavior instead of simply clarifying ownership boundaries | not chosen for this horizon |

GitHub therefore remains the delivery plane, while hosted Airflow remains the runtime scheduling plane. The later retry and backfill runbooks should assume Airflow as the operator surface until a future decision changes that explicitly.

## GitHub Versus GCP Delivery Boundary

The current delivery story is split intentionally:

- GitHub owns reviewed artifacts, CI validation, image publication, and Terraform-driven infrastructure changes.
- GCP owns runtime execution: Cloud Run serving, hosted Airflow scheduling, retries, backfills, runtime secrets and identities, and hosted telemetry.
- Terraform outputs, repository variables, and published images form the handoff contract between the two planes.

For this horizon, hosted Airflow on the retained operator host remains the orchestration surface of record. That means Cloud Run is the serving surface, not the scheduler, and GitHub Actions is the delivery plane, not the runtime orchestrator.

## Operator Recovery Lane

The active shared environment now has one reviewed recovery split:

- delivery failures before runtime execution stay on the GitHub plus Terraform side
- serving rollout retries use the explicit runtime trigger contract, not ad hoc SSH-only release changes
- feature retries and backfills stay on hosted Airflow on the retained operator host
- replaying one logical date starts with `feature_pipeline`; the downstream `training_pipeline` run should remain asset-triggered when the replay is meant to refresh production training state

This keeps the recovery story aligned with the topology: GitHub advances reviewed delivery, Cloud Run serves the public API, and hosted Airflow on the retained host owns runtime replay work.

## Honest Mapping From Local To Cloud

| Local component | Current hosted path |
|----------------|---------------------|
| `app` container | hosted inference target for the primary shared API, plus the retained hosted full-stack app surface for control-plane duties |
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
    MLF --> RUN[Hosted inference target]
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
| Inference pipeline | serve the primary hosted API on Cloud Run while retaining the hosted full-stack app surface for operator duties |
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
| Public exposure | local ports on the developer machine | Cloud Run is the shared hosted API surface; the retained hosted full-stack target stays private by default; operator dashboards stay private unless you deliberately publish them |

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
- Hosted Airflow remains the orchestration surface of record for runtime scheduling, retries, and backfills.
- The two hosted paths now solve different roles: Cloud Run is the API surface, and the compose host keeps the broader operator stack online.
- The monitoring stack stays intentionally small and reviewable through checked-in dashboards, alert rules, and scrape config.

## Why This Fits The Project Brief

The goal is cloud-ready pipelines and cloud orchestration. This mapping keeps the validated backend design, but replaces the local support stack with cloud services that can run after deployment.

See [Architecture](architecture.md) for the current runtime view and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the maintainer path that bootstraps and advances these hosted targets. The repository root also includes a Terraform README with the deployment details.
