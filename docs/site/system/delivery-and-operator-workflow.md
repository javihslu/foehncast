# Delivery and Operator Workflow

FoehnCast keeps contributor onboarding and shared-cloud delivery separate on purpose. Contributors use `./scripts/bootstrap-local.sh` to run the validated local evaluator. Maintainers use `./scripts/bootstrap-gcp.sh`, GitHub Actions, and Terraform to bootstrap and advance the shared hosted environment. This page records the current workflow contract validated by the bootstrap scripts, the Terraform reference, and the cloud-operator tests.

!!! note "Scope"

    This page describes the current validated delivery and operator workflow.
    It is not a roadmap.
    Future deployment changes should be documented after they are chosen and implemented.

## Workflow In One View

<div class="mermaid">
flowchart LR
    subgraph Local[Default contributor lane]
        CLONE[Clone repo]
        LOCAL[./scripts/bootstrap-local.sh]
        LSTACK[Local evaluator stack]
        LVERIFY[Feature and training hand-off plus Feast and monitoring checks]
    end

    subgraph Bootstrap[One-time maintainer bootstrap]
        SHELL[Google Cloud Shell]
        BGCP[./scripts/bootstrap-gcp.sh --bootstrap-only --configure-github-actions]
        BACKEND[Remote Terraform backend]
        VARS[GitHub repository variables]
    end

    subgraph Remote[Normal shared-cloud delivery]
        PUSH[Push to main or manual workflow dispatch]
        TFWF[.github/workflows/terraform.yml]
        HOST[Hosted full-stack target]
        RUN[Primary Cloud Run target]
    end

    CLONE --> LOCAL --> LSTACK --> LVERIFY
    SHELL --> BGCP
    BGCP --> BACKEND
    BGCP --> VARS
    PUSH --> TFWF
    BACKEND --> TFWF
    VARS --> TFWF
    TFWF --> HOST
    TFWF --> RUN
</div>

The split matters because the local path is the supported public onboarding path, while the cloud path assumes GCP ownership, GitHub repository administration, and access to private operator surfaces.

## Current Lanes

| Lane | Current target | Main job |
|------|----------------|----------|
| Local evaluator lane | `./scripts/bootstrap-local.sh` plus local Compose | run the default contributor path |
| Delivery lane | GitHub Actions plus Terraform plus OIDC | publish reviewed artifacts and apply reviewed infrastructure changes |
| Shared API lane | hosted inference target on Cloud Run | serve the shared public API |
| Operator lane | hosted full-stack target on one GCP host | keep Airflow, MLflow, monitoring, and private recovery work online |

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

When the script runs a normal apply instead of bootstrap-only mode, it verifies both hosted lanes. Cloud Run must answer `/health`, `/spots`, and `/metrics`, and the health payload must expose the served alias and model version. The operator host must keep its app URL private. If that app URL is public, bootstrap fails fast instead of treating the VM as a public fallback.

## Day-2 Delivery Contract

After the one-time bootstrap establishes OIDC, the remote backend, and the repository-variable contract, GitHub Actions becomes the primary operator surface for Terraform-managed changes.

| Surface | Current role | Current contract |
|------|---------------|------------------|
| `.github/workflows/terraform.yml` | primary Terraform operator path | pushes to `main` automatically resolve to `apply` after bootstrap; manual dispatch stays available for `plan`, `destroy`, `cleanup`, and explicit overrides |
| `scripts/configure-github-actions.sh` | repo-variable sync | Terraform outputs are copied into GitHub repository variables so the remote workflow reads one shared contract |
| `terraform/terraform.tfvars` | bootstrap input | used during the interactive bootstrap path, not as the day-2 source of truth for remote applies |
| runtime image workflows | reviewed artifact publishing | publish automation builds and publishes runtime images, but it does not deploy Cloud Run, shift traffic, or mutate MLflow aliases directly |
| `.github/workflows/trigger-runtime-release.yml` | reviewed runtime handoff | today GitHub sends one explicit runtime release request into hosted Airflow after the retained operator host refreshes to the reviewed git ref; this handoff is transitional until Composer owns it |
| `scripts/prepare-feast-cloud.sh` | hosted Feast follow-up | run this after a remote apply succeeds and curated BigQuery rows exist |

The remote workflow reads repository-backed values for project, state, storage, BigQuery, and hosted target toggles. Lower-level Cloud Run settings such as container port, CPU, and memory stay repo-variable-backed instead of becoming manual workflow inputs.

Checked-in examples and bootstrap outputs can seed the contract, but GitHub repository variables stay structural delivery inputs only. Runtime passwords, API tokens, and other secret-bearing values belong in the runtime environment or a managed secret path instead of the repository-variable sync. Both hosted lanes still read the same Terraform-managed storage, Feast, and MLflow contract. See [Configuration and Contracts](configuration-and-contracts.md) for the reviewed inventory.

## Current Retained-Host Dependencies

The shared environment still depends on the retained operator host in a few specific places. This table is the current inventory for the active migration wave.

| Surface | Current dependency | Classification | Next migration issue |
|------|--------------------|----------------|----------------------|
| runtime release handoff | `.github/workflows/trigger-runtime-release.yml` still refreshes the VM checkout over SSH and runs `scripts/trigger-runtime-release.sh` to trigger the host-local `runtime_release` DAG | transitional | #224 |
| hosted DAG execution and recovery | runtime retries, backfills, and manual replay still assume SSH access to the retained host and host-local Airflow | transitional | #224 |
| bootstrap and repo-variable plumbing | `scripts/bootstrap-gcp.sh`, `.github/workflows/terraform.yml`, and `scripts/terraform-platform-state.sh` still resolve and sync `GCP_ONLINE_COMPOSE_*` inputs | transitional | #224 |
| sync evidence and operator checks | the retained host still writes `.state/online-compose-sync/last-success.json`, and hosted verification still checks that sync evidence through `/metrics` | keep for now | later host-shrink issue |
| cloud-operator regression tests | `tests/test_cloud_operator_contract.py` and the online-compose sync tests still enforce the retained-host contract directly | keep while migrating | same issue as the production surface being changed |

## Hosted Orchestration Boundary

The current hosted orchestration path and the target managed direction are different on purpose.

| Concern | Current operational path | Target managed direction |
|------|---------------------------|--------------------------|
| Hosted Airflow surface | retained operator host | Cloud Composer |
| Reviewed runtime release entry | GitHub OIDC plus SSH to the retained host, then local `runtime_release` DAG trigger | reviewed request should reach Composer without VM SSH |
| Scheduling, retries, and backfills | retained-host Airflow | Composer |
| Operator host role | Airflow, MLflow, monitoring, and private app checks on one VM | shrink after Composer absorbs orchestration; keep only the services that still need a VM |

Today the retained host path remains the operational recovery surface. It is not the intended long-term hosted orchestration authority.

## GitHub Versus GCP Boundary

The reviewed delivery plane and the runtime execution plane still have different responsibilities.

| Plane | Current owner | What it owns | What it must not own |
|------|---------------|--------------|----------------------|
| Reviewed delivery | GitHub Actions plus Terraform | lint, test, build, image publish, Terraform plan/apply/destroy, and reviewed deploy workflows | runtime scheduling, retries, backfills, and long-lived operator state |
| Runtime execution | GCP-hosted runtime surfaces | Cloud Run serving, hosted Airflow scheduling, retries, backfills, runtime environment injection, and operator telemetry | source control, CI review, and infrastructure policy review |
| Shared handoff | repository variables, published images, Terraform outputs, and runtime release requests | reviewed contract from GitHub into GCP runtime surfaces | ad hoc operator-only divergence from the declared contract |

GitHub Actions may trigger reviewed delivery workflows, but runtime scheduling does not belong to GitHub. Today that runtime orchestration still lives on the retained operator host. The target managed surface is Cloud Composer.

## Runtime Release Trigger Contract

GitHub now has exactly one reviewed handoff into runtime execution.

<div class="mermaid">
flowchart LR
    GHW[Trigger Runtime Release workflow]
    SSH[OIDC plus SSH to retained operator host]
    SCRIPT[trigger-runtime-release.sh]
    DAG[runtime_release DAG]
    REPORT[runtime-release-latest.json]
    SUMMARY[GitHub workflow summary]

    GHW --> SSH --> SCRIPT --> DAG --> REPORT --> SUMMARY
</div>

- signal: `.github/workflows/trigger-runtime-release.yml` sends one JSON request with a single action and the associated release coordinates
- receiver: `./scripts/trigger-runtime-release.sh` runs on the retained operator host and triggers the hosted Airflow `runtime_release` DAG locally
- auth path: GitHub Actions uses OIDC into the deployer service account and Compute Engine SSH; GitHub does not store Airflow credentials or call a public Airflow endpoint
- observable outcome: the workflow waits for the `runtime_release` DAG to succeed and captures `airflow/reports/runtime-release-latest.json`

Supported actions:

- `deploy_candidate`
- `promote_candidate`
- `rollback_live`

This keeps the handoff explicit while deeper runtime automation still lives behind the Airflow side of the boundary. It is the current operational contract, not the intended long-term hosted entry path. The target managed direction is the same reviewed request reaching Composer without a retained-host refresh step.

## Composer Readiness Requirements

Cloud Composer is still a target, not a provisioned surface in this repo. Before it can become the hosted orchestration authority, the repo needs an explicit contract for:

| Requirement | Current repo shape | What later Composer work must replace or define |
|------|--------------------|-----------------------------------------------|
| DAG packaging | DAGs currently arrive through the retained host checkout and compose-mounted repo path | a reviewed DAG delivery path that does not depend on a VM checkout |
| Python dependencies | Airflow dependencies currently live in the retained-host container image path | a hosted Airflow dependency bundle compatible with Composer |
| Secrets and runtime config | the retained host reads runtime configuration from the VM-local environment and service identity | a managed secret and runtime-config path for hosted orchestration |
| Network and API reachability | the current trigger contract reaches Airflow through VM SSH and host-local API access | a reviewed runtime-release entry path that reaches Composer without VM SSH |
| Operator access model | retries, backfills, and recovery currently assume SSH to the retained host | a clear managed operator access model for Composer-owned orchestration |

## Retry And Backfill Runbooks

The recovery lane is now explicit too. Operators should retry work on the same plane that owns it instead of jumping between GitHub and runtime surfaces.

These are the current runbooks while hosted orchestration still lives on the retained host.

| Situation | Where to act | Normal procedure | Minimum evidence |
|------|---------------|------------------|------------------|
| Terraform or image publication fails before any runtime request is sent | GitHub Actions | fix the reviewed delivery input, then rerun the failed GitHub workflow | GitHub workflow URL plus the updated workflow summary |
| candidate deploy, promotion, or rollback handoff needs another attempt | GitHub Actions through the runtime trigger contract | rerun `.github/workflows/trigger-runtime-release.yml` with the same reviewed release coordinates so the retained operator host refreshes and the hosted Airflow `runtime_release` DAG records a new acknowledgement | GitHub workflow URL plus `airflow/reports/runtime-release-latest.json` |
| a feature slice failed or needs replay for one logical date | hosted Airflow on the retained operator host | SSH to the host, verify Airflow health, trigger `feature_pipeline` with an explicit logical date, and wait for the DAG to succeed | logical date, feature DAG run id, and `airflow/reports/feature-pipeline-<dataset>-latest.json` |
| a replayed feature slice should refresh training state too | hosted Airflow on the retained operator host | let the feature replay publish the training-request asset and wait for the asset-triggered `training_pipeline` run instead of treating training as a separate first step | training DAG run id plus `airflow/reports/training-pipeline-<dataset>-latest.json` |
| training must be rerun without replaying feature ingestion | hosted Airflow on the retained operator host | use a manual `training_pipeline` run only when the curated feature slice already exists and the operator is intentionally choosing the requested stage in DAG config | training DAG run id, requested stage, model version, and training summary JSON |

The retained operator host stays private by default, so the recovery path assumes SSH to the host rather than a public Airflow endpoint.

Example feature replay on the retained host:

```bash
cd /opt/foehncast
docker compose -f docker-compose.yml -f docker-compose.cloud.yml --env-file .env exec -T airflow-webserver \
    airflow dags trigger feature_pipeline \
    --logical-date "2026-05-14T00:00:00Z" \
    --run-id "manual_backfill__2026-05-14T00-00-00Z"
```

After the trigger, keep the same host-side wait contract:

- `feature_pipeline` should reach `success` for the chosen logical date
- the downstream `training_pipeline` should reach `success` as an `asset_triggered` run when the replay is meant to refresh production model state
- operators should check the latest summary JSON files under `airflow/reports/` before treating the replay as complete

Serving rollout problems should use the runtime trigger contract, not the backfill path. GitHub sends the reviewed deploy, promote, or rollback request, and the runtime side records one explicit acknowledgement.

## Rollback And Retirement Coordinates

Rollback uses the runtime trigger contract instead of direct GitHub runtime mutation.

- `.github/workflows/publish-app-image.yml` publishes the reviewed app image only
- `.github/workflows/trigger-runtime-release.yml` is the single reviewed GitHub-to-runtime handoff for candidate deploy, promotion, and rollback requests
- `.github/workflows/promote-candidate.yml` and `.github/workflows/rollback-live-release.yml` stay as blocked redirect workflows so the old entry points do not continue mutating runtime state directly
- `airflow/reports/runtime-release-latest.json` and its history files record the acknowledged handoff on the runtime side
- reopening the hosted VM app on port `8000` is not part of rollback; the shared environment treats that as misconfiguration

VM retirement is a separate question. The VM stays online while Airflow, MLflow, and monitoring still define the retained control plane. Later retirement should happen only after that operator lane gets smaller explicitly.

Practical recovery split:

- use GitHub workflow reruns when reviewed delivery failed before runtime execution
- use hosted Airflow retries and backfills when runtime data or orchestration work failed after delivery
- use the runtime trigger contract when the serving release handoff itself must be retried

## What The Cloud-Operator Tests Enforce

The cloud-operator tests keep the delivery path honest in a few specific ways:

- Terraform output names and GitHub repository variable names must stay in one shared mapping
- the remote workflow must read the repository-backed contract instead of requiring operators to re-enter the same platform values on every run
- pushes to `main` only become automatic remote applies after bootstrap has populated the required repository variables; before that, push runs explain the skip and manual runs fail fast
- hosted verification fails if Cloud Run is not provisioned or if the VM app is public, because Cloud Run is the only supported public API path in this configuration
- repository-variable resync after apply is best effort, so a GitHub token limitation does not invalidate a successful Terraform apply
- destroy and cleanup remain explicit maintainer actions with project-id confirmation checks

That is why the public docs can describe the shared-cloud path as reviewable and repeatable without pretending it is a casual contributor setup.

## Delivery Boundaries That Stay Deliberate

These boundaries stay explicit across the scripts, Terraform reference, and tests:

- the local Docker evaluator remains the only default contributor path
- the shared cloud environment stays operator-owned, even though the repository and images are public
- `terraform/terraform.tfvars` belongs to bootstrap and local preview work, while day-2 remote runs read GitHub repository variables
- runtime scheduling, retries, and backfills belong to hosted Airflow for this horizon rather than to GitHub Actions
- runtime promotion, rollback, and live traffic control do not run inside GitHub workflows; GitHub only sends the reviewed runtime release request
- Grafana, Airflow, MLflow, and Prometheus remain operator surfaces rather than rider-facing product surfaces
- public docs should explain those surfaces with rendered evidence and checked-in configuration, not live control-plane embeds

The same split also keeps cloud retirement reviewable. Destroy and cleanup stay separate workflow commands, and cleanup only runs the follow-up actions the operator selected.

## Why This Workflow Works

- it gives contributors one small supported setup path instead of parallel onboarding stories
- it keeps the one-time cloud bootstrap explicit and interactive, which is safer for project, billing, and hosted-target choices
- it moves normal day-2 infrastructure changes into GitHub Actions so operators do not need local Terraform for routine work
- it keeps shared-cloud configuration reviewable because Terraform outputs, repository variables, and workflow behavior are tied together by regression tests

See [Interfaces and Surfaces](interfaces-and-surfaces.md), [Hosted Full-Stack](hosted-full-stack.md), [Cloud Mapping](cloud-mapping.md), and [Monitoring](monitoring.md) for the surrounding runtime and exposure boundaries.
