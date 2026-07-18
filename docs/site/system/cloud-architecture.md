# Cloud Deployment

*Status: the course deployment described here was taken down after grading (July 2026). The page stays as the reference architecture; the Terraform under `terraform/` deploys an identical copy.*

The cloud deployment runs on GCP managed services (Cloud Run, BigQuery, Cloud Storage, Cloud SQL). Most services scale to zero; the Cloud SQL instance for MLflow metadata is the only service with a standing cost. The pipeline code is identical to the local stack — only the infrastructure underneath changes.

## Architecture Map

<div class="mermaid">
flowchart TB
    classDef public fill:#0f2530,stroke:#0f766e,color:#fff
    classDef protected fill:#fff4e6,stroke:#c2410c
    classDef managed fill:#e6f4f1,stroke:#0f766e
    classDef storage fill:#eef2f7,stroke:#475569
    classDef cicd fill:#f1f5f9,stroke:#475569

    subgraph PublicLane ["Public lane"]
        direction TB
        UI["Streamlit UI\n:8501"]:::public
        APP["FastAPI App\n:8000"]:::public
    end

    subgraph OperatorLane ["Operator lane (protected)"]
        direction TB
        MLF["MLflow Tracking\n:5001"]:::protected
        WF["Cloud Workflows"]:::protected
        SCHED["Cloud Scheduler"]:::protected
    end

    subgraph DataLayer ["Data layer (managed)"]
        direction TB
        BQ["BigQuery\nfeatures + monitoring"]:::storage
        GCS["Cloud Storage\nartifacts + registry"]:::storage
        FS["Firestore\nonline store"]:::storage
        SQL["Cloud SQL micro\nMLflow metadata"]:::storage
    end

    subgraph MetricsLayer ["Metrics (managed)"]
        GMP["Google Managed\nPrometheus"]:::managed
    end

    BUILD["CI/CD\nGitHub Actions + Cloud Build"]:::cicd

    SCHED -->|cron| WF
    UI -->|on-demand| WF
    WF -->|feature → train → infer| APP

    APP --> BQ
    APP --> FS
    APP --> GCS
    APP --> MLF
    APP --> GMP

    UI --> GMP

    MLF --> SQL
    MLF --> GCS

    BUILD --> APP
    BUILD --> UI
    BUILD --> MLF

    click BUILD "../ci-cd/" "CI/CD"
</div>

Image builds and deployments are described on the [CI/CD](ci-cd.md) page.

## Service Inventory

Cloud Run hosts exactly three services (App, MLflow, UI) plus four jobs (feature, training, inference, drift), all triggered by the Cloud Workflows cascade.

| Service | GCP Product | Container Port | Access | Purpose |
|---------|-------------|---------------|--------|---------|
| **Streamlit UI** | Cloud Run | 8501 | Public | Rider-facing dashboard with spot rankings, forecasts, and native Altair metric charts |
| **FastAPI App** | Cloud Run | 8000 | Public | Inference API — `/predict`, `/rank`, `/spots`, `/health`, `/metrics` |
| **MLflow** | Cloud Run | 5001 | Protected | Tracking server and model registry — service-account-only invocation |
| **Cloud Workflows** | Workflows | — | Protected | Pipeline orchestration: feature → training → inference cascade |
| **Cloud Scheduler** | Scheduler | — | Protected | Cron trigger for scheduled pipeline runs |
| **BigQuery** | BigQuery | — | IAM | Feature storage, monitoring events |
| **Cloud Storage** | GCS | — | IAM | MLflow artifacts, Feast registry, pipeline reports |
| **Firestore** | Firestore | — | IAM | Feast online store (Datastore mode) |
| **Cloud SQL** | Cloud SQL | 5432 | Private | MLflow metadata (PostgreSQL micro, no authorized networks) |
| **GMP** | Managed Prometheus | — | IAM | Metric ingestion and query (PromQL-compatible) |
| **Cloud Build** | Cloud Build | — | IAM | Container image builds from reviewed source |
| **Artifact Registry** | Artifact Registry | — | IAM | Docker image repository |

## Local to Cloud Mapping

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

### Why Airflow Locally, Cloud Workflows in Production

Orchestration differs by environment: local runs use Airflow, while the hosted stack uses Cloud Workflows and Cloud Scheduler. Cloud Workflows keeps costs near zero because there is no always-on scheduler. The pipeline code is identical in both — only the trigger mechanism differs. Contributors who just want reproducible results use `dvc repro` without any orchestrator.

## Access Model

<div class="grid cards">
<ul>
<li>
<p><strong>Public services</strong></p>
<p>UI and App use <code>allUsers</code> Cloud Run IAM invoker. Anonymous access, no login required.</p>
</li>
<li>
<p><strong>Protected services</strong></p>
<p>MLflow uses service-account-only invocation. Other Cloud Run services authenticate via ID tokens. Operators access via <code>gcloud run services proxy</code>.</p>
</li>
<li>
<p><strong>Managed data</strong></p>
<p>BigQuery, GCS, Firestore, and Cloud SQL are locked to the Cloud Run service account via IAM. No public endpoints.</p>
</li>
<li>
<p><strong>Build pipeline</strong></p>
<p>GitHub Actions authenticates via Workload Identity Federation (OIDC). Cloud Build runs in the project. No long-lived credentials.</p>
</li>
</ul>
</div>

## Identity Model

- **GitHub Actions** → Workload Identity Federation (OIDC) → deployer service account
- **Cloud Run services** → narrower runtime service accounts (least privilege)
- **Cloud Workflows** → managed service identity
- No long-lived credential files anywhere

## Bootstrap and Day-2

1. One-time: `./scripts/bootstrap-gcp.sh` from Cloud Shell
2. Day-2: Terraform (manual dispatch), Cloud Build triggers (on push)
3. Rollback: Cloud Run probes auto-rollback unhealthy revisions

On a first run the container images must reach Artifact Registry before Terraform creates the Cloud Run services that consume them. Bootstrap enforces this order: foundation apply (Artifact Registry and IAM) → build the three images → full apply. Use `--skip-image-build` only when the images already exist.

See the [Operator Runbook](delivery-and-operator-workflow.md) for the full process.

## What Stays Out of Cloud

These are local/CI-only:

- `development_env` container
- Notebooks
- Docs build tooling
- Local MinIO and Datastore emulator

## Cost Forecast

All estimates use GCP pricing as of 2026. Actual costs depend on usage patterns.

### Idle (no traffic)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| Cloud Run (3 services) | $0.00 | Scale-to-zero, no minimum instances |
| Cloud SQL (db-f1-micro) | ~$7.67 | Always-on micro instance, cheapest tier |
| BigQuery | $0.00 | First 1 TB query free, 10 GB storage free |
| Cloud Storage | ~$0.02 | ~1 GB artifacts at $0.020/GB |
| Firestore | $0.00 | Free tier covers demo volume |
| GMP | $0.00 | First 50M samples/month free |
| Cloud Workflows | $0.00 | First 5,000 steps/month free |
| Cloud Scheduler | $0.00 | First 3 jobs free |
| Artifact Registry | ~$0.10 | ~1 GB images at $0.10/GB |
| **Total idle** | **~$8/mo** | |

### Demo load (occasional use, ~100 requests/day)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| Cloud Run (3 services) | ~$0.50 | Cold starts + 100 req/day, 256 MB–1 GB memory |
| Cloud SQL | ~$7.67 | Same as idle |
| BigQuery | ~$0.01 | Small query volume |
| Cloud Workflows | $0.00 | ~30 executions/month |
| **Total demo** | **~$9/mo** | |

### Production-like (scheduled pipelines, continuous traffic)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| Cloud Run | ~$5–15 | Depends on min instances, concurrency |
| Cloud SQL | ~$7.67 | Consider db-g1-small ($25/mo) for higher traffic |
| BigQuery | ~$1–5 | Query volume dependent |
| GMP | $0.00 | Usually within free tier |
| **Total production** | **~$15–30/mo** | |

!!! tip "Cost controls"

    - Set `min_instance_count = 0` on all Cloud Run services (default).
    - Use `db-f1-micro` for Cloud SQL — upgrade only if needed.
    - BigQuery on-demand pricing avoids reserved slot costs.
    - Cloud Scheduler runs are essentially free at demo scale.
    - Set billing alerts at $10 and $25 thresholds.
