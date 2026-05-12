# Repository

The repository keeps runtime code, orchestration, tests, and public documentation separate so the same Feature-Training-Inference split stays visible in both the source tree and the deployment story.

## Current Layout

```text
src/foehncast/
  config.py
  feature_pipeline/
  training_pipeline/
  inference_pipeline/
  monitoring/
  spots/
dags/
scripts/
terraform/
feature_repo/
prometheus_config/
grafana_work/
tests/
docs/
```

## Where To Start

- `src/foehncast/`: the application modules for configuration, feature engineering, training, inference, monitoring, and spot metadata.
- `dags/`: Airflow entry points for the feature and training workflows.
- `scripts/`: local bootstrap, cloud bootstrap, remote Terraform, and helper scripts.
- `terraform/`: hosted infrastructure definition plus operator-facing notes.
- `feature_repo/`: the Feast integration repo and configuration surface.
- `prometheus_config/` and `grafana_work/`: the checked-in monitoring stack configuration for Prometheus and Grafana.
- `tests/`: regression coverage for the core pipeline logic and API behavior.
- `docs/`: the public documentation site and system notes.

One local workload data root lives under `data/`, while local runtime state stays separate. For example, curated feature rows and Feast offline parquet belong under `data/`, but local Feast registry, rendered runtime config, and inference prediction logs belong under `.state/` instead of mixing service state into the workload dataset tree.

Airflow also writes operator-facing artifacts under `airflow/reports/`. That directory now includes the latest feature-pipeline run summary JSON and evaluation markdown outputs, and the local app mounts it so Prometheus and Grafana can expose the latest feature-pipeline monitoring panels.

## Why The Layout Matters

The runtime code lives under one package, while orchestration, operator scripts, infrastructure, tests, and docs stay beside it instead of being mixed into the same folder tree. That makes it easier to explain which parts define the model pipeline, which parts schedule it, which parts provision hosted environments, and which parts document the result.

Central configuration lives in `config.yaml` and `src/foehncast/config.py`, so the feature, training, and inference paths read from the same settings model instead of scattering constants across modules.

Feature engineering starts in `feature_pipeline/engineer.py`, where raw weather inputs are turned into the engineered feature vector shared by training and inference.

There is currently no separate product UI package in the repository. The optional interactive demo surface that does exist lives inside the inference pipeline, for example `src/foehncast/inference_pipeline/demo.py`, rather than in a separate top-level app tree.

## Configuration Ownership

- `config.yaml`: workload defaults and app-facing contracts such as rider, spots, API fields, validation, model settings, the default storage mode, and MLflow naming.
- `.env` and environment variables: runtime-instance wiring such as bind hosts, selected backend, MLflow tracking URI, objectstore identifiers, BigQuery identifiers, and service URIs for a concrete local or hosted environment.
- `terraform/terraform.tfvars`: infrastructure desired state such as regions, buckets, service names, machine shape, and deployment toggles.
- `feature_repo/feature_store*.yaml`: checked-in Feast reference configs that stay separate from the base application config.
- `.state/feast/feature_store.runtime.yaml`: the rendered runtime Feast binding generated from environment and used by the app and host-side Feast CLI commands.
- `.state/monitoring/prediction-log.jsonl`: the local inference monitoring log used to compare current model outputs against earlier outputs from the same model version.
- `airflow/reports/feature-pipeline-*-latest.json`: the persisted feature-pipeline summary files that the local monitoring path republishes through the app `/metrics` endpoint.

The supported curated-storage backends are intentionally narrow: `s3` for the local MinIO-backed baseline and `bigquery` for the hosted analytical surface. The older file-backed curated-store compatibility path is no longer part of the runtime contract.

The same ownership rule now applies to MLflow connection details: the tracked experiment and model names stay in `config.yaml`, while the tracking URI is runtime wiring resolved from environment.

## Local Data And State Boundary

- `data/`: workload data such as curated parquet outputs and Feast offline export files.
- `.state/`: local runtime or integration state such as Feast registry, rendered runtime configuration, and the local prediction-monitoring log.

This matters because local development should still be inspectable, but the repo should not treat runtime state as if it were part of the workload dataset contract.

This split matters because the package should not own deployment metadata it does not consume. Runtime and infrastructure layers can render values into the environment, while the workload code keeps a smaller and clearer configuration surface.
