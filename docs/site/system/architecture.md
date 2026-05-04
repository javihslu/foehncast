# Architecture

FoehnCast follows the Feature-Training-Inference pattern. This keeps data preparation, model work, and serving logic separate.

## FTI Overview

```mermaid
flowchart LR
    OME[Open-Meteo] --> F1[Ingest]
    F1 --> F2[Engineer]
    F2 --> F3[Validate]
    F3 --> F4[Store]
    F4 --> FS[(Feature store)]

    FS --> T1[Label]
    T1 --> T2[Train]
    T2 --> T3[Evaluate]
    T3 --> T4[Register]
    T4 --> MR[(MLflow)]

    FS --> I1[Predict]
    MR --> I1
    OSRM[OSRM] --> I2[Rank]
    I1 --> I2
    I2 --> I3[Serve]
```

## Pipeline Responsibilities

| Layer | Role | Current state |
|------|------|---------------|
| Feature pipeline | Collect, transform, validate, and store weather data | implemented and runnable through Airflow |
| Training pipeline | Build labels, train the model, evaluate it, and register it | implemented and runnable through Airflow |
| Inference pipeline | Produce predictions, rank spots, and expose results | implemented in the app container |
| Shared services | Feature store and model registry | running in the local stack |

## Infrastructure Baseline

| Component | Local now | Cloud target |
|-----------|-----------|--------------|
| Feature storage | Local Parquet or S3-compatible storage | BigQuery |
| Model registry | MLflow with local services | MLflow with cloud-backed artifacts |
| Serving | FastAPI app container | Cloud Run |
| Orchestration | Airflow containers | Cloud Composer / managed Airflow |
| Artifacts | MinIO | GCS |
| Monitoring | local baseline and stubs | later MS4 work |

## Current Validation

- The feature DAG runs successfully in Airflow.
- The training DAG runs successfully in Airflow.
- The inference service responds from its own container.
- The container-side test suite passes.

## Cloud Direction

The local stack is now a proof of execution, not the final hosting model. The next step is to map the same pipeline boundaries onto managed GCP services instead of changing the application structure.

See the cloud target in [cloud-mapping.md](cloud-mapping.md).
