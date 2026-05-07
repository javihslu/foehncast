# Getting Started

This page keeps the operator choices simple. Start with the local evaluator path unless you explicitly need to provision cloud infrastructure.

## Choose The Right Path

| Path | Use it when | Main command |
|------|-------------|--------------|
| Local evaluator | You want the default development and evaluation flow with no GCP setup | `./scripts/bootstrap-local.sh` |
| Cloud operator | You want to provision a hosted environment in your own GCP project | `./scripts/bootstrap-gcp.sh` |
| Remote day-2 operations | You already bootstrapped the cloud prerequisites and want repeatable plan, apply, destroy, and cleanup commands | `./scripts/terraform-remote.sh` |

## Local Evaluator

This is the default path for a fresh machine.

1. Install Docker.
2. Clone the repository.
3. Run `./scripts/bootstrap-local.sh`.

You do not need `gcloud`, Terraform, GitHub Actions variables, or a local compiler toolchain for this path.

After bootstrap completes, the main local endpoints are:

- App: `http://127.0.0.1:8000`
- Airflow: `http://127.0.0.1:8080`
- MLflow: `http://127.0.0.1:5001`

Example check:

```bash
curl -fsS -X POST http://127.0.0.1:8000/rank \
  -H 'content-type: application/json' \
  -d '{"spot_ids":["silvaplana","urnersee"]}'
```

## Cloud Operator

Use this path only when you want to run FoehnCast in a GCP project you control.

Preferred first bootstrap:

1. Open Google Cloud Shell.
2. Clone the repository.
3. Run `./scripts/bootstrap-gcp.sh`.

That keeps `gcloud`, Terraform, project creation, billing linkage, and Terraform state handling in an admin shell instead of on the evaluator machine.

After bootstrap, use the remote helper for normal operations:

```bash
./scripts/terraform-remote.sh plan
./scripts/terraform-remote.sh apply
./scripts/terraform-remote.sh destroy
./scripts/terraform-remote.sh cleanup --cleanup-delete-state-bucket --cleanup-clear-github-actions
```

If you want the helper to watch the GitHub Actions workflow it dispatches, add `--wait`.

## What Lives Where

- `src/foehncast/`: application code for feature engineering, training, inference, monitoring, and configuration
- `dags/`: Airflow workflow entry points
- `scripts/`: local bootstrap, cloud bootstrap, remote Terraform, and helper scripts
- `terraform/`: hosted infrastructure definition and operator notes
- `tests/`: regression coverage for the pipeline and API behavior
- `docs/`: GitHub Pages source for the public documentation
- `ui/`: Streamlit demo surface

## Read Next

- [Architecture](system/architecture.md)
- [Feature Pipeline](system/feature-pipeline.md)
- [Cloud Mapping](system/cloud-mapping.md)
- [Repository](system/repository.md)
- [Milestones](milestones/index.md)
