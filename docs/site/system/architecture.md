# Architecture

FoehnCast keeps one stable Feature-Training-Inference split across every runtime mode. What changes across milestones is the hosting model around that split, not the application boundaries themselves.

!!! note "How to read this page"

    The validated baseline is the local Compose stack.
    The hosted paths reuse the same feature, training, and inference modules, but move storage, auth, and runtime services onto GCP in different ways.

## Architecture In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Feature pipeline</strong></p>
<p>Forecast data is ingested, engineered, validated, and stored as curated feature rows.</p>
</li>
<li>
<p><strong>Training pipeline</strong></p>
<p>Curated rows are labeled, used for training and evaluation, and registered through MLflow.</p>
</li>
<li>
<p><strong>Inference pipeline</strong></p>
<p>The FastAPI app serves health, predict, rank, and optional online-feature routes.</p>
</li>
<li>
<p><strong>Runtime surfaces</strong></p>
<p>The same pipeline split can run locally, on a full online compose host, or as an inference-only Cloud Run service.</p>
</li>
</ul>
</div>

## Current Local Architecture

<div class="mermaid">
flowchart TD
    OME[Open-Meteo] --> FEAT[Feature DAG]
    FEAT --> PAR[(Curated features)]
    PAR --> TRAIN[Training DAG]
    TRAIN --> MLF[(MLflow registry)]

    OME --> APP[FastAPI app]
    OSRM[OSRM] --> APP
    MLF --> APP

    PAR --> FEAST[(Optional Feast lookup)]
    FEAST --> APP
</div>

## Stable Pipeline Boundaries

| Layer | Responsibility | Current runtime surface |
|------|----------------|-------------------------|
| Feature pipeline | Collect, engineer, validate, and store weather data | local Airflow DAG plus the configured storage backend |
| Training pipeline | Label data, train the model, evaluate it, and register a serving version | local Airflow DAG plus MLflow |
| Inference pipeline | Serve health, predict, rank, and spot-list responses | FastAPI app container |
| Optional online features | Surface curated fields through an online lookup route | optional Feast-backed path plus demo page |

## Current Runtime Surfaces

| Mode | What runs there | Purpose |
|------|-----------------|---------|
| Local Compose baseline | Airflow, MLflow, FastAPI, and the development container | default validated path for development and course evaluation |
| Online compose host | the full Airflow, MLflow, and API stack on one GCP host | simplest way to keep the whole project online |
| Optional Cloud Run path | the FastAPI inference service only | separate deployable serving surface |
| GitHub automation | image publishing and Terraform workflows | repeatable delivery for the hosted paths |

The online compose host exposes only the app on port `8000` by default. Airflow and MLflow stay private unless their ports are explicitly opened.

## Representative Validation

| Check | What it shows |
|-------|---------------|
| feature DAG run through Airflow | the feature path executes inside the orchestration layer |
| training DAG run through Airflow | the training path executes inside the orchestration layer |
| API health and prediction routes | the app serves a real model-backed inference surface |
| optional Feast lookup path | the curated features can also be surfaced online without changing the base pipeline split |
| container-side test suite | the local runtime remains reproducible after stack setup |

## How The Hosted Paths Relate

<div class="mermaid">
flowchart LR
    LOCAL[Validated local stack] --> HOST[Online compose host<br/>full stack]
    LOCAL --> RUN[Optional Cloud Run app<br/>inference only]
    HOST --> NEXT[More managed cloud mapping]
    RUN --> NEXT
</div>

The online compose host is the current full-stack hosted path. Cloud Run remains a useful inference-only path. Both reuse the same application structure instead of creating a second architecture.

## Why This Architecture Holds Up

- The personalized ranking logic stays in the inference layer.
- Feature engineering and training remain reusable across local and hosted paths.
- Hosted changes mostly affect storage, auth, orchestration, and image delivery.
- Optional components such as Feast layer on top of the same curated features instead of splitting the design.

See [Use Case and Data](use-case.md) for the rider-focused problem framing and [Cloud Mapping](cloud-mapping.md) for the hosted path details.
