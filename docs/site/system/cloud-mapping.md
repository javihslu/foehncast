# Cloud Mapping

This page shows how local services map to cloud equivalents. The pipeline code stays the same — only the infrastructure underneath changes.

## Local → Cloud

<div class="mermaid">
flowchart TD
    classDef core fill:#f5f5f5,stroke:#333
    classDef local fill:#e1f5fe,stroke:#01579b
    classDef cloud fill:#fff8e1,stroke:#f57f17

    CORE["Same Python code"]:::core

    subgraph Local ["Local (Docker)"]
        direction LR
        LSUP["Airflow + MLflow + Prometheus"]:::local
        LDATA["MinIO + Feast emulator"]:::local
    end

    subgraph Cloud ["Cloud (GCP)"]
        direction LR
        COPS["Cloud Workflows + MLflow"]:::cloud
        CDATA["BigQuery + GCS + Firestore"]:::cloud
        CAPI["Cloud Run API"]:::cloud
    end

    CORE --> Local
    CORE --> Cloud
</div>

## Service Mapping

| Concern | Local | Cloud |
|---------|-------|-------|
| Object storage | MinIO | GCS |
| Feature storage | MinIO parquet | BigQuery |
| Online features | Datastore emulator | Firestore |
| Model registry | MLflow (SQLite) | MLflow (Cloud SQL) |
| Orchestration | Airflow (Docker) | Cloud Workflows + Scheduler |
| Serving | FastAPI (localhost) | Cloud Run |
| Monitoring | Prometheus + StatsD | Managed Prometheus |
| Image builds | — | Cloud Build → Artifact Registry |
| Delivery | — | GitHub Actions + Terraform + OIDC |

## Why Airflow Locally, Cloud Workflows in Production

The orchestration layer is intentionally asymmetric. Airflow locally demonstrates scheduling, retries, assets, and DAG dependencies — proving orchestration competence without cloud spend. Cloud Workflows in production keeps costs near zero (no always-on scheduler). The pipeline code is identical in both — only the trigger mechanism differs. Contributors who just want reproducible results use `dvc repro` without any orchestrator.

## What Stays the Same

- `config.yaml` means the same thing in both environments
- Feature, training, and inference pipeline boundaries
- FastAPI routes and `/metrics` contract
- Container images and application code
- DVC works locally and in CI (not in cloud runtime)

## What's Different

| Cloud adds | Purpose |
|-----------|---------|
| Cloud Run | Public API (scale-to-zero) |
| Cloud Workflows | Scheduled pipeline triggers |
| Cloud Build | Container image publishing |
| BigQuery | Analytical storage for features and monitoring |
| IAM + OIDC | Authentication (no long-lived keys) |

## Access Control

| Access level | Services |
|-------------|----------|
| Public (`allUsers`) | FastAPI App, Streamlit UI |
| Protected (service-account) | MLflow, Cloud Workflows |
| IAM-only (no public endpoint) | BigQuery, GCS, Firestore, Cloud SQL |
| OIDC (CI) | GitHub Actions → Cloud Build |

## What Stays Out of Cloud

These are local/CI-only:

- `development_env` container
- Notebooks
- Docs build tooling
- Local MinIO and Datastore emulator

## Related Pages

- [Cloud Architecture](cloud-architecture.md) — detailed service inventory and costs
- [Delivery Workflow](delivery-and-operator-workflow.md) — how code gets to Cloud Run
- [Local Evaluator](local-evaluator.md) — the Docker-based local equivalent
