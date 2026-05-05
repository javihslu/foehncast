# Cloud Mapping

FoehnCast already has two hosted directions: a full online compose host and an optional Cloud Run inference service. This page explains how the validated local stack maps onto GCP without changing the core Feature-Training-Inference boundaries.

!!! note "What this page does and does not claim"

    The shared GCP baseline and the hosted entry points exist today.
    Not every longer-term managed service is finished yet, so this page distinguishes between what is implemented now and what remains a transition target.

## Cloud Paths In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Shared GCP baseline</strong></p>
<p>Terraform can provision APIs, Artifact Registry, a GCS artifact bucket, BigQuery storage, and GitHub OIDC identities.</p>
</li>
<li>
<p><strong>Online compose host</strong></p>
<p>A single Compute Engine host can run Airflow, MLflow, and the API from the same repository.</p>
</li>
<li>
<p><strong>Optional Cloud Run path</strong></p>
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
- Cloud deployment keeps the same pipeline boundaries.
- Cloud services replace the local support services used for evaluation and development.
- The app remains a deployable container because inference is a service, not a DAG.

## Current Hosted Topology

<div class="mermaid">
flowchart LR
    TF[Terraform baseline] --> GCP[Shared GCP resources]
    GCP --> HOST[Online compose host]
    GCP --> RUN[Optional Cloud Run service]
    GCP --> GH[GitHub OIDC delivery]
    HOST --> STACK[Airflow + MLflow + API]
    RUN --> API[Inference API only]
</div>

## What Exists Today

| Surface | Current state | Notes |
|--------|---------------|-------|
| Shared GCP baseline | implemented as Terraform inputs and resources | APIs, Artifact Registry, GCS, BigQuery, and OIDC identities |
| Online compose host | implemented as an optional Terraform path | clones the repo, writes `.env`, and runs the full stack |
| Cloud Run service | implemented as an optional Terraform path | serves the inference API only |
| GitHub delivery | implemented | publishes runtime images and can run Terraform remotely |
| BigQuery backend support | implemented in the application | local and hosted runtimes can point the storage backend at BigQuery |

## Honest Mapping From Local To Cloud

| Local component | Current hosted path | Longer-term managed direction |
|----------------|---------------------|-------------------------------|
| `app` container | online compose host or optional Cloud Run service | keep inference as a deployable service |
| Airflow containers | online compose host today | managed Airflow / Cloud Composer later |
| MLflow local service | online compose host today | possibly a separate hosted MLflow service later |
| Local feature storage | BigQuery backend already available | BigQuery remains the cloud data target |
| Local MLflow artifact volume | GCS bucket in the shared baseline | GCS-backed artifacts stay the direction |
| `development_env` container | local and CI only | not intended as a cloud runtime |
| Optional Feast path | can sit on top of the same curated data | can later point the feature view at BigQuery |

## Cloud Pipeline Shape

<div class="mermaid">
flowchart TD
    OME[Open-Meteo] --> FEAT[Feature job]
    FEAT --> BQ[(BigQuery curated features)]
    BQ --> TRAIN[Training job]
    TRAIN --> MLF[(MLflow)]
    MLF --> RUN[Cloud Run app]
    OME --> RUN
    OSRM[OSRM] --> RUN
    BQ --> FEAST[Optional Feast view]
    FEAST --> RUN
</div>

| Layer | Cloud direction |
|------|-----------------|
| Feature pipeline | write curated rows to BigQuery |
| Training pipeline | read curated rows, train, evaluate, and register through MLflow |
| Inference pipeline | serve the API on the compose host or through Cloud Run |
| Optional Feast path | point the same logical feature view at BigQuery instead of local parquet |

## Runtime Differences That Matter

| Area | Local baseline | Hosted path |
|------|----------------|-------------|
| Storage | local parquet by default | BigQuery becomes the shared cloud data surface |
| Artifacts | local MLflow artifact volume | GCS bucket |
| Auth | local `.env` plus developer credentials | runtime service accounts and GitHub OIDC |
| Image source | local builds | GHCR runtime images or Artifact Registry app image |
| Public exposure | local ports on the developer machine | compose host exposes only the app by default; Cloud Run exposes only the inference service |

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
