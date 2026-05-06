# Terraform Baseline

This directory defines the shared GCP baseline plus the two hosted deployment paths already described in the public docs.

## Terraform In One View

| Surface | Purpose | Current role |
|---------|---------|--------------|
| Shared GCP baseline | APIs, storage, identities, and registries | common foundation for both hosted paths |
| Online compose host | full Airflow, MLflow, and API stack | simplest way to keep the whole project online |
| Optional Cloud Run path | inference-only FastAPI service | separate hosted surface for the app |
| GitHub OIDC delivery | remote Terraform and image-based deploys | repeatable automation path |

```mermaid
flowchart LR
   TF[Terraform] --> BASE[Shared GCP baseline]
   BASE --> HOST[Online compose host]
   BASE --> RUN[Optional Cloud Run service]
   BASE --> GH[GitHub OIDC delivery]
```

## What This Directory Covers

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

## Which Path To Use

- Use the online compose host when you want Airflow, MLflow, and the API online together.
- Use Cloud Run when you only need the inference API as a hosted service.
- Use the shared GCP baseline when you are provisioning a hosted or BigQuery-backed path. Pure local validation does not need the shared GCP baseline.

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

The host uses a dedicated runtime service account with BigQuery job and dataset edit access, so the Airflow, training, and app containers can rely on Application Default Credentials instead of mounted key files.

On first boot, the host generates an Airflow admin password locally and stores it at `/opt/foehncast/airflow/.admin-password`. Retrieve it over SSH when you need to sign in instead of passing it through Terraform input variables.

The online host starts:

- FastAPI on port `8000`
- Airflow on port `8080` only if you explicitly expose it
- MLflow on port `5001` only if you explicitly expose it

By default, `online_compose_public_ports = [8000]`, so only the app is internet-reachable. If you want public admin UIs, add `8080` or `5001` deliberately.

The compose-host path is the simplest way to keep the whole course stack online without forcing Airflow into Cloud Run.

## What The Hosted Paths Expose

| Path | Public surface by default | Notes |
|------|---------------------------|-------|
| Online compose host | app on port `8000` | Airflow and MLflow stay private unless explicitly exposed |
| Cloud Run | inference API URL | app-only deployment |

## Teardown

For disposable test environments created from the local bootstrap path, use:

`./scripts/teardown-gcp.sh --plan-only`

Review the destroy preview, then rerun `./scripts/teardown-gcp.sh` without `--plan-only` when you are ready. If the current working copy has no local Terraform state from the bootstrap path, the helper skips the Terraform destroy path but can still run explicit cleanup flags. Otherwise it authenticates with `gcloud`, runs `terraform destroy` against your local `terraform/terraform.tfvars`, and can optionally clean auxiliary deployment state:

- `--clear-github-actions` removes the synced GitHub Actions repository variables from your fork or target repo
- `--delete-state-bucket` deletes `${project_id}-foehncast-tfstate` if you also want to remove the extra bucket created for the remote workflow path
- `--delete-project` queues the bootstrap-created GCP project itself for deletion after the Terraform-managed resources are gone; use this only for disposable smoke environments. The script prompts for the exact project id unless you also pass `--auto-approve`.

This teardown utility is intended for the local bootstrap-and-test path. It destroys Terraform-managed resources from the local state in your working copy. A smoother long-term operator path is to run destroy remotely against the same remote state backend that created the environment, so teardown does not depend on a contributor laptop.

For environments managed through the remote backend, use the manual GitHub Actions Terraform workflow with `command=destroy`. The remote path uses the same OIDC-authenticated backend as remote apply and requires `destroy_confirmation` to exactly match the resolved GCP project id before it will continue.

Remote destroy intentionally stops at Terraform-managed resources tracked in the remote backend. After that, use the same workflow with `command=cleanup` for post-destroy cleanup of the Terraform state bucket and the synced GitHub repository variables when you want to retire the environment fully.

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

After that first sync, use `./scripts/terraform-remote.sh` for common remote Terraform plan, apply, destroy, and cleanup commands.

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

Use `.github/workflows/terraform.yml` to run validate, plan, apply, destroy, or cleanup from GitHub Actions without requiring local Terraform. The manual workflow bootstraps the GCS backend bucket if needed for remote plan or apply, runs Terraform against that backend, and can sync the GitHub repository variables after a successful apply.

For the common operator path, trigger that workflow with `./scripts/terraform-remote.sh` instead of opening the Actions UI manually.

Examples:

- `./scripts/terraform-remote.sh plan`
- `./scripts/terraform-remote.sh apply`
- `./scripts/terraform-remote.sh destroy`
- `./scripts/terraform-remote.sh cleanup --cleanup-delete-state-bucket --cleanup-clear-github-actions`

For `command=destroy`, the workflow does not create a missing backend bucket. Instead it fails fast unless the remote state backend already exists, and it requires `destroy_confirmation` to match the resolved GCP project id. That keeps remote teardown explicit and tied to the same state that created the environment.

For `command=cleanup`, the workflow skips Terraform execution entirely. Instead it runs guarded follow-up cleanup actions after a previous destroy. `cleanup_confirmation` must match the resolved GCP project id, and at least one cleanup action must be selected:

- `cleanup_delete_state_bucket=true` deletes the remote Terraform state bucket if it still exists
- `cleanup_clear_github_actions=true` clears the synced GitHub Actions repository variables on the target repository

The recommended remote retirement sequence is:

1. run `command=destroy`
2. verify the destroy result
3. run `command=cleanup` with the specific cleanup flags you want

Authentication options:

- remote workflow path: GitHub OIDC variables already exist from a previous apply
- initial bootstrap path: run `./scripts/bootstrap-gcp.sh` in Google Cloud Shell or another admin shell, then `./scripts/configure-github-actions.sh` before using the remote workflow

Remote Terraform is OIDC-only. Missing repository variables should fail fast instead of falling back to a separate secret-based auth path.

After the first bootstrap has created the workload identity provider, deployer service account, and repository variables, prefer the remote workflow for day-2 plan, apply, destroy, and cleanup work through `./scripts/terraform-remote.sh` or the manual GitHub Actions UI.

## Shared Repo vs Personal Deployments

The upstream repository workflows are intended for the shared project environment. They use repository-scoped variables, package publishing, and cloud identities that belong to that shared environment.

The upstream repository may also publish public GHCR images as convenience artifacts. Those images are meant to reduce setup friction, not to fund or centralize other people's deployments.

The upstream workflows are guarded so jobs run only when both the original actor and the triggering actor are the repository owner.

State-changing upstream jobs should also use protected GitHub environments:

- `terraform-admin` for the remote Terraform workflow
- `cloud-run-production` for Cloud Run updates after image publish

For a personal deployment:

- run `./scripts/bootstrap-gcp.sh` in Google Cloud Shell or another admin shell, or
- fork the repository and configure the same GitHub Actions variables and secrets in that fork

That keeps billing, package ownership, and cloud credentials aligned with the person or team operating the environment. Compute, storage, and network costs stay with that operator.

## Recommended Reading Order

1. Read the root `README.md` for the runtime overview.
2. Use this file when you need the Terraform-specific deployment inputs and teardown steps.
3. Use `docs/site/system/cloud-mapping.md` when you want the higher-level architecture explanation.

## Cloud Operator Bootstrap

Use this only for the initial hosted-environment bootstrap, or when you intentionally need direct admin access to the cloud project.

Preferred environment: Google Cloud Shell. That keeps the admin toolchain off the default evaluator machine and matches the intended operator path.

Run this in Cloud Shell or another admin shell:

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

After Terraform apply, the script refreshes `.env` with the managed project ID, bucket, BigQuery dataset and table, and Cloud Run service name. Authentication itself stays in the active `gcloud` application default credentials for the admin shell you used, while Terraform creates the runtime service accounts for Cloud Run and GitHub delivery.

To restart from scratch:

`rm -f .env terraform/terraform.tfvars && ./scripts/bootstrap-gcp.sh`

If you already know all values and want a rerun without prompts:

`./scripts/bootstrap-gcp.sh --non-interactive`

## Local BigQuery Use

This section is separate from the default local evaluator path and from the Cloud Shell bootstrap path. Use it only when your local Docker services need direct BigQuery access.

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
