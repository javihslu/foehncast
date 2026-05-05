# Feast Repo

This optional Feast repo sits on top of the curated features that FoehnCast already writes. It does not replace the main feature pipeline, the local bootstrap path, or the default storage baseline.

## When To Use It

Use this repo when you want to demonstrate or test an online feature lookup path on top of the same curated weather features already produced by the project.

```mermaid
flowchart LR
   Curated[Curated features] --> FeastRepo[Feast repo]
   FeastRepo --> Online[Online feature store]
   Online --> API[Optional /features/online path]
```

## What Lives Here

| File | Role |
|------|------|
| `features.py` | Feast entities, source selection, feature view, and feature service |
| `feature_store.yaml` | default local Feast configuration |
| `feature_store.gcp.yaml.example` | starting point for a BigQuery-backed cloud setup |

## Local Path

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

Local Feast does not require MinIO or a local S3-compatible object store. The offline source is an exported parquet file built from the curated feature rows already written by the main pipeline.

## What The Local Path Assumes

- the main feature pipeline has already produced curated local features
- Feast is only an extra lookup layer on top of those features
- the API routes `/features/online` and `/features/online/demo` are optional extensions, not the main inference path

## Cloud Path

1. Start from `feature_store.gcp.yaml.example` and adapt the bucket, project, and staging paths.
2. Set `FOEHNCAST_FEAST_SOURCE=bigquery`.
3. Set `FOEHNCAST_FEAST_BIGQUERY_TABLE` to a BigQuery table or view that exposes curated rows with `spot_id`, `forecast_time`, and the same curated feature columns defined in `features.py`.

The simplest cloud hand-off from the current storage layer is a BigQuery view that filters the curated feature table to the split or dataset you want Feast to read.

Keep the storage roles separate:

- raw landing belongs in GCS or another object storage layer
- curated analytical features belong in native BigQuery tables
- Feast reads the curated layer, not the raw landing layer
- GCS still matters for Feast registry and staging paths in the cloud config

## Why Feast Stays Optional

- the main project already works without Feast
- the base ranking and prediction flows do not depend on it
- it is most useful when you want to demonstrate or test online feature serving as an extra capability

See the root `README.md` for the main runtime overview and `docs/site/system/cloud-mapping.md` for the hosted storage direction.
