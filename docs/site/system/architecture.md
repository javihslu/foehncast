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
| Feature pipeline | Collect, transform, validate, and store weather data | ingest and engineer are implemented |
| Training pipeline | Build labels, train the model, evaluate it, and register it | planned |
| Inference pipeline | Produce predictions, rank spots, and expose results | planned |
| Shared services | Feature store and model registry | planned baseline in config |

## Infrastructure Baseline

| Component | Baseline |
|-----------|----------|
| Feature storage | Local Parquet files |
| Model registry | MLflow |
| Serving | FastAPI |
| Orchestration | Airflow |
| Monitoring | Drift detection plus dashboard tooling |
