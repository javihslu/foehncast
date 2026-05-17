# Inference Pipeline

FoehnCast keeps inference inside the application layer. The same FastAPI serving contract runs locally, on Cloud Run, and on the private operator lane. Cloud Run is the shared public API. The operator-lane app stays private for internal checks.

This page describes what the running app owns and what stays optional or operator-controlled.

!!! note "Scope"

    This page describes the validated inference-path contract.
    It does not redefine orchestration or the hosted build.
    The serving contract stays stable regardless of hosted control-plane changes.

## Inference Shape

<div class="mermaid">
flowchart LR
    subgraph RequestPath ["Request path"]
        direction TB
        REQ["Requested spots"]
        RES["Resolve configured spots"]
        WX["Fetch Open-Meteo forecast"]
        ENG["Engineer shared features"]
        REQ --> RES --> WX --> ENG
    end

    subgraph ModelPath ["Model path"]
        direction TB
        REG["MLflow serving alias"]
        MOD["Load served model"]
        REG --> MOD
    end

    subgraph OutputPath ["Outputs"]
        direction TB
        PRE["/predict response"]
        RNK["Rank with rider profile and drive time"]
        OUT["/rank response"]
        MON["Prediction monitoring hand-off"]
        PRE --> RNK --> OUT
    end

    subgraph OptionalPath ["Demo surfaces"]
        direction TB
        ONL["/features/online lookup"]
        DEMO["Online-features demo"]
        DASH["Streamlit live demo"]
        ONL --> DEMO
    end

    ENG --> MOD
    MOD --> PRE
    RES --> ONL
    DASH --> PRE
    DASH --> OUT
    PRE --> MON
    OUT --> MON
</div>

Inference stays request-focused:

- the app resolves configured spots and fetches fresh forecast data on demand
- the serving model is loaded from the registry alias that represents the live contract
- prediction and ranking reuse the same forecast payload instead of forking into separate pipelines
- the Feast lookup path stays optional and does not gate the main prediction surface
- monitoring is triggered from the request path but the operator metrics surface stays separate

## Endpoint Responsibilities

| Surface | Main responsibility | Must not become |
|------|----------------------|-----------------|
| `/health` | expose app readiness plus the served alias and model version | a deployment control plane |
| `/spots` | return the configured set of supported spots | a source of hidden business rules |
| `/predict` | return per-spot forecast rows with continuous `quality_index` values | a training, labeling, or promotion path |
| `/rank` | score the same prediction payload for one rider profile | a second prediction model or a dashboard layer |
| `/features/online` | expose Feast-backed online feature rows for app-side integrations | a required dependency for normal prediction requests |
| `/features/online/demo` | give a lightweight HTML page for manual lookup checks | the main rider product UI |

The app also serves `/metrics`, but that route belongs to the monitoring hand-off described below rather than to the core rider-facing inference contract.

## Model Resolution Boundary

Inference serves one registry alias at a time. The serving contract is:

- the registered model name is `foehncast-quality`
- the default live alias is `champion`
- `FOEHNCAST_MLFLOW_SERVING_ALIAS` can override the served alias when an operator needs to pin another registry view
- `/health` returns `status`, `model_alias`, and `model_version` so a runtime check can confirm what is actually being served
- prediction responses also include `model_version` so downstream consumers can tie a response back to the active registry version

This keeps serving aligned with the training registry contract without giving the inference service promotion or rollback authority.

## Prediction Boundary

The prediction path is intentionally narrow:

- requested spot IDs are resolved against the configured spot list, and unknown spots return `404` instead of silently falling back
- live weather comes from the Open-Meteo forecast pull for each requested spot
- the request horizon is capped by `inference.max_horizon_hours`, which defaults to `14`
- the same `engineer_features` step used by the feature path rebuilds the feature vector expected by the trained model
- the served feature columns come from `model.features` in `config.yaml`
- the app returns forecast rows as timestamps plus continuous `quality_index` values

That means the request path scores a trained model against fresh forecast features. It does not recompute the synthetic training labels, emit evaluation artifacts, or move registry aliases.

## Ranking Boundary

`/rank` is not a second model. It reuses the prediction payload from `/predict` and then scores the candidate spots for the configured rider profile.

The ranking contract is:

- ranking weights come from `config.yaml`; the default weights are `0.6` for peak quality, `0.3` for ride-versus-drive ratio, and `0.1` for rideable duration
- drive-time cost comes from the rider profile plus the OSRM routing lookup
- session duration is derived from the forecast hours that clear the rideable threshold
- the route returns ranked numeric rows such as `quality_index`, `drive_minutes`, `session_hours`, `ride_drive_ratio`, and `score`

This keeps ranking personal without hiding another model behind the API. The Streamlit demo can add rider-facing labels and summary cards on top of the same ranked data.

## Online Feature Boundary

The online feature route is a separate integration surface layered on top of the same curated contract.

The online-feature contract is:

- the default Feast repo path is `feature_repo/`, with `FOEHNCAST_FEAST_REPO_PATH` as an override
- a call without explicit feature names uses the `foehncast_model_v1` feature service
- a call with explicit feature names resolves them against the `spot_forecast_features` view unless the caller already supplies a fully qualified feature reference
- the route returns row-shaped feature data instead of leaking Feast's columnar response shape
- the route returns `503` when the Feast runtime dependency or configured repo is missing and `400` when the requested feature list is invalid

This path stays optional. Normal `/predict` and `/rank` requests do not depend on Feast being available.

## Rider Demo Surfaces

FoehnCast keeps the rider-facing demo separate from operator dashboards.

The demo surfaces are:

- the Streamlit live demo, which loads live predictions, applies the ranking helper, and presents rider-facing cards and tables
- the online-features demo page, which issues manual `/features/online` calls against the running app

The Streamlit helper rounds continuous quality scores into stable rider-facing labels from `Unsafe` through `Perfect Storm`, uses the configured forecast horizon to describe the live window, and exposes the served `model_version` in the returned payload. That makes it a public-safe evaluation surface, not an operator dashboard.

## Monitoring Hand-Off

Prediction routes emit monitoring signals, but the monitoring surface itself stays separate.

The monitoring hand-off is:

- `/predict` and `/rank` schedule background prediction-monitoring work after a successful response payload is built
- the background path records scheduling and execution outcomes and emits prediction-drift metrics from retained prediction history
- `/metrics` merges durable feature and training summaries, retained prediction-log metrics, hosted-sync metrics, hindcast validation results, and in-process prediction-monitoring counters
- hindcast validation runs hourly in the background, comparing past predictions against observed weather to measure real forecast accuracy; results persist in `.state/monitoring/hindcast-validation.json`

This keeps the inference service responsible for request-side facts while leaving dashboards, alert rules, and long-range operator review to the monitoring stack.

## Scheduled Inference

Inference also runs as a scheduled Airflow DAG alongside the request-driven app path.

The `inference_pipeline` DAG is:

- triggered by the `foehncast_mlflow_model_registry` asset, meaning it runs automatically after a new model version is registered
- executes `run_inference_pipeline_step`, which predicts across all configured spots using the champion model
- emits the `foehncast_inference_prediction_log` asset so downstream monitoring and hindcast validation can consume fresh predictions
- can also be triggered manually from the Airflow UI when the operator wants a batch prediction refresh

This keeps the prediction-event history populated even when no rider requests arrive, which is important for hindcast validation and drift detection over time.

## Runtime Role

| Runtime mode | Inference role |
|------|---------------------|
| Local evaluator | FastAPI app serves predictions from locally-registered MLflow model; the `inference_pipeline` DAG runs batch predictions after model registration |
| Cloud Run | shared public API with the same serving contract |
| Cloud Composer | scheduled inference DAG runs batch predictions after model registration |
| Private operator host | internal checks next to other hosted operator services |

See [Architecture](architecture.md) for the lane summary and [Hosted Full-Stack](hosted-full-stack.md) for the hosted exposure and transition rules.

## Why This Structure Works

- live requests stay narrow enough to verify through simple route and dashboard tests
- the shared feature contract is reused instead of inventing a serving-only schema
- responses tie back to a concrete registry version without giving the app promotion authority
- one FastAPI contract runs locally, on Cloud Run, and on the operator surface without contract changes
- the Feast lookup path is useful for integration checks while prediction and ranking work from the core app alone

See [Architecture](architecture.md), [Training Pipeline](training-pipeline.md), [Monitoring](monitoring.md), and [Cloud Mapping](cloud-mapping.md) for the surrounding system boundaries.
