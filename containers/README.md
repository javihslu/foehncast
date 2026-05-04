# Container Components

This directory holds the files for the local container stack.

- Compose files define services, networks, volumes, dependencies, and environment variables.
- Small startup scripts handle setup steps for each component.
- Init services write a health file when setup is done, so other services can wait for them.

## Main components

### `mlflow/`

- `model-registry`: runs the MLflow tracking and model registry server with SQLite metadata and a local artifact volume served through MLflow.

### `airflow/`

- `airflow-init`: sets up the metadata database, log directories, and health marker, and can create an admin user when local auth is enabled.
- `airflow-webserver`: serves the UI and API.
- `airflow-scheduler`: schedules DAG runs.
- `airflow-triggerer`: handles deferred task triggers.

### `development_env/`

- `development_env`: keeps a local development container ready with the project environment synced by `uv`.

### `app/`

- `app`: runs the FastAPI inference service in its own container so prediction and ranking are part of the stack.

## Local validation

For the shortest evaluator path, run `./scripts/bootstrap-local.sh` from the repo root. It builds the local stack, seeds the feature and training DAGs, and checks the API health endpoint.

The default local path keeps feature data on local files, starts Airflow and MLflow without a login, and resets local Docker volumes for a clean run each time.
Optional S3-compatible settings can still be injected through the environment for experiments, but they are no longer part of the default local stack.

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
