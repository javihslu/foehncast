# Feature Pipeline

The feature pipeline fetches weather forecasts, engineers useful features from them, validates the output, and stores curated rows. Those rows then feed training, Feast, and inference.

## Steps

<div class="mermaid">
flowchart TD
    ING["Ingest forecasts"] --> ENG["Engineer features"]
    ENG --> VAL["Validate"]
    VAL --> STO["Store curated rows"]
    STO --> FEAST["Prepare Feast data"]
    FEAST --> REQ["Publish training-request asset"]
</div>

| Step | What it does |
|------|-------------|
| Ingest | Pulls forecast data from Open-Meteo, checks expected columns |
| Engineer | Creates derived features (cyclical encoding, gust metrics, etc.) |
| Validate | Rejects rows with missing columns, nulls, or out-of-range values |
| Store | Writes curated parquet to MinIO (local) or BigQuery (cloud) |
| Feast prep | Exports data for Feast online serving |

## Feature Engineering

Raw weather values pass through unchanged. On top of them, we add derived columns:

| Feature | Input | Why |
|---------|-------|-----|
| `hour_of_day_sin/cos` | Timestamp | Cyclical time encoding (no break at midnight) |
| `day_of_year_sin/cos` | Timestamp | Season encoding (no break at year-end) |
| `wind_direction_10m_sin/cos` | Wind direction | Circular encoding (no break at 360°→0°) |
| `gust_excess_10m` | Gusts − sustained wind | How much stronger gusts are than steady wind |
| `gust_factor` | Gusts / sustained wind | Ratio for gustiness (used in labeling) |
| `wind_steadiness` | Rolling wind speed CV | Low = steady, high = variable |
| `shore_alignment` | Wind dir + shore orientation | How well wind hits the spot cross-shore |

We use tree-based models, so circular encoding matters more than blanket scaling.

## Time and Seasonality Features

Swiss kite spots behave differently across seasons — summer thermals, winter pressure systems, daylight changes. We handle this with the four cyclical time columns above (`hour_of_day_sin/cos`, `day_of_year_sin/cos`) instead of separate seasonal models. Sin/cos encoding means the model understands that 23:00 is close to 00:00, and December 31 is close to January 1.

The same columns serve all three pipelines: the feature pipeline creates them from forecast timestamps, training includes them in the model feature vector, and inference rebuilds them from live timestamps with the same function.

Why keep it simple:

- No separate summer/winter models
- No wide month-dummy encoding
- No special seasonal architecture
- Just four extra features that give the tree-based model time context

If we ever need more seasonal complexity, it has to prove itself through better model metrics first.

## Validation

Validation catches broken data, not bad forecasts. It's a structural gate:

- All required columns must be present
- Cyclical features must be in [-1, 1]
- `gust_excess_10m` must be ≥ 0
- Completeness checks catch nulls (ratio features go null when wind → 0)

## Storage

<div class="mermaid">
flowchart TD
    FRAME["Curated DataFrame"] --> WRITE["write_features()"]
    WRITE --> BACKEND{"Backend?"}
    BACKEND -->|Local| MINIO["MinIO (S3)"]
    BACKEND -->|Cloud| BQ["BigQuery"]
</div>

The `STORAGE_BACKEND` env var picks `s3` or `bigquery`. Same interface, same output shape.

| Data layer | Local | Cloud |
|-----------|-------|-------|
| Curated features | MinIO parquet | BigQuery table |
| Feast offline source | Exported parquet | BigQuery view |
| Feast online store | Datastore emulator | Firestore |

## DVC Mapping

DVC wraps the offline steps into one `curate` stage:

```yaml
curate:
  cmd: python -m foehncast.dvc_stages curate
  outs: [data/<dataset>/]
```

DVC proves the data is reproducible. Airflow handles scheduling, retries, and the training-request trigger.

## Wind Units

Wind values stay in km/h (as received from Open-Meteo). The `hourly_units` map is validated at ingest and logged in the pipeline summary. Domain thresholds (rideable wind limits) are configured in knots and converted at scoring time.
