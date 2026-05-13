# Inference Pipeline

FoehnCast keeps inference inside the application layer. The serving path resolves the live MLflow alias, fetches fresh forecasts for configured spots, rebuilds the shared engineered feature vector, returns per-spot quality predictions, and optionally exposes the Feast-backed online lookup without pulling training or operator concerns into the request path.

This page records the current serving contract that is validated in the local stack and in endpoint, dashboard, and cloud-runtime tests. It focuses on what the running app owns today and what stays optional or operator-controlled.

!!! note "Scope"

    This page describes the current validated inference-path contract.
    It is not a roadmap.
    Future changes should be documented after they are chosen and implemented.

## Inference Shape

<div class="mermaid">
flowchart LR
    REQ[Requested spots] --> RES[Resolve configured spots]
    RES --> WX[Fetch Open-Meteo forecast]
    WX --> ENG[Engineer shared features]
    REG[MLflow serving alias] --> MOD[Load served model]
    ENG --> MOD
    MOD --> PRE[/predict response]
    PRE --> RNK[Rank with rider profile and drive time]
    RNK --> OUT[/rank response]
    RES --> ONL[/features/online lookup]
    ONL --> DEMO[Online-features demo]
    DASH[Streamlit live demo] --> PRE
    DASH --> OUT
    PRE --> MON[Prediction monitoring hand-off]
    OUT --> MON
</div>

The important boundary is that inference stays request-focused:

- the app resolves configured spots and fetches fresh forecast data on demand
- the serving model is loaded from the registry alias that represents the live contract
- prediction and ranking reuse the same forecast payload instead of forking into separate pipelines
- the Feast lookup path stays optional and does not gate the main prediction surface
- monitoring is triggered from the request path, but the operator metrics surface stays separate

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

Inference serves one registry alias at a time. The current contract is:

- the registered model name is `foehncast-quality`
- the default live alias is `champion`
- `FOEHNCAST_MLFLOW_SERVING_ALIAS` can override the served alias when an operator needs to pin another registry view
- `/health` returns `status`, `model_alias`, and `model_version` so a runtime check can confirm what is actually being served
- prediction responses also include `model_version` so downstream consumers can tie a response back to the active registry version

This keeps serving aligned with the training registry contract without giving the inference service promotion or rollback authority.

## Prediction Boundary

The prediction path is intentionally narrow:

- requested spot IDs are resolved against the configured spot list, and unknown spots return `404` instead of silently falling back
- live weather comes from the current Open-Meteo forecast pull for each requested spot
- the request horizon is capped by `inference.max_horizon_hours`, which is currently `14`
- the same `engineer_features` step used by the feature path rebuilds the feature vector expected by the trained model
- the served feature columns come from `model.features` in `config.yaml`
- the app returns forecast rows as timestamps plus continuous `quality_index` values

That means the request path scores a trained model against fresh forecast features. It does not recompute the synthetic training labels, emit evaluation artifacts, or move registry aliases.

## Ranking Boundary

`/rank` is not a second model. It reuses the prediction payload from `/predict` and then scores the candidate spots for the configured rider profile.

The current ranking contract is:

- ranking weights come from `config.yaml` and are currently `0.6` for peak quality, `0.3` for ride-versus-drive ratio, and `0.1` for rideable duration
- drive-time cost comes from the rider profile plus the OSRM routing lookup
- session duration is derived from the forecast hours that clear the rideable threshold
- the route returns ranked numeric rows such as `quality_index`, `drive_minutes`, `session_hours`, `ride_drive_ratio`, and `score`

This keeps ranking personal without hiding another model behind the API. The Streamlit demo can add rider-facing labels and summary cards on top of the same ranked data.

## Online Feature Boundary

The online feature route is a separate integration surface layered on top of the same curated contract.

The current online-feature contract is:

- the default Feast repo path is `feature_repo/`, with `FOEHNCAST_FEAST_REPO_PATH` as an override
- a call without explicit feature names uses the `foehncast_model_v1` feature service
- a call with explicit feature names resolves them against the `spot_forecast_features` view unless the caller already supplies a fully qualified feature reference
- the route returns row-shaped feature data instead of leaking Feast's columnar response shape
- the route returns `503` when the Feast runtime dependency or configured repo is missing and `400` when the requested feature list is invalid

This path stays optional. Normal `/predict` and `/rank` requests do not depend on Feast being available.

## Rider Demo Surfaces

FoehnCast keeps the rider-facing demo separate from operator dashboards.

The current demo surfaces are:

- the Streamlit live demo, which loads live predictions, applies the ranking helper, and presents rider-facing cards and tables
- the online-features demo page, which issues manual `/features/online` calls against the running app

The Streamlit helper rounds continuous quality scores into stable rider-facing labels from `Unsafe` through `Perfect Storm`, uses the configured forecast horizon to describe the current live window, and exposes the current `model_version` in the returned payload. That makes it a public-safe evaluation surface, not an operator dashboard.

## Monitoring Hand-Off

Prediction routes emit monitoring signals, but the monitoring surface itself stays separate.

The current hand-off is:

- `/predict` and `/rank` schedule background prediction-monitoring work after a successful response payload is built
- the background path records scheduling and execution outcomes and emits prediction-drift metrics from retained prediction history
- `/metrics` merges durable feature and training summaries, retained prediction-log metrics, hosted-sync metrics, and in-process prediction-monitoring counters

This keeps the inference service responsible for request-side facts while leaving dashboards, alert rules, and long-range operator review to the monitoring stack.

## Hosted Serving Boundary

The same FastAPI app runs across the supported serving targets.

The current hosted contract is:

- the local evaluator target serves the full app inside the Compose stack
- the hosted full-stack target keeps the app online next to the other runtime services on one GCP host
- the hosted inference target publishes the same FastAPI inference surface on Cloud Run without shipping Airflow, notebooks, docs tooling, or local emulators
- cloud bootstrap and operator checks verify the live `/health` and `/spots` routes when the hosted inference path is enabled

That boundary matters because the app is the product and service surface. Grafana remains an operator surface, not the rider product UI.

## Why This Structure Works

- it keeps live requests narrow enough to verify through simple route and dashboard tests
- it reuses the shared feature contract instead of inventing a serving-only schema
- it ties responses back to a concrete registry version without giving the app promotion authority
- it keeps the Feast lookup path useful for integration checks while leaving prediction and ranking available from the core app alone

See [Architecture](architecture.md), [Training Pipeline](training-pipeline.md), [Monitoring](monitoring.md), and [Cloud Mapping](cloud-mapping.md) for the surrounding system boundaries.
