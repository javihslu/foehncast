# FoehnCast

FoehnCast ranks Swiss kiteboarding options for one rider profile. It combines forecast weather, engineered wind features, drive-time information, and a trained quality model to answer one practical question: which spot is worth the trip next?

The project keeps one stable Feature-Training-Inference split across all runtime modes. What changes is the hosting model around that split, not the application structure. In practice, the repo supports three operator paths: a local evaluation baseline, collaborator-owned GCP provisioning, and maintainer-managed shared deployment automation.

## System Shape

```mermaid
flowchart LR
    Forecasts[Forecast APIs] --> Features[Feature pipeline]
    Features --> Curated[Curated features]
    Curated --> Training[Training pipeline]
    Training --> Registry[MLflow registry]
    Registry --> API[FastAPI health, predict, and rank]
    Forecasts --> API
    Drive[OSRM drive time] --> API
    Curated --> Feast[Optional Feast layer]
    Feast --> API
```

## Runtime Modes

| Mode | What runs there | Main use |
|------|-----------------|----------|
| Local Compose baseline | Airflow, MLflow, FastAPI, and the development container | default development and evaluation path |
| Online compose host | the full Airflow, MLflow, and API stack on one GCP host | simplest way to keep the whole project online |
| Optional Cloud Run path | the FastAPI inference service only | inference-only deployment surface |
| GitHub automation | image publishing and Terraform workflows | GitOps for the hosted paths, not ML pipeline orchestration |

```mermaid
flowchart TB
    subgraph Local
        LocalAirflow[Airflow]
        LocalMLflow[MLflow]
        LocalAPI[FastAPI]
    end
    subgraph Online
        GHCR[GHCR runtime images]
        Terraform[Terraform workflow]
        Host[GCP online compose host]
        CloudRun[Optional Cloud Run app]
    end
    GHCR --> Host
    Terraform --> Host
    Terraform --> CloudRun
```

## What Works Today

| Area | Current state | Meaning |
|------|---------------|---------|
| Feature pipeline | Working | Airflow can ingest, engineer, validate, and store curated weather features |
| Training pipeline | Working | Airflow can label data, train the model, evaluate it, and register a version in MLflow |
| Inference pipeline | Working | the app serves `/health`, `/spots`, `/predict`, `/rank`, and the optional online-feature routes |
| Online runtime | Working | `docker-compose.cloud.yml` plus Terraform can run Airflow, MLflow, and the API on one online host |
| Cloud Run path | Available | the inference API can also be provisioned separately as a Cloud Run service |
| CI/CD path | Working | GitHub Actions publishes runtime images and can drive Terraform remotely |
| Local reproducibility | Working | `./scripts/bootstrap-local.sh` builds the local stack from a clean state and validates it |

## Local Quick Start

This is the default path for a fresh machine.

1. Install Docker.
2. Clone the repository.
3. Run `./scripts/bootstrap-local.sh`.

The script initializes `.env` from `.env.example` when needed, builds the local stack, runs the feature and training DAGs, and waits for the API to become healthy.

After it finishes, the main endpoints are:

- App: `http://127.0.0.1:8000`
- Airflow: `http://127.0.0.1:8080`
- MLflow: `http://127.0.0.1:5001`

Airflow and MLflow open directly in local mode. The bootstrap path resets Docker volumes before starting so the evaluator workflow begins from a clean state. Feature storage defaults to local files, and optional S3-compatible settings are only needed for non-default experiments.
Feature refresh scheduling stays inside Airflow. `AIRFLOW_FEATURE_SCHEDULE` defaults to `0 */6 * * *`; set it to an empty value, `manual`, or `off` when you want a purely manual local stack.

For stepwise debugging, use notebooks against the `development_env` container rather than embedding notebook logic into the pipelines themselves. The development container keeps its own Linux virtual environment and masks the host `.venv`; the image now installs the locked Python environment at build time, and startup only registers the `FoehnCast (development_env)` Jupyter kernel. In VS Code attached to `development_env`, select that kernel or `/home/appuser/.venv/bin/python` directly. Rebuild the development image after changing `pyproject.toml` or `uv.lock`.

Example check:

```bash
curl -fsS -X POST http://127.0.0.1:8000/rank \
  -H 'content-type: application/json' \
  -d '{"spot_ids":["silvaplana","urnersee"]}'
```

## Personal GCP Quick Start

Use this when a collaborator wants a private FoehnCast environment in their own GCP project.

Install:

- Google Cloud CLI (`gcloud`)
- Terraform
- GitHub CLI (`gh`) only if you want GitHub Actions in your own fork to publish and redeploy automatically

Run:

```bash
./scripts/bootstrap-gcp.sh
```

The interactive setup signs you into GCP, lets you pick or create a project, confirms region and storage defaults, optionally provisions Cloud Run, and can align GitHub Actions variables for your own fork. During setup it writes `.env` and `terraform/terraform.tfvars`, then refreshes them from Terraform outputs after apply.

Useful variants:

- Restart from scratch: `rm -f .env terraform/terraform.tfvars && ./scripts/bootstrap-gcp.sh`
- Skip prompts when you already know the values: `./scripts/bootstrap-gcp.sh --non-interactive`
- Configure fork automation during bootstrap: `./scripts/bootstrap-gcp.sh --configure-github-actions --repo <your-github-user>/foehncast`

## Hosted Paths

### Full online stack

Use the online compose-host path when you want Airflow, MLflow, and the API running together in the cloud.

1. Publish the runtime images with the `Publish Runtime Images` workflow, or let the host build once from the repo if the images are not published yet.
2. Run the `Terraform` workflow with `apply` and set `provision_online_compose_host=true`.
3. Provide at least:
   - `project_id`
   - `artifact_bucket_name`
   - the repository OIDC variables from `./scripts/configure-github-actions.sh`
4. Read the Terraform output for the public app URL:
   - `online_compose_app_url`
5. Retrieve the generated Airflow admin password from the host when you need UI access:
   - `gcloud compute ssh <host> --zone <zone> --project <project> --command 'sudo cat /opt/foehncast/airflow/.admin-password'`

The online host clones the repo, writes a runtime `.env` file with the Terraform-managed GCP and BigQuery settings, pulls the GHCR images when available, and falls back to local Docker builds on the host if needed.

Only the app is exposed publicly by default. Airflow and MLflow stay bound to the host loopback interface unless you explicitly add `8080` or `5001` to `online_compose_public_ports`.

### Optional Cloud Run service

Cloud Run stays available as an inference-only path for the app service.

- Set `provision_cloud_run_service=true` in the Terraform inputs.
- Provide `mlflow_tracking_uri` so the service can reach the registry.
- Publish the app image through the Artifact Registry plus Cloud Run workflow path.

When you finish a disposable cloud test, run `./scripts/teardown-gcp.sh --plan-only` first to preview the destroy, then rerun without `--plan-only` when you are ready to remove the Terraform-managed resources created from your local `.env` and `terraform/terraform.tfvars`. In a fresh clone with no local Terraform state, the helper skips the Terraform destroy path cleanly. `--clear-github-actions`, `--delete-state-bucket`, and `--delete-project` still work as explicit cleanup actions when you request them. `--delete-project` is intended for disposable smoke environments where you also want the bootstrap-created GCP project queued for deletion, and it prompts for the exact project id unless you also pass `--auto-approve`.

## Deployment Ownership

- The upstream repository is a public source, journal, and automation surface for the shared project.
- Public container images are convenience artifacts, not a shared hosting promise.
- Anyone who wants an online instance should deploy in a fork or in a cloud account they control.
- Compute, storage, network, and managed-service costs stay with the operator of that deployment.
- State-changing upstream workflows are guarded and intended for the shared project environment.

## GitHub Automation

- Airflow owns feature and training pipeline execution inside the ML stack. GitHub Actions is reserved for GitOps concerns such as image publishing, Terraform, and deployment automation.
- `.github/workflows/publish-runtime-images.yml`: publishes app, Airflow, MLflow, and development images to GHCR.
- `.github/workflows/terraform.yml`: runs Terraform validate on changes and supports manual remote plan or apply with a GCS backend.
- `.github/workflows/publish-app-image.yml`: keeps the optional Artifact Registry plus Cloud Run path for the inference API.

`./scripts/configure-github-actions.sh` syncs the GCP deploy variables plus the Terraform state bucket defaults back into the repository. When Cloud Run is not provisioned yet, it leaves `GCP_CLOUD_RUN_SERVICE` unset so the guarded workflow stays skipped without carrying stale values.

## Optional Feast

Feast stays optional and layered on the same curated features.

1. Install: `uv sync --group feast`
2. Prepare local Feast state: `./scripts/prepare-feast-local.sh`
3. Materialize: `cd feature_repo && uv run --group feast feast materialize-incremental "$(date -u +"%Y-%m-%dT%H:%M:%S")"`
4. Query the helper or HTTP route:
   - `uv run --group feast python -c "from foehncast.inference_pipeline.online_features import get_online_spot_features; print(get_online_spot_features(['silvaplana'], ['wind_speed_10m', 'gust_factor']))"`
   - `curl -fsS -X POST http://127.0.0.1:8000/features/online -H 'content-type: application/json' -d '{"spot_ids":["silvaplana"],"feature_names":["wind_speed_10m","gust_factor"]}'`

## More Detail

- `containers/README.md`
- `terraform/README.md`
- `docs/site/system/cloud-mapping.md`
- `feature_repo/README.md`
