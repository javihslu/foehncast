# Hosted Full-Stack

FoehnCast keeps the hosted full-stack target as the private operator lane in the shared environment. Cloud Run carries the public API lane. Cloud Composer owns hosted orchestration. Cloud Build publishes runtime images. The operator services — MLflow, monitoring, and private app checks — run on managed GCP surfaces alongside the same shared data layer.

This page describes the hosted full-stack contract and how the managed services split responsibilities.

!!! note "Scope"

    This page describes the validated hosted operator contract.
    It explains the split between Cloud Run, Cloud Composer, Cloud Build, and supporting operator services.
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
        RUN["Cloud Run API"]:::platform
        CMP["Cloud Composer"]:::operator
        MLF["MLflow"]:::operator
        MON["Monitoring"]:::operator
    end

    TF --> DATA
    DATA --> RUN
    DATA --> CMP
    GH --> RUN
    GH --> CMP
    CMP --> MLF
    CMP --> MON
</div>

## Role In The Shared Environment

| Lane | Concrete target | Main role |
|------|----------------|-----------|
| Shared API lane | Cloud Run hosted inference target | serve the public FastAPI routes |
| Operator lane | Cloud Composer plus managed operator services | provide the hosted orchestration, tracking, and monitoring surface |

The hosted full-stack target stays a runtime target, not a contributor environment. It depends on shared GCP storage and identities instead of local emulators, and it stays private while Cloud Run owns public serving.

## Shared Core And Hosted Differences

| Shared with the local evaluator | Different in the hosted operator lane |
|------|--------------------------------------|
| Same Feature-Training-Inference boundaries | BigQuery, GCS, and Datastore replace local object and emulator surfaces |
| Same FastAPI app and Feast-backed feature path | Cloud Run carries the shared public API while the operator services stay private |
| Same Airflow, MLflow, and monitoring roles | Cloud Composer owns orchestration; MLflow and monitoring run as managed operator services |
| Same repository and runtime contracts | service accounts and GitHub OIDC replace local developer credentials |

That makes the hosted full-stack target a managed operator surface, not a single-VM deployment.

## Surface Responsibilities

| Surface | Main responsibility | Must not become |
|------|----------------------|-----------------|
| Shared GCP baseline | provide Artifact Registry, GCS, BigQuery, Datastore, and identity foundations | the application runtime itself |
| Cloud Composer | schedule DAGs, retries, backfills, and runtime release handoff | a contributor setup path or notebook host |
| Cloud Run | serve the public FastAPI product and service routes | a hidden deployment control plane |
| Cloud Build | publish reviewed runtime images to Artifact Registry | a substitute for GitHub-reviewed delivery |
| MLflow, Prometheus, and Grafana | operator tracking, monitoring, and review | the rider-facing interface |
| GitHub OIDC delivery | run remote Terraform and image-driven deploy updates | a substitute for the runtime orchestrator |

## Runtime Contract

The hosted full-stack target relies on these shared runtime dependencies:

- BigQuery for the curated cloud feature layer
- GCS for MLflow artifacts and Feast registry-style storage
- a named Datastore-mode database for Feast online serving
- the same Feast runtime contract used by the Cloud Run path so both hosted targets point at the same logical serving configuration
- runtime service accounts with appropriate IAM roles instead of mounted key files

The identity split around this target is deliberate:

- GitHub Actions uses the deployer identity for Terraform apply, image publish, and Cloud Run rollout work.
- Cloud Run uses its own narrower runtime identity for the inference-only service.
- Cloud Composer uses a dedicated service account scoped to orchestration, training, MLflow, and Feast preparation.

The Composer identity remains broader than the Cloud Run identity only because orchestration still owns more responsibilities in the hosted environment. The goal is to keep each service's IAM scope as narrow as its actual duties require.

## Bootstrap And Day-2 Delivery

The hosted full-stack target is not part of the default contributor path. Its lifecycle splits into one-time maintainer bootstrap and GitHub-managed day-2 delivery after bootstrap. For this target, the hosted-specific contract is: Terraform provisions managed services and shared cloud data surfaces, GitHub Actions publishes DAGs and images, and the operator services stay private while Cloud Run remains the public API lane.

See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the detailed bootstrap, remote Terraform, and runtime-release handoff steps.

## Hosted Sync Contract

The hosted environment tracks deployment state through durable evidence rather than VM-local state.

The sync contract is:

- Cloud Composer receives reviewed DAG bundles from the GitHub publish workflow
- each successful sync writes `.state/hosted-sync/last-success.json`
- the app republishes that status through `/metrics`
- Grafana can show the last successful hosted refresh from the same sync state

This makes the hosted target observable through standard metrics and evidence files.

## Exposure And Verification

The shared hosted target keeps exposure narrow by default.

The exposure contract is:

- Cloud Composer and MLflow stay private through IAM and network controls
- operator monitoring surfaces remain on the operator side unless you deliberately publish them
- `bootstrap-gcp` treats Cloud Run as the primary hosted API path and verifies `/health`, `/spots`, and `/metrics`

This preserves the same public-surface rule used across the rest of the docs: the app is the product and service surface, while operator tools remain private by default.

## What Stays Out Of This Target

The hosted full-stack path deploys runtime services only.

These surfaces stay local or CI-only:

- `development_env`
- notebooks
- docs build tooling
- the local MinIO objectstore
- the local Datastore emulator

## Rollback

Cloud Run remains the only supported public API path in the shared environment, so rollback uses the reviewed runtime trigger contract. The runtime trigger sends a reviewed rollback request to the Composer Airflow API.

See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the detailed rollback and retry runbooks.

## Why This Target Works

- it keeps the full operator stack online in the shared environment using managed GCP services
- it reuses the same repository and application boundaries as the local evaluator target
- it keeps the hosted runtime tied to reviewable Terraform outputs, GitHub delivery, and metrics
- it keeps public exposure narrow enough that the app remains the only default internet-facing surface
- it uses managed orchestration instead of VM-owned scheduling

See [Architecture](architecture.md), [Local Evaluator](local-evaluator.md), [Inference Pipeline](inference-pipeline.md), [Cloud Mapping](cloud-mapping.md), and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the surrounding runtime and deployment boundaries.
