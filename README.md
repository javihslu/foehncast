# FoehnCast

FoehnCast predicts kiteboarding conditions with a Feature-Training-Inference pipeline. The repo supports two distinct ways of working:

- Local evaluation for a new developer, reviewer, or professor.
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

### Cloud maintainer path

Use this only when you are provisioning or updating the shared GCP deployment.

1. Authenticate locally with `./scripts/gcp-auth.sh`.
2. Configure Terraform inputs in `terraform/terraform.tfvars`.
3. Apply Terraform to provision the cloud baseline.
4. Authenticate the GitHub CLI with `gh auth login`, then run `./scripts/configure-github-actions.sh` to push the required GitHub repository variables from the Terraform outputs. It skips `GCP_CLOUD_RUN_SERVICE` until the Cloud Run service exists.
5. Let GitHub Actions publish the deployable app image and update the existing Cloud Run service on pushes to `main`.

## Deployment stance

A single script that clones the repo, logs into GCP, provisions infrastructure, builds images, and deploys everything is possible, but it is not the best primary interface for this project.

The better split is:

- Local Docker bootstrap for evaluators and first-time developers.
- Terraform for infrastructure.
- GitHub Actions for build and deployment automation.
- Airflow for feature and training workflows after the platform exists.

That keeps the evaluation path simple and the cloud path reproducible.

## More detail

- Local stack notes: `containers/README.md`
- Cloud mapping: `docs/site/system/cloud-mapping.md`
- Terraform baseline: `terraform/README.md`
