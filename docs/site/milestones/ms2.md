# MS2 Backend

<span class="fc-pill fc-pill--done">Completed</span>

MS2 turned the proposal into a working back-end. The local container stack now runs the feature, training, and inference paths, and Airflow can execute the feature and training pipelines end to end.

## Current Backend Status

| Area | State | Notes |
|------|-------|-------|
| `config.py` | done | Loads and caches `config.yaml` |
| `feature_pipeline.ingest` | done | Fetches forecast data for all configured spots |
| `feature_pipeline.engineer` | done | Adds wind-quality and time features |
| `feature_pipeline.validate` | done | Checks required columns and simple range rules |
| `feature_pipeline.store` | done | Writes feature data to local or S3-compatible storage |
| `training_pipeline` | done | Labels data, trains the model, logs metrics, and registers a version in MLflow |
| `inference_pipeline` | done | Serves `/health`, `/spots`, `/predict`, and `/rank` |
| `dags/` | done | Airflow runs the feature DAG and the training DAG |
| Docker stack | done | Airflow, MLflow, MinIO, app, and development container run through Compose |

## What Was Validated

- `airflow dags test feature_pipeline 2024-01-01` completed successfully.
- `airflow dags test training_pipeline 2024-01-01` completed successfully.
- `curl -fsS http://127.0.0.1:8000/health` returned a healthy API response.
- `curl -fsS -X POST http://127.0.0.1:8000/predict ...` returned live predictions from the app container.
- `docker compose --env-file .env.example exec -T development_env uv run pytest` passed with `72 passed`.

## What MS2 Shows

<div class="grid cards" markdown>

- **Feature path**

    Forecast data can be fetched, engineered, validated, and stored through one runnable pipeline.

- **Training path**

    Airflow can train a model, write an evaluation report, and register a new version in MLflow.

- **Inference path**

    A dedicated app container serves prediction and ranking endpoints from the same stack.

- **Reproducibility**

    The back-end can be started and tested from Docker Compose instead of depending on host-only runs.

</div>

## Next Step Toward The Cloud

MS2 proves that the back-end is running locally in containers. The next step is to map the same pipeline split to managed cloud services such as cloud-hosted Airflow, cloud storage, and the later BigQuery-based data path without changing the pipeline boundaries.
