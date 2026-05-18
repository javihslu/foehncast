# Delivery and Operator Workflow

FoehnCast keeps contributor onboarding and shared-cloud delivery separate. Contributors use `./scripts/bootstrap-local.sh` to run the validated local evaluator. Maintainers use `./scripts/bootstrap-gcp.sh`, GitHub Actions, and Terraform to bootstrap and advance the shared hosted environment. The hosted architecture is Cloud Build plus Cloud Run. This page describes the workflow contract.

!!! note "Scope"

    This page describes the validated delivery and operator workflow.
    It covers the Cloud Run and Cloud Build hosted architecture.
    It is not the local evaluator setup guide.

## Workflow In One View

<div class="mermaid">
flowchart TD
    subgraph Local["fab:fa-docker Contributor lane"]
        direction LR
        CLONE["Clone repo"]
        LOCAL["bootstrap-local.sh"]
        LVERIFY["Local stack + checks"]
        CLONE --> LOCAL --> LVERIFY
    end

    subgraph Maintainer["fab:fa-google Maintainer lane"]
        direction LR
        SHELL["Cloud Shell"]
        BGCP["bootstrap-gcp.sh"]
        HANDOFF["Remote TF + repo vars"]
        PUSH["Push or dispatch"]
        TFWF["fab:fa-github terraform.yml"]
        RUN["Cloud Run API"]
        SHELL --> BGCP --> HANDOFF --> TFWF
        PUSH --> TFWF
        TFWF --> RUN
    end
</div>

The local path is the supported onboarding path. The cloud path assumes GCP ownership, GitHub repository administration, and access to private operator surfaces.

The remote workflow lands on Cloud Run for the public API lane. Cloud Build publishes runtime images. Orchestration runs on local Airflow via Docker Compose.

## Supported Paths

| Path | Audience | Main tools | Main result |
|------|----------|------------|-------------|
| Default contributor path | contributor or reviewer | local Docker plus `./scripts/bootstrap-local.sh` | validated one-machine evaluator stack |
| One-time shared-cloud bootstrap | maintainer | Google Cloud Shell plus `./scripts/bootstrap-gcp.sh` | remote Terraform backend, repository-variable contract, and first hosted setup |
| Reviewed day-2 delivery | maintainer | GitHub Actions plus Terraform plus OIDC | reviewed infrastructure and runtime updates |
| Runtime recovery | maintainer | local Airflow plus the runtime release script | retries, backfills, and reviewed serving handoffs |

## Default Contributor Path

The default contributor path stays local and small:

1. Clone the repository.
2. Install Docker.
3. Run `./scripts/bootstrap-local.sh`.

This path does not require local `gcloud`, Terraform, or GitHub Actions repository variables. The bootstrap validates the full local evaluator contract, not just container startup, and prints alternate endpoints automatically when the preferred ports are already occupied. See [Local Evaluator](local-evaluator.md) for the full local runtime contract.

## One-Time Shared Cloud Bootstrap

The cloud bootstrap is a maintainer workflow, not a second onboarding path. The preferred environment is Google Cloud Shell so admin tools stay off the default evaluator machine.

For the initial shared-cloud setup, run:

`./scripts/bootstrap-gcp.sh --bootstrap-only --configure-github-actions`

The script is interactive. It walks the operator through `gcloud` authentication, project and billing selection, hosted-target choices, and GitHub repository-variable sync.

In `--bootstrap-only` mode the script prepares the remote Terraform backend, prints the handoff summary, and leaves the broader hosted apply to the remote workflow. It writes `.env` and `terraform/terraform.tfvars` so the local checkout reflects the selected project.

In normal apply mode the script also verifies both hosted lanes: Cloud Run must answer `/health`, `/spots`, and `/metrics`, and the operator host must keep its app URL private.

## Reviewed Day-2 Delivery

After the one-time bootstrap establishes OIDC and the remote backend, GitHub Actions becomes the primary surface for Terraform-managed changes.

| Surface | Purpose |
|------|---------|
| `.github/workflows/terraform.yml` | primary Terraform operator path for reviewed apply, plan, destroy, cleanup, and explicit overrides |
| `scripts/configure-github-actions.sh` | sync Terraform outputs into GitHub repository variables |
| `terraform/terraform.tfvars` | interactive bootstrap input, not the day-2 source of truth |
| runtime image workflows | submit reviewed hosted image builds to Cloud Build and publish images to Artifact Registry |
| `scripts/prepare-feast-cloud.sh` | hosted Feast follow-up after a remote apply and curated BigQuery rows exist |

The remote workflow reads repository-backed values for project, state, storage, BigQuery, and hosted-target toggles. Cloud Run settings such as instance count, container port, CPU, and memory are also repo-variable-backed.

Repository variables stay structural delivery inputs only. Runtime passwords, API tokens, and other secrets belong in the runtime environment or a managed secret path. Both hosted lanes read the same Terraform-managed storage, Feast, and MLflow contract. See [Configuration and Contracts](configuration-and-contracts.md) for the full inventory.

## Orchestration

Local Airflow (via Docker Compose) owns orchestration: DAG scheduling, retries, backfills, and runtime release handoff.

| Concern | Implementation |
|------|------------------------|
| Airflow surface | local Docker Compose |
| Runtime release entry | `scripts/trigger-runtime-release.sh` against local Airflow API |
| Scheduling, retries, and backfills | local Airflow |
| Operator services | MLflow, monitoring, and private app checks |

## GitHub Versus GCP Boundary

The reviewed delivery plane and the runtime execution plane have different responsibilities.

| Plane | Active owner | What it owns | What it must not own |
|------|---------------|--------------|----------------------|
| Reviewed delivery | GitHub Actions plus Terraform | lint, test, build, image publish, Terraform plan/apply/destroy, and reviewed deploy workflows | runtime scheduling, retries, backfills, and long-lived operator state |
| Runtime execution | GCP-hosted runtime surfaces | Cloud Run serving, operator telemetry | source control, CI review, and infrastructure policy review |
| Shared handoff | repository variables, published images, Terraform outputs, and runtime release requests | reviewed contract from GitHub into GCP runtime surfaces | ad hoc operator-only divergence from the declared contract |

GitHub Actions triggers reviewed delivery workflows, but runtime scheduling does not belong to GitHub. Runtime orchestration lives on local Airflow.

## Runtime Release Trigger Contract

The runtime release handoff uses a single script against the Airflow API.

<div class="mermaid">
flowchart TD
    SCRIPT["scripts/trigger-runtime-release.sh"] --> API["Airflow API"]
    API --> DAG["runtime_release DAG"]
    DAG --> REPORT["runtime-release-latest.json"]
</div>

- signal: `scripts/trigger-runtime-release.sh` sends one JSON request with a single action and the associated release coordinates
- receiver: the local Airflow API
- observable outcome: the script waits for the `runtime_release` DAG to succeed and captures the configured runtime release summary target

Supported actions:

- `deploy_candidate`
- `promote_candidate`
- `rollback_live`

This keeps the handoff explicit while deeper runtime automation still lives behind the Airflow side of the boundary.

## Retry And Backfill Runbooks

Operators should retry work on the same plane that owns it instead of jumping between GitHub and runtime surfaces.

| Situation | Where to act | Normal procedure | Minimum evidence |
|------|---------------|------------------|------------------|
| Terraform or image publication fails before any runtime request is sent | GitHub Actions | fix the reviewed delivery input, then rerun the failed GitHub workflow | GitHub workflow URL plus the updated workflow summary |
| candidate deploy, promotion, or rollback handoff needs another attempt | local Airflow | rerun `scripts/trigger-runtime-release.sh` with the same release coordinates | runtime release summary target |
| a feature slice failed or needs replay for one logical date | local Airflow | trigger `feature_pipeline` with an explicit logical date and wait for the DAG to succeed | logical date, feature DAG run id, and `airflow/reports/feature-pipeline-<dataset>-latest.json` |
| a replayed feature slice should refresh training state too | local Airflow | let the feature replay publish the training-request asset and wait for the asset-triggered `training_pipeline` run | training DAG run id plus `airflow/reports/training-pipeline-<dataset>-latest.json` |
| training must be rerun without replaying feature ingestion | local Airflow | use a manual `training_pipeline` run only when the curated feature slice already exists | training DAG run id, requested stage, model version, and training summary JSON |

The operator services stay private by default. Recovery uses the local Airflow UI or API.

After the trigger, keep the same wait contract:

- `feature_pipeline` should reach `success` for the chosen logical date
- the downstream `training_pipeline` should reach `success` as an `asset_triggered` run when the replay is meant to refresh production model state
- operators should check the latest summary JSON files under `airflow/reports/` before treating the replay as complete

Serving rollout problems should use the runtime trigger contract, not the backfill path. GitHub sends the reviewed deploy, promote, or rollback request, and the runtime side records one explicit acknowledgement.

## Rollback

Rollback uses the runtime trigger contract instead of direct GitHub runtime mutation.

- `.github/workflows/publish-app-image.yml` publishes the reviewed app image only
- `scripts/trigger-runtime-release.sh` is the single reviewed handoff for candidate deploy, promotion, and rollback requests
- `.github/workflows/promote-candidate.yml` and `.github/workflows/rollback-live-release.yml` stay as blocked redirect workflows so the old entry points do not continue mutating runtime state directly
- the configured runtime release summary target records the acknowledged handoff on the runtime side

Practical recovery split:

- use GitHub workflow reruns when reviewed delivery failed before runtime execution
- use local Airflow retries and backfills when runtime data or orchestration work failed after delivery
- use the runtime trigger script when the serving release handoff itself must be retried

## Reviewable Boundaries

These boundaries stay explicit across the scripts, Terraform reference, and workflow contract:

- the local Docker evaluator remains the only default contributor path
- the shared cloud environment stays operator-owned, even though the repository and images are public
- `terraform/terraform.tfvars` belongs to bootstrap and local preview work, while day-2 remote runs read GitHub repository variables
- runtime scheduling, retries, and backfills belong to local Airflow, not to GitHub Actions
- runtime promotion, rollback, and live traffic control do not run inside GitHub workflows; GitHub only sends the reviewed runtime release request
- Airflow, MLflow, and Prometheus remain operator surfaces rather than rider-facing product surfaces
- public docs should explain those surfaces with rendered evidence and checked-in configuration, not live control-plane embeds

The same split keeps cloud retirement reviewable. Destroy and cleanup stay separate workflow commands, and cleanup only runs the follow-up actions the operator selected.

## Why This Workflow Works

- contributors get one supported setup path instead of parallel onboarding stories
- the one-time cloud bootstrap is explicit and interactive, which is safer for project, billing, and hosted-target choices
- day-2 infrastructure changes run through GitHub Actions so operators do not need local Terraform
- Terraform outputs, repository variables, and workflow behavior are tied together by regression tests
- managed orchestration through local Airflow keeps scheduling local and reproducible

See [Interfaces and Surfaces](interfaces-and-surfaces.md), [Hosted Full-Stack](hosted-full-stack.md), [Cloud Mapping](cloud-mapping.md), and [Monitoring](monitoring.md) for the surrounding runtime and exposure boundaries.
