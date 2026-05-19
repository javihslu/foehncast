# Local Evaluator

The local evaluator is the default way to run FoehnCast. It starts everything in Docker Compose and verifies the full pipeline works before declaring success.

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
    classDef pipeline fill:#e1f5fe,stroke:#01579b
    classDef storage fill:#ececff,stroke:#9370db
    classDef app fill:#222,stroke:#333,color:#fff
    classDef monitor fill:#fff8e1,stroke:#f57f17

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

The bootstrap doesn't just start containers — it proves the system works:

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

## Related Pages

- [Getting Started](../getting-started.md) — quick setup instructions
- [Architecture](architecture.md) — how this fits the FTI split
- [Delivery Workflow](delivery-and-operator-workflow.md) — cloud deployment (separate from local)
