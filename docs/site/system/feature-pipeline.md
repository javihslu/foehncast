# Feature Pipeline

FoehnCast keeps the feature pipeline as a clear set of boundaries. The same curated feature contract drives the local evaluator and the hosted paths: forecast data is ingested, turned into curated features, checked against explicit bounds, stored through a backend abstraction, and then reshaped for Feast serving without changing the meaning of the feature set.

This page describes the validated feature contract. It focuses on what each stage owns and what stays outside its scope.

!!! note "Scope"

    This page describes the validated feature-path contract.
    It is not a roadmap.
    Future changes belong here only after the contract changes.

## Pipeline Shape

<div class="mermaid">
flowchart TD
    subgraph Input ["Inputs"]
        direction TB
        CFG["Spot and storage config"]
        ING["Ingest raw forecast rows"]
        CFG --> ING
    end

    subgraph Curated ["Curated path"]
        direction TB
        ENG["Engineer curated features"]
        VAL["Validate schema and ranges"]
        STO["Store curated rows"]
        ENG --> VAL --> STO
    end

    subgraph Handoff ["Handoff"]
        direction TB
        OFF["Build Feast offline frame"]
        EXP["Export Feast-ready parquet"]
        FEAST["Publish Feast-sync asset"]
        REQ["Publish training-request asset"]
        OFF --> EXP --> FEAST --> REQ
    end

    ING --> ENG
    STO --> OFF
</div>

Each stage has one clear job:

- ingest proves the upstream weather contract
- engineering creates the curated feature frame
- validation rejects structurally broken outputs
- storage preserves the curated contract without mutating it
- Feast preparation consumes curated rows instead of reimplementing the feature pipeline
- Airflow publishes the downstream asset hand-offs after persistence and Feast preparation succeed

## Runtime Role

| Runtime mode | What the feature path does |
|------|-----------------------------|
| Local evaluator | Airflow writes curated rows to the local storage baseline and prepares Feast downstream |
| Active shared environment | the same DAG and curated contract write to BigQuery and keep Feast downstream through the hosted storage surfaces |
| Hosted inference target | consumes the curated layer through the app and Feast; it does not run the feature DAG itself |

## DVC Mapping

For reproducible local and CI runs, DVC collapses the offline feature path into one `curate` stage.

| DVC stage | Covers | Stops at |
|------|--------|----------|
| `curate` | ingest, engineer, validate, and local curated-data materialization | `data/<dataset>/` parquet outputs |

That means DVC proves the curated-data hand-off, not the full runtime orchestration. Airflow still owns the Feast-sync and training-request assets used in the running stack.

## Notebook Review Surface

The repo keeps one runtime-aware notebook review surface at `notebooks/feat_01_ingest_validation.ipynb`. The notebook runs the same feature-pipeline steps in either lane, writes a backend-tagged summary to `.state/notebook_reviews/feature_pipeline_summary_<backend>.json`, and can compare the stable output fields in place when the other backend artifact already exists.

Outside the notebook, the same parity check is available as a normal repo command:

```bash
make notebook-review-compare NOTEBOOK_REVIEW_BACKEND=s3
```

That command compares the stable review fields across the S3 and BigQuery summaries and leaves the expected runtime-specific differences, such as backend name and storage target, out of the pass or fail decision.

## Stage Responsibilities

| Stage | Main responsibility | Must not become |
|------|----------------------|-----------------|
| Ingest | fetch forecast rows and make source assumptions explicit | hidden enrichment or silent schema rewriting |
| Engineering | turn raw rows into stable, curated features | a place where storage or training concerns leak in |
| Validation | stop missing columns, null-heavy outputs, and impossible numeric ranges | a semantic quality model |
| Storage | persist and restore curated rows faithfully | a second feature-engineering stage |
| Feast preparation | project curated rows into offline and entity frames | a replacement for the base feature store |
| Export | materialize a stable artifact for local Feast workflows | another place where feature semantics can drift |

## Ingest Boundary

The ingest stage uses the live forecast helper rather than a notebook-only mock. The first contract to defend is upstream shape and timestamp behavior.

The validated ingest assumptions are:

- expected forecast columns are checked explicitly
- missing and unexpected columns are surfaced rather than ignored
- timestamp ordering and duplicate timestamps are inspected
- timezone semantics are made explicit before later storage and Feast hand-offs
- the upstream wind-unit contract is explicit: Open-Meteo is requested with `wind_speed_unit=kmh`, the returned `hourly_units` map is validated at ingest, and the persisted pipeline summary records those units for later review

For this project, raw weather features stay in source weather units, which means km/h for wind speed and gusts. That is separate from domain-facing rideability thresholds, which remain configured in knots and are converted at scoring time instead of changing the stored feature contract.

Ingest keeps the upstream payload boundary explicit instead of mixing raw capture with curated enrichment.

## Curated Feature Boundary

The engineering layer creates the project's curated feature frame. The feature set already reflects several design choices that should stay stable:

- cyclical time variables are encoded with sine and cosine instead of plain integers
- shoreline fit is represented with circular math through `shore_alignment`
- gustiness is carried as both a stable absolute surplus (`gust_excess_10m`) for the model and a ratio (`gust_factor`) retained for label semantics
- steadiness remains an operational wind-quality signal through `wind_steadiness`
- raw columns remain available alongside engineered columns so downstream validation and storage operate on one complete curated frame
- the datetime index and time basis are preserved so later storage and Feast preparation can add persistence and serving context without redefining the feature set

The supported training path is tree-based, so feature representation quality matters more than blanket scaling. Circular wind-direction encoding and the shift toward `gust_excess_10m` follow that same choice. The engineering stage stays narrow: create curated rows first, then let validation, storage, and Feast-specific projection happen downstream.

## Validation Boundary

Validation is structural, not semantic. It is there to stop broken feature frames before they reach storage, training, or Feast preparation.

The validation contract is:

- required columns cover the actual curated feature frame, not only raw ingest fields
- configured range checks cover the engineered features that later storage and Feast preparation depend on
- cyclical features and `shore_alignment` are bounded where the math makes the valid range explicit
- `gust_excess_10m`, `gust_factor`, and `wind_steadiness` are lower-bounded rather than aggressively clipped
- completeness checks remain important because ratio-based features can go null when sustained wind approaches zero
- validation is the explicit gate before downstream persistence and Feast projection

This layer does not decide whether a forecast is good for riding. That belongs to the downstream ranking and prediction logic.

## Storage Boundary

Storage works only if it behaves like persistence rather than transformation. A stored feature frame should come back with the same schema, index semantics, and numeric values that validation approved.

<div class="mermaid">
flowchart TD
    FEAT["Curated feature frame"] --> WRITE["write_features"]
    WRITE --> BACKEND["Local, S3-compatible, or BigQuery backend"]
    BACKEND --> READ["read_features"]
    READ --> ROUND["Round-trip checks"]
</div>

The storage contract is:

- local, S3-compatible, and BigQuery backends may use different write-time metadata internally
- rerunning one logical spot-and-dataset write must replace that slice instead of accumulating cloud-only duplicates
- downstream reads must restore the same curated feature frame shape
- backend-specific columns must not leak into consumers after read-back
- round-trip checks should show matching row counts, matching columns, matching index behavior, and no numeric drift
- the stored frame should preserve the time basis needed for later Feast projection after read-back
- storage should operate on validation-approved curated rows, not compensate for upstream quality failures

That is why raw landing, curated storage, and Feast should remain separate responsibilities rather than one blurred storage layer.

## Storage Layering

| Data role | Local baseline | Cloud direction |
|----------|----------------|-----------------|
| Raw landing | files if retained at all | GCS |
| Curated features | MinIO-backed parquet objects | native BigQuery tables |
| Feast offline source | exported parquet | BigQuery table or view over curated rows |
| Feast registry and staging | local files | GCS |
| Feast online store | Datastore-mode emulator | Datastore |

The local operator path mirrors the cloud storage roles closely: MinIO-backed object storage for curated objects and MLflow artifacts, exported parquet for the local Feast offline source, and a Datastore-mode emulator for the local Feast online store. Curated persistence stays separate from Feast serving, and both stay separate from registry metadata.

## Storage Control Surface

The storage split is not only conceptual. The repository exposes it through explicit runtime and infrastructure surfaces so the local path and the cloud target stay aligned.

| Surface | Role |
|------|------|
| Backend selection | `storage.backend` keeps curated persistence explicit with `s3` or `bigquery` |
| Curated storage | `S3FeatureStoreBackend` is the local MinIO-backed path; `BigQueryFeatureStoreBackend` is the cloud path |
| Feast offline source | local export writes `data/feast/<dataset>.parquet`; cloud Feast reads a BigQuery table or view |
| Feast runtime state | local `.state/feast/*` files and cloud GCS paths keep Feast metadata separate from curated data |
| Terraform baseline | Terraform provisions GCS, BigQuery, and Datastore surfaces without changing feature semantics |

Terraform is part of the storage boundary because it provisions the cloud-side GCS and BigQuery surfaces that the feature pipeline expects. It should supply the bucket, dataset, and table baseline while leaving ingest, engineering, validation, storage, and Feast preparation responsible for their own stage contracts. The local baseline uses MinIO for blob-style surfaces, but the cloud target still keeps curated features in BigQuery and the Feast online store in Datastore rather than flattening everything behind one object API.

## Feast Boundary

Feast is downstream from the curated feature store. It should consume curated rows, not reach back into raw ingestion or recompute engineering logic.

<div class="mermaid">
flowchart TD
    STORED["Stored curated rows"] --> OFF["build_offline_store_frame"]
    STORED --> ENT["build_entity_rows"]
    OFF --> HIST["Historical retrieval inputs"]
    ENT --> HIST
    HIST --> EXP["export_offline_store"]
</div>

That means:

- `build_offline_store_frame(...)` and `build_entity_rows(...)` stay thin projections over stored curated data
- `export_offline_store(...)` is a deterministic materialization step, not a second feature-engineering stage
- `prepare_feature_store(...)` is the Airflow-owned orchestration step that exports curated rows, renders the runtime config, applies the Feast repo, and materializes the online store without redefining the feature contract
- the local preparation script is an operator wrapper around those helpers, not the real source of truth for the feature contract
- local and cloud Feast bindings stay downstream of curated persistence instead of redefining feature logic

The Airflow-facing part of the contract matters here: the feature DAG emits explicit curated-feature and Feast-sync assets after `prepare_feature_store(...)` succeeds, then optionally publishes the training-request asset that schedules the training DAG. That makes the feature-to-training boundary visible in Airflow instead of hiding it behind a direct trigger.

This keeps the same conceptual split available in both local and cloud directions: curated features first, Feast second.

## Why This Structure Works

- it keeps pipeline boundaries explicit enough for Airflow orchestration
- it keeps local-first development simple without blocking a BigQuery-backed cloud path
- it prevents Feast from becoming a surrogate landing layer or feature store owner
- it gives README and site documentation stable sections that can be explained without embedding run-specific notebook output

See [Architecture](architecture.md) for the broader system view and [Cloud Mapping](cloud-mapping.md) for the GCP direction.
