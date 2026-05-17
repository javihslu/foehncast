# Cloud Architecture

FoehnCast runs entirely on serverless and managed GCP services. Every compute component scales to zero when idle. The only fixed-cost resource is the Cloud SQL micro instance for MLflow metadata.

!!! note "What this page covers"

    Interactive architecture map, service inventory, access model, and cost forecast for the hosted environment.

## Architecture Map

The diagram below shows every cloud component. Click a node to open its GCP Console page.

<div class="mermaid">
flowchart TB
    classDef public fill:#c8e6c9,stroke:#2e7d32,color:#1b5e20
    classDef protected fill:#fff3e0,stroke:#e65100,color:#bf360c
    classDef managed fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    classDef storage fill:#ede7f6,stroke:#4527a0,color:#311b92
    classDef cicd fill:#f5f5f5,stroke:#616161,color:#212121

    subgraph PublicLane ["Public lane"]
        direction TB
        UI["Streamlit UI\n:8501"]:::public
        APP["FastAPI App\n:8000"]:::public
        GF["Grafana\n:3000"]:::public
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

    subgraph BuildLane ["Build lane (CI/CD)"]
        direction TB
        GHA["GitHub Actions\n+ OIDC"]:::cicd
        CB["Cloud Build"]:::cicd
        AR["Artifact Registry"]:::cicd
    end

    SCHED -->|cron| WF
    UI -->|on-demand| WF
    WF -->|feature → train → infer| APP

    APP --> BQ
    APP --> FS
    APP --> GCS
    APP --> MLF
    APP --> GMP

    UI --> GMP
    GF --> GMP

    MLF --> SQL
    MLF --> GCS

    GHA --> CB
    CB --> AR
    AR --> APP
    AR --> UI
    AR --> GF
    AR --> MLF

    click UI "https://console.cloud.google.com/run?project=" "Open Cloud Run"
    click APP "https://console.cloud.google.com/run?project=" "Open Cloud Run"
    click GF "https://console.cloud.google.com/run?project=" "Open Cloud Run"
    click MLF "https://console.cloud.google.com/run?project=" "Open Cloud Run"
    click WF "https://console.cloud.google.com/workflows?project=" "Open Workflows"
    click SCHED "https://console.cloud.google.com/cloudscheduler?project=" "Open Scheduler"
    click BQ "https://console.cloud.google.com/bigquery?project=" "Open BigQuery"
    click GCS "https://console.cloud.google.com/storage/browser?project=" "Open Cloud Storage"
    click FS "https://console.cloud.google.com/firestore?project=" "Open Firestore"
    click SQL "https://console.cloud.google.com/sql/instances?project=" "Open Cloud SQL"
    click GMP "https://console.cloud.google.com/monitoring?project=" "Open Monitoring"
    click CB "https://console.cloud.google.com/cloud-build/builds?project=" "Open Cloud Build"
    click AR "https://console.cloud.google.com/artifacts?project=" "Open Artifact Registry"
</div>

## Service Inventory

| Service | GCP Product | Container Port | Access | Purpose |
|---------|-------------|---------------|--------|---------|
| **Streamlit UI** | Cloud Run | 8501 | Public | Rider-facing dashboard with spot rankings, forecasts, and Grafana embeds |
| **FastAPI App** | Cloud Run | 8000 | Public | Inference API — `/predict`, `/rank`, `/spots`, `/health`, `/metrics` |
| **Grafana** | Cloud Run | 3000 | Public | Read-only dashboards (anonymous viewer, embedding enabled) |
| **MLflow** | Cloud Run | 5001 | Protected | Tracking server and model registry — service-account-only invocation |
| **Cloud Workflows** | Workflows | — | Protected | Pipeline orchestration: feature → training → inference cascade |
| **Cloud Scheduler** | Scheduler | — | Protected | Cron trigger for scheduled pipeline runs |
| **BigQuery** | BigQuery | — | IAM | Feature storage, monitoring events |
| **Cloud Storage** | GCS | — | IAM | MLflow artifacts, Feast registry, pipeline reports |
| **Firestore** | Firestore | — | IAM | Feast online store (Datastore mode) |
| **Cloud SQL** | Cloud SQL | 5432 | Private | MLflow metadata (PostgreSQL micro, no public IP) |
| **GMP** | Managed Prometheus | — | IAM | Metric ingestion and query (PromQL-compatible) |
| **Cloud Build** | Cloud Build | — | IAM | Container image builds from reviewed source |
| **Artifact Registry** | Artifact Registry | — | IAM | Docker image repository |

## Access Model

<div class="grid cards">
<ul>
<li>
<p><strong>Public services</strong></p>
<p>UI, App, and Grafana use <code>allUsers</code> Cloud Run IAM invoker. Anonymous access, no login required.</p>
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

## Cost Forecast

All estimates use GCP pricing as of 2026. Actual costs depend on usage patterns.

### Idle (no traffic)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| Cloud Run (4 services) | $0.00 | Scale-to-zero, no minimum instances |
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
| Cloud Run (4 services) | ~$0.50 | Cold starts + 100 req/day, 256 MB–1 GB memory |
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
