# Delivery and Operator Workflow

FoehnCast keeps contributor onboarding and shared-cloud delivery separate. Contributors use `./scripts/bootstrap-local.sh` to run the validated local evaluator. Maintainers use `./scripts/bootstrap-gcp.sh`, GitHub Actions, and Terraform to bootstrap and advance the shared hosted environment. The hosted architecture is Cloud Build plus Cloud Composer. This page describes the workflow contract.

!!! note "Scope"

    This page describes the validated delivery and operator workflow.
    It covers the Cloud Composer and Cloud Build hosted architecture.
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
        CMP["Cloud Composer"]
        RUN["Cloud Run API"]
        SHELL --> BGCP --> HANDOFF --> TFWF
        PUSH --> TFWF
        TFWF --> CMP
        TFWF --> RUN
    end
</div>

The split matters because the local path is the supported onboarding path, while the cloud path assumes GCP ownership, GitHub repository administration, and access to private operator surfaces.

The remote workflow lands on two hosted runtime surfaces: Cloud Run for the public API lane and Cloud Composer for hosted orchestration, scheduling, and recovery. Cloud Build publishes runtime images.

## Supported Paths

| Path | Audience | Main tools | Main result |
|------|----------|------------|-------------|
| Default contributor path | contributor or reviewer | local Docker plus `./scripts/bootstrap-local.sh` | validated one-machine evaluator stack |
| One-time shared-cloud bootstrap | maintainer | Google Cloud Shell plus `./scripts/bootstrap-gcp.sh` | remote Terraform backend, repository-variable contract, and first hosted setup |
| Reviewed day-2 delivery | maintainer | GitHub Actions plus Terraform plus OIDC | reviewed infrastructure and runtime updates |
| Runtime recovery | maintainer | Cloud Composer Airflow plus the runtime trigger workflow | retries, backfills, and reviewed serving handoffs |

## Default Contributor Path

The default contributor path stays local and small:

1. Clone the repository.
2. Install Docker.
3. Run `./scripts/bootstrap-local.sh`.

This path does not require local `gcloud`, Terraform, or GitHub Actions repository variables. The bootstrap validates the full local evaluator contract, not just container startup, and prints alternate endpoints automatically when the preferred ports are already occupied. See [Local Evaluator](local-evaluator.md) for the full local runtime contract.

## One-Time Shared Cloud Bootstrap

The cloud bootstrap is a maintainer workflow, not a second onboarding path. The preferred first-time environment is Google Cloud Shell. That keeps admin tools off the default evaluator machine and matches the supported no-local-install path.

For the initial shared-cloud setup, run:

`./scripts/bootstrap-gcp.sh --bootstrap-only --configure-github-actions`

The script is interactive by design. It asks the operator to authenticate with `gcloud`, choose or create the target project and billing context, confirm the hosted identifiers and data surfaces, choose which hosted targets to enable, and sync the GitHub repository variables that the remote workflow uses later.

In `--bootstrap-only` mode, the script prepares the remote Terraform control plane, prints the remote-state and identity handoff, and leaves the broader hosted apply to the remote workflow. It also writes `.env` and `terraform/terraform.tfvars` in the working tree so the local checkout reflects the selected project and platform identifiers.

When the script runs a normal apply instead of bootstrap-only mode, it verifies both hosted lanes. Cloud Run must answer `/health`, `/spots`, and `/metrics`, and the operator host must keep its app URL private.

## Reviewed Day-2 Delivery

After the one-time bootstrap establishes OIDC, the remote backend, and the repository-variable contract, GitHub Actions becomes the primary operator surface for Terraform-managed changes.

| Surface | Purpose |
|------|---------|
| `.github/workflows/terraform.yml` | primary Terraform operator path for reviewed apply, plan, destroy, cleanup, and explicit overrides |
| `scripts/configure-github-actions.sh` | sync Terraform outputs into GitHub repository variables |
| `terraform/terraform.tfvars` | interactive bootstrap input, not the day-2 source of truth |
| runtime image workflows | submit reviewed hosted image builds to Cloud Build and publish images to Artifact Registry |
| `.github/workflows/publish-composer-dags.yml` | publish the reviewed DAG and source bundle to the provisioned Composer DAG bucket |
| `.github/workflows/trigger-runtime-release.yml` | send one explicit reviewed runtime release request to the Composer Airflow API |
| `scripts/prepare-feast-cloud.sh` | hosted Feast follow-up after a remote apply and curated BigQuery rows exist |

The remote workflow reads repository-backed values for project, state, storage, BigQuery, and hosted target toggles. Lower-level Cloud Run settings such as minimum and maximum instance count, container port, CPU, and memory stay repo-variable-backed instead of becoming manual workflow inputs.

GitHub publishes the repo-managed DAG and source bundle into the Composer DAG bucket. Composer gets a reviewed PyPI baseline for the checked-in DAG bundle and can consume reviewed `sm://...` Secret Manager env references through the shared runtime env helper.

Checked-in examples and bootstrap outputs can seed the contract, but GitHub repository variables stay structural delivery inputs only. Runtime passwords, API tokens, and other secret-bearing values belong in the runtime environment or a managed secret path instead of the repository-variable sync. Both hosted lanes read the same Terraform-managed storage, Feast, and MLflow contract. See [Configuration and Contracts](configuration-and-contracts.md) for the reviewed inventory.

## Hosted Orchestration

Cloud Composer owns hosted orchestration: DAG scheduling, retries, backfills, and runtime release handoff.

| Concern | Hosted implementation |
|------|------------------------|
| Hosted Airflow surface | Cloud Composer |
| Reviewed runtime release entry | GitHub OIDC plus access token to the Composer Airflow API |
| Scheduling, retries, and backfills | Cloud Composer |
| Operator services | MLflow, monitoring, and private app checks as managed services |

## GitHub Versus GCP Boundary

The reviewed delivery plane and the runtime execution plane have different responsibilities.

| Plane | Active owner | What it owns | What it must not own |
|------|---------------|--------------|----------------------|
| Reviewed delivery | GitHub Actions plus Terraform | lint, test, build, image publish, Terraform plan/apply/destroy, and reviewed deploy workflows | runtime scheduling, retries, backfills, and long-lived operator state |
| Runtime execution | GCP-hosted runtime surfaces | Cloud Run serving, Cloud Composer scheduling, retries, backfills, runtime environment injection, and operator telemetry | source control, CI review, and infrastructure policy review |
| Shared handoff | repository variables, published images, Terraform outputs, and runtime release requests | reviewed contract from GitHub into GCP runtime surfaces; runtime release reaches the Composer Airflow API | ad hoc operator-only divergence from the declared contract |

GitHub Actions may trigger reviewed delivery workflows, but runtime scheduling does not belong to GitHub. Runtime orchestration lives on Cloud Composer.

## Runtime Release Trigger Contract

GitHub now has exactly one reviewed handoff into runtime execution.

<div class="mermaid">
flowchart LR
    GHW["fab:fa-github Runtime release workflow"] --> TARGET["reviewed receiver selection"]
<div class="mermaid">
flowchart LR
    GHW["fab:fa-github Runtime release workflow"] --> AUTH["OIDC + access token"]
    AUTH --> API["Composer Airflow API"]
    API --> DAG["runtime_release DAG"]
    DAG --> REPORT["runtime-release-latest.json"]
    REPORT --> SUMMARY["GitHub workflow summary"]
</div>

- signal: `.github/workflows/trigger-runtime-release.yml` sends one JSON request with a single action and the associated release coordinates
- receiver: the Composer Airflow API
- auth path: GitHub OIDC plus a Google access token for the Composer Airflow API; the GitHub service account maps to an Airflow user or role
- observable outcome: the workflow waits for the `runtime_release` DAG to succeed and captures the configured runtime release summary target with requested receiver metadata; the Composer path reads the durable `gs://...` report contract derived from the artifact bucket

Supported actions:

- `deploy_candidate`
- `promote_candidate`
- `rollback_live`

This keeps the handoff explicit while deeper runtime automation still lives behind the Airflow side of the boundary.

## Composer Runtime Contract

Cloud Composer is the hosted orchestration surface. The contract covers:

| Concern | Implementation |
|------|----------------|
| DAG packaging | GitHub publishes the reviewed DAG and source bundle to the Composer DAG bucket; the bundle includes DAG entrypoints, the `foehncast` Python package, `config.yaml`, `pyproject.toml`, and `feature_repo` |
| Python dependencies | Terraform seeds a reviewed Composer PyPI baseline for the checked-in DAG bundle; extra `cloud_composer_pypi_packages` overrides are available for follow-up slices |
| Secrets and runtime config | Composer consumes reviewed `sm://...` Secret Manager env references resolved by the shared runtime env helper |
| Network and API reachability | the runtime trigger reaches the Composer Airflow API through GitHub OIDC plus a Google access token |
| Operator access model | Composer provides the Airflow UI for scheduling, retries, backfills, and recovery |

The runtime release acknowledgement path writes the reviewed summary to durable GCS storage derived from the artifact bucket.

## Retry And Backfill Runbooks

Operators should retry work on the same plane that owns it instead of jumping between GitHub and runtime surfaces.

| Situation | Where to act | Normal procedure | Minimum evidence |
|------|---------------|------------------|------------------|
| Terraform or image publication fails before any runtime request is sent | GitHub Actions | fix the reviewed delivery input, then rerun the failed GitHub workflow | GitHub workflow URL plus the updated workflow summary |
| candidate deploy, promotion, or rollback handoff needs another attempt | GitHub Actions through the runtime trigger contract | rerun `.github/workflows/trigger-runtime-release.yml` with the same reviewed release coordinates so the Composer API handoff records a new acknowledgement | GitHub workflow URL plus the configured runtime release summary target |
| a feature slice failed or needs replay for one logical date | Cloud Composer Airflow | trigger `feature_pipeline` with an explicit logical date through the Composer Airflow UI and wait for the DAG to succeed | logical date, feature DAG run id, and `airflow/reports/feature-pipeline-<dataset>-latest.json` |
| a replayed feature slice should refresh training state too | Cloud Composer Airflow | let the feature replay publish the training-request asset and wait for the asset-triggered `training_pipeline` run instead of treating training as a separate first step | training DAG run id plus `airflow/reports/training-pipeline-<dataset>-latest.json` |
| training must be rerun without replaying feature ingestion | Cloud Composer Airflow | use a manual `training_pipeline` run only when the curated feature slice already exists and the operator is intentionally choosing the requested stage in DAG config | training DAG run id, requested stage, model version, and training summary JSON |

The operator services stay private by default. Recovery uses the Composer Airflow UI or API.

After the trigger, keep the same wait contract:

- `feature_pipeline` should reach `success` for the chosen logical date
- the downstream `training_pipeline` should reach `success` as an `asset_triggered` run when the replay is meant to refresh production model state
- operators should check the latest summary JSON files under `airflow/reports/` before treating the replay as complete

Serving rollout problems should use the runtime trigger contract, not the backfill path. GitHub sends the reviewed deploy, promote, or rollback request, and the runtime side records one explicit acknowledgement.

## Rollback

Rollback uses the runtime trigger contract instead of direct GitHub runtime mutation.

- `.github/workflows/publish-app-image.yml` publishes the reviewed app image only
- `.github/workflows/trigger-runtime-release.yml` is the single reviewed GitHub-to-runtime handoff for candidate deploy, promotion, and rollback requests
- `.github/workflows/promote-candidate.yml` and `.github/workflows/rollback-live-release.yml` stay as blocked redirect workflows so the old entry points do not continue mutating runtime state directly
- the configured runtime release summary target records the acknowledged handoff on the runtime side, including requested receiver metadata

Practical recovery split:

- use GitHub workflow reruns when reviewed delivery failed before runtime execution
- use Cloud Composer retries and backfills when runtime data or orchestration work failed after delivery
- use the runtime trigger contract when the serving release handoff itself must be retried

## Reviewable Boundaries

These boundaries stay explicit across the scripts, Terraform reference, and workflow contract:

- the local Docker evaluator remains the only default contributor path
- the shared cloud environment stays operator-owned, even though the repository and images are public
- `terraform/terraform.tfvars` belongs to bootstrap and local preview work, while day-2 remote runs read GitHub repository variables
- runtime scheduling, retries, and backfills belong to Cloud Composer, not to GitHub Actions
- runtime promotion, rollback, and live traffic control do not run inside GitHub workflows; GitHub only sends the reviewed runtime release request
- Grafana, Airflow, MLflow, and Prometheus remain operator surfaces rather than rider-facing product surfaces
- public docs should explain those surfaces with rendered evidence and checked-in configuration, not live control-plane embeds

The same split also keeps cloud retirement reviewable. Destroy and cleanup stay separate workflow commands, and cleanup only runs the follow-up actions the operator selected.

## Why This Workflow Works

- it gives contributors one supported setup path instead of parallel onboarding stories
- it keeps the one-time cloud bootstrap explicit and interactive, which is safer for project, billing, and hosted-target choices
- it moves normal day-2 infrastructure changes into GitHub Actions so operators do not need local Terraform for routine work
- it keeps shared-cloud configuration reviewable because Terraform outputs, repository variables, and workflow behavior are tied together by regression tests
- it uses managed orchestration through Cloud Composer instead of VM-owned scheduling

See [Interfaces and Surfaces](interfaces-and-surfaces.md), [Hosted Full-Stack](hosted-full-stack.md), [Cloud Mapping](cloud-mapping.md), and [Monitoring](monitoring.md) for the surrounding runtime and exposure boundaries.
