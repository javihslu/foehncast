# MS2 Backend

<span class="fc-pill fc-pill--done">Completed</span>

MS2 is where the proposal became runnable software. The local stack executes the feature, training, and inference paths together with real forecast data and a working API surface.

!!! note "How to read this page"

    MS1 defined the baseline idea. MS2 is the first milestone where that idea exists as a working local backend.
    This page focuses on what is implemented and locally validated, not on the later hosted or automation paths.

## MS2 In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Feature path</strong></p>
<p>Weather forecasts are ingested, engineered, validated, and stored as curated feature rows.</p>
</li>
<li>
<p><strong>Training path</strong></p>
<p>The curated rows are labeled, used for model training, and registered through MLflow.</p>
</li>
<li>
<p><strong>Inference path</strong></p>
<p>The API serves health, predict, rank, and spot-list endpoints from the trained model.</p>
</li>
<li>
<p><strong>Optional online features</strong></p>
<p>The same curated features can also be surfaced through an optional Feast-backed lookup path.</p>
</li>
</ul>
</div>

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

## From Proposal To Running Backend

| MS1 baseline | What MS2 turned it into |
|--------------|--------------------------|
| FTI architecture | runnable feature, training, and inference modules |
| Local-first path | a working Compose stack with Airflow, MLflow, and the API |
| MLflow registry baseline | tracked training runs plus a serving model version |
| Wind-quality feature engineering | implemented feature functions plus cyclical time features |
| Personalized spot ranking | working prediction and ranking endpoints |
| Feast in the stack story | an optional layer instead of a mandatory runtime dependency |

## Backend Surface

| Area | State | Notes |
|------|-------|-------|
| Configuration | implemented | `config.py` loads the shared YAML configuration used across the pipelines |
| Feature pipeline | implemented | ingest, engineer, validate, and store are all present in runnable code |
| Training pipeline | implemented | label, train, evaluate, and register feed MLflow |
| Inference pipeline | implemented | `/health`, `/spots`, `/predict`, `/rank`, `/features/online`, and `/features/online/demo` are defined in the app |
| Orchestration | implemented locally | Airflow runs the feature and training DAGs |
| Local runtime | implemented | Compose brings up Airflow, MLflow, the API, and the development container |
| Optional Feast path | implemented as an option | curated local features can also be exported, materialized, and queried online |

## Representative Local Validation

| Check | What it proves |
|-------|----------------|
| `airflow dags test feature_pipeline 2024-01-01` | the feature DAG can execute through Airflow |
| `airflow dags test training_pipeline 2024-01-01` | the training DAG can execute through Airflow |
| `curl -fsS http://127.0.0.1:8000/health` | the API starts with a serving model version |
| `curl -fsS -X POST http://127.0.0.1:8000/predict ...` | the app returns live per-spot predictions |
| `docker compose exec -T development_env uv run pytest` | the local stack still passes the regression suite after initialization |

## Why MS2 Is The Real Backend Baseline

- The full FTI split exists in runnable code instead of stubs.
- Airflow already exercises the feature and training paths.
- The app already serves the inference path from a registered model version.
- The local stack is a proof of execution, not a mock-up.

## What Changed After MS1

| Proposal expectation | MS2 refinement |
|----------------------|----------------|
| first model uses a simple engineered feature set | the implemented engineer step also adds cyclical time features |
| feature-store language suggests a heavier default stack | the current baseline keeps local storage as the default and Feast as optional |
| inference is a planned API layer | inference now includes health, list, predict, rank, and optional online-feature routes |

## Next Step Toward The Cloud

MS2 proves that the backend runs locally in containers. The next step is to keep the same pipeline boundaries while moving the supporting infrastructure toward the hosted paths described in the system section.

See [MS1 Proposal](ms1.md) for the original baseline and [Architecture](../system/architecture.md) for the current system view.
