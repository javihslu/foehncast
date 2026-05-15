# Hosted Full-Stack (Retained Operator Host)

FoehnCast keeps the hosted full-stack target as the private operator lane in the active shared environment. It runs Airflow, MLflow, the FastAPI app, and the monitoring stack on one Compute Engine host while Cloud Run carries the public API lane. This retained host keeps the operator stack online while hosted image builds move toward Cloud Build and hosted orchestration moves toward Cloud Composer.

This page describes the hosted full-stack contract. It focuses on the active shared runtime target, not on future migrations.

!!! note "Scope"

    This page describes the validated retained operator host contract.
    It explains why that host is a retained operator surface rather than the intended long-term hosted control plane.
    It is not the Composer cutover plan.

## Target Shape

<div class="mermaid">
flowchart LR
    classDef infra fill:#f5f5f5,stroke:#333
    classDef runner fill:#f4f1ea,stroke:#f05032
    classDef platform fill:#fff,stroke:#4285F4
    classDef operator fill:#fff8e1,stroke:#f57f17

    TF["Terraform baseline"]:::infra
    GH["fab:fa-github GitHub Actions + OIDC"]:::runner

    subgraph GCP ["fab:fa-google Hosted environment"]
        direction LR
        DATA["BigQuery + GCS + Datastore"]:::platform
        HOST["Compute Engine operator host"]:::operator
        APP["FastAPI app"]:::operator
        AIR["Airflow"]:::operator
        MLF["MLflow"]:::operator
        MON["Prometheus + StatsD + Grafana"]:::operator
        SYNC["Repo sync timer"]:::operator
    end

    TF --> DATA
    DATA --> HOST
    GH --> HOST
    HOST --> APP
    HOST --> AIR
    HOST --> MLF
    HOST --> MON
    HOST --> SYNC
    SYNC --> APP
    APP --> MON
</div>

## Role In The Shared Environment

| Lane | Concrete target | Main role |
|------|----------------|-----------|
| Shared API lane | Cloud Run hosted inference target | serve the public FastAPI routes |
| Operator lane | hosted full-stack target on one VM | provide the active operator surface until the managed hosted control plane is ready |

The hosted full-stack target stays a runtime target, not a contributor environment. It depends on shared GCP storage and identities instead of local emulators, and it stays private while Cloud Run owns public serving.

## Shared Core And Hosted Differences

| Shared with the local evaluator | Different in the hosted operator lane |
|------|--------------------------------------|
| Same Feature-Training-Inference boundaries | BigQuery, GCS, and Datastore replace local object and emulator surfaces |
| Same FastAPI app and Feast-backed feature path | Cloud Run carries the shared public API while the host stays private |
| Same Airflow, MLflow, and monitoring roles | one VM bundles the operator stack until the managed control plane takes over |
| Same repository and runtime contracts | service accounts and GitHub OIDC replace local developer credentials |

That makes the hosted full-stack target a retained support lane, not the target hosted architecture.

## Surface Responsibilities

| Surface | Main responsibility | Must not become |
|------|----------------------|-----------------|
| Shared GCP baseline | provide Artifact Registry, GCS, BigQuery, Datastore, and identity foundations | the application runtime itself |
| Online compose host | keep the active operator stack online from one VM | a contributor setup path, notebook host, or long-term orchestration authority |
| FastAPI app | serve the product and service routes | a hidden deployment control plane |
| Airflow, MLflow, Prometheus, StatsD exporter, and Grafana | operator orchestration, tracking, monitoring, and review | the rider-facing interface |
| GitHub OIDC delivery | run remote Terraform and image-driven deploy updates | a substitute for the runtime host |

This keeps the shared environment honest. The runtime lives on the host, while Terraform and GitHub delivery keep the dependencies and rollout path reviewable.

## Runtime Contract

The hosted full-stack target relies on these shared runtime dependencies:

- BigQuery for the curated cloud feature layer
- GCS for MLflow artifacts and Feast registry-style storage
- a named Datastore-mode database for Feast online serving
- the same Feast runtime contract used by the Cloud Run path so both hosted targets point at the same logical serving configuration
- a dedicated VM service account with Application Default Credentials instead of mounted key files

That service account is expected to cover BigQuery jobs, BigQuery Storage API read sessions, bucket object access for MLflow and Feast, and Datastore access. The goal is to let the hosted containers read the shared cloud surfaces directly without inventing a separate credential path.

The identity split around this target is deliberate:

- GitHub Actions uses the deployer identity for Terraform apply, image publish, and Cloud Run rollout work.
- Cloud Run uses its own narrower runtime identity for the inference-only service.
- the online compose host uses a separate runtime identity because it still bundles Airflow, training, MLflow, Feast preparation, and the app on one VM.

That online compose runtime identity is the retained-operator contract. It remains broader than the Cloud Run identity only because the host still owns more responsibilities in the active shared environment. The intended hosted direction is to remove Airflow from this VM rather than to keep widening what the VM owns.

## Bootstrap And Day-2 Delivery

The hosted full-stack target is not part of the default contributor path. Its lifecycle still splits into one-time maintainer bootstrap and GitHub-managed day-2 delivery after bootstrap. For this target, the hosted-specific contract is simple: Terraform provisions the VM and shared cloud data surfaces, the host sync refreshes the repository and runtime `.env`, and the VM app must stay private while Cloud Run remains the public API lane.

See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the detailed bootstrap, remote Terraform, and runtime-release handoff steps.

## Host Sync Contract

The online compose host is not meant to drift indefinitely after the first apply.

The sync contract is:

- the host installs a `foehncast-online-compose-sync` systemd timer
- each sync fetches the configured Git ref and refreshes the hosted compose stack
- each successful sync writes `/opt/foehncast/.state/online-compose-sync/last-success.json`
- the app republishes that status through `/metrics`
- Grafana can show the last successful hosted refresh from the same retained sync state

This makes the hosted target observable without turning SSH into the only source of truth for what the VM last deployed.

This sync path matters only while the retained host still owns operator duties. It should shrink or disappear once managed build and orchestration paths take over.

## Exposure And Verification

The shared hosted target keeps exposure narrow by default.

The exposure contract is:

- `online_compose_public_ports = []` keeps the operator host private by default
- Airflow and MLflow stay private unless you intentionally expose their ports
- operator monitoring surfaces remain on the operator side unless you deliberately publish them yourself
- `bootstrap-gcp` treats Cloud Run as the primary hosted API path and verifies `/health`, `/spots`, and `/metrics`
- `bootstrap-gcp` expects the retained VM app to stay private and fails if port `8000` is exposed publicly

This preserves the same public-surface rule used across the rest of the docs: the app is the product and service surface, while operator tools remain private by default.

## What Stays Out Of This Target

The hosted full-stack path deploys runtime services only.

These surfaces stay local or CI-only:

- `development_env`
- notebooks
- docs build tooling
- the local MinIO objectstore
- the local Datastore emulator

## Rollback And Retirement Gate

Cloud Run remains the only supported public API path in the shared environment, so rollback uses the reviewed runtime trigger contract rather than reopening the VM app publicly. The narrower retirement question stays separate: the VM remains online only while Airflow, MLflow, sync status, or operator monitoring still need the retained control plane.

See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the detailed rollback and retry runbooks.

## Why This Target Works

- it keeps the full operator stack online in the active shared environment while the managed hosted control plane is still being defined
- it reuses the same repository and application boundaries as the local evaluator target
- it keeps the hosted runtime tied to reviewable Terraform outputs, GitHub delivery, and sync metrics
- it keeps public exposure narrow enough that the app remains the only default internet-facing surface
- it treats the retained host as a controlled transition surface instead of the desired permanent orchestration home

See [Architecture](architecture.md), [Local Evaluator](local-evaluator.md), [Inference Pipeline](inference-pipeline.md), [Cloud Mapping](cloud-mapping.md), and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the surrounding runtime and deployment boundaries.
