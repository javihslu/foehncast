# Changelog

Notable changes since the MLOPS FS26 course code freeze. The graded state is
tagged `course-freeze`; the post-course release is `v1.1.0`. The rider console
and the media kit are unchanged since `v1.1.0`.

## [v1.2.0] — 2026-07-19

Hardening, reproducibility, and documentation since the post-course release.
Compare: <https://github.com/javihslu/foehncast/compare/v1.1.0...v1.2.0>

### Deployment and reproducibility

- Recreate and tear down the GCP platform cleanly on a fresh project: `terraform destroy` completes, and Cloud Run probes no longer wedge a platform that has no registered model yet (#130).
- Build platform images before the first apply (#106); retry feast apply only on the parquet-visibility race (#105); fail loudly when the repository-variable sync stream breaks (#104).
- Start the object store and the feast online store with the default stack (#109).
- Deterministic training: seed numpy and pin `PYTHONHASHSEED` at the training entry points (#110); refresh `dvc.lock` and the training reports to match shipped code (#116); bump locked packages (#111).

### Serving and pipelines

- Return 503 on an empty feature registry and materialize the full offline range (#126).
- Harden the pipeline run endpoint and workflow run ordering (#125).

### Documentation

- Lead with the local path and document the control-plane environment variables (#119); describe the control-plane abstraction in the repository layout (#124).
- State the backfill upper-air approximation as a model limitation (#123); explain the R2 convention on constant-label training windows (#128).
- Mark the cloud deployment decommissioned (#118); list `feast_online_store` among the built container services (#117).
- Credit the Open-Meteo, MeteoSwiss, and OSRM data sources with their licence terms, add an educational-use disclaimer, and document deploying your own copy (#132).
- Refresh the visual tour with current console and wind-map captures, and read every tour image from the shared capture set (#144, #146).

### Maintenance

- Extend Dependabot to the container base images and the compose stacks (#134).

## [v1.1.0] — 2026-07-17

Post-course release. Everything since the course freeze, squashed into one
reviewable commit.
Compare: <https://github.com/javihslu/foehncast/compare/course-freeze...v1.1.0>

- Rider console: heatmap-first session-quality view with cell selection driving a wind dial and metrics; freshness dials double as run buttons; regional wind map and visual polish.
- Model lifecycle: candidate-first registration, with the champion moved only by operator promotion; shadow scoring of candidate against champion on every inference batch.
- Monitoring: feature-freshness gauge with a stale-data alert; train-versus-forecast dataset drift; capped prediction-health panel.
- Deployment parity: the cloud UI receives the serve URL and control token so local and cloud render identically.
- Docs and material: model card for the served model; media kit page with cover, screenshots, and demo videos.

## [course-freeze] — 2026-07-10

The state submitted for MLOPS FS26 grading.
