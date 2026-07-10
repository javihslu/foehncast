# Local Stack

The local stack is the default way to run FoehnCast. The bootstrap script doubles as the local evaluator: it starts everything in Docker Compose and smoke-tests the full pipeline before declaring success.

## What Bootstrap Does

```bash
./scripts/bootstrap-local.sh
```

The script:

1. Starts Docker services (Airflow, MLflow, MinIO, app, Prometheus)
2. Waits for Airflow health
3. Runs the feature pipeline → training pipeline (asset-triggered)
4. Prepares Feast serving state
5. Verifies app `/health` and `/metrics`
6. Reports success with endpoint URLs

If default ports are busy, it picks the next free ones and tells you.

## Architecture

<div class="mermaid">
flowchart TD
    classDef pipeline fill:#e6f4f1,stroke:#0f766e
    classDef storage fill:#eef2f7,stroke:#475569
    classDef app fill:#0f2530,stroke:#0f766e,color:#fff
    classDef monitor fill:#fff4e6,stroke:#c2410c

    EXT["Weather APIs"]

    subgraph Stack ["Docker Compose"]
        direction LR
        AIR["Airflow"]:::pipeline
        FEAT["Feature DAG"]:::pipeline
        MIN["MinIO"]:::storage
        TRN["Training DAG"]:::pipeline
        MLF["MLflow"]:::storage
        FEAST["Feast emulator"]:::storage
        APP["FastAPI"]:::app
        MON["Prometheus"]:::monitor
    end

    EXT --> FEAT
    AIR --> FEAT
    AIR --> TRN
    FEAT --> MIN
    FEAT --> TRN
    MIN --> TRN
    TRN --> MLF
    MIN --> FEAST
    FEAST --> APP
    MLF --> APP
    APP --> MON
</div>

## Three Entry Points

| Entry point | When to use | What it covers |
|-------------|-------------|---------------|
| `./scripts/bootstrap-local.sh` | Full local runtime | All services + pipeline run + verification |
| `dvc repro` | Reproducible offline rerun | Curate + train, writes to `data/` and `reports/` |
| `curl localhost:8000/rank` | Test serving | Just the running app |

## Services

| Service | Port | What |
|---------|------|------|
| FastAPI app | 8000 | Prediction and ranking API |
| Airflow | 8080 | DAG scheduling and monitoring |
| MLflow | 5001 | Experiment tracking and model registry |
| Prometheus | 9090 | Metrics collection |
| MinIO | 9000 | S3-compatible object storage |
| Feast emulator | — | Datastore-mode online serving |
| StatsD exporter | 9102 | Drift metrics |

## What Gets Verified

The bootstrap starts all containers and checks that the core pipeline runs end to end:

- Airflow webserver, scheduler, triggerer all healthy
- Feature pipeline DAG runs successfully
- Training pipeline triggers from the feature asset
- App serves `/health` with a real model version
- `/features/online` returns Feast data
- `/metrics` exposes monitoring gauges

## Local State

| Type | Location | Persists? |
|------|----------|-----------|
| Airflow metadata/logs | Docker volumes | Reset on bootstrap |
| Curated features | MinIO | Reset on bootstrap |
| MLflow artifacts | MinIO | Reset on bootstrap |
| Prediction history | `.state/monitoring/` | Retained |
| Pipeline summaries | `airflow/reports/` | Retained |
