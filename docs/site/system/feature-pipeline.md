# Feature Pipeline

FoehnCast treats the feature pipeline as a contract, not just a sequence of helper calls. Forecast data is ingested, transformed into curated features, validated against explicit bounds, stored through a backend abstraction, and then reshaped for optional Feast use without changing the meaning of the feature set.

This page captures the stable design that has been validated in the local stack and in the stepwise review workflow. It focuses on what each stage is responsible for, what data boundary it owns, and what should remain outside its scope.

!!! note "What this page does and does not claim"

    This page describes the validated feature-path contract.
    It does not claim that every future feature is already final.
    The current design is stable enough for local operation, Airflow orchestration, and public documentation, while still leaving room for future feature additions and cloud refinements.

## Pipeline Shape

<div class="mermaid">
flowchart LR
    CFG[Spot and storage config] --> ING[Ingest raw forecast rows]
    ING --> ENG[Engineer curated features]
    ENG --> VAL[Validate schema and ranges]
    VAL --> STO[Store curated rows]
    STO --> OFF[Build Feast offline frame]
    OFF --> EXP[Export Feast-ready parquet]
</div>

The important design choice is that each stage has one clear job:

- ingest proves the upstream weather contract
- engineering creates the curated feature frame
- validation rejects structurally broken outputs
- storage preserves the curated contract without mutating it
- Feast preparation consumes curated rows instead of reimplementing the feature pipeline

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

The ingest stage uses the live forecast helper rather than a notebook-only mock. That matters because the first contract to defend is upstream shape and timestamp behavior.

The validated ingest assumptions are:

- expected forecast columns are checked explicitly
- missing and unexpected columns are surfaced rather than ignored
- timestamp ordering and duplicate timestamps are inspected
- timezone semantics are made explicit before later storage and Feast hand-offs
- the upstream wind-unit contract is explicit: Open-Meteo is requested with `wind_speed_unit=kmh`, the returned `hourly_units` map is validated at ingest, and the persisted pipeline summary records those units for later review

For this project, raw weather features stay in source weather units, which currently means km/h for wind speed and gusts. That is separate from domain-facing rideability thresholds, which remain configured in knots and are converted at scoring time instead of changing the stored feature contract.

If the project grows a more formal landing layer, ingest should still preserve the upstream payload faithfully instead of mixing raw capture with curated enrichment.

## Curated Feature Boundary

The engineering layer creates the project's curated feature frame. The current feature set already reflects several design choices that should remain stable:

- cyclical time variables are encoded with sine and cosine instead of plain integers
- shoreline fit is represented with circular math through `shore_alignment`
- gustiness and steadiness are engineered as operational wind-quality signals
- raw columns remain available alongside engineered columns so downstream validation and storage operate on one complete curated frame
- the datetime index and time basis are preserved so later storage and Feast preparation can add persistence and serving context without redefining the feature set

The current training path is tree-based, so the design priority is feature representation quality rather than blanket feature scaling. The most important future refinement area is circular wind-direction representation and gustiness robustness, not a generic normalization layer.

The engineering stage should also stay narrow. It creates the curated feature frame, but it should not add serving metadata or turn into a Feast-specific layer. That downstream hand-off remains intentional: engineer first, then validate, store, and only later project into Feast-friendly shapes.

## Validation Boundary

Validation is structural, not semantic. It is there to stop broken feature frames before they reach storage, training, or Feast preparation.

The current validated contract is:

- required columns cover the actual curated feature frame, not only raw ingest fields
- configured range checks cover the engineered features that later storage and Feast preparation depend on
- cyclical features and `shore_alignment` are bounded where the math makes the valid range explicit
- `gust_factor` and `wind_steadiness` are lower-bounded rather than aggressively clipped
- completeness checks remain important because ratio-based features can go null when sustained wind approaches zero
- validation is the explicit gate before downstream persistence and Feast projection

This layer is not supposed to decide whether a forecast is good for riding. That belongs to the downstream ranking and prediction logic.

## Storage Boundary

Storage works only if it behaves like persistence rather than transformation. A stored feature frame should come back with the same schema, index semantics, and numeric values that validation approved.

<div class="mermaid">
flowchart LR
    FEAT[Curated feature frame] --> WRITE[write_features]
    WRITE --> BACKEND[Local, S3-compatible, or BigQuery backend]
    BACKEND --> READ[read_features]
    READ --> ROUND[Round-trip checks]
</div>

The current storage contract is:

- local, S3-compatible, and BigQuery backends may use different write-time metadata internally
- rerunning one logical spot-and-dataset write must replace that slice instead of accumulating cloud-only duplicates
- downstream reads must restore the same curated feature frame shape
- backend-specific columns must not leak into consumers after read-back
- round-trip checks should show matching row counts, matching columns, matching index behavior, and no numeric drift
- the stored frame should preserve the time basis needed for later Feast projection after read-back
- storage should operate on validation-approved curated rows, not compensate for upstream quality failures

This is why raw landing, curated storage, and Feast should remain separate responsibilities rather than one blurred storage layer.

## Storage Layering

| Data role | Local baseline | Cloud direction |
|----------|----------------|-----------------|
| Raw landing | files if retained at all | GCS |
| Curated features | parquet | native BigQuery tables |
| Feast offline source | exported parquet | BigQuery table or view over curated rows |
| Feast registry and staging | local files | GCS |
| Feast online store | SQLite | Datastore |

The local default stays intentionally simple. S3-compatible object storage remains optional for explicit compatibility testing, not the primary developer path.

## Storage Control Surface

The storage split is not only conceptual. The repository exposes it through explicit runtime and infrastructure surfaces so the local path and the cloud target stay aligned.

| Surface | Current implementation | Why it matters |
|------|------------------------|----------------|
| Backend selection | `storage.backend` in `config.yaml` | keeps the active persistence mode explicit instead of hard-coding one storage path |
| Curated local store | `LocalFeatureStoreBackend` writing `data/<dataset>/<spot>.parquet` | keeps the local baseline inspectable and low-friction |
| Optional object-store path | `S3FeatureStoreBackend` | supports compatibility testing without becoming the default architecture |
| Curated cloud store | `BigQueryFeatureStoreBackend` writing the configured project, dataset, and table | matches the cloud analytical target and preserves rerun-safe slice replacement |
| Feast offline local source | `export_offline_store(...)` writing `data/feast/<dataset>.parquet` | keeps Feast downstream from curated persistence |
| Feast cloud source | BigQuery table or view referenced by the cloud Feast config | avoids duplicating feature logic in a separate serving path |
| Feast registry and staging | local `registry.db` in development, GCS in the cloud path | keeps registry metadata separate from the curated dataset |
| Terraform baseline | Terraform-managed GCS plus BigQuery baseline | wires the cloud storage surfaces without changing the feature contract itself |

Terraform is part of the storage boundary because it provisions the cloud-side GCS and BigQuery surfaces that the feature pipeline expects. It should supply the bucket, dataset, and table baseline while leaving ingest, engineering, validation, storage, and Feast preparation responsible for their own stage contracts.

## Feast Boundary

Feast is downstream from the curated feature store. It should consume curated rows, not reach back into raw ingestion or recompute engineering logic.

<div class="mermaid">
flowchart LR
    STORED[Stored curated rows] --> OFF[build_offline_store_frame]
    STORED --> ENT[build_entity_rows]
    OFF --> HIST[Historical retrieval inputs]
    ENT --> HIST
    HIST --> EXP[export_offline_store]
</div>

That means:

- `build_offline_store_frame(...)` and `build_entity_rows(...)` stay thin projections over stored curated data
- `export_offline_store(...)` is a deterministic materialization step, not a second feature-engineering stage
- the local preparation script is an operator wrapper around those helpers, not the real source of truth for the feature contract
- local Feast stays lightweight with exported parquet plus SQLite, while the cloud direction stays aligned with curated BigQuery plus Datastore and GCS support

This keeps the same conceptual split available in both local and cloud directions: curated features first, Feast second.

## Why This Holds Up

- it keeps pipeline boundaries explicit enough for Airflow orchestration
- it keeps local-first development simple without blocking a BigQuery-backed cloud path
- it prevents Feast from becoming a surrogate landing layer or feature store owner
- it gives README and site documentation stable sections that can be explained without embedding run-specific notebook output

See [Architecture](architecture.md) for the broader system view and [Cloud Mapping](cloud-mapping.md) for the GCP direction.
