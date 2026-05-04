# Container Components

This directory holds the files for the local container stack.

- Compose files define services, networks, volumes, dependencies, and environment variables.
- Small startup scripts handle setup steps for each component.
- Init services write a health file when setup is done, so other services can wait for them.

## Main components

### `objectstore/`

- `objectstore`: runs MinIO for local object storage.
- `objectstore-init`: creates the artifact bucket that MLflow needs before the registry starts.

### `mlflow/`

- `model-registry`: runs the MLflow tracking and model registry server with SQLite metadata and the MinIO artifact bucket.

### `airflow/`

- `airflow-init`: sets up the metadata database, admin user, log directories, and health marker.
- `airflow-webserver`: serves the UI and API.
- `airflow-scheduler`: schedules DAG runs.
- `airflow-triggerer`: handles deferred task triggers.

### `development_env/`

- `development_env`: keeps a local development container ready with the project environment synced by `uv`.

### `app/`

- `app`: runs the FastAPI inference service in its own container so prediction and ranking are part of the stack.

## Local validation

Run these checks before deployment work:

1. `docker compose --env-file .env.example up --build -d --remove-orphans`
2. `docker compose --env-file .env.example ps -a`
3. `curl -fsS http://127.0.0.1:8080/health`
4. `curl -fsS http://127.0.0.1:8000/health`
5. `docker compose --env-file .env.example exec -T airflow-scheduler airflow dags list`

## Build targets

- Local development uses the base `docker-compose.yml`, so images build natively on the current machine.
- GCP-targeted local runs add `docker-compose.gcp.yml`, which mounts host ADC and pins the deployable app service to `linux/amd64`.
- Example: `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.gcp.yml build app`
- For release publishing, keep the same target architecture in CI with `docker buildx build --platform linux/amd64 ...`.
