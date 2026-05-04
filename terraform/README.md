# Terraform Baseline

This directory manages the first GCP infrastructure baseline for FoehnCast:

- required Google APIs
- Artifact Registry for container images
- a GCS bucket for artifacts
- a GitHub Actions deployer service account
- a Cloud Run runtime service account
- GitHub OIDC trust via Workload Identity Federation

It is a bootstrap layer, not the full cloud runtime yet.

## Current Scope

Today Terraform prepares the shared cloud foundation that the validated MS2 stack needs before the full cloud cutover:

- container image publishing
- artifact storage
- BigQuery feature-store dataset and curated feature table
- optional Cloud Run inference service definition
- deploy identities
- GitHub to GCP authentication

The Cloud Run service is intentionally gated behind `provision_cloud_run_service` so the baseline can be applied before the release image and MLflow endpoint exist.

## Cloud Run Inputs

When `provision_cloud_run_service = true`, provide:

- a published app image in Artifact Registry
- `mlflow_tracking_uri` pointing to a reachable MLflow service
- any extra runtime configuration in `cloud_run_env_vars`

Terraform already injects the default BigQuery storage environment for the Cloud Run service using the managed dataset and table IDs. Cloud Run should rely on its runtime service account for auth, not on mounted key files.

## GitHub Delivery Inputs

The repository includes `.github/workflows/publish-app-image.yml` for `linux/amd64` app image publishing to Artifact Registry and optional Cloud Run rollout. Set these GitHub repository variables:

- `GCP_PROJECT_ID`
- `GCP_LOCATION`
- `GCP_ARTIFACT_REPOSITORY`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT_EMAIL`
- `GCP_CLOUD_RUN_SERVICE` to enable automatic deploys after publish

Recommended mappings from Terraform-managed values:

- `GCP_WORKLOAD_IDENTITY_PROVIDER` = `terraform output -raw github_workload_identity_provider`
- `GCP_SERVICE_ACCOUNT_EMAIL` = `terraform output -raw github_deployer_service_account`
- `GCP_ARTIFACT_REPOSITORY` = your `artifact_registry_repository_id` input, for example `foehncast-docker`
- `GCP_CLOUD_RUN_SERVICE` = `terraform output -raw cloud_run_service_name`

When `GCP_CLOUD_RUN_SERVICE` is set and the service already exists, the workflow publishes an immutable `sha-<commit>` image tag and then updates the existing Cloud Run service to that image. Terraform remains the source of truth for the service baseline such as service account, scaling, ingress, and environment variables.

## Next Cloud Additions

The intended next resources for the cloud-hosted pipeline are:

- managed Airflow provisioning for feature and training DAGs
- a cloud-hosted MLflow deployment choice
- CI automation for managed Airflow artifact delivery

## Local Use

1. Bootstrap your local GCP session:
   `./scripts/gcp-auth.sh`
2. If you want local Docker services to read or write BigQuery, start them with the GCP override file so ADC is mounted into the containers:
   `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.gcp.yml up -d`
3. Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars`.
4. Fill in the project-specific values.
5. Run:
   `cd terraform && terraform init && terraform fmt -check && terraform validate`

This Terraform path is aimed at maintainers who are setting up or changing the cloud platform. It should not be the default evaluation path for a professor or a new developer who only needs to run the system once.

## Bootstrap Notes

- Terraform manages project services after authentication, but the project still needs a usable GCP project and billing enabled.
- Commit `terraform/.terraform.lock.hcl` so provider resolution stays reproducible across local runs and CI.

## CI/CD Guidance

- Prefer GitHub OIDC with `google-github-actions/auth`.
- Do not store service account keys in repository secrets.
- Restrict the OIDC provider to this repository and the `main` branch.
- Grant the deployer service account only the roles needed for build and deploy.
