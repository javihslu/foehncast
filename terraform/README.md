# Terraform Baseline

This directory covers two cloud paths:

- a shared GCP baseline for datasets, registries, identities, and optional Cloud Run inference
- an optional single online Docker host that runs the full Airflow, MLflow, and API stack from the same repo

## Current Scope

Terraform can provision:

- required Google APIs
- Artifact Registry for app images used by the Cloud Run path
- a GCS bucket for shared artifacts
- a BigQuery dataset and feature table
- GitHub OIDC trust and deploy identities
- an optional Cloud Run inference service
- an optional Compute Engine host for the full online container stack

The Cloud Run service remains inference-only. The full online stack is the compose-host path.

## Cloud Run Inputs

When `provision_cloud_run_service = true`, provide:

- a published app image in Artifact Registry
- `mlflow_tracking_uri` pointing to a reachable MLflow service
- any extra runtime configuration in `cloud_run_env_vars`

Terraform already injects the default BigQuery storage environment for the Cloud Run service using the managed dataset and table IDs. Cloud Run should rely on its runtime service account for auth, not on mounted key files.

## Online Compose Host Inputs

When `provision_online_compose_host = true`, provide:

- optional image overrides if you do not want the default GHCR `:main` tags
- any extra stack environment in `online_compose_env_vars`

Terraform provisions a dedicated network, static public IP, and Compute Engine instance. The instance clones the repo, writes a runtime `.env` file with the Terraform-managed GCP and BigQuery settings, tries to pull the GHCR images, and falls back to local Docker builds on the host if the packages are not available yet.

On first boot, the host generates an Airflow admin password locally and stores it at `/opt/foehncast/airflow/.admin-password`. Retrieve it over SSH when you need to sign in instead of passing it through Terraform input variables.

The online host starts:

- FastAPI on port `8000`
- Airflow on port `8080` only if you explicitly expose it
- MLflow on port `5001` only if you explicitly expose it

By default, `online_compose_public_ports = [8000]`, so only the app is internet-reachable. If you want public admin UIs, add `8080` or `5001` deliberately.

The compose-host path is the simplest way to keep the whole course stack online without forcing Airflow into Cloud Run.

## Teardown

For disposable test environments created from the local bootstrap path, use:

`./scripts/teardown-gcp.sh --plan-only`

Review the destroy preview, then rerun `./scripts/teardown-gcp.sh` without `--plan-only` when you are ready. If the current working copy has no local Terraform state from the bootstrap path, the helper skips the Terraform destroy path but can still run explicit cleanup flags. Otherwise it authenticates with `gcloud`, runs `terraform destroy` against your local `terraform/terraform.tfvars`, and can optionally clean auxiliary deployment state:

- `--clear-github-actions` removes the synced GitHub Actions repository variables from your fork or target repo
- `--delete-state-bucket` deletes `${project_id}-foehncast-tfstate` if you also want to remove the extra bucket created for the remote workflow path
- `--delete-project` queues the bootstrap-created GCP project itself for deletion after the Terraform-managed resources are gone; use this only for disposable smoke environments. The script prompts for the exact project id unless you also pass `--auto-approve`.

This teardown utility is intended for the local bootstrap-and-test path. It destroys Terraform-managed resources from the local state in your working copy.

## GitHub Delivery Inputs

The repository uses two delivery workflows:

- `.github/workflows/publish-runtime-images.yml` publishes the runtime images to GHCR
- `.github/workflows/publish-app-image.yml` keeps the optional Artifact Registry plus Cloud Run path for the inference service

Set these GitHub repository variables:

- `GCP_PROJECT_ID`
- `GCP_LOCATION`
- `GCP_ARTIFACT_REPOSITORY`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT_EMAIL`
- `GCP_TERRAFORM_STATE_BUCKET`
- `GCP_TERRAFORM_STATE_PREFIX`
- `GCP_CLOUD_RUN_SERVICE` to enable automatic deploys after publish

The easiest way to set them is:

1. authenticate `gh` with `gh auth login`
2. apply Terraform
3. run `./scripts/configure-github-actions.sh`

The helper script reads the Terraform outputs, sets the required GitHub Actions variables on the repository remote, and leaves `GCP_CLOUD_RUN_SERVICE` unset until the Cloud Run service has actually been provisioned. It also writes the Terraform state bucket defaults used by the GitHub Actions Terraform workflow.

Recommended mappings from Terraform-managed values:

- `GCP_WORKLOAD_IDENTITY_PROVIDER` = `terraform output -raw github_workload_identity_provider`
- `GCP_SERVICE_ACCOUNT_EMAIL` = `terraform output -raw github_deployer_service_account`
- `GCP_ARTIFACT_REPOSITORY` = your `artifact_registry_repository_id` input, for example `foehncast-docker`
- `GCP_TERRAFORM_STATE_BUCKET` = `${project_id}-foehncast-tfstate`
- `GCP_TERRAFORM_STATE_PREFIX` = `terraform/state`
- `GCP_CLOUD_RUN_SERVICE` = `terraform output -raw cloud_run_service_name`

When `GCP_CLOUD_RUN_SERVICE` is set and the service already exists, the workflow publishes an immutable `sha-<commit>` image tag and then updates the existing Cloud Run service to that image. Terraform remains the source of truth for the service baseline such as service account, scaling, ingress, and environment variables.

## GitHub Actions Terraform Path

Use `.github/workflows/terraform.yml` to run validate, plan, or apply from GitHub Actions without requiring local Terraform. The manual workflow bootstraps the GCS backend bucket if needed, runs Terraform against that backend, and can sync the GitHub repository variables after a successful apply.

Authentication options:

- remote workflow path: GitHub OIDC variables already exist from a previous apply
- initial bootstrap path: run `./scripts/bootstrap-gcp.sh` locally, then `./scripts/configure-github-actions.sh` before using the remote workflow

Remote Terraform is OIDC-only. Missing repository variables should fail fast instead of falling back to a separate secret-based auth path.

## Shared Repo vs Personal Deployments

The upstream repository workflows are intended for the shared project environment. They use repository-scoped variables, package publishing, and cloud identities that belong to that shared environment.

The upstream repository may also publish public GHCR images as convenience artifacts. Those images are meant to reduce setup friction, not to fund or centralize other people's deployments.

The upstream workflows are guarded so jobs run only when both the original actor and the triggering actor are the repository owner.

State-changing upstream jobs should also use protected GitHub environments:

- `terraform-admin` for the remote Terraform workflow
- `cloud-run-production` for Cloud Run updates after image publish

For a personal deployment:

- run `./scripts/bootstrap-gcp.sh` locally, or
- fork the repository and configure the same GitHub Actions variables and secrets in that fork

That keeps billing, package ownership, and cloud credentials aligned with the person or team operating the environment. Compute, storage, and network costs stay with that operator.

## Interactive Setup

Run this on a fresh clone if you want the browser-authenticated local bootstrap:

`./scripts/bootstrap-gcp.sh`

Then do the following in order:

1. Sign in in the browser when `gcloud` opens the login flow.
2. Pick an existing GCP project or type `n` to create a new one.
3. Pick a billing account from the list shown by the script.
4. Confirm or edit the values for region, bucket, Artifact Registry repository, BigQuery dataset, and BigQuery table.
5. Decide whether to provision Cloud Run during setup. If yes, enter the MLflow tracking URI.
6. Decide whether to configure GitHub Actions for your fork. If yes, enter the fork as `owner/repo`.
7. Let Terraform apply complete.

Examples:

- `Project number, project id, or n: n`
- `New GCP project id: foehncast-jane-dev`
- `Billing account number or id [1]: 1`
- `GCP region [europe-west6]:`
- `Cloud Run service name [foehncast-serve]:`

The script writes `.env` and `terraform/terraform.tfvars` during setup.

After Terraform apply, the script refreshes `.env` with the managed project ID, bucket, BigQuery dataset and table, and Cloud Run service name. Authentication itself stays in local `gcloud` application default credentials, while Terraform creates the runtime service accounts for Cloud Run and GitHub delivery.

To restart from scratch:

`rm -f .env terraform/terraform.tfvars && ./scripts/bootstrap-gcp.sh`

If you already know all values and want a rerun without prompts:

`./scripts/bootstrap-gcp.sh --non-interactive`

## Local BigQuery Use

1. Bootstrap your local GCP session:
   `./scripts/gcp-auth.sh`
2. If you want local Docker services to read or write BigQuery, initialize `.env` first with `./scripts/bootstrap-local.sh` if needed, then start them with the GCP override file so ADC is mounted into the containers:
   `docker compose -f docker-compose.yml -f docker-compose.gcp.yml up -d`
3. Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars`.
4. Fill in the project-specific values.
5. Run:
   `cd terraform && terraform init && terraform fmt -check && terraform validate`

This Terraform path is aimed at maintainers who are setting up or changing the cloud platform and at collaborators provisioning their own project with the interactive script.

If the script does not show a billing account, stop and sign in with a Google account that can see one.

Commit `terraform/.terraform.lock.hcl` so provider resolution stays reproducible across local runs and CI.

## CI/CD Guidance

- Prefer GitHub OIDC with `google-github-actions/auth`.
- Do not store service account keys in repository secrets.
- Restrict the OIDC provider to this repository and the `main` branch.
- Grant the deployer service account only the roles needed for build and deploy.
