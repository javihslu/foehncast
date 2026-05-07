# Feast Repo

This Feast repo sits on top of the curated features that FoehnCast already writes. It does not replace the main feature pipeline or the local bootstrap path; it is the serving layer bound to that curated contract.

## When To Use It

Use this repo when you want to operate the Feast serving layer on top of the same curated weather features already produced by the project.

```mermaid
flowchart LR
   Curated[Curated features] --> FeastRepo[Feast repo]
   FeastRepo --> Online[Online feature store]
   Online --> API[/features/online path]
```

## What Lives Here

| File | Role |
|------|------|
| `features.py` | Feast entities, source selection, feature view, and feature service |
| `feature_store.yaml` | checked-in local reference configuration |
| `feature_store.gcp.yaml.example` | checked-in cloud reference configuration |

The runtime contract now renders the active Feast config from environment into `.state/feast/feature_store.runtime.yaml` and points the app and host-side CLI commands at that generated file.

## Local Path

1. Sync the Feast dependency group for host-side CLI commands if needed:
   `uv sync --group feast`
2. Export the current stored features, render the active Feast runtime config, apply the repo, and materialize the local online store:
   `./scripts/prepare-feast-local.sh`
3. Read features back through the application-side helper:
   `uv run --group feast python -c "from foehncast.inference_pipeline.online_features import get_online_spot_features; print(get_online_spot_features(['silvaplana'], ['wind_speed_10m', 'gust_factor']))"`
4. Or use the API endpoint if the app is already running:
   `curl -fsS -X POST http://127.0.0.1:8000/features/online -H 'content-type: application/json' -d '{"spot_ids":["silvaplana"],"feature_names":["wind_speed_10m","gust_factor"]}'`
5. Or open the built-in demo page in the running app:
   `http://127.0.0.1:8000/features/online/demo`

The local repo keeps using the default local stack. It does not replace the existing feature pipeline or the local bootstrap path.
The online read should return a dictionary with `rows`, `returned_features`, and the requested spot values when materialization has already run.
The app runtime image includes Feast support and the bundled repo path; the generated config under `.state/feast/feature_store.runtime.yaml` binds the local resources to that shared contract.
The default `./scripts/bootstrap-local.sh` path runs this preparation step and verifies `/features/online` automatically.

The default local stack uses the bundled MinIO surface for curated feature storage and MLflow artifacts. Feast still reads an exported parquet offline source built from those curated rows, while the registry and runtime config stay under `.state/feast/` and the online store runs through the bundled Datastore-mode emulator.

The local split is intentional:

- workload data stays under `data/feast/*.parquet`
- Feast runtime state stays under `.state/feast/`

That keeps the derived offline source separate from local registry and runtime config state, while the emulator remains disposable between local runs.

## What The Local Path Assumes

- the main feature pipeline has already produced curated features through the local objectstore-backed baseline
- Feast is the required serving layer on top of those curated features
- the API routes `/features/online` and `/features/online/demo` are part of the application surface

## Cloud Path

1. Set `FOEHNCAST_FEAST_SOURCE=bigquery`.
2. Set `GCP_PROJECT_ID` and `GCP_BUCKET_NAME`, or the Feast-specific overrides `FOEHNCAST_FEAST_PROJECT_ID`, `FOEHNCAST_FEAST_REGISTRY`, and `FOEHNCAST_FEAST_GCS_STAGING_LOCATION`.
3. Set `FOEHNCAST_FEAST_BIGQUERY_TABLE` to a BigQuery table or view that exposes curated rows with `spot_id`, `forecast_time`, and the same curated feature columns defined in `features.py`.
4. Optionally set `FOEHNCAST_FEAST_BIGQUERY_DATASET` and `FOEHNCAST_FEAST_BIGQUERY_LOCATION` if the defaults do not fit the target environment.
5. Set `FOEHNCAST_FEAST_DATASTORE_DATABASE` when the hosted environment uses a named Datastore-mode database for Feast online serving.
6. Run `./scripts/prepare-feast-cloud.sh` after curated BigQuery rows are available. It renders the active Feast runtime config, applies the repo, and materializes the Datastore online store.

The cloud bootstrap and Terraform-managed hosted runtimes populate this same Feast env contract automatically. You do not need to keep a separate handwritten cloud YAML in sync for normal operator flows.

The simplest cloud hand-off from the current storage layer is a BigQuery view that filters the curated feature table to the split or dataset you want Feast to read.

Keep the storage roles separate:

- raw landing belongs in GCS or another object storage layer
- curated analytical features belong in native BigQuery tables
- Feast reads the curated layer, not the raw landing layer
- GCS still matters for Feast registry and staging paths in the rendered cloud runtime config

## Why Feast Stays Downstream

- curated feature storage remains the source of truth
- the base feature, training, and ranking logic still depend on curated rows, not on Feast internals
- Feast adds the formal serving and registry layer on top of that curated contract instead of replacing it

See the root `README.md` for the main runtime overview and `docs/site/system/cloud-mapping.md` for the hosted storage direction.
