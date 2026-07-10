# Architecture

FoehnCast follows the Feature → Training → Inference (FTI) pattern, with the same code running locally in Docker and in the cloud on GCP.

## The Big Picture

<div class="mermaid">
flowchart LR
    classDef pipe fill:#e6f4f1,stroke:#0f766e
    classDef store fill:#eef2f7,stroke:#475569
    classDef app fill:#0f2530,stroke:#0f766e,color:#fff

    EXT["Weather APIs"]

    subgraph Feature ["Feature Pipeline"]
        direction TB
        ING[Ingest] --> ENG[Engineer] --> VAL[Validate] --> STO[Store]
    end

    subgraph Training ["Training Pipeline"]
        direction TB
        LAB[Label] --> TRN[Train] --> EVAL[Evaluate] --> REG[Register]
    end

    subgraph Inference ["Inference Pipeline"]
        direction TB
        API[API]:::app --> PRED[Predict] --> RANK[Rank]
    end

    FEAST["Feast online store"]:::store
    MLF["MLflow registry"]:::store

    EXT --> ING
    STO --> LAB
    STO --> FEAST
    REG --> MLF

    FEAST --> API
    MLF --> API
    EXT --> API
</div>

## Three Pipelines

| Pipeline | Input | Output | Triggered by |
|----------|-------|--------|-------------|
| Feature | Weather API responses | Curated parquet files | Airflow schedule or `dvc repro` |
| Training | Curated features | Registered model in MLflow | Feature pipeline completion |
| Inference | Live forecast + model | Ranked spots | API request |

## DVC vs. Airflow

Both run the same Python code. DVC is for reproducibility, Airflow is for scheduling.

<div class="mermaid">
flowchart TD
    classDef ctl fill:#f1f5f9,stroke:#475569
    classDef pipe fill:#e6f4f1,stroke:#0f766e
    classDef store fill:#eef2f7,stroke:#475569
    classDef serve fill:#fff4e6,stroke:#c2410c

    subgraph DVCPath ["DVC (offline, reproducible)"]
        DVCY["dvc.yaml"]:::ctl --> DVCCLI["python -m foehncast.dvc_stages"]:::ctl
    end

    subgraph AirflowPath ["Airflow (scheduled, monitored)"]
        FDAG["feature_dag"]:::ctl --> FEAT["Feature pipeline"]:::pipe
        TDAG["training_dag"]:::ctl --> TRAIN["Training pipeline"]:::pipe
        IDAG["inference_dag"]:::ctl --> INF["Inference pipeline"]:::pipe
    end

    DVCCLI --> FEAT
    DVCCLI --> TRAIN
    FEAT --> CUR["Curated dataset"]:::store
    CUR --> TRAIN
    CUR --> FEAST["Feast online store"]:::store
    TRAIN --> REG["MLflow model"]:::store
    REG --> INF
    INF --> PLOG["Prediction log"]:::store
    FEAST --> API["FastAPI"]:::serve
    REG --> API
</div>

| Path | Use case | Outputs |
|------|----------|---------|
| DVC | Reproduce offline pipelines locally or in CI | `data/`, `reports/` |
| Airflow | Schedule runs, handle retries, show DAG dependencies | Curated features, model, predictions |
| FastAPI | Serve live predictions | `/predict`, `/rank`, `/spots`, `/metrics` |

## Local Stack

Everything runs in Docker Compose. One command starts it all. The service diagram, ports, and verification steps live on the [Local Stack](local-evaluator.md) page.

## Cloud Stack

Same pipelines, different infrastructure. Cloud Run handles serving, Cloud Workflows handles scheduling.

<div class="mermaid">
flowchart TD
    classDef data fill:#eef2f7,stroke:#475569
    classDef serve fill:#fff4e6,stroke:#c2410c

    LIVE["Weather + drive-time data"]
    DATA["BigQuery + GCS + MLflow"]:::data

    subgraph Run ["Cloud Run"]
        direction TB
        RAPI["FastAPI app"]:::serve
    end

    LIVE --> RAPI
    DATA --> RAPI
</div>

The full local-to-cloud service mapping lives on the [Cloud Deployment](cloud-architecture.md) page.

## Compose Overlay Pattern

The Docker Compose setup uses overlays to swap backends without changing application code:

| File | What it does |
|------|-------------|
| `docker-compose.yml` | Base services (Airflow, MLflow, app, UI, monitoring) |
| `docker-compose.objectstore.yml` | Local overlay: adds MinIO + Feast emulator |
| `docker-compose.gcp.yml` | Cloud overlay: wires in BigQuery/GCS credentials |

```bash
# Local (default)
docker compose -f docker-compose.yml -f docker-compose.objectstore.yml up

# Cloud-parity testing
GCP_PROJECT_ID=my-project docker compose -f docker-compose.yml -f docker-compose.gcp.yml up
```

The Python config reads `STORAGE_BACKEND` (either `s3` or `bigquery`) to resolve paths at runtime.

## Storage Rules

- **Curated features** go in MinIO locally, BigQuery in the cloud
- **Model artifacts** go in MinIO locally, GCS in the cloud
- **Prediction logs** are for monitoring, not for users
- **Feast** reads from the curated layer — it doesn't replace the feature pipeline

The payoff: the same code runs everywhere (local = cloud minus infra), clear pipeline boundaries keep the system testable in isolation, and adding a spot or feature never touches the architecture.
