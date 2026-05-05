# FoehnCast Journal

FoehnCast ranks Swiss kiteboarding spots for one rider profile by combining live weather forecasts, engineered wind features, drive-time information, and a trained quality model. This journal explains how the project is designed, how it is set up, and how it is operated across local, online, and CI/CD paths.

## What This Site Covers

- the working local stack for feature, training, and inference
- the operating modes used for local evaluation, online hosting, and CI/CD
- the milestone-by-milestone story behind the course submission
- the cloud mapping that keeps the same application boundaries in a hosted environment

## Operating Model

| Mode | Who operates it | Who pays for it | Purpose |
|------|-----------------|-----------------|---------|
| Local stack | Any reader or contributor | The person running Docker locally | Development, evaluation, and reproducible local validation |
| Online stack | The operator of a fork or a local cloud setup | The operator's own cloud account | A full online deployment of Airflow, MLflow, and the API |
| Upstream CI/CD | Repository maintainer | The upstream repository account | Validation, docs publishing, and reference image publishing |
| Fork CI/CD | Fork owner | The fork owner's GitHub and cloud accounts | Personal or team-specific automation without using the upstream environment |

Public GHCR images are convenience artifacts for reuse. They do not provide shared hosting, and deployment costs still belong to the operator running the stack.

The repository keeps local evaluation and maintainer-managed automation separate, so forks can reuse the same deployment shape with their own approvals and cloud accounts.

## What Works

| Area | Current state | What it means |
|------|---------------|---------------|
| Feature pipeline | Working | Airflow can ingest, engineer, validate, and store curated weather features for the configured spots |
| Training pipeline | Working | Airflow can label data, train the model, evaluate it, and register a version in MLflow |
| Inference pipeline | Working | The app serves `/health`, `/spots`, `/predict`, and `/rank` from the registered model |
| Optional Feast path | Working | Curated local features can be exported, materialized, and queried through Feast, the helper, the API, and the demo page |
| Online runtime | Working | `docker-compose.cloud.yml` plus Terraform can run Airflow, MLflow, and the API on a single online host |
| CI/CD path | Working | GitHub Actions can publish images, validate infrastructure, and drive the online deployment path |
| Local reproducibility | Working | `bootstrap-local.sh` brings the stack up from a clean state and validates the local path |

## End-to-End Local Flow

<div class="mermaid">
flowchart LR
    OME[Open-Meteo forecast] --> FEAT[Feature DAG]
    FEAT --> PAR[(Curated feature parquet)]
    PAR --> TRAIN[Training DAG]
    TRAIN --> MLF[(MLflow registry)]

    OME --> APP[FastAPI app]
    OSRM[OSRM drive times] --> APP
    MLF --> APP
    APP --> API[Predict and rank endpoints]

    PAR --> FEXP[Optional Feast export]
    FEXP --> FEAST[(Feast online store)]
    FEAST --> APP
    APP --> FEATAPI[Online feature endpoint and demo]
</div>

## Short Roadmap

The core idea is fixed: keep the same Feature-Training-Inference split and change the infrastructure in small steps instead of redesigning the code.

<div class="mermaid">
flowchart LR
    LOCAL[Local stack<br/>runs with real data] --> DATA[Cloud data path<br/>BigQuery and GCS-backed services]
    DATA --> DEPLOY[Managed runtime<br/>same app and DAG split]
    DEPLOY --> FINAL[Operations<br/>monitoring and final wrap-up]
</div>

- **Local stack**: the proof that the pipelines run together.
- **Cloud data path**: reuse the same boundaries with BigQuery for curated data and GCS-backed artifacts.
- **Managed runtime**: move orchestration and serving to managed GCP services or an online compose host instead of changing the application shape.
- **Operations**: finish automation, monitoring, and final delivery material.

## Reading Guide

- **Journal**: operating model, design framing, and roadmap.
- **Milestones**: course-facing progress by submission checkpoint.
- **System**: the working architecture, cloud target, and repository layout.
