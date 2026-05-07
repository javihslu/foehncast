# MS2 Backend

<span class="fc-pill fc-pill--done">Completed</span>

MS2 is where the proposal became runnable software. The important result is simple: the local stack now executes the feature, training, and inference paths together with real forecast data and a working API surface.

!!! note "How to read this page"

    MS1 defined the baseline idea.
    MS2 is the first checkpoint where that idea exists as a working local backend.
    This page stays focused on the validated local system, not on later cloud or automation detail.

## MS2 Outcome

| Area | What MS2 established |
|------|----------------------|
| Feature path | forecast data can be ingested, engineered, validated, and stored as curated rows |
| Training path | curated rows can be labeled, trained on, evaluated, and registered through MLflow |
| Inference path | the app serves health, predict, rank, and spot-list endpoints from a trained model |
| Local runtime | Docker Compose runs Airflow, MLflow, the API, and the development container together |
| Optional online features | curated features can also be surfaced through an optional Feast-backed lookup path |

## What Runs End To End

<div class="mermaid">
flowchart LR
    OME[Open-Meteo] --> FEAT[Feature DAG]
    FEAT --> PAR[(Curated features)]
    PAR --> TRAIN[Training DAG]
    TRAIN --> MLF[(MLflow)]
    MLF --> APP[FastAPI app]
    OME --> APP
    OSRM[OSRM] --> APP
    APP --> OUT[Health, predict, and rank responses]
    PAR --> FEAST[Optional Feast lookup]
    FEAST --> APP
</div>

## Representative Validation

| Check | What it proves |
|-------|----------------|
| `airflow dags test feature_pipeline 2024-01-01` | the feature DAG can execute through Airflow |
| `airflow dags test training_pipeline 2024-01-01` | the training DAG can execute through Airflow |
| `curl -fsS http://127.0.0.1:8000/health` | the API starts with a serving model version |
| `curl -fsS -X POST http://127.0.0.1:8000/predict ...` | the app returns live per-spot predictions |
| `docker compose exec -T development_env uv run pytest` | the local stack still passes the regression suite after initialization |

## What Changed From MS1

| Proposal expectation | MS2 refinement |
|----------------------|----------------|
| first model uses a simple engineered feature set | the implemented engineer step also adds cyclical time features |
| feature-store language suggests a heavier default stack | the current baseline keeps local storage as the default and Feast as optional |
| inference is a planned API layer | inference now includes health, list, predict, rank, and optional online-feature routes |

## Why MS2 Matters

- The full FTI split exists in runnable code instead of stubs.
- Airflow already exercises the feature and training paths.
- The app already serves the inference path from a registered model version.
- The local stack is a proof of execution, not a mock-up.

MS2 proves that the backend runs locally in containers. The next step is to keep the same pipeline boundaries while improving the presentation story and then the hosted operating model.

See [MS1 Proposal](ms1.md) for the original baseline and [Architecture](../system/architecture.md) for the current system view.
