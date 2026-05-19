# Architecture

FoehnCast follows the Feature → Training → Inference (FTI) pattern. The same code runs locally in Docker and in the cloud on GCP. This page explains how the pieces connect.

## The Big Picture

<div class="mermaid">
flowchart TD
    classDef pipe fill:#e1f5fe,stroke:#01579b
    classDef store fill:#ececff,stroke:#9370db
    classDef app fill:#222,stroke:#333,color:#fff

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
    classDef ctl fill:#f5f5f5,stroke:#333
    classDef pipe fill:#e1f5fe,stroke:#01579b
    classDef store fill:#ececff,stroke:#9370db
    classDef serve fill:#fff8e1,stroke:#f57f17

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

Everything runs in Docker Compose. One command starts it all.

<div class="mermaid">
flowchart TD
    classDef pipeline fill:#e1f5fe,stroke:#01579b
    classDef storage fill:#ececff,stroke:#9370db
    classDef app fill:#222,stroke:#333,color:#fff
    classDef monitor fill:#fff8e1,stroke:#f57f17

    EXT["Weather APIs"]

    subgraph Stack ["Docker Compose"]
        direction LR
        FEAT["Feature DAG"]:::pipeline
        MIN["MinIO"]:::storage
        TRAIN["Training DAG"]:::pipeline
        MLF["MLflow"]:::storage
        FEAST["Feast"]:::storage
        APP["FastAPI"]:::app
        MON["Prometheus"]:::monitor
    end

    EXT --> FEAT
    FEAT --> MIN
    FEAT --> TRAIN
    MIN --> TRAIN
    TRAIN --> MLF
    MIN --> FEAST
    FEAST --> APP
    MLF --> APP
    APP --> MON
</div>

## Cloud Stack

Same pipelines, different infrastructure. Cloud Run handles serving, Cloud Workflows handles scheduling.

<div class="mermaid">
flowchart TD
    classDef data fill:#ececff,stroke:#9370db
    classDef serve fill:#fff8e1,stroke:#f57f17

    LIVE["Weather + drive-time data"]
    DATA["BigQuery + GCS + MLflow"]:::data

    subgraph Run ["Cloud Run"]
        direction TB
        RAPI["FastAPI app"]:::serve
    end

    LIVE --> RAPI
    DATA --> RAPI
</div>

| Concern | Local | Cloud |
|---------|-------|-------|
| Storage | MinIO (S3-compatible) | BigQuery + GCS |
| Orchestration | Airflow (Docker) | Cloud Workflows + Scheduler |
| Serving | FastAPI on localhost | Cloud Run (scale-to-zero) |
| Monitoring | Prometheus + StatsD | Managed Prometheus |
| Model registry | MLflow (SQLite) | MLflow (Cloud SQL) |

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

## Why This Works

- Same code runs everywhere (local = cloud minus infra)
- Clear pipeline boundaries prevent spaghetti
- Each pipeline can be tested independently
- Adding a new spot or feature doesn't require changing the architecture

## Related Pages

- [Feature Pipeline](feature-pipeline.md) — how ingestion and feature engineering work
- [Training Pipeline](training-pipeline.md) — labelling, training, and model registration
- [Inference Pipeline](inference-pipeline.md) — API serving and ranking logic
- [Cloud Architecture](cloud-architecture.md) — GCP deployment details
- [Monitoring](monitoring.md) — metrics, alerts, drift detection
