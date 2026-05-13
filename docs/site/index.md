# FoehnCast Docs

FoehnCast ranks Swiss kiteboarding spots for one rider profile by combining live weather forecasts, engineered wind features, drive-time information, and a trained quality model. Use the repository README for the short summary. Use this site for setup help, product scope, runtime notes, and operator guidance.

The default contributor path stays local with Docker. The shared cloud path is maintainer-owned and documented separately.

This site keeps rider-facing demo surfaces, service APIs, operator dashboards, and public-safe rendered evidence separate on purpose. Grafana belongs to the operator layer here. It is not the primary product UI and the public docs do not depend on live private dashboard embeds.

## Start Here

| Need | Read this |
|------|-----------|
| Run the project locally with the default evaluator workflow | [Getting Started](getting-started.md) |
| Maintain the shared cloud environment or understand the setup split | [Delivery and Operator Workflow](system/delivery-and-operator-workflow.md) |
| Understand what stays in package config versus runtime wiring | [Configuration and Contracts](system/configuration-and-contracts.md) |
| Understand which routes and tools are rider-facing, service-only, or operator-only | [Interfaces and Surfaces](system/interfaces-and-surfaces.md) |
| Understand the Feature-Training-Inference split | [Architecture](system/architecture.md) |
| See how the hosted path maps onto GCP | [Cloud Mapping](system/cloud-mapping.md) |
| Understand the main code and folder layout | [Repository](system/repository.md) |
| Understand the rider scope and data inputs | [Use Case and Data](system/use-case.md) |

## Operating Model

| Mode | Who runs it | Purpose |
|------|-------------|---------|
| Local stack | Any reader or contributor | Development, evaluation, and reproducible validation |
| Shared cloud environment | Repository maintainer or fork owner after one-time bootstrap | Full hosted deployment of Airflow, MLflow, and the API |
| GitHub automation | Repository maintainer or fork owner after bootstrap | Image publishing, Terraform workflows, and docs publishing |

Public images are convenience artifacts, not a shared hosting promise. If you want a running online environment, deploy it in infrastructure you control.

## Surface Guide

| Surface | Primary audience | Exposure | Current examples |
|------|------------------|----------|------------------|
| Rider-facing demo surfaces | rider, reviewer, contributor | public-safe when shown as screenshots or rendered outputs | Streamlit demo, ranking examples, and the online-features demo page |
| Service APIs | clients, smoke tests, support services | service-only | `/health`, `/spots`, `/predict`, `/rank`, `/features/online`, and `/metrics` |
| Operator dashboards and control planes | maintainer or deployment operator | internal-only by default | Airflow, MLflow, Prometheus, and Grafana |
| Public-safe docs and evidence | reviewer, course audience, fork reader | public-safe | docs pages, rendered evaluation markdown, summary JSON-derived charts, and screenshots |

Use the rider demo or API examples to explain the product surface. Use rendered artifacts or screenshots to explain operations in public docs. Keep live operator dashboards private unless you are intentionally running your own environment.

## System In One View

<div class="mermaid">
flowchart LR
    OME[Open-Meteo forecast] --> FEAT[Feature DAG]
    FEAT --> PAR[(Curated features)]
    PAR --> TRAIN[Training DAG]
    TRAIN --> MLF[(MLflow registry)]

    OME --> APP[FastAPI app]
    OSRM[OSRM drive times] --> APP
    MLF --> APP
    APP --> API[Predict and rank endpoints]

    PAR --> FEAST[(Feast serving layer)]
    FEAST --> APP
</div>

## Current Status

| Area | Status | Meaning |
|------|--------|---------|
| Feature pipeline | Working | The feature DAG ingests, engineers, validates, and stores curated weather features |
| Training pipeline | Working | The training DAG labels data, trains the model, evaluates it, and registers fresh versions in MLflow under the requested registry alias |
| Inference pipeline | Working | The app serves the model-backed API routes used for health, prediction, and ranking |
| Hosted runtime | Working | Terraform plus the online compose stack can run Airflow, MLflow, and the API on GCP |
| CI/CD | Working | GitHub Actions validates docs and infrastructure and supports remote Terraform operations |

## Documentation Map

### Overview

- [Getting Started](getting-started.md): choose the right setup path and run the first commands.
- [Use Case and Data](system/use-case.md): the rider profile, spot set, and data sources behind the ranking.
- [Repository](system/repository.md): where the code, orchestration, tests, docs, and demo live.
- [Configuration and Contracts](system/configuration-and-contracts.md): what belongs in `config.yaml`, what runtime env resolves, and what infrastructure keeps outside the package.
- [Interfaces and Surfaces](system/interfaces-and-surfaces.md): which screens, routes, dashboards, and docs belong to riders, services, operators, or public review.

### Runtime and Deployment

- [Architecture](system/architecture.md): the stable Feature-Training-Inference split and runtime surfaces.
- [Local Evaluator](system/local-evaluator.md): the default local runtime contract for contributors.
- [Delivery and Operator Workflow](system/delivery-and-operator-workflow.md): the maintainer path for shared cloud bootstrap and day-2 delivery.
- [Hosted Full-Stack](system/hosted-full-stack.md): the active shared hosted runtime target and sync contract.
- [Cloud Mapping](system/cloud-mapping.md): how local boundaries map onto hosted storage and runtime choices.

### Pipelines and Modeling

- [Feature Pipeline](system/feature-pipeline.md): how data moves from forecast ingestion to curated features.
- [Training Pipeline](system/training-pipeline.md): how labeled data becomes a registered serving model.
- [Inference Pipeline](system/inference-pipeline.md): how prediction, ranking, and online feature lookup are served.
- [Seasonality](system/seasonality.md): how cyclical time features capture recurring daily and yearly structure.

### Operations

- [Monitoring](system/monitoring.md): how Prometheus, Grafana, alerts, and runtime evidence stay on the operator side.
