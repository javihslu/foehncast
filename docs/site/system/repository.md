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
ui/
tests/
docs/
```

## Where To Start

- `src/foehncast/`: the application modules for configuration, feature engineering, training, inference, monitoring, and spot metadata.
- `dags/`: Airflow entry points for the feature and training workflows.
- `scripts/`: local bootstrap, cloud bootstrap, remote Terraform, and helper scripts.
- `terraform/`: hosted infrastructure definition plus operator-facing notes.
- `feature_repo/`: the optional Feast configuration and export surface.
- `ui/`: the Streamlit demo surface.
- `tests/`: regression coverage for the core pipeline logic and API behavior.
- `docs/`: the public documentation site, milestone pages, and system notes used in the course handoff.

## Why The Layout Matters

The runtime code lives under one package, while orchestration, operator scripts, infrastructure, tests, and docs stay beside it instead of being mixed into the same folder tree. That makes it easier to explain which parts define the model pipeline, which parts schedule it, which parts provision hosted environments, and which parts document the result.

Central configuration lives in `config.yaml` and `src/foehncast/config.py`, so the feature, training, and inference paths read from the same settings model instead of scattering constants across modules.

Feature engineering starts in `feature_pipeline/engineer.py`, where raw weather inputs are turned into the engineered feature vector shared by training and inference.
