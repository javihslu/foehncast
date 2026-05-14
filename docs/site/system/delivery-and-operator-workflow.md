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
        RUN[Optional Cloud Run target]
    end

    CLONE --> LOCAL --> LSTACK --> LVERIFY
    SHELL --> BGCP
    BGCP --> BACKEND
    BGCP --> VARS
    PUSH --> TFWF
    BACKEND --> TFWF
    VARS --> TFWF
    TFWF --> HOST
    TFWF -. when enabled .-> RUN
</div>

The split matters because the local path is the supported public onboarding path, while the cloud path assumes GCP ownership, GitHub repository administration, and access to private operator surfaces.

## Default Contributor Path

The default contributor path stays local and small:

1. Clone the repository.
2. Install Docker.
3. Run `./scripts/bootstrap-local.sh`.

This path does not require local `gcloud`, Terraform, or GitHub Actions repository variables.

The local bootstrap owns the full evaluator hand-off instead of stopping at container startup:

- it creates `.env` from `.env.example` when needed
- it resets Docker volumes, Airflow metadata, and disposable local runtime artifacts so each run starts clean
- it starts the validated runtime subset without enabling the optional `development_env` container
- it waits for Airflow component health checks and the Airflow API health payload
- it verifies Grafana dashboard, alert-rule, contact-point, and policy provisioning before any pipeline run starts
- it runs the `feature_pipeline` DAG for the selected date and waits for the asset-triggered `training_pipeline` run to succeed
- it prepares local Feast state, verifies `/features/online`, and checks hosted-sync metrics on `/metrics`

If the preferred local ports are already occupied, the bootstrap resolves alternate bindings and prints the final endpoints. See [Local Evaluator](local-evaluator.md) for the full local runtime contract.

## One-Time Shared Cloud Bootstrap

The cloud bootstrap is a maintainer workflow, not a second onboarding path. The preferred first-time environment is Google Cloud Shell. That keeps admin tools off the default evaluator machine and matches the supported no-local-install path.

For the initial shared-cloud setup, run:

`./scripts/bootstrap-gcp.sh --bootstrap-only --configure-github-actions`

The script is interactive by design. It asks the operator to:

- sign in with `gcloud`
- choose an existing GCP project or create one
- choose a billing account
- confirm or edit the region, state bucket, Artifact Registry repository, BigQuery dataset, and BigQuery table
- choose which hosted targets to enable
- sync the GitHub repository variables that the shared cloud path uses later

In `--bootstrap-only` mode, the script prepares the remote Terraform control plane and leaves the broader hosted apply to the remote workflow. It also writes `.env` and `terraform/terraform.tfvars` in the working tree so the local repository reflects the selected project and platform identifiers.

When the script runs a normal apply instead of bootstrap-only mode, it also verifies the hosted runtime surfaces that Terraform exposed. Both hosted targets are expected to answer the same app contract on `/health`, `/spots`, and `/metrics`. The hosted full-stack path additionally proves that `/metrics` includes the hosted sync freshness signals when the compose host is enabled.

## Day-2 Delivery Contract

After the one-time bootstrap establishes OIDC, the remote backend, and the repository-variable contract, GitHub Actions becomes the primary operator surface for Terraform-managed changes.

| Surface | Current role | Current contract |
|------|---------------|------------------|
| `.github/workflows/terraform.yml` | primary Terraform operator path | pushes to `main` automatically resolve to `apply` after bootstrap; manual dispatch stays available for `plan`, `destroy`, `cleanup`, and explicit overrides |
| `scripts/configure-github-actions.sh` | repo-variable sync | Terraform outputs are copied into GitHub repository variables so the remote workflow reads one shared contract |
| `terraform/terraform.tfvars` | bootstrap input | used during the interactive bootstrap path, not as the day-2 source of truth for remote applies |
| runtime image workflows | app delivery follow-up | when Terraform has already provisioned `GCP_CLOUD_RUN_SERVICE`, publish automation updates the existing Cloud Run service with new images |
| `scripts/prepare-feast-cloud.sh` | hosted Feast follow-up | run this after a remote apply succeeds and curated BigQuery rows exist |

This contract is deliberate. The remote workflow reads repository-backed values for project, state, storage, BigQuery, and hosted target toggles. Lower-level Cloud Run settings such as container port, CPU, and memory stay repo-variable-backed instead of becoming more manual workflow inputs.

That same split is also the current ownership boundary for cloud-facing values. Checked-in examples and bootstrap outputs can seed the contract, but GitHub repository variables remain structural delivery inputs only. Runtime passwords, API tokens, and other secret-bearing values belong in the runtime environment or a managed secret path instead of the repository-variable sync. See [Configuration and Contracts](configuration-and-contracts.md) for the reviewed inventory.

## Hosted Serving Contract

The hosted full-stack target and the Cloud Run target should read as one serving story, not two ad hoc ones.

- `/health` is the shared readiness route on both hosted targets and should report `status`, `model_alias`, and `model_version`.
- `/spots` is the shared service-facing catalog route on both hosted targets.
- `/metrics` is the shared operator-facing scrape route on both hosted targets.
- both hosted targets rely on the same Terraform-managed app wiring for storage, Feast, and MLflow inputs.
- the hosted full-stack target adds one operator-only extension on `/metrics`: the online-compose sync freshness signals that do not exist on Cloud Run.

## What The Cloud-Operator Tests Enforce

The cloud-operator tests keep the delivery path honest in a few specific ways:

- Terraform output names and GitHub repository variable names must stay in one shared mapping
- the remote workflow must read the repository-backed contract instead of requiring operators to re-enter the same platform values on every run
- pushes to `main` only become automatic remote applies after bootstrap has populated the required repository variables; before that, push runs explain the skip and manual runs fail fast
- repository-variable resync after apply is best effort, so a GitHub token limitation does not invalidate a successful Terraform apply
- destroy and cleanup remain explicit maintainer actions with project-id confirmation checks

This is why the public docs can describe the shared-cloud path as reviewable and repeatable without pretending it is a casual contributor setup.

## Delivery Boundaries That Stay Deliberate

Several boundaries stay explicit across the scripts, Terraform reference, and tests:

- the local Docker evaluator remains the only default contributor path
- the shared cloud environment stays operator-owned, even though the repository and images are public
- `terraform/terraform.tfvars` belongs to bootstrap and local preview work, while day-2 remote runs read GitHub repository variables
- Grafana, Airflow, MLflow, and Prometheus remain operator surfaces rather than rider-facing product surfaces
- public docs should explain those surfaces with rendered evidence and checked-in configuration, not live control-plane embeds

The same split also keeps cloud retirement reviewable. Destroy and cleanup stay separate workflow commands, and cleanup only runs the specific follow-up actions that the operator selected.

## Why This Workflow Works

- it gives contributors one small supported setup path instead of parallel onboarding stories
- it keeps the one-time cloud bootstrap explicit and interactive, which is safer for project, billing, and hosted-target choices
- it moves normal day-2 infrastructure changes into GitHub Actions so operators do not need local Terraform for routine work
- it keeps shared-cloud configuration reviewable because Terraform outputs, repository variables, and workflow behavior are tied together by regression tests

See [Interfaces and Surfaces](interfaces-and-surfaces.md), [Hosted Full-Stack](hosted-full-stack.md), [Cloud Mapping](cloud-mapping.md), and [Monitoring](monitoring.md) for the surrounding runtime and exposure boundaries.
