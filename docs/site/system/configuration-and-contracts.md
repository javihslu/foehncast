# Configuration and Contracts

FoehnCast keeps workload configuration, runtime wiring, infrastructure inputs, and generated runtime state separate. This page describes that contract so readers do not have to reconstruct it from `config.yaml`, `src/foehncast/config.py`, the repository notes, and the operator docs.

The goal is not to document every environment variable in isolation. The goal is to make the ownership boundary explicit: what the package owns, what the runtime injects, and what infrastructure or operator tooling should keep outside the package config.

!!! note "Scope"

    This page describes the validated configuration boundary.
    It is not a proposal for a future settings system.
    New settings should follow these ownership rules unless the architecture changes first.

## Contract In One View

<div class="mermaid">
flowchart TD
    TF["Terraform and GitHub delivery variables"] --> ENV[".env and environment variables"]
    YAML["config.yaml"] --> PY["src/foehncast/config.py"]
    ENV --> PY
    PY --> APP["App, DAGs, training, inference"]
    APP --> MON[".state and airflow/reports contracts"]
    ENV --> FEASTCFG[".state/feast/feature_store.runtime.yaml"]
    FEASTCFG --> FEAST["Feast runtime"]
</div>

The important rule is that the package owns workload semantics, while runtime and infrastructure layers own deployment-specific wiring.

## Ownership Boundary

| Surface | Owns | Example values | Must not become |
|------|------|------------------|-----------------|
| `config.yaml` | workload defaults and app-facing contracts | rider profile, spot list, API source settings, validation rules, model features, labeling bands, MLflow names, inference weights, monitoring thresholds | a dump of project IDs, service names, bind hosts, or deployment topology |
| `.env` and environment variables | concrete runtime wiring for one local or hosted instance | `STORAGE_BACKEND`, `STORAGE_S3_BUCKET`, `STORAGE_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `STORAGE_BIGQUERY_*`, `MLFLOW_TRACKING_URI`, bind hosts, Feast source selection | the source of truth for rider, spot, or model semantics |
| `terraform/terraform.tfvars` and GitHub delivery variables | infrastructure desired state and hosted rollout inputs | regions, buckets, service names, machine shape, OIDC, remote Terraform state, Cloud Run and hosted-host toggles | the place where model features, ranking weights, or validation rules live |
| `feature_repo/feature_store*.yaml` | checked-in Feast reference configuration | local reference config and cloud example config | a replacement for the base application config |
| `.state/feast/feature_store.runtime.yaml` | rendered runtime Feast binding | active repo path, registry path, online-store binding, offline source target | a hand-maintained checked-in config file |
| `.state/monitoring/*.jsonl` and `airflow/reports/*.json` | retained local monitoring and rendered operator evidence | prediction-event history and latest pipeline summary contracts | app-facing workload configuration |

This split keeps the workload code smaller and clearer. The package does not need to own deployment metadata it only consumes after runtime wiring resolves it.

## What Stays In `config.yaml`

The checked-in YAML owns the stable workload and product contract.

| Section | What it controls |
|------|-------------------------|
| `rider` | baseline rider profile and home location used by ranking |
| `api` | upstream weather and routing source settings |
| `spots` | the fixed spot list and shore metadata |
| `storage` | the curated-storage mode and its supported values, including `s3` and `bigquery` |
| `warehouse` | retained warehouse contracts for curated features and prediction events |
| `validation` | required columns, completeness rules, and accepted numeric ranges |
| `model` | algorithm choice, feature sets, target field, split ratio, and seed |
| `labeling` | the synthetic quality-band rules and danger thresholds |
| `mlflow` | experiment name, model name, and alias naming |
| `inference` | live horizon and ranking weights |
| `monitoring` | drift threshold, evaluation window, and local retention knobs |

This is why the training and inference pages can point back to `config.yaml` for feature lists, ranking weights, and label semantics without treating those values as runtime secrets.

## What Runtime Wiring Resolves

`src/foehncast/config.py` keeps the YAML and the runtime wiring separate instead of mutating one into the other.

The resolution rules are:

- `FOEHNCAST_CONFIG_PATH` can point the loader at a different YAML file when needed
- the loader caches the checked-in YAML, but runtime helpers resolve environment overrides when the caller asks for storage or MLflow settings
- storage wiring resolves from environment first, then from local-safe defaults
- MLflow experiment and model naming stay in YAML, while `MLFLOW_TRACKING_URI` remains runtime wiring
- the resolved storage config also exposes explicit warehouse contracts for curated features and prediction events

The test contract in `tests/test_config.py` already checks the most important behaviors:

- environment overrides apply after the initial YAML load
- runtime resolution does not mutate the cached YAML values
- obsolete YAML runtime wiring is ignored instead of being treated as active config
- default and custom warehouse contracts stay explicit instead of being inferred indirectly

That means the package does not need a second handwritten runtime config file just to switch from local to hosted wiring.

## Runtime Wiring Examples

The checked-in `.env.example` shows the kind of values that belong in runtime wiring.

| Runtime surface | Example values |
|------|------------------|
| Curated storage binding | `STORAGE_BACKEND`, `STORAGE_S3_BUCKET`, `STORAGE_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `STORAGE_BIGQUERY_PROJECT_ID`, `STORAGE_BIGQUERY_DATASET`, `STORAGE_BIGQUERY_TABLE` |
| MLflow connection | `MLFLOW_TRACKING_URI`, `MLFLOW_ARTIFACT_DESTINATION` |
| Local service exposure | `APP_BIND_HOST`, `AIRFLOW_BIND_HOST`, `PROMETHEUS_PORT` |
| Monitoring history path | `FOEHNCAST_PREDICTION_EVENT_LOG_PATH` |
| Feast runtime binding | `FOEHNCAST_FEAST_SOURCE`, `FOEHNCAST_FEAST_REPO_PATH`, `FOEHNCAST_FEAST_CONFIG_PATH`, `FOEHNCAST_FEAST_BIGQUERY_*`, `FOEHNCAST_FEAST_DATASTORE_*` |

These values describe one concrete runtime instance. They should stay overridable because the local evaluator, shared API lane, and hosted operator surfaces do not all bind to the same services.

In the shared hosted path, the operator surfaces stay intentionally smaller than the local evaluator. Their runtime wiring should stay explicit instead of being treated as a permanent deployment shape.

## Cloud Runtime Inventory

The shared cloud path uses four value surfaces plus identity-backed auth. The simple split is this: delivery surfaces carry reviewed hosted identifiers and toggles, runtime surfaces carry concrete per-environment wiring, and identities carry cloud access.

| Source surface | Example values | Owned by | Consumed by | Secret rule |
|------|---------------------------|----------|-------------|-------------|
| checked-in examples and repo defaults | `.env.example` placeholders, `terraform/terraform.tfvars.example`, checked-in operator docs | repository | bootstrap prompts, local operators, reviewers | structural examples only; never live credentials |
| bootstrap outputs in the working tree | `.env`, `terraform/terraform.tfvars`, Terraform outputs echoed by `./scripts/bootstrap-gcp.sh` | maintainer running bootstrap for one environment | local preview applies, bootstrap verification, `scripts/configure-github-actions.sh` | hosted identifiers and toggles only; not a long-term secret store |
| GitHub repository variables | `GCP_PROJECT_ID`, `GCP_LOCATION`, `GCP_ARTIFACT_REPOSITORY`, `GCP_BIGQUERY_*`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT_EMAIL`, Cloud Run sizing and enablement flags | GitHub delivery control plane, normally synced from Terraform outputs | `.github/workflows/terraform.yml`, image-publish workflows, repo-config action | structural delivery contract only; do not store runtime passwords, API tokens, or key files here |
| runtime `.env` and hosted runtime env vars | `MLFLOW_TRACKING_URI`, `AIRFLOW__API_AUTH__JWT_SECRET`, `cloud_run_env_vars` | runtime operator or platform for one running surface | local evaluator, hosted operator lane, shared API lane, Airflow auth checks | concrete runtime wiring; secret-bearing values should stay local-only or move to Secret Manager or another managed secret path |
| identity-backed auth surfaces | GitHub OIDC, Cloud Run service account | repository admin plus GCP IAM | GitHub workflows and hosted runtimes | prefer identities over stored cloud credentials; not a secret distribution path |

This inventory keeps the boundary explicit:

- `config.yaml` keeps workload semantics.
- `terraform/terraform.tfvars` and GitHub repository variables keep structural hosted rollout inputs.
- runtime `.env` and hosted env injections carry concrete per-environment wiring for the local evaluator, the active operator lane, or the shared API lane.
- secret-bearing runtime values should not move into committed examples or repository variables just because they are cloud-facing.

This page inventories where those values live. [Delivery and Operator Workflow](delivery-and-operator-workflow.md) owns the maintainer bootstrap, repository-variable sync, and remote-apply runbook that moves between those surfaces.

## Storage And Warehouse Contract

The storage boundary is intentionally narrow.

The curated-storage contract is:

- `s3` is the local MinIO-backed baseline
- `bigquery` is the hosted analytical baseline
- the older file-backed curated-store compatibility path is no longer part of the runtime contract

The runtime layer also keeps the warehouse contracts explicit instead of burying them in ad hoc SQL or monitoring code:

- curated features default to the `foehncast.forecast_features` table contract with day partitioning on `forecast_time`
- prediction events default to the `foehncast_monitoring.prediction_events` table contract with day partitioning on `prediction_timestamp`; BigQuery-backed hosted runtimes use that warehouse table as the durable prediction-history source
- both contracts keep explicit clustering and retention settings

This matters because retained monitoring facts belong in retained event history and warehouse tables, not in restart-sensitive request counters or implicit table names.

## Feast And Monitoring Runtime State

Two generated state areas are part of the runtime contract even though they are not workload config.

| Generated surface | Why it exists |
|------|----------------|
| `.state/feast/feature_store.runtime.yaml` | binds the running environment to the checked-in Feast repo without forcing operators to hand-edit a second runtime YAML |
| `.state/monitoring/prediction-log.jsonl` | bounded local working set derived from prediction writes for request-side drift checks |
| `.state/monitoring/prediction-events.jsonl` | retained local prediction-event history contract and the durable history source for local S3-backed runtimes |
| `airflow/reports/feature-pipeline-*-latest.json` | persisted pipeline summary that the app republishes through `/metrics` for Prometheus |

These files are runtime artifacts. They are inspectable and useful, but they are not part of the checked-in workload contract and should not be promoted into `config.yaml`.

## What Stays Out Of Package Config

The package config should not absorb deployment topology or operator rollout state.

Keep these outside `config.yaml`:

- concrete GCP project ids, bucket names, Cloud Run service names, and hosted machine shapes
- GitHub OIDC and remote Terraform state configuration
- public-port exposure decisions for hosted admin surfaces
- credentials and key-file paths
- per-environment bind hosts, ports, and service URLs

Those values belong in runtime env, Terraform inputs, or GitHub delivery variables because they describe where the system runs, not what the workload means.

## Why This Split Works

- training and inference can share one workload contract without hard-coding deployment details
- local and hosted runtimes can switch storage and service bindings without forking the package config
- Feast stays downstream from the curated feature contract instead of becoming a shadow settings system
- operator state stays inspectable under `.state/` and `airflow/reports/` without pretending to be workload source data

See [Repository](repository.md), [Feature Pipeline](feature-pipeline.md), [Inference Pipeline](inference-pipeline.md), [Local Evaluator](local-evaluator.md), [Cloud Mapping](cloud-mapping.md), and [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the surrounding runtime and deployment boundaries.
