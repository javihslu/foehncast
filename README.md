# FoehnCast

FoehnCast predicts kiteboarding conditions with a Feature-Training-Inference pipeline. The repo supports three distinct ways of working:

- Local evaluation for a new developer, reviewer, or professor.
- Personal GCP provisioning for a collaborator using their own cloud project.
- Cloud provisioning and deployment for the maintainer of the GCP environment.

## Recommended Paths

### Local quick start

This is the default path for a fresh machine.

1. Install Docker.
2. Clone the repository.
3. Run:
   `./scripts/bootstrap-local.sh`

The script builds the local stack, runs the feature and training DAGs, and waits for the API to become healthy.

After it finishes, the main endpoints are:

- App: `http://127.0.0.1:8000`
- Airflow: `http://127.0.0.1:8080`
- MLflow: `http://127.0.0.1:5001`
- MinIO: `http://127.0.0.1:9001`

Example request:

`curl -fsS -X POST http://127.0.0.1:8000/rank -H 'content-type: application/json' -d '{"spot_ids":["silvaplana","urnersee"]}'`

### Personal GCP quick start

Use this when a collaborator wants a private FoehnCast environment in their own GCP project.

Install:

- Google Cloud CLI (`gcloud`)
- Terraform
- GitHub CLI (`gh`) only if you want GitHub Actions in your own fork to publish and redeploy automatically

Run:

`./scripts/bootstrap-gcp.sh`

What to do in the interactive setup:

1. Sign in in the browser when the script opens `gcloud` login.
2. Pick an existing GCP project from the list, or type `n` to create a new one.
   Example: `Project number, project id, or n: n`
   Example: `New GCP project id: foehncast-jane-dev`
3. Pick a billing account from the list shown by the script.
   Example: `Billing account number or id [1]: 1`
4. Confirm or edit the default values for region, artifact bucket, Artifact Registry repository, BigQuery dataset, and BigQuery table.
   Example: `GCP region [europe-west6]:`
   Example: `Artifact bucket name [foehncast-artifacts-foehncast-jane-dev]:`
5. Choose whether to provision Cloud Run now.
   If you answer `yes`, enter the MLflow tracking URL when asked.
6. Choose whether to configure GitHub Actions for your own fork.
   If you answer `yes`, enter the fork in `owner/repo` format.
   Example: `GitHub repository for deployment automation [jane/foehncast]: jane/foehncast`
7. Wait for Terraform to finish.

The script writes `.env` and `terraform/terraform.tfvars` for you during setup. After Terraform apply, it refreshes `.env` with the project, bucket, BigQuery, and Cloud Run service values from Terraform outputs.

If you want to restart from scratch, run:

`rm -f .env terraform/terraform.tfvars && ./scripts/bootstrap-gcp.sh`

If you already know your values and want automation without prompts, use:

`./scripts/bootstrap-gcp.sh --non-interactive`

Optional fork-based automation:

`./scripts/bootstrap-gcp.sh --configure-github-actions --repo <your-github-user>/foehncast`

Use that only if you want GitHub Actions in your fork to publish images and redeploy into your own project after the initial bootstrap. The script will also align Terraform's GitHub OIDC settings to that fork.

### Shared GCP maintainer path

Use this only when you are provisioning or updating the shared GCP deployment for the main repository.

1. Authenticate locally with `./scripts/gcp-auth.sh`.
2. Configure Terraform inputs in `terraform/terraform.tfvars`.
3. Apply Terraform to provision the cloud baseline.
4. Authenticate the GitHub CLI with `gh auth login`, then run `./scripts/configure-github-actions.sh` to push the required GitHub repository variables from the Terraform outputs. It skips `GCP_CLOUD_RUN_SERVICE` until the Cloud Run service exists.
5. Let GitHub Actions publish the deployable app image and update the existing Cloud Run service on pushes to `main`.

## Deployment stance

A single script that clones the repo, logs into GCP, creates projects, provisions infrastructure, builds images, and deploys everything is possible, but it is not the best default interface for this project.

The better split is:

- Local Docker bootstrap for evaluators and first-time developers.
- Browser-authenticated local bootstrap for collaborators provisioning their own GCP project.
- Terraform for infrastructure inside an existing GCP project with billing already enabled.
- GitHub Actions for CI on the shared repo and for shared or fork-specific deployment automation after bootstrap.
- Airflow for feature and training workflows after the platform exists.

That keeps the evaluation path simple, avoids hiding billing and project-ownership assumptions inside a script, and still leaves GitHub Actions with a clear role.

## Why GitHub Actions Still Matters

GitHub Actions should not be the only bootstrap path for collaborator-owned projects. Repo-level cloud credentials and variables are a poor fit when several people each want their own GCP environment.

GitHub Actions still matters for three reasons:

- CI stays centralized for lint, tests, docs, and image build checks.
- The shared main-branch environment can keep using GitHub Actions for publish and deploy.
- A collaborator who wants repo-driven redeploys can wire GitHub Actions into their own fork after local bootstrap instead of doing that setup up front.

If startup speed becomes an issue later, the next optimization is not to make GitHub mandatory. It is to let GitHub Actions publish a reusable app image that collaborator-owned projects can consume, so the bootstrap path provisions infrastructure quickly without forcing each user to rebuild everything locally.

The least invasive default is therefore: local browser auth plus Terraform for personal environments, GitHub Actions for shared automation and optional fork automation.

## More detail

- Local stack notes: `containers/README.md`
- Cloud mapping: `docs/site/system/cloud-mapping.md`
- Terraform baseline: `terraform/README.md`
