# Getting Started

This page keeps the operator choices simple. Start with the local evaluator path unless you explicitly need to provision cloud infrastructure.

## Choose The Right Path

| Path | Use it when | Main command |
|------|-------------|--------------|
| Local evaluator | You want the default development and evaluation flow with the bundled objectstore and Feast setup, but no GCP setup | `./scripts/bootstrap-local.sh` |
| Cloud operator | You want to provision a hosted environment in your own GCP project | `./scripts/bootstrap-gcp.sh` |
| Remote day-2 operations | You already bootstrapped the cloud prerequisites and want repeatable plan, apply, destroy, and cleanup commands | `./scripts/terraform-remote.sh` |

## Local Evaluator

This is the default path for a fresh machine.

1. Install Docker.
2. Clone the repository.
3. Run `./scripts/bootstrap-local.sh`.

You do not need `gcloud`, Terraform, GitHub Actions variables, or a local compiler toolchain for this path.

The local evaluator path uses the bundled MinIO surface as the default object-access layer for curated feature persistence and MLflow artifacts, while Feast uses the bundled Datastore-mode emulator as the required online-serving layer on top of the curated contract. If the preferred local host ports are already occupied, the bootstrap helper moves the bindings to the next free ports and prints the chosen endpoints.

After bootstrap completes, the main local endpoints are:

- App: `http://127.0.0.1:8000`
- Airflow: `http://127.0.0.1:8080`
- MLflow: `http://127.0.0.1:5001`
- Objectstore UI: printed by the bootstrap helper when the stack comes up
- Feast online store emulator: printed by the bootstrap helper when the stack comes up

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
The bootstrap writes `.env` and `terraform/terraform.tfvars` and asks explicitly whether the next apply should enable the inference-only Cloud Run target and/or the full online compose host target.

After bootstrap, use the remote helper for normal operations:

```bash
./scripts/terraform-remote.sh plan
./scripts/terraform-remote.sh apply
./scripts/terraform-remote.sh destroy
./scripts/terraform-remote.sh cleanup --cleanup-delete-state-bucket --cleanup-clear-github-actions
```

If you want the helper to watch the GitHub Actions workflow it dispatches, add `--wait`.

Hosted deployment keeps the runtime scope tight. The cloud targets deploy runtime services only; `development_env`, notebooks, docs build tooling, the local objectstore, and the local Datastore emulator stay local or CI-only.

## What Lives Where

- `src/foehncast/`: application code for feature engineering, training, inference, monitoring, and configuration
- `dags/`: Airflow workflow entry points
- `scripts/`: local bootstrap, cloud bootstrap, remote Terraform, and helper scripts
- `terraform/`: hosted infrastructure definition and operator notes
- `feature_repo/`: Feast integration surface and config repo
- `tests/`: regression coverage for the pipeline and API behavior
- `docs/`: GitHub Pages source for the public documentation

## Read Next

- [Architecture](system/architecture.md)
- [Feature Pipeline](system/feature-pipeline.md)
- [Cloud Mapping](system/cloud-mapping.md)
- [Repository](system/repository.md)
- [Milestones](milestones/index.md)
