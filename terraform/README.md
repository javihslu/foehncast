# Terraform Baseline

This directory manages the first GCP infrastructure baseline for FoehnCast:

- required Google APIs
- Artifact Registry for container images
- a GCS bucket for artifacts
- a GitHub Actions deployer service account
- a Cloud Run runtime service account
- GitHub OIDC trust via Workload Identity Federation

## Local Use

1. Bootstrap your local GCP session:
   `./scripts/gcp-auth.sh`
2. Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars`.
3. Fill in the project-specific values.
4. Run:
   `cd terraform && terraform init && terraform fmt -check && terraform validate`

## Bootstrap Notes

- Terraform manages project services after authentication, but the project still needs a usable GCP project and billing enabled.
- Commit `terraform/.terraform.lock.hcl` so provider resolution stays reproducible across local runs and CI.

## CI/CD Guidance

- Prefer GitHub OIDC with `google-github-actions/auth`.
- Do not store service account keys in repository secrets.
- Restrict the OIDC provider to this repository and the `main` branch.
- Grant the deployer service account only the roles needed for build and deploy.
