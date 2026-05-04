# Cloud Mapping

FoehnCast keeps the same Feature-Training-Inference split in the cloud. The goal is not to invent a second architecture, but to move the validated local container stack onto managed GCP services.

## Mapping Principle

- Local Docker proves that the pipelines run together.
- Cloud deployment keeps the same pipeline boundaries.
- Support services in the cloud replace local-only tools such as MinIO.
- The app remains a deployable container because inference is a service, not a DAG.

## Local To Cloud Mapping

| Local component | Cloud target | Role |
|----------------|-------------|------|
| `app` container | Cloud Run service | Serve `/health`, `/spots`, `/predict`, and `/rank` |
| Airflow containers | Cloud Composer / managed Airflow | Schedule and run feature and training DAGs |
| MinIO object store | GCS bucket | Store artifacts and other object data |
| Local feature storage | BigQuery tables | Hold curated feature data for cloud pipelines |
| MLflow with SQLite + MinIO | MLflow service with GCS-backed artifacts | Track runs, metrics, and registered model versions |
| Artifact Registry bootstrap | Artifact Registry | Store deployable container images |
| `development_env` container | CI jobs and local prototyping only | Keep local workflows reproducible without becoming a cloud runtime |

## Cloud Pipeline Shape

### Feature pipeline

1. Airflow triggers ingestion from Open-Meteo.
2. Feature engineering and validation run in Python modules.
3. Curated feature outputs are written to BigQuery.
4. Optional raw or intermediate artifacts can still be written to GCS.

### Training pipeline

1. Airflow triggers training on the current feature data.
2. The training job reads from BigQuery.
3. Metrics and artifacts are logged to MLflow.
4. The trained model is registered and promoted by alias.
5. The evaluation report is written from logged metrics, not by reloading the model in a later task.

### Inference pipeline

1. Cloud Run serves the FastAPI container.
2. The service fetches live forecasts and loads the promoted model version.
3. Ranking stays inside the service because it is request-driven logic.

## What Changes In The Cloud

| Area | Local now | Cloud target |
|------|-----------|--------------|
| Feature storage | local Parquet or S3-compatible store | BigQuery |
| Artifacts | MinIO | GCS |
| Orchestration | local Airflow containers | Cloud Composer / managed Airflow |
| Inference | local app container | Cloud Run |
| Runtime auth | local env file | service accounts and OIDC |

## Local BigQuery Development Path

For local Docker runs, the shared config can now switch to `storage.backend=bigquery` entirely through environment variables.

The remaining requirement is credentials inside the Linux containers. Use:

1. `./scripts/gcp-auth.sh`
2. `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.gcp.yml up -d`

The optional `docker-compose.gcp.yml` override mounts the host `~/.config/gcloud` directory into the app, Airflow, and development containers, and it pins the deployable app service to `linux/amd64` so local image checks match the GCP target architecture without a second Compose file.

## What Still Needs To Be Added

- A Cloud Run deployment stage that consumes the published `linux/amd64` app image.
- A cloud-hosted MLflow deployment choice.
- Managed Airflow provisioning and DAG deployment.

## Current Terraform Support

The Terraform baseline now covers the first cloud runtime slice:

- Artifact Registry and GCS bootstrap
- BigQuery dataset plus curated feature table
- an optional Cloud Run inference service definition

The repository now also includes a GitHub Actions workflow that publishes the `containers/app/Dockerfile` image to Artifact Registry on `main` when the required OIDC and registry variables are configured.

The application code now also supports a `bigquery` storage backend through the shared feature-store abstraction, so feature writes and training reads can move to BigQuery without changing the pipeline modules themselves. Local container runs can mount ADC via `docker-compose.gcp.yml`, while Cloud Run keeps using its runtime service account.

The Cloud Run service stays opt-in until a real release image and MLflow endpoint are available.

## Why This Fits The Project Brief

The project brief asks for cloud-ready pipelines and cloud orchestration. This mapping keeps the backend already validated in MS2, but replaces the local support stack with cloud services that can run autonomously after deployment.
