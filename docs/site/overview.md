# Overview

FoehnCast is a local-first ML system that helps you pick the best kiteboarding spot. This page shows how it's organized and where local vs. cloud differ.

## The Core Design

The same Feature → Training → Inference pattern runs everywhere — locally or in the cloud.

<div class="mermaid">
flowchart TD
  classDef data fill:#ececff,stroke:#9370db
  classDef pipeline fill:#e1f5fe,stroke:#01579b
  classDef app fill:#222,stroke:#333,color:#fff

  DATA["Weather forecasts"]:::data

  subgraph Build ["Build path (offline)"]
    direction TB
    FEAT["Feature pipeline"]:::pipeline
    CURATED["Curated features"]:::data
    TRAIN["Training pipeline"]:::pipeline
    REG["MLflow registry"]:::data
    FEAT --> CURATED --> TRAIN --> REG
  end

  subgraph Serve ["Serve path (online)"]
    direction TB
    API["FastAPI app"]:::app
    RANK["Ranked spots"]:::data
    API --> RANK
  end

  DATA --> FEAT
  CURATED --> API
  REG --> API
</div>

## Local vs. Cloud

Both environments run the same Python code. The difference is where data lives and how things get scheduled.

<div class="mermaid">
flowchart TD
  classDef shared fill:#f5f5f5,stroke:#333,stroke-dasharray: 5 5
  classDef local fill:#e1f5fe,stroke:#01579b
  classDef cloud fill:#fff8e1,stroke:#f57f17

  CORE["Same Python code"]:::shared

  subgraph Local ["Local (Docker Compose)"]
    direction LR
    LOPS["Airflow + MLflow + Prometheus"]:::local
    LDATA["MinIO + Feast emulator"]:::local
  end

  subgraph Cloud ["Cloud (GCP)"]
    direction LR
    CDATA["BigQuery + GCS"]:::cloud
    CAPI["Cloud Run (public)"]:::cloud
  end

  CORE --> Local
  CORE --> Cloud
</div>

| Concern | Local | Cloud |
|---------|-------|-------|
| Storage | MinIO (S3-compatible) | BigQuery + GCS |
| Orchestration | Airflow (Docker) | Cloud Workflows |
| Serving | FastAPI on localhost | Cloud Run |
| Monitoring | Prometheus + StatsD | Managed Prometheus |
| Cost | Free | ~$8/mo (Cloud SQL) |

## Reading Order

1. **[Use Case and Data](system/use-case.md)** — what problem we're solving
2. **[Getting Started](getting-started.md)** — run it locally
3. **[Architecture](system/architecture.md)** — the FTI split and how pipelines connect
4. **[Feature](system/feature-pipeline.md)**, **[Training](system/training-pipeline.md)**, **[Inference](system/inference-pipeline.md)** — each pipeline in detail
5. **[Monitoring](system/monitoring.md)** — metrics, drift detection, alerts
6. **[Cloud Architecture](system/cloud-architecture.md)** — the GCP deployment
