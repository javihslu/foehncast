# Feast Repo

This Feast repo sits downstream from the curated features that FoehnCast already writes. It does not replace the main feature pipeline or the default contributor path. It is the serving layer bound to that curated contract.

## Path Split

| Path | Who uses it | Main entrypoint | What happens |
|------|-------------|-----------------|--------------|
| Local evaluator | contributor or reviewer | `./scripts/bootstrap-local.sh` | prepares Feast automatically and verifies `/features/online` |
| Manual local Feast prep | contributor troubleshooting the serving layer | `./scripts/prepare-feast-local.sh` | renders the local runtime config, applies the repo, and materializes the emulator-backed online store |
| Shared cloud path | maintainer | `./scripts/prepare-feast-cloud.sh` after remote apply | applies the same Feast contract to curated BigQuery rows and the hosted Datastore online store |

Use [../docs/site/system/delivery-and-operator-workflow.md](../docs/site/system/delivery-and-operator-workflow.md) for the maintainer workflow split. This README stays focused on the Feast serving layer itself.

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

The normal local path is still `./scripts/bootstrap-local.sh`. Use the manual Feast steps only when you want to inspect or rerun the serving layer yourself.

1. Sync the Feast dependency group for host-side CLI commands if needed:
   `uv sync --group feast`
2. Render the active Feast runtime config, apply the repo, and materialize the local online store:
   `./scripts/prepare-feast-local.sh`
3. Verify through one of these surfaces:

| Surface | Example |
|---------|---------|
| Python helper | `uv run --group feast python -c "from foehncast.inference_pipeline.online_features import get_online_spot_features; print(get_online_spot_features(['silvaplana'], ['wind_speed_10m', 'gust_excess_10m']))"` |
| API route | `curl -fsS -X POST http://127.0.0.1:8000/features/online -H 'content-type: application/json' -d '{"spot_ids":["silvaplana"],"feature_names":["wind_speed_10m","gust_excess_10m"]}'` |
| Demo page | `http://127.0.0.1:8000/features/online/demo` |

The local repo keeps using the default local stack. The app runtime image includes Feast support and the bundled repo path, the generated config under `.state/feast/feature_store.runtime.yaml` binds the local resources to that shared contract, and `./scripts/bootstrap-local.sh` already runs this preparation step for the supported contributor path.

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

This is the maintainer path. Start with [../docs/site/system/delivery-and-operator-workflow.md](../docs/site/system/delivery-and-operator-workflow.md), then use this repo after curated BigQuery rows are available.

The current cloud contract is:

- `FOEHNCAST_FEAST_SOURCE=bigquery`
- `FOEHNCAST_FEAST_BIGQUERY_TABLE` points at a BigQuery table or view with `spot_id`, `forecast_time`, and the curated feature columns defined in `features.py`
- the bootstrap and Terraform-managed hosted runtimes normally populate the project, registry, staging, and Datastore settings for the shared environment
- `./scripts/prepare-feast-cloud.sh` renders the active runtime config, applies the repo, and materializes the hosted online store

The hosted VM and Cloud Run targets are expected to share these bindings:

| Binding | Shared hosted value |
|------|----------------------|
| runtime source | `FOEHNCAST_FEAST_SOURCE=bigquery` |
| rendered config path | `.state/feast/feature_store.runtime.yaml` |
| registry | `gs://<artifact-bucket>/feast/registry.db` |
| staging | `gs://<artifact-bucket>/feast/staging` |
| offline source | curated BigQuery table `<project>.<dataset>.<table>` |
| default curated dataset | `foehncast` unless the environment overrides it |
| online store | Datastore-mode database `feast-online` unless the environment overrides it |

The checked-in `feature_store.gcp.yaml.example` is a reference for that same hosted contract. The running hosted targets do not consume it directly; they consume the rendered runtime config produced from environment.

If another environment needs different defaults, override the Feast-specific BigQuery, registry, staging, or Datastore settings through the corresponding environment variables.

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
