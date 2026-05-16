# Composer DAG Validation

How to validate FoehnCast DAGs in a Cloud Composer environment.

## Prerequisites

- Terraform has provisioned the Composer environment (`provision_cloud_composer_environment = true`)
- `gcloud` is authenticated with a principal that has Composer access
- The Composer environment is healthy and the Airflow web UI is reachable

## 1. Build and Upload DAGs

```bash
# Resolve the Composer DAG bucket from Terraform outputs
DAG_GCS_PREFIX="$(cd terraform && terraform output -raw cloud_composer_dag_gcs_prefix)"

# Build and publish the DAG bundle
./scripts/publish-composer-dags.sh --dag-gcs-prefix "$DAG_GCS_PREFIX"
```

This builds the Composer bundle (DAG files, `foehncast/` source, `config.yaml`,
`pyproject.toml`, `feature_repo/`) and syncs it to the Composer DAG bucket via
`gcloud storage rsync`.

## 2. Verify DAG Import

After upload, check the Airflow web UI or CLI for import errors:

```bash
COMPOSER_ENV="$(cd terraform && terraform output -raw cloud_composer_environment_name)"
REGION="$(cd terraform && terraform output -raw region)"

gcloud composer environments run "$COMPOSER_ENV" \
  --location "$REGION" \
  dags list
```

Expected DAGs:

| DAG ID | Schedule | Description |
|--------|----------|-------------|
| `feature_pipeline` | `0 */6 * * *` | Ingest, engineer, validate, store features; trigger retraining |
| `training_pipeline` | Asset-triggered | Train, evaluate, register model |
| `runtime_release` | Manual | Record runtime release handoff |

## 3. Trigger Feature Pipeline DAG

```bash
gcloud composer environments run "$COMPOSER_ENV" \
  --location "$REGION" \
  dags trigger -- feature_pipeline
```

Monitor the run in the Airflow UI or via:

```bash
gcloud composer environments run "$COMPOSER_ENV" \
  --location "$REGION" \
  dags list-runs -- -d feature_pipeline
```

## 4. Verify Connectivity

The feature pipeline DAG exercises these connections:

| Service | Verification |
|---------|-------------|
| BigQuery | Feature store read/write in `store_features` task |
| GCS | Artifact storage via MLflow or direct GCS writes |
| Datastore | Feast online store materialization |

Check task logs in the Airflow UI for connection errors. Common issues:

- **Missing PyPI packages**: Composer environment must have the packages listed
  in `terraform/main.tf` under `cloud_composer_env_config.software_config.pypi_packages`
- **IAM permissions**: The Composer SA (`foehncast-composer`) needs BigQuery,
  GCS, and Datastore access
- **Network connectivity**: Composer uses a private network; ensure VPC peering
  or firewall rules allow access to required services

## 5. Document Issues

If any tasks fail, file follow-up issues with:

- The failing task ID and error message
- Whether the failure is a packaging issue (missing module/config) or a
  connectivity issue (IAM/network)
- The Composer environment version and Airflow image version
