# Hosted Full-Stack (Transitional Operator Host)

FoehnCast keeps the hosted full-stack target as the current private operator lane. It runs Airflow, MLflow, the FastAPI app, and the monitoring stack on one Compute Engine host while Cloud Run carries the public API lane. This host is transitional: it keeps the current operator stack online while hosted image builds move toward Cloud Build and hosted orchestration moves toward Cloud Composer.

This page records the current hosted full-stack contract that is described by the cloud bootstrap, Terraform reference, and cloud-operator tests. It focuses on the active shared runtime target, not on future migrations.

!!! note "Scope"

    This page describes the current retained operator host contract.
    It explains why that host is transitional rather than the intended long-term hosted control plane.
    It is not the Composer cutover plan.

## Target Shape

<div class="mermaid">
flowchart LR
    TF[Terraform baseline] --> GCP[Shared GCP resources]
    GCP --> HOST[Online compose host]
    GH[GitHub OIDC delivery] --> HOST

    BQ[(BigQuery curated features)] --> HOST
    GCS[(GCS artifacts and Feast registry)] --> HOST
    DS[(Datastore online store)] --> HOST

    HOST --> APP[FastAPI app]
    HOST --> AIR[Airflow]
    HOST --> MLF[MLflow]
    HOST --> MON[Prometheus + StatsD exporter + Grafana]
    HOST --> SYNC[Repo sync timer]
    SYNC --> MET[/metrics sync status]
    MET --> MON
</div>

## Role In The Shared Environment

| Lane | Current target | Main role |
|------|----------------|-----------|
| Shared API lane | Cloud Run hosted inference target | serve the public FastAPI routes |
| Operator lane | hosted full-stack target on one VM | keep Airflow, MLflow, monitoring, and private app checks online while the managed hosted control plane is not ready yet |

The important boundary is that the hosted full-stack target stays a runtime target, not a contributor environment. It depends on shared GCP storage and identity surfaces instead of local emulators, updates through the maintainer bootstrap plus remote Terraform and host sync path, and stays on the private operator side while Cloud Run owns public serving. It is a retained support lane, not the target hosted architecture.

## Surface Responsibilities

| Surface | Main responsibility | Must not become |
|------|----------------------|-----------------|
| Shared GCP baseline | provide Artifact Registry, GCS, BigQuery, Datastore, and identity foundations | the application runtime itself |
| Online compose host | keep the current operator stack online from one VM | a contributor setup path, notebook host, or long-term orchestration authority |
| FastAPI app | serve the product and service routes | a hidden deployment control plane |
| Airflow, MLflow, Prometheus, StatsD exporter, and Grafana | operator orchestration, tracking, monitoring, and review | the rider-facing interface |
| GitHub OIDC delivery | run remote Terraform and image-driven deploy updates | a substitute for the runtime host |

This keeps the current shared environment honest. The runtime lives on the host, while Terraform and GitHub delivery keep the dependencies and rollout path reviewable.

## Runtime Contract

The hosted full-stack target currently relies on these shared runtime dependencies:

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

That online compose runtime identity is the current transition contract. It remains broader than the Cloud Run identity only because the host still owns more responsibilities today. The intended hosted direction is to remove Airflow from this VM rather than to keep widening what the VM owns.

## Bootstrap And Day-2 Delivery

The hosted full-stack target is not part of the default contributor path. Its lifecycle still splits into one-time maintainer bootstrap and GitHub-managed day-2 delivery after bootstrap. For this current target, the hosted-specific contract is simple: Terraform provisions the VM and shared cloud data surfaces, the host sync refreshes the repository and runtime `.env`, and the VM app must stay private while Cloud Run remains the public API lane.

See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the detailed bootstrap, remote Terraform, and runtime-release handoff steps.

## Host Sync Contract

The online compose host is not meant to drift indefinitely after the first apply.

The current sync contract is:

- the host installs a `foehncast-online-compose-sync` systemd timer
- each sync fetches the configured Git ref and refreshes the hosted compose stack
- each successful sync writes `/opt/foehncast/.state/online-compose-sync/last-success.json`
- the app republishes that status through `/metrics`
- Grafana can show the last successful hosted refresh from the same retained sync state

This makes the hosted target observable without turning SSH into the only source of truth for what the VM last deployed.

This sync path matters only while the retained host still owns operator duties. It should shrink or disappear once managed build and orchestration paths take over.

## Exposure And Verification

The shared hosted target keeps exposure narrow by default.

The current contract is:

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
