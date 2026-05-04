# Feast Repo

This optional Feast repo sits on top of the curated features that FoehnCast already writes.

## Local path

1. Sync the optional dependency group:
   `uv sync --group feast`
2. Export the current stored features into a single Feast parquet source and apply the repo:
   `./scripts/prepare-feast-local.sh`
3. Materialize the latest values into the local SQLite online store:
   `cd feature_repo && uv run --group feast feast materialize-incremental "$(date -u +"%Y-%m-%dT%H:%M:%S")"`
4. Read features back through the application-side helper:
   `uv run --group feast python -c "from foehncast.inference_pipeline.online_features import get_online_spot_features; print(get_online_spot_features(['silvaplana'], ['wind_speed_10m', 'gust_factor']))"`
5. Or use the optional API endpoint if the app is already running:
   `curl -fsS -X POST http://127.0.0.1:8000/features/online -H 'content-type: application/json' -d '{"spot_ids":["silvaplana"],"feature_names":["wind_speed_10m","gust_factor"]}'`
6. Or open the built-in demo page in the running app:
   `http://127.0.0.1:8000/features/online/demo`

The local repo keeps using the default local stack. It does not replace the existing feature pipeline or the local bootstrap path.
The online read should return a dictionary with `rows`, `returned_features`, and the requested spot values when materialization has already run.

## Cloud path

1. Start from `feature_store.gcp.yaml.example` and adapt the bucket, project, and staging paths.
2. Set `FOEHNCAST_FEAST_SOURCE=bigquery`.
3. Set `FOEHNCAST_FEAST_BIGQUERY_TABLE` to a BigQuery table or view that exposes curated rows with `spot_id`, `forecast_time`, and the same curated feature columns defined in `features.py`.

The simplest cloud hand-off from the current storage layer is a BigQuery view that filters the curated feature table to the split or dataset you want Feast to read.
