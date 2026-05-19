# Configuration

FoehnCast separates "what the app does" (`config.yaml`) from "where it runs" (environment variables). This page explains the split.

## The Rule

<div class="mermaid">
flowchart TD
    YAML["config.yaml\n(what)"] --> PY["config.py"]
    ENV[".env / env vars\n(where)"] --> PY
    TF["Terraform\n(infra)"] --> ENV
    PY --> APP["App, DAGs, training"]
</div>

- **`config.yaml`** owns product logic: spots, model features, thresholds, weights
- **Environment variables** own deployment details: bucket names, URIs, credentials
- **Terraform** owns cloud infrastructure: projects, regions, service accounts

## What's in `config.yaml`

| Section | Controls |
|---------|---------|
| `rider` | Home location, weight, quiver |
| `spots` | The six spots with shore orientation |
| `api` | Open-Meteo and OSRM settings |
| `model` | Algorithm, feature list, seed, split ratio |
| `labeling` | Quality band rules, danger thresholds |
| `inference` | Forecast horizon, ranking weights |
| `monitoring` | Drift threshold, evaluation window |
| `mlflow` | Experiment and model names |
| `storage` | Backend mode (`s3` or `bigquery`) |
| `validation` | Required columns, accepted ranges |

## What's in Environment Variables

| Category | Examples |
|----------|---------|
| Storage | `STORAGE_BACKEND`, `STORAGE_S3_BUCKET`, `STORAGE_S3_ENDPOINT` |
| MLflow | `MLFLOW_TRACKING_URI`, `MLFLOW_ARTIFACT_DESTINATION` |
| Ports | `APP_BIND_HOST`, `AIRFLOW_BIND_HOST` |
| Feast | `FOEHNCAST_FEAST_SOURCE`, `FOEHNCAST_FEAST_REPO_PATH` |
| Cloud credentials | `AWS_ACCESS_KEY_ID`, `GCP_PROJECT_ID` |

## What Stays Out of `config.yaml`

- GCP project IDs, bucket names, service URLs
- Credentials and key files
- Port bindings and host addresses
- GitHub OIDC configuration
- Terraform state details

These describe **where** the system runs, not **what** it does.

## How Resolution Works

`src/foehncast/config.py` loads the YAML once, then resolves runtime values from env vars:

- `FOEHNCAST_CONFIG_PATH` can point to a different YAML
- Storage settings: env vars override YAML defaults
- MLflow URI: always from env
- Config is cached — runtime resolution doesn't mutate it

## Storage Backends

| Backend | Local | Cloud |
|---------|-------|-------|
| `s3` | MinIO parquet | — |
| `bigquery` | — | BigQuery tables |

The app reads `STORAGE_BACKEND` and picks the right client. Same code, different data plane.

## Related Pages

- [Architecture](architecture.md) — how config flows through the system
- [Local Evaluator](local-evaluator.md) — where `.env` gets set
- [Cloud Mapping](cloud-mapping.md) — cloud-specific wiring
