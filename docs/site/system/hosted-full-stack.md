# Hosted Full-Stack

FoehnCast no longer runs a separate hosted full-stack Airflow target. The shared environment now keeps a public Cloud Run lane plus a smaller set of private operator surfaces and managed cloud automation. Local Airflow remains the reviewed DAG runtime and runtime-release handoff path.

This page describes the hosted surfaces that remain after removing the old full-stack VM and managed-orchestration tracks.

!!! note "Scope"

    This page describes the remaining hosted cloud surfaces.
    Cloud Run carries the public API lane.
    Cloud Workflows, Cloud Scheduler, MLflow, and monitoring stay on the operator side.
    It is not the local evaluator setup guide.

## Target Shape

<div class="mermaid">
flowchart TD
    classDef infra fill:#f5f5f5,stroke:#333
    classDef runner fill:#f4f1ea,stroke:#f05032
    classDef platform fill:#fff,stroke:#4285F4
    classDef operator fill:#fff8e1,stroke:#f57f17

    TF["Terraform baseline"]:::infra
    GH["fab:fa-github GitHub Actions + OIDC"]:::runner

    subgraph GCP ["fab:fa-google Hosted environment"]
        direction LR
        DATA["BigQuery + GCS + Datastore"]:::platform
        RUN["Cloud Run services"]:::platform
        WF["Cloud Workflows + Scheduler"]:::operator
        MLF["MLflow"]:::operator
        MON["Managed monitoring"]:::operator
    end

    TF --> DATA
    DATA --> RUN
    DATA --> MLF
    DATA --> WF
    GH --> RUN
    GH --> MLF
    GH --> WF
    RUN --> MON
    MLF --> MON
</div>

## Role In The Shared Environment

| Lane | Concrete target | Main role |
|------|----------------|-----------|
| Shared API lane | Cloud Run hosted API and UI surfaces | serve the public FastAPI routes and rider-facing views |
| Operator surfaces | protected MLflow, monitoring, and internal checks | provide private tracking and review surfaces |
| Hosted automation | Cloud Workflows plus Cloud Scheduler | coordinate scheduled cloud-side refreshes |

The hosted cloud path stays a runtime target, not a contributor environment. It depends on shared GCP storage and identities instead of local emulators, and it stays private while Cloud Run owns public serving.

## Shared Core And Hosted Differences

| Shared with the local evaluator | Different in the hosted cloud path |
|------|--------------------------------------|
| Same Feature-Training-Inference boundaries | BigQuery, GCS, and Datastore replace local object and emulator surfaces |
| Same FastAPI app and Feast-backed feature path | Cloud Run carries the shared public API while operator surfaces stay private |
| Same MLflow and monitoring roles | hosted automation moves to Cloud Workflows and Cloud Scheduler instead of a hosted Airflow stack |
| Same repository and runtime contracts | service accounts and GitHub OIDC replace local developer credentials |

That keeps the hosted path smaller than the old full-stack design without changing the pipeline boundaries.

## Surface Responsibilities

| Surface | Main responsibility | Must not become |
|------|----------------------|-----------------|
| Shared GCP baseline | provide Artifact Registry, GCS, BigQuery, Datastore, and identity foundations | the application runtime itself |
| Cloud Run | serve the public FastAPI product and service routes plus selected hosted services | a hidden deployment control plane |
| Cloud Workflows + Scheduler | coordinate scheduled hosted automation | a contributor setup path or notebook host |
| Cloud Build | publish reviewed runtime images to Artifact Registry | a substitute for GitHub-reviewed delivery |
| MLflow and monitoring | operator tracking and monitoring | the rider-facing interface |
| GitHub OIDC delivery | run remote Terraform and image-driven deploy updates | a substitute for the runtime orchestrator |

## Runtime Contract

The hosted cloud path relies on these shared runtime dependencies:

- BigQuery for the curated cloud feature layer
- GCS for MLflow artifacts, pipeline reports, and Feast registry-style storage
- a named Datastore-mode database for Feast online serving
- Cloud SQL for MLflow metadata
- runtime service accounts with appropriate IAM roles instead of mounted key files

The identity split around this target is deliberate:

- GitHub Actions uses the deployer identity for Terraform apply, image publish, and Cloud Run rollout work
- Cloud Run services use narrower runtime identities for serving and service-to-service access
- Cloud Workflows and Cloud Scheduler use managed service identities to call reviewed runtime entry points

The goal is to keep each service's IAM scope as narrow as its actual duties require.

## Bootstrap And Day-2 Delivery

The hosted cloud path is not part of the default contributor setup. Its lifecycle splits into one-time maintainer bootstrap and GitHub-managed day-2 delivery after bootstrap. Terraform provisions shared services and optional hosted automation, GitHub Actions publishes images and updates hosted surfaces, and local Airflow remains the reviewed DAG runtime when maintainers need explicit runtime-release evidence.

See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the detailed bootstrap, remote Terraform, and runtime-release handoff steps.

## Exposure And Verification

The shared hosted target keeps exposure narrow by default.

The exposure contract is:

- Cloud Run API and UI surfaces are the only public-facing endpoints by default
- MLflow, monitoring, and hosted automation surfaces stay private through IAM and network controls
- `bootstrap-gcp` treats Cloud Run as the primary hosted API path and verifies `/health`, `/spots`, and `/metrics`

This preserves the same public-surface rule used across the rest of the docs: the app is the product and service surface, while operator tools remain private by default.

## What Stays Out Of This Target

The hosted cloud path deploys runtime services only.

These surfaces stay local or CI-only:

- `development_env`
- notebooks
- docs build tooling
- the local MinIO objectstore
- the local Datastore emulator

## Rollback

Cloud Run remains the only supported public API path in the shared environment, so rollback still uses the reviewed runtime-release handoff. The request goes through `scripts/trigger-runtime-release.sh` against the configured Airflow API endpoint, typically from the local operator path.

See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the detailed rollback and retry runbooks.

## Why This Target Works

- it keeps the full operator stack online in the shared environment using managed GCP services
- it reuses the same repository and application boundaries as the local evaluator target
- it keeps the hosted runtime tied to reviewable Terraform outputs, GitHub delivery, and metrics
- it keeps public exposure narrow enough that the app remains the only default internet-facing surface
- it uses managed orchestration instead of VM-owned scheduling

See [Architecture](architecture.md), [Local Evaluator](local-evaluator.md), [Inference Pipeline](inference-pipeline.md), [Cloud Mapping](cloud-mapping.md), and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the surrounding runtime and deployment boundaries.
