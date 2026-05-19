# Hosted Cloud Environment

The cloud environment runs on GCP with Cloud Run for serving and managed services for everything else. No VMs, no hosted Airflow — orchestration stays local.

## What Runs in GCP

<div class="mermaid">
flowchart TD
    classDef platform fill:#e3f2fd,stroke:#1565c0
    classDef operator fill:#fff8e1,stroke:#f57f17

    TF["Terraform"] --> DATA["BigQuery + GCS + Firestore"]:::platform
    DATA --> RUN["Cloud Run (public API)"]:::platform
    DATA --> MLF["MLflow (protected)"]:::operator
    DATA --> WF["Cloud Workflows + Scheduler"]:::operator
    GH["GitHub Actions"] --> RUN
    GH --> MLF
</div>

| Service | Role | Access |
|---------|------|--------|
| Cloud Run (App + UI) | Public serving | Public |
| MLflow | Model registry + tracking | Protected (service-account) |
| Cloud Workflows | Pipeline scheduling | Protected |
| BigQuery | Feature + monitoring storage | IAM-only |
| GCS | Artifacts, Feast registry | IAM-only |
| Firestore | Feast online store | IAM-only |
| Cloud SQL | MLflow metadata | Private |

## Same Code, Different Infra

| Shared with local | Different in cloud |
|-------------------|--------------------|
| FTI pipeline boundaries | BigQuery + GCS replace MinIO |
| FastAPI routes and Feast | Cloud Run replaces localhost |
| MLflow and monitoring roles | Cloud Workflows replaces Airflow |
| Application code and containers | Service accounts replace dev credentials |

## What Stays Out

These don't get deployed to the cloud:

- `development_env` container
- Notebooks
- Docs build tooling
- Local MinIO and Datastore emulator

## Identity Model

- **GitHub Actions** → Workload Identity Federation (OIDC) → deployer service account
- **Cloud Run services** → narrower runtime service accounts (least privilege)
- **Cloud Workflows** → managed service identity
- No long-lived credential files anywhere

## Bootstrap and Day-2

1. One-time: `./scripts/bootstrap-gcp.sh` from Cloud Shell
2. Day-2: GitHub Actions runs Terraform and publishes images
3. Rollback: `scripts/trigger-runtime-release.sh` against local Airflow

See [Delivery Workflow](delivery-and-operator-workflow.md) for the full process.

## Related Pages

- [Cloud Architecture](cloud-architecture.md) — service inventory and cost breakdown
- [Cloud Mapping](cloud-mapping.md) — local ↔ cloud equivalents
- [Local Evaluator](local-evaluator.md) — the contributor-facing alternative
