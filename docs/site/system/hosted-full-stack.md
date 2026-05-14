# Hosted Full-Stack

FoehnCast keeps the hosted full-stack target as the retained operator control plane. This target keeps Airflow, MLflow, the FastAPI app, and the operator monitoring stack online from one Compute Engine host while Cloud Run carries the only promoted public API path.

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
    HOST --> MON[Prometheus + StatsD exporter + Grafana]
    HOST --> SYNC[Repo sync timer]
    SYNC --> MET[/metrics sync status]
    MET --> MON
</div>

The important boundary is that the hosted full-stack target stays a runtime target, not a contributor environment:

- the same repository owns the running Airflow, MLflow, app, and monitoring surfaces
- the host depends on shared GCP storage and identity surfaces instead of local emulators
- GitHub Actions remote Terraform plus the host sync timer update the target after the one-time maintainer bootstrap
- Cloud Run is the only promoted public API path, while this VM keeps the retained operator stack available

## Surface Responsibilities

| Surface | Main responsibility | Must not become |
|------|----------------------|-----------------|
| Shared GCP baseline | provide Artifact Registry, GCS, BigQuery, Datastore, and identity foundations | the application runtime itself |
| Online compose host | keep the full runtime stack online from one VM | a contributor setup path or notebook host |
| FastAPI app | serve the product and service routes | a hidden deployment control plane |
| Airflow, MLflow, Prometheus, StatsD exporter, and Grafana | operator orchestration, tracking, monitoring, and review | the rider-facing interface |
| GitHub OIDC delivery | run remote Terraform and image-driven deploy updates | a substitute for the runtime host |

This keeps the current shared environment honest. The runtime lives on the host, while Terraform and GitHub delivery keep the dependencies and rollout path reviewable.

## Shared Environment Today

The shared environment keeps this target online today:

- Cloud Run is the primary hosted API surface for shared serving traffic
- one Compute Engine host still runs Airflow, MLflow, the FastAPI app, Prometheus, the StatsD exporter, and Grafana together
- maintainers bootstrap the shared GCP baseline and remote Terraform control plane once from Google Cloud Shell
- GitHub Actions remote Terraform applies advance the shared environment after bootstrap
- the VM-hosted app remains part of the operator runtime on the host, but it is not treated as a second public API path

That keeps the deployment story concrete: Cloud Run is the one promoted shared hosted API URL, while the compose host remains the retained full-stack operator path.

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

That online compose runtime identity is the current transition contract, not the preferred steady-state shape for every managed runtime. It remains broader than the Cloud Run identity only because the host still owns more responsibilities today.

## Bootstrap And Day-2 Delivery

The hosted full-stack target is not part of the default contributor path. Its lifecycle is split into two layers:

- a one-time maintainer bootstrap through `./scripts/bootstrap-gcp.sh --bootstrap-only --configure-github-actions` from Google Cloud Shell
- GitHub-managed day-2 delivery for remote Terraform runs and image-based updates after the shared environment is bootstrapped

The current bootstrap and host contract is:

- Terraform can provision the Compute Engine host, static IP, network, and cloud data surfaces
- day-2 remote applies read synced GitHub repository variables instead of treating `terraform.tfvars` as the ongoing source of truth
- the host clones the repository, writes a runtime `.env`, and pulls the published images
- if those images are not available, the sync fails fast so the image contract stays simple and reviewable
- bootstrap prints the primary hosted API target first, then the Cloud Run, host, app, Airflow, and MLflow URLs when those outputs exist
- bootstrap verifies the promoted Cloud Run path through `/health`, `/spots`, and `/metrics` when it is enabled
- bootstrap fails if the retained VM app is publicly exposed, because Cloud Run is the only supported public API path in this configuration

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

- `online_compose_public_ports = []` keeps the operator host private by default
- Airflow and MLflow stay private unless you intentionally expose their ports
- operator monitoring surfaces remain on the operator side unless you deliberately publish them yourself
- `bootstrap-gcp` treats Cloud Run as the primary hosted API path and verifies its `/health`, `/spots`, and `/metrics` routes when enabled
- `bootstrap-gcp` expects the retained VM app to stay private and fails if port `8000` is still exposed publicly

This preserves the same public-surface rule used across the rest of the docs: the app is the product and service surface, while operator tools remain private by default.

## What Stays Out Of This Target

The hosted full-stack path deploys runtime services only.

These surfaces stay local or CI-only:

- `development_env`
- notebooks
- docs build tooling
- the local MinIO objectstore
- the local Datastore emulator

The hosted target also does not remain a second public API path. Cloud Run carries the promoted serving role, while the VM keeps the broader operator stack online.

## Rollback And Retirement Gate

The remaining gate is not whether the VM should keep a public serving fallback. That fallback is already retired. Cloud Run is the only supported public API path in the shared environment.

The current rollback contract is:

- `.github/workflows/publish-app-image.yml` publishes the reviewed app image only
- `.github/workflows/trigger-runtime-release.yml` is the reviewed GitHub-to-runtime handoff for candidate deploy, promotion, and rollback requests
- `airflow/reports/runtime-release-latest.json` records the latest acknowledged serving rollout request on the runtime side
- bootstrap and Terraform verification fail if the VM app becomes public again instead of treating that as rollback

The remaining retirement decision is narrower:

- the VM stays online while Airflow, MLflow, sync status, and operator monitoring still need the retained control plane
- the VM can lose its remaining private app role only after the operator stack no longer needs host-local app checks and the orchestration surface of record is explicit
- when that gate is met, retiring or slimming the VM should be handled as operator-plane cleanup, not as public-serving rollback

## Why This Target Works

- it keeps the full operator stack online in the active shared environment without forcing Airflow into Cloud Run
- it reuses the same repository and application boundaries as the local evaluator target
- it keeps the hosted runtime tied to reviewable Terraform outputs, GitHub delivery, and sync metrics
- it keeps public exposure narrow enough that the app remains the only default internet-facing surface

See [Architecture](architecture.md), [Local Evaluator](local-evaluator.md), [Inference Pipeline](inference-pipeline.md), [Cloud Mapping](cloud-mapping.md), and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the surrounding runtime and deployment boundaries.
