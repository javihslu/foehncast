# MS2 Coaching

<span class="fc-pill fc-pill--progress">In Progress</span>

MS2 is about turning the proposal into a working back-end and checking whether the architecture is still the right one.

## Current Backend Status

| Area | State | Notes |
|------|-------|-------|
| `config.py` | done | Loads and caches `config.yaml` |
| `feature_pipeline.ingest` | done | Fetches forecast and archive data from Open-Meteo |
| `feature_pipeline.engineer` | done | Adds `wind_steadiness`, `gust_factor`, and `shore_alignment` |
| `feature_pipeline.validate` | next | Validation rules still need implementation |
| `feature_pipeline.store` | next | Parquet write path still needs implementation |
| `training_pipeline` | next | Label, train, evaluate, and register are still missing |
| `inference_pipeline` | next | Predict, rank, and serve are still missing |
| `dags/` | next | Orchestration wrappers are still missing |
| Docker stack | next | Reproducible local stack is still missing |

## Points for the Coaching Session

- Is the local Parquet baseline enough for MS2, with MinIO or Feast deferred to later work?
- Should Airflow be demonstrated in MS2, or is it acceptable once the feature and training modules are complete?
- How much of the MeteoSwiss validation path is expected before MS4?

## Current Implementation Chain

```mermaid
flowchart LR
    CFG[config.py] --> ING[ingest.py]
    ING --> ENG[engineer.py]
    ENG --> NEXT[validate.py and store.py]
    NEXT --> TRAIN[training_pipeline]
```
