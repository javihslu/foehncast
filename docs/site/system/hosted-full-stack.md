# Hosted Full-Stack

FoehnCast uses a hosted full-stack target for the current shared environment. This target keeps Airflow, MLflow, the FastAPI app, and the operator monitoring stack online from one Compute Engine host while reusing the shared GCP baseline for storage, identity, and image-delivery dependencies.

This page records the current hosted full-stack contract that is described by the cloud bootstrap, Terraform reference, and cloud-operator tests. It focuses on the active shared runtime target, not on future migrations.

!!! note "Scope"

    This page describes the current validated hosted full-stack target.
    It is not a roadmap.
    Future changes should be documented after they are chosen and implemented.

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
    HOST --> MON[Prometheus and Grafana]
    HOST --> SYNC[Repo sync timer]
    SYNC --> MET[/metrics sync status]
    MET --> MON
</div>

The important boundary is that the hosted full-stack target stays a runtime target, not a contributor environment:

- the same repository owns the running Airflow, MLflow, app, and monitoring surfaces
- the host depends on shared GCP storage and identity surfaces instead of local emulators
- GitHub delivery updates the target after the initial maintainer bootstrap
- only the app is public by default, while operator tools stay private unless deliberately exposed

## Surface Responsibilities

| Surface | Main responsibility | Must not become |
|------|----------------------|-----------------|
| Shared GCP baseline | provide Artifact Registry, GCS, BigQuery, Datastore, and identity foundations | the application runtime itself |
| Online compose host | keep the full runtime stack online from one VM | a contributor setup path or notebook host |
| FastAPI app | serve the product and service routes | a hidden deployment control plane |
| Airflow, MLflow, Prometheus, and Grafana | operator orchestration, tracking, monitoring, and review | the rider-facing interface |
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

## Bootstrap And Delivery Boundary

The hosted full-stack target is not part of the default contributor path. Its lifecycle is split into two layers:

- a maintainer bootstrap through `./scripts/bootstrap-gcp.sh` to create or reuse the shared GCP baseline and the optional online compose host target
- GitHub-managed day-2 delivery for remote Terraform runs and image-based updates after the shared environment is bootstrapped

The current bootstrap and host contract is:

- Terraform can provision the Compute Engine host, static IP, network, and cloud data surfaces
- the host clones the repository, writes a runtime `.env`, and tries to pull the published images
- if those images are not available yet, the host can build them locally as a fallback
- bootstrap prints the host, app, Airflow, and MLflow URLs when those outputs exist
- bootstrap can verify the hosted app through `/health` and `/metrics` when the app URL is publicly exposed

That split keeps one-time environment setup separate from normal day-2 delivery.

## Host Sync Contract

The online compose host is not meant to drift indefinitely after the first apply.

The current sync contract is:

- the host installs a `foehncast-online-compose-sync` systemd timer
- each sync fetches the configured Git ref and refreshes the hosted compose stack
- each successful sync writes `/opt/foehncast/.state/online-compose-sync/last-success.json`
- the app republishes that status through `/metrics`
- Grafana can show the last successful hosted refresh from the same retained sync state

This makes the hosted target observable without turning SSH into the only source of truth for what the VM last deployed.

## Exposure And Verification

The shared hosted target keeps exposure narrow by default.

The current contract is:

- `online_compose_public_ports = [8000]` keeps only the app internet-reachable by default
- Airflow and MLflow stay private unless you intentionally expose their ports
- operator monitoring surfaces remain on the operator side unless you deliberately publish them yourself
- `bootstrap-gcp` waits for the hosted `/health` endpoint and checks `/metrics` for the online compose sync metrics when the app URL is public
- if the hosted app URL is not publicly exposed, bootstrap skips that runtime verification instead of pretending the route was checked

This preserves the same public-surface rule used across the rest of the docs: the app is the product and service surface, while operator tools remain private by default.

## What Stays Out Of This Target

The hosted full-stack path deploys runtime services only.

These surfaces stay local or CI-only:

- `development_env`
- notebooks
- docs build tooling
- the local MinIO objectstore
- the local Datastore emulator

The hosted target also does not replace the separate Cloud Run path. The inference-only target still exists as the smaller hosted option when the whole stack does not need to stay online together.

## Why This Target Works

- it keeps the full operator stack online without forcing Airflow into Cloud Run
- it reuses the same repository and application boundaries as the local evaluator target
- it keeps the hosted runtime tied to reviewable Terraform outputs, GitHub delivery, and sync metrics
- it keeps public exposure narrow enough that the app remains the only default internet-facing surface

See [Architecture](architecture.md), [Local Evaluator](local-evaluator.md), [Inference Pipeline](inference-pipeline.md), and [Cloud Mapping](cloud-mapping.md) for the surrounding runtime and deployment boundaries.
