# FoehnCast Docs

FoehnCast ranks Swiss kiteboarding spots for one rider profile by combining live weather forecasts, engineered wind features, drive-time information, and a trained quality model. Use the repository README for the short summary. Use this site for setup help, system notes, and operator guidance.

## Start Here

| Need | Read this |
|------|-----------|
| Run the project locally with the default evaluator workflow | [Getting Started](getting-started.md) |
| Understand the Feature-Training-Inference split | [Architecture](system/architecture.md) |
| See how the hosted path maps onto GCP | [Cloud Mapping](system/cloud-mapping.md) |
| Understand the main code and folder layout | [Repository](system/repository.md) |
| Understand the rider scope and data inputs | [Use Case and Data](system/use-case.md) |

## Operating Model

| Mode | Who runs it | Purpose |
|------|-------------|---------|
| Local stack | Any reader or contributor | Development, evaluation, and reproducible validation |
| Online stack | The operator of a fork or a personal cloud setup | Full hosted deployment of Airflow, MLflow, and the API |
| GitHub automation | Repository maintainer or fork owner | Image publishing, Terraform workflows, and docs publishing |

Public images are convenience artifacts, not a shared hosting promise. If you want a running online environment, deploy it in infrastructure you control.

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
| Training pipeline | Working | The training DAG labels data, trains the model, evaluates it, and registers fresh versions in MLflow under a candidate alias |
| Inference pipeline | Working | The app serves the model-backed API routes used for health, prediction, and ranking |
| Hosted runtime | Working | Terraform plus the online compose stack can run Airflow, MLflow, and the API on GCP |
| CI/CD | Working | GitHub Actions validates docs and infrastructure and supports remote Terraform operations |

## Documentation Map

- [Getting Started](getting-started.md): choose the right operator path and run the first commands.
- [Architecture](system/architecture.md): the stable Feature-Training-Inference split and runtime surfaces.
- [Feature Pipeline](system/feature-pipeline.md): how data moves from forecast ingestion to curated features.
- [Cloud Mapping](system/cloud-mapping.md): how local boundaries map onto hosted storage and runtime choices.
- [Repository](system/repository.md): where the code, orchestration, tests, docs, and demo live.
- [Use Case and Data](system/use-case.md): the rider profile, spot set, and data sources behind the ranking.
