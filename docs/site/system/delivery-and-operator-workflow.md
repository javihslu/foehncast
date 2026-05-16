# Delivery and Operator Workflow

FoehnCast keeps contributor onboarding and shared-cloud delivery separate. Contributors use `./scripts/bootstrap-local.sh` to run the validated local evaluator. Maintainers use `./scripts/bootstrap-gcp.sh`, GitHub Actions, and Terraform to bootstrap and advance the shared hosted environment. The intended hosted direction is Cloud Build plus Cloud Composer. This page describes the workflow contract and the boundary that later hosted work should move toward.

!!! note "Scope"

    This page describes the validated delivery and operator workflow.
    It also names the intended managed hosted direction so the active host-backed path is not mistaken for the final design.
    It is not a cutover runbook for Composer or Cloud Build.

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
        HOST["Hosted ops lane"]
        RUN["Cloud Run API"]
        SHELL --> BGCP --> HANDOFF --> TFWF
        PUSH --> TFWF
        TFWF --> HOST
        TFWF --> RUN
    end
</div>

The split matters because the local path is the supported onboarding path, while the cloud path assumes GCP ownership, GitHub repository administration, and access to private operator surfaces.

The remote workflow lands on two hosted runtime surfaces: Cloud Run for the public API lane and the retained operator host for Airflow, MLflow, monitoring, and private recovery work. It can also provision an optional Cloud Composer environment for readiness work. The target managed direction keeps the same onboarding split but replaces host-owned build and orchestration duties with Cloud Build and Cloud Composer.

## Supported Paths

| Path | Audience | Main tools | Main result |
|------|----------|------------|-------------|
| Default contributor path | contributor or reviewer | local Docker plus `./scripts/bootstrap-local.sh` | validated one-machine evaluator stack |
| One-time shared-cloud bootstrap | maintainer | Google Cloud Shell plus `./scripts/bootstrap-gcp.sh` | remote Terraform backend, repository-variable contract, and first hosted setup |
| Reviewed day-2 delivery | maintainer | GitHub Actions plus Terraform plus OIDC | reviewed infrastructure and runtime updates |
| Runtime recovery | maintainer | hosted Airflow on the retained operator host plus the runtime trigger workflow | retries, backfills, and reviewed serving handoffs |

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
| `.github/workflows/trigger-runtime-release.yml` | send one explicit reviewed runtime release request into the selected Airflow receiver while the default `auto` mode prefers Composer only after its access-ready contract is true and otherwise falls back to the retained host |
| `scripts/prepare-feast-cloud.sh` | hosted Feast follow-up after a remote apply and curated BigQuery rows exist |

The remote workflow reads repository-backed values for project, state, storage, BigQuery, and hosted target toggles. Lower-level Cloud Run settings such as minimum and maximum instance count, container port, CPU, and memory stay repo-variable-backed instead of becoming manual workflow inputs.

GitHub can now publish the repo-managed DAG and source bundle into the provisioned Composer DAG bucket. Composer now gets a reviewed PyPI baseline for the checked-in DAG bundle, Trigger Runtime Release now prefers Composer Airflow automatically when the managed URI, artifact bucket, and access-ready contract are all in place, and Composer can now consume reviewed `sm://...` Secret Manager env references through the shared runtime env helper. Runtime secret delivery for other hosted paths and the full cutover away from the retained-host fallback still need separate follow-up work.

The runtime trigger now has an explicit reviewed receiver selection contract as well: `auto` is the default reviewed selection mode, it prefers `composer_airflow` only when the managed URI, artifact bucket, and access-ready contract are all present, and it otherwise falls back to `retained_host` while that path remains active. Operators can still choose `retained_host` or `composer_airflow` deliberately when they want to override the automatic selection.

Checked-in examples and bootstrap outputs can seed the contract, but GitHub repository variables stay structural delivery inputs only. Runtime passwords, API tokens, and other secret-bearing values belong in the runtime environment or a managed secret path instead of the repository-variable sync. Both hosted lanes still read the same Terraform-managed storage, Feast, and MLflow contract. See [Configuration and Contracts](configuration-and-contracts.md) for the reviewed inventory.

## Retained-Host Responsibilities

The shared environment still depends on the retained operator host in a few specific places.

| Responsibility | Why it still uses the host | Target direction |
|------|-----------------------------|------------------|
| runtime release handoff | GitHub still refreshes the VM checkout over SSH and reaches the host-local Airflow API adapter for the `runtime_release` DAG | reviewed request should reach Composer without VM SSH |
| hosted DAG execution and recovery | retries, backfills, and manual replay still assume host-local Airflow | Composer should own hosted orchestration and recovery |
| sync evidence and private operator checks | the host still writes `.state/online-compose-sync/last-success.json` and keeps operator surfaces online | shrink or replace this VM role after orchestration leaves the host |

## Hosted Orchestration Boundary

The current hosted orchestration path and the target managed direction are different on purpose.

| Concern | Current operational path | Target managed direction |
|------|---------------------------|--------------------------|
| Hosted Airflow surface | retained operator host | Cloud Composer |
| Reviewed runtime release entry | GitHub OIDC plus SSH to the retained host, then local `runtime_release` DAG trigger | reviewed request should reach Composer without VM SSH |
| Scheduling, retries, and backfills | retained-host Airflow | Composer |
| Operator host role | Airflow, MLflow, monitoring, and private app checks on one VM | shrink after Composer absorbs orchestration; keep only the services that still need a VM |

Today the retained host path remains the operational recovery surface. It is not the intended long-term hosted orchestration authority.
Terraform can provision the managed surface ahead of that cutover, but runtime release, retries, and backfills still belong to the retained-host path until the reviewed handoff stops depending on VM SSH.

## GitHub Versus GCP Boundary

The reviewed delivery plane and the runtime execution plane still have different responsibilities.

| Plane | Active owner | What it owns | What it must not own |
|------|---------------|--------------|----------------------|
| Reviewed delivery | GitHub Actions plus Terraform | lint, test, build, image publish, Terraform plan/apply/destroy, and reviewed deploy workflows | runtime scheduling, retries, backfills, and long-lived operator state |
| Runtime execution | GCP-hosted runtime surfaces | Cloud Run serving, hosted Airflow scheduling, retries, backfills, runtime environment injection, and operator telemetry | source control, CI review, and infrastructure policy review |
| Shared handoff | repository variables, published images, Terraform outputs, and runtime release requests | reviewed contract from GitHub into GCP runtime surfaces; it reaches runtime through the retained-host handoff today and later should reach managed Airflow directly | ad hoc operator-only divergence from the declared contract |

GitHub Actions may trigger reviewed delivery workflows, but runtime scheduling does not belong to GitHub. In the active shared environment, that runtime orchestration still lives on the retained operator host. The target managed surface is Cloud Composer.

## Runtime Release Trigger Contract

GitHub now has exactly one reviewed handoff into runtime execution.

<div class="mermaid">
flowchart LR
    GHW["fab:fa-github Runtime release workflow"] --> TARGET["reviewed receiver selection"]
    TARGET --> SSH["OIDC + SSH to retained host"]
    TARGET --> API["OIDC + access token to Composer Airflow API"]
    SSH --> SCRIPT["trigger-runtime-release.sh"]
    API --> SCRIPT
    SCRIPT --> DAG["runtime_release DAG"]
    DAG --> REPORT["runtime-release-latest.json"]
    REPORT --> SUMMARY["GitHub workflow summary"]
</div>

- signal: `.github/workflows/trigger-runtime-release.yml` sends one JSON request with a single action and the associated release coordinates
- receiver: Trigger Runtime Release now defaults to `auto`, prefers `composer_airflow` when the managed URI, artifact bucket, and access-ready contract are ready, and otherwise falls back to `retained_host`; operators can still choose either reviewed receiver deliberately
- auth path: the retained-host path uses GitHub OIDC plus Compute Engine SSH to reach the host-local Airflow API; the Composer path uses GitHub OIDC plus a Google access token for the Composer Airflow API and assumes the GitHub service account already maps to an Airflow user or role
- observable outcome: the workflow waits for the `runtime_release` DAG to succeed and captures the configured runtime release summary target with requested and selected receiver metadata; on the retained host the default remains `airflow/reports/runtime-release-latest.json`, while the Composer path reads the durable `gs://...` report contract derived from the artifact bucket

Supported actions:

- `deploy_candidate`
- `promote_candidate`
- `rollback_live`

This keeps the handoff explicit while deeper runtime automation still lives behind the Airflow side of the boundary. It is the active contract, not the intended long-term hosted entry path. The default still points at the retained host; Composer handoff is opt-in until the access path is ready. The target managed direction is the same reviewed request reaching Composer without a retained-host refresh step.

## Composer Readiness Requirements

Cloud Composer is now provisionable as a managed-Airflow readiness surface, but it is still not the hosted orchestration authority in this repo. Before it can take over that role, the repo needs an explicit contract for:

| Requirement | Current repo shape | What later Composer work must replace or define |
|------|--------------------|-----------------------------------------------|
| DAG packaging | DAGs currently arrive through the retained host checkout and compose-mounted repo path | a reviewed DAG delivery path that does not depend on a VM checkout |
| Python dependencies | Terraform now seeds a reviewed Composer PyPI baseline for the checked-in DAG bundle | extend or replace that baseline when later Composer work needs private indexes, non-PyPI or system-level dependencies, or broader DAG coverage |
| Secrets and runtime config | the retained host still reads VM-local environment, and Composer can now consume reviewed `sm://...` Secret Manager env references resolved by the shared runtime helper | broader managed secret and runtime-config delivery across the hosted orchestration surface |
| Network and API reachability | the current trigger contract keeps retained-host SSH as the default path and exposes an opt-in Composer Airflow API path | a managed default Airflow access path that no longer depends on retained-host SSH |
| Operator access model | retries, backfills, and recovery currently assume SSH to the retained host | a clear managed operator access model for Composer-owned orchestration |

GitHub can now publish the repo-managed DAG and source bundle into the provisioned Composer DAG bucket. This creates a reviewed DAG delivery path that does not depend on a VM checkout for the checked-in DAG and source bundle. It intentionally publishes the DAG entrypoints, the `foehncast` Python package, `config.yaml`, `pyproject.toml`, and `feature_repo`, and Terraform now seeds the reviewed Composer PyPI package baseline needed by that checked-in DAG bundle. The baseline still allows extra `cloud_composer_pypi_packages` overrides for follow-up slices, and Composer can now receive reviewed `sm://...` Secret Manager env bindings resolved by the shared runtime helper, but it does not yet make the Composer API handoff the default runtime release path or cover every hosted secret-delivery surface.

The runtime release acknowledgement path is now portable as well: the same DAG can keep writing the reviewed summary to the retained-host default path today, or to a durable storage target such as `gs://...` when the managed orchestration path is ready to own that evidence directly.

## Retry And Backfill Runbooks

Operators should retry work on the same plane that owns it instead of jumping between GitHub and runtime surfaces. These are the retained-host runbooks while hosted orchestration still lives on the retained host.

| Situation | Where to act | Normal procedure | Minimum evidence |
|------|---------------|------------------|------------------|
| Terraform or image publication fails before any runtime request is sent | GitHub Actions | fix the reviewed delivery input, then rerun the failed GitHub workflow | GitHub workflow URL plus the updated workflow summary |
| candidate deploy, promotion, or rollback handoff needs another attempt | GitHub Actions through the runtime trigger contract | rerun `.github/workflows/trigger-runtime-release.yml` with the same reviewed release coordinates and the same selected receiver so the retained operator host or the Composer API handoff records a new acknowledgement | GitHub workflow URL plus the configured runtime release summary target |
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
- the configured runtime release summary target records the acknowledged handoff on the runtime side, including requested and selected receiver metadata; on the retained host the default remains `airflow/reports/runtime-release-latest.json`
- reopening the hosted VM app on port `8000` is not part of rollback; the shared environment treats that as misconfiguration

VM retirement is a separate question. The VM stays online only while Airflow, MLflow, and monitoring still define the retained control plane. Airflow should leave the VM before that host is treated as steady state.

Practical recovery split:

- use GitHub workflow reruns when reviewed delivery failed before runtime execution
- use hosted Airflow retries and backfills when runtime data or orchestration work failed after delivery
- use the runtime trigger contract when the serving release handoff itself must be retried

## Reviewable Boundaries

These boundaries stay explicit across the scripts, Terraform reference, and workflow contract:

- the local Docker evaluator remains the only default contributor path
- the shared cloud environment stays operator-owned, even though the repository and images are public
- `terraform/terraform.tfvars` belongs to bootstrap and local preview work, while day-2 remote runs read GitHub repository variables
- runtime scheduling, retries, and backfills belong to hosted Airflow in the active shared environment and to Composer after the managed cutover, not to GitHub Actions
- runtime promotion, rollback, and live traffic control do not run inside GitHub workflows; GitHub only sends the reviewed runtime release request
- Grafana, Airflow, MLflow, and Prometheus remain operator surfaces rather than rider-facing product surfaces
- public docs should explain those surfaces with rendered evidence and checked-in configuration, not live control-plane embeds

The same split also keeps cloud retirement reviewable. Destroy and cleanup stay separate workflow commands, and cleanup only runs the follow-up actions the operator selected.

## Why This Workflow Works

- it gives contributors one supported setup path instead of parallel onboarding stories
- it keeps the one-time cloud bootstrap explicit and interactive, which is safer for project, billing, and hosted-target choices
- it moves normal day-2 infrastructure changes into GitHub Actions so operators do not need local Terraform for routine work
- it keeps shared-cloud configuration reviewable because Terraform outputs, repository variables, and workflow behavior are tied together by regression tests
- it records the retained-host workflow without pretending that VM-backed orchestration is the desired hosted end state

See [Interfaces and Surfaces](interfaces-and-surfaces.md), [Hosted Full-Stack](hosted-full-stack.md), [Cloud Mapping](cloud-mapping.md), and [Monitoring](monitoring.md) for the surrounding runtime and exposure boundaries.
