# Overview

FoehnCast is a local-first ML system that helps you pick the best kiteboarding spot. This page shows how it's organized and where local vs. cloud differ.

## The Core Design

The same Feature → Training → Inference pattern runs everywhere — locally or in the cloud.

<div class="mermaid">
flowchart TD
  classDef data fill:#eef2f7,stroke:#475569
  classDef pipeline fill:#e6f4f1,stroke:#0f766e
  classDef app fill:#0f2530,stroke:#0f766e,color:#fff

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
  classDef shared fill:#f1f5f9,stroke:#475569,stroke-dasharray: 5 5
  classDef local fill:#e6f4f1,stroke:#0f766e
  classDef cloud fill:#fff4e6,stroke:#c2410c

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
| Orchestration | Airflow (Docker) | Cloud Workflows + Scheduler |
| Serving | FastAPI on localhost | Cloud Run |
| Monitoring | Prometheus + StatsD | Managed Prometheus |
| Cost | Free | ~$8/mo (Cloud SQL) |

The full service-by-service mapping lives on the [Cloud Deployment](system/cloud-architecture.md) page.
